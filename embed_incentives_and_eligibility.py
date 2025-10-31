import os, time, json, psycopg2
from dotenv import load_dotenv
from tqdm import tqdm
from openai import OpenAI
from usage_logger import log_usage, extract_usage_fields

# -----------------------------------------------------------
#  CONFIGURAÇÃO
# -----------------------------------------------------------

PROMPT = """Extrai JSON estrito com campos:
- allowed_cae_labels: string[]
- keywords_required: string[]
- keywords_bonus: string[]
Apenas JSON válido na resposta."""

load_dotenv()

DB_URL = os.getenv("DATABASE_URL")
OPENAI_KEY = os.getenv("OPENAI_API_KEY")

client = OpenAI(api_key=OPENAI_KEY)
conn = psycopg2.connect(DB_URL)
cur = conn.cursor()

# -----------------------------------------------------------
#  SELECIONA OS INCENTIVOS (usa a tua PK real)
# -----------------------------------------------------------
cur.execute("""
  SELECT incentive_pk,
         coalesce(title,'') || ' | ' ||
         coalesce(ai_description, description, '') || ' | ' ||
         coalesce(eligibility_criteria,'') AS txt,
         coalesce(eligibility_criteria,'') AS crit
  FROM incentives
  WHERE embedding IS NULL OR eligibility IS NULL
""")
rows = cur.fetchall()
print(f"{len(rows)} incentivos para processar.\n")

# -----------------------------------------------------------
#  LOOP PRINCIPAL
# -----------------------------------------------------------
for rid, txt, crit in tqdm(rows, desc="Incentivos", unit="row"):

    # --- 1️⃣ Embedding
    emb = [0.0]*1536
    if txt.strip():
        emb_resp = client.embeddings.create(
            model="text-embedding-3-small",
            input=txt[:2000]
        )
        usage = extract_usage_fields(emb_resp)
        log_usage(
            source="embed_incentives",
            model="text-embedding-3-small",
            prompt_tokens=usage["prompt_tokens"],
            completion_tokens=usage["completion_tokens"],
            metadata={"incentive_id": rid, "phase": "embedding"}
        )
        emb = emb_resp.data[0].embedding
        time.sleep(0.05)  # para não saturar a API

    # --- 2️⃣ Extrair JSON de elegibilidade
    elig = None
    if crit.strip():
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            response_format={"type": "json_object"},  # força JSON válido
            temperature=0,
            messages=[{
                "role": "user",
                "content": f"{PROMPT}\n\n---\n{crit[:2000]}\n---"
            }]
        )
        usage = extract_usage_fields(resp)
        log_usage(
            source="embed_incentives",
            model="gpt-4o-mini",
            prompt_tokens=usage["prompt_tokens"],
            completion_tokens=usage["completion_tokens"],
            metadata={"incentive_id": rid, "phase": "eligibility"}
        )
        try:
            elig = json.loads(resp.choices[0].message.content)
        except Exception:
            elig = {"allowed_cae_labels": [], "keywords_required": [], "keywords_bonus": []}
        time.sleep(0.05)

    # --- 3️⃣ Atualizar base de dados
    cur.execute("""
        UPDATE incentives
        SET embedding = %s,
            eligibility = %s
        WHERE incentive_pk = %s
    """, (emb, json.dumps(elig) if elig else None, rid))
    conn.commit()

# -----------------------------------------------------------
#  FINALIZAÇÃO
# -----------------------------------------------------------
cur.close()
conn.close()
print("\n✅ Processo concluído com sucesso!")
