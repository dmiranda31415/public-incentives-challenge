# explain_matches.py
import os, json, time, psycopg2
from dotenv import load_dotenv
from psycopg2.extras import execute_values
from openai import OpenAI, APIError, RateLimitError, APIConnectionError
from usage_logger import log_usage, extract_usage_fields

# ------------- CONFIG -------------
TOP_K_FROM_MATCHES = 5          # quantos candidatos ler por incentivo (matches já tem 5)
MAX_TEXT = 800                  # corta descrições longas no prompt
MODEL = "gpt-4o-mini"
SLEEP_BETWEEN = 0.05            # pausa curta entre incentivos
RETRIES = 5

PROMPT_TEMPLATE = """Contexto do incentivo:
Título: {title}
Descrição: {desc}
Critérios (texto): {crit}
Eligibility (JSON): {elig}

Candidatos (top {k}) — usa SEMPRE o campo 'id' para referenciar a empresa.
Campo RULE_PASS indica se cumpre as regras de elegibilidade (CAE + keywords obrigatórias).
{table}

Tarefa:
1) Ordena objetivamente os candidatos privilegiando RULE_PASS = true. Se todos forem false, indica limitações e ordena mesmo assim.
2) Para os 5 primeiros, devolve ID e uma frase curta (razão objetiva). Não repitas o nome.
3) Responde apenas em JSON válido:
{{
  "top5": [
    {{"company_id": 123, "reason": "..." }},
    {{"company_id": 456, "reason": "..." }},
    {{"company_id": 789, "reason": "..." }},
    {{"company_id": 111, "reason": "..." }},
    {{"company_id": 222, "reason": "..." }}
  ]
}}
"""

# ------------- FUNÇÕES -------------
def call_chat(client: OpenAI, prompt: str):
    """Faz chamada à API da OpenAI com retries automáticos"""
    for t in range(RETRIES):
        try:
            return client.chat.completions.create(
                model=MODEL,
                response_format={"type": "json_object"},  # força JSON
                temperature=0,
                messages=[{"role": "user", "content": prompt}]
            )
        except (APIConnectionError, APIError, RateLimitError) as e:
            wait = 1.5 * (t + 1)
            print(f"⚠️  API erro {type(e).__name__}. Retry {t+1}/{RETRIES} em {wait:.1f}s...")
            time.sleep(wait)
    return None

# ------------- PIPELINE -------------
def format_company_row(idx: int, row: dict) -> str:
    desc_clean = (row["trade_description"] or '')[:180].replace('\n', ' ')
    rule_flag = "TRUE" if row["rule_pass"] else "FALSE"
    return (
        f"{idx}. id={row['company_id']} | RULE_PASS={rule_flag} | {row['company_name']} | "
        f"CAE={row['cae']} | score={row['score']:.3f} | {desc_clean}"
    )

def main():
    load_dotenv()
    db_url = os.getenv("DATABASE_URL")
    api_key = os.getenv("OPENAI_API_KEY")

    if not db_url or not api_key:
        print("❌ Faltam DATABASE_URL ou OPENAI_API_KEY no .env")
        return

    client = OpenAI(api_key=api_key)
    conn = psycopg2.connect(db_url)
    cur = conn.cursor()

    cur.execute("""
      SELECT i.incentive_pk,
             COALESCE(i.title,'') AS title,
             COALESCE(i.ai_description, i.description, '') AS desc,
             COALESCE(i.eligibility_criteria,'') AS crit,
             COALESCE(i.eligibility, '{}'::jsonb) AS elig
      FROM incentives i
      WHERE i.embedding IS NOT NULL
    """)
    incentives = cur.fetchall()
    total = len(incentives)
    print(f"🔎 Incentivos a processar: {total}")

    done = 0
    for iid, title, desc, crit, elig in incentives:
        cur.execute("""
          SELECT m.company_id,
                 m.score,
                 COALESCE(m.rule_pass::text, 'null') AS rule_pass_json,
                 c.company_name,
                 c.cae_primary_label,
                 c.trade_description_native
          FROM matches m
          JOIN companies c ON c.id = m.company_id
          WHERE m.incentive_id = %s
          ORDER BY m.rank
          LIMIT %s
        """, (iid, TOP_K_FROM_MATCHES))
        raw_rows = cur.fetchall()
        if not raw_rows:
            print(f"ℹ️  Sem candidatos em matches para incentivo {iid} - '{title[:60]}'")
            done += 1
            continue

        rows = []
        for row in raw_rows:
            try:
                rule_pass = json.loads(row[2]) if row[2] not in (None, 'null') else False
                rule_pass = bool(rule_pass)
            except Exception:
                rule_pass = False
            rows.append({
                "company_id": row[0],
                "score": float(row[1]),
                "rule_pass": rule_pass,
                "company_name": row[3],
                "cae": row[4],
                "trade_description": row[5],
            })

        passed = [r for r in rows if r["rule_pass"]]
        rows_for_prompt = passed if passed else rows[:TOP_K_FROM_MATCHES]

        table_lines = [format_company_row(i + 1, r) for i, r in enumerate(rows_for_prompt)]
        table = "\n".join(table_lines)

        prompt = PROMPT_TEMPLATE.format(
            title=title[:MAX_TEXT],
            desc=(desc or "")[:MAX_TEXT],
            crit=(crit or "")[:MAX_TEXT],
            elig=json.dumps(elig, ensure_ascii=False),
            k=min(TOP_K_FROM_MATCHES, len(rows_for_prompt)),
            table=table
        )

        resp = call_chat(client, prompt)
        if not resp:
            print(f"❌ Falha final no incentivo {iid} - '{title[:60]}' (sem resposta após retries)")
            done += 1
            continue

        usage = extract_usage_fields(resp)
        log_usage(
            source="explain_matches",
            model=MODEL,
            prompt_tokens=usage["prompt_tokens"],
            completion_tokens=usage["completion_tokens"],
            metadata={"incentive_id": iid, "rows": len(rows_for_prompt)}
        )

        try:
            data = json.loads(resp.choices[0].message.content)
            top5 = data.get("top5", [])[:5]
        except Exception as e:
            print(f"❌ JSON inválido no incentivo {iid}: {e}")
            done += 1
            continue

        valid_ids = {r["company_id"] for r in rows_for_prompt}
        id_to_name = {r["company_id"]: r["company_name"] for r in rows_for_prompt}

        ordered = []
        for i, item in enumerate(top5):
            cid = item.get("company_id")
            if cid in valid_ids:
                reason = (item.get("reason") or "").strip()
                exp = f"{id_to_name[cid]} — {reason}" if reason else id_to_name[cid]
                ordered.append((i + 1, cid, exp))

        if not ordered:
            print(f"⚠️  Sem IDs válidos devolvidos para incentivo {iid} - '{title[:60]}'")
            done += 1
            continue

        try:
            execute_values(
                cur,
                """
                UPDATE matches AS m
                SET rank = v.rank, explanation = v.explanation
                FROM (VALUES %s) AS v(incentive_id, company_id, rank, explanation)
                WHERE m.incentive_id = v.incentive_id AND m.company_id = v.company_id
                """,
                [(iid, cid, rk, exp) for rk, cid, exp in ordered],
                template="(%s,%s,%s,%s)"
            )
            conn.commit()
            print(f"✅ Atualizado incentivo {iid} — top {len(ordered)} com explicações.")
        except Exception as e:
            conn.rollback()
            print(f"❌ Erro ao atualizar incentivo {iid}: {e}")

        done += 1
        time.sleep(SLEEP_BETWEEN)

    cur.close(); conn.close()
    print(f"🏁 Concluído: {done}/{total} incentivos processados.")

if __name__ == "__main__":
    main()

