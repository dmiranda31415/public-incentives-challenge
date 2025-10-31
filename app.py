import os, json, psycopg2, re
from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from openai import OpenAI

# --------------------------------
# Boot
# --------------------------------
load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not DATABASE_URL or not OPENAI_API_KEY:
    raise RuntimeError("DATABASE_URL e OPENAI_API_KEY são obrigatórios")

conn = psycopg2.connect(DATABASE_URL)
conn.autocommit = True
client = OpenAI(api_key=OPENAI_API_KEY)

app = FastAPI(title="Public Incentives API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

CHAT_MODEL = "gpt-4o-mini"
END_SENTINEL = "[[END_STREAM]]"

# --------------------------------
# Utils
# --------------------------------
def uget(usage_obj, *keys, default=0):
    """Lê contadores de tokens do objeto usage (SDK novo)."""
    if usage_obj is None:
        return default
    for k in keys:
        v = getattr(usage_obj, k, None)
        if v is not None:
            return int(v)
    return default

# --------------------------------
# Endpoints
# --------------------------------
@app.get("/health")
def health():
    with conn.cursor() as cur:
        cur.execute("SELECT 1")
        ok = cur.fetchone()[0] == 1
    return {"ok": ok}

@app.get("/incentives/{incentive_id}")
def get_incentive(incentive_id: int):
    with conn.cursor() as cur:
        cur.execute("""
          SELECT incentive_pk, title, coalesce(ai_description,description,'') AS description,
                 coalesce(eligibility_criteria,'') AS eligibility_criteria,
                 eligibility
          FROM incentives WHERE incentive_pk = %s
        """, (incentive_id,))
        row = cur.fetchone()
    if not row:
        raise HTTPException(404, "Incentivo não encontrado")
    return {
        "id": row[0], "title": row[1], "description": row[2],
        "eligibility_criteria": row[3], "eligibility": row[4]
    }

@app.get("/matches/{incentive_id}")
def get_matches(incentive_id: int):
    with conn.cursor() as cur:
        cur.execute("""
          SELECT m.rank, m.score, m.explanation,
                 c.id, c.company_name, c.cae_primary_label
          FROM matches m
          JOIN companies c ON c.id = m.company_id
          WHERE m.incentive_id = %s
          ORDER BY m.rank
        """, (incentive_id,))
        rows = cur.fetchall()
    return [
        {"rank": r[0], "score": float(r[1]), "explanation": r[2],
         "company_id": r[3], "company_name": r[4], "cae": r[5]}
        for r in rows
    ]

@app.get("/chat/stream")
def chat_stream(q: str = Query(..., min_length=1), k: int = 5):
    normalized_q = (q or "").lower()
    is_how_question = normalized_q.strip().startswith("como")
    ask_for_companies = any(w in normalized_q for w in ["empresa", "empresas", "companhia", "companhias"])
    MIN_MATCH_THRESHOLD = 1

    def gen():
        try:
            # ---------- 1) Buscar contexto ----------
            with conn.cursor() as cur:
                # id explícito: “incentivo 3”
                m = re.search(r"(?i)incentivo\s*(\d+)", q or "")
                if m:
                    cur.execute("""
                      SELECT incentive_pk, title, coalesce(ai_description,description,'') AS d
                      FROM incentives WHERE incentive_pk = %s
                    """, (int(m.group(1)),))
                    incs = cur.fetchall()
                    match_count = len(incs)
                else:
                    # ILIKE livre
                    cur.execute("""
                      SELECT incentive_pk, title, coalesce(ai_description,description,'') AS d
                      FROM incentives
                      WHERE title ILIKE %s OR coalesce(ai_description,description,'') ILIKE %s
                      ORDER BY incentive_pk DESC
                      LIMIT %s
                    """, (f"%{q}%", f"%{q}%", k))
                    incs = cur.fetchall()
                    cur.execute("""
                      SELECT COUNT(*) FROM incentives
                      WHERE title ILIKE %s OR coalesce(ai_description,description,'') ILIKE %s
                    """, (f"%{q}%", f"%{q}%"))
                    match_count = int(cur.fetchone()[0])

                    # Fallback FTS
                    if match_count == 0:
                        terms = re.sub(r"[^\w\s]", " ", q).strip()
                        if terms:
                            cur.execute("""
                              WITH src AS (
                                SELECT incentive_pk,
                                       title,
                                       coalesce(ai_description,description,'') AS d,
                                       to_tsvector('portuguese',
                                         coalesce(title,'') || ' ' ||
                                         coalesce(description,'') || ' ' ||
                                         coalesce(ai_description,'') || ' ' ||
                                         coalesce(eligibility_criteria,'') || ' ' ||
                                         coalesce(eligibility::text,'')
                                       ) AS vec
                                FROM incentives
                              )
                              SELECT incentive_pk, title, d,
                                     ts_rank(vec, plainto_tsquery('portuguese', %s)) AS r
                              FROM src
                              WHERE vec @@ plainto_tsquery('portuguese', %s)
                              ORDER BY r DESC, incentive_pk DESC
                              LIMIT %s
                            """, (terms, terms, k))
                            incs = [(r[0], r[1], r[2]) for r in cur.fetchall()]

                            cur.execute("""
                              WITH src AS (
                                SELECT to_tsvector('portuguese',
                                         coalesce(title,'') || ' ' ||
                                         coalesce(description,'') || ' ' ||
                                         coalesce(ai_description,'') || ' ' ||
                                         coalesce(eligibility_criteria,'') || ' ' ||
                                         coalesce(eligibility::text,'')
                                       ) AS vec
                                FROM incentives
                              )
                              SELECT COUNT(*) FROM src
                              WHERE vec @@ plainto_tsquery('portuguese', %s)
                            """, (terms,))
                            match_count = int(cur.fetchone()[0])

                # Fallback absoluto
                if not incs:
                    cur.execute("""
                      SELECT incentive_pk, title, coalesce(ai_description,description,'') AS d
                      FROM incentives ORDER BY incentive_pk DESC LIMIT %s
                    """, (k,))
                    incs = cur.fetchall()
                    if not m:
                        match_count = 0

                # Se pergunta “como …” e não pede empresas, reduz a 1 incentivo
                if is_how_question and not ask_for_companies and not m:
                    incs = incs[:1]
                    if match_count:
                        match_count = min(match_count, len(incs))

                if match_count < MIN_MATCH_THRESHOLD:
                    incs = []
                    match_count = 0

                cur.execute("SELECT COUNT(*) FROM incentives")
                total_incentives = int(cur.fetchone()[0])
                cur.execute("SELECT COUNT(*) FROM companies")
                total_companies = int(cur.fetchone()[0])

            context_items = []
            with conn.cursor() as cur:
                for iid, title, desc in incs:
                    matches = []
                    if not (is_how_question and not ask_for_companies):
                        cur.execute("""
                          SELECT m.rank, c.company_name, c.cae_primary_label, coalesce(m.explanation,'')
                          FROM matches m JOIN companies c ON c.id = m.company_id
                          WHERE m.incentive_id = %s ORDER BY m.rank
                        """, (iid,))
                        top = cur.fetchall()
                        matches = [{"rank": r, "company": n, "cae": cae, "why": exp}
                                   for r, n, cae, exp in top]

                    context_items.append({
                        "incentive_id": iid,
                        "title": title,
                        "description": desc,
                        "matches": matches,
                    })

            # ---------- 2) Prompt ----------
            system = (
                "Responde de forma concisa e factual. Identifica o tipo de pergunta:"
                " • 'quantos/quantas' → responde com números e percentagens."
                " • 'quais/qual' → lista incentivos/empresas em bullets."
                " • 'como' → dá passos claros; só menciona empresas se a pergunta as referir."
                " Nunca inventes dados fora do contexto."
            )

            formatting = (
                "Formata em Markdown. Para cada incentivo:\n"
                "### Incentivo {incentive_id} — {titulo}\n\n"
                "**Resumo curto:** frase concisa.\n\n"
                "**Pontos-chave**\n- ponto 1\n- ponto 2\n\n"
            )
            if not (is_how_question and not ask_for_companies):
                formatting += "**Empresas elegíveis**\n1. **Nome** — CAE / justificativa\n\n"

            if is_how_question:
                formatting = (
                    "Inicia com '### Passos recomendados' (lista numerada, ≥3 passos).\n"
                ) + formatting

            formatting += "Omitir secções vazias."

            meta = {
                "k": k,
                "num_context_items": len(context_items),
                "matching_count": match_count,
                "total_incentives": total_incentives,
                "total_companies": total_companies,
            }

            if not context_items:
                context_json = "[]"
                extra_note = (
                    "Não foram encontrados incentivos diretamente relevantes; dá orientação genérica."
                )
            else:
                context_json = json.dumps(context_items, ensure_ascii=False)[:7000]
                extra_note = ""

            user = (
                f"Pergunta: {q}\n"
                f"Meta: {json.dumps(meta, ensure_ascii=False)}\n"
                f"{extra_note}\n"
                f"Instruções de formatação: {formatting}\n"
                f"Contexto JSON:\n{context_json}"
            )

            # ---------- 3) Streaming OpenAI ----------
            prompt_tokens = completion_tokens = 0
            with client.responses.stream(
                model=CHAT_MODEL,
                input=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=0.2,
                max_output_tokens=400,
            ) as stream:
                have_text = False
                for event in stream:
                    if event.type == "response.output_text.delta":
                        chunk = event.delta or ""
                        if chunk:
                            have_text = True
                            yield chunk
                    elif event.type == "response.completed":
                        usage = getattr(event.response, "usage", None)
                        prompt_tokens     = uget(usage, "prompt_tokens", "input_tokens", default=0)
                        completion_tokens = uget(usage, "completion_tokens", "output_tokens", default=0)
                        break
                    elif event.type == "response.error":
                        break
                if not have_text:
                    yield ""
                yield END_SENTINEL

            # (Opcional) logging de usage — aqui só imprimimos para debug
            # print(f"usage: prompt={prompt_tokens}, completion={completion_tokens}")

        except Exception as e:
            # Em caso de erro, fecha a stream de forma limpa
            yield "\n\n(ocorreu um erro a gerar a resposta)"
            yield END_SENTINEL

    return StreamingResponse(gen(), media_type="text/plain")
