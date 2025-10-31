import os, time, math
from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import execute_values
from openai import OpenAI, APIError, RateLimitError
from tqdm import tqdm
from usage_logger import log_usage, extract_usage_fields

load_dotenv()
DB_URL = os.environ["DATABASE_URL"]
OPENAI_KEY = os.environ["OPENAI_API_KEY"]

BATCH_EMB  = 100      # quantos textos por chamada à API
BATCH_DB   = 500      # commits por este nº de updates
MAX_CHARS  = 2000     # corta textos longos (reduz tokens/custo)
MODEL      = "text-embedding-3-small"

def clean_text(s: str) -> str:
    s = (s or "").strip()
    if not s:
        return ""
    # corta por caracteres (simples e suficiente); se quiseres, troca por contador de tokens
    return s[:MAX_CHARS]

def main():
    client = OpenAI(api_key=OPENAI_KEY)
    conn = psycopg2.connect(DB_URL)
    conn.autocommit = False

    # server-side cursor (streaming do servidor)
    cur = conn.cursor(name="companies_stream", withhold=True)
    cur.itersize = 2000
    cur.execute("""
        SELECT id, 
               coalesce(trade_description_native,'') || ' | ' ||
               coalesce(cae_primary_label,'')        || ' | ' ||
               coalesce(company_name,'')             AS txt
        FROM companies
        WHERE embedding IS NULL
    """)

    pending_updates = []
    processed = 0
    pbar = tqdm(desc="Embeddings", unit="rows")

    def flush_updates():
        """Atualiza em lote no Postgres."""
        nonlocal pending_updates, processed
        if not pending_updates:
            return
        execute_values(
            conn.cursor(),
            """
            UPDATE companies AS c
            SET embedding = v.embedding
            FROM (VALUES %s) AS v(id, embedding)
            WHERE c.id = v.id
            """,
            pending_updates,
            template="(%s, %s)"
        )
        conn.commit()
        processed += len(pending_updates)
        pbar.update(len(pending_updates))
        pending_updates = []

    batch_texts = []
    batch_ids = []

    try:
        while True:
            rows = cur.fetchmany(cur.itersize)
            if not rows:
                break
            for company_id, raw_txt in rows:
                txt = clean_text(raw_txt)
                batch_ids.append(company_id)
                batch_texts.append(txt if txt else None)  # None → tratamos já abaixo

                # quando atingimos o tamanho do batch, chamamos a API
                if len(batch_texts) >= BATCH_EMB:
                    # gera embeddings para o lote
                    embeddings = get_embeddings(client, batch_texts, MODEL)
                    # agrega para update
                    for cid, emb in zip(batch_ids, embeddings):
                        pending_updates.append((cid, emb))
                    batch_ids.clear()
                    batch_texts.clear()

                    # commit por lotes
                    if len(pending_updates) >= BATCH_DB:
                        flush_updates()

        # último lote (se sobrar)
        if batch_texts:
            embeddings = get_embeddings(client, batch_texts, MODEL)
            for cid, emb in zip(batch_ids, embeddings):
                pending_updates.append((cid, emb))
            batch_ids.clear()
            batch_texts.clear()

        flush_updates()
        pbar.close()
        print(f"✅ Concluído. Atualizadas {processed} linhas.")

    finally:
        try:
            cur.close()
        except Exception:
            pass
        conn.close()

def get_embeddings(client: OpenAI, texts, model):
    """Chama a API em batch, com retry/backoff. Substitui vazios por vetor zero."""
    # Substitui None/"" por vetor zero para manter dimensão
    # (podes também optar por saltar update nesses casos)
    if all(t is None or t.strip() == "" for t in texts):
        return [[0.0]*1536 for _ in texts]

    # onde o texto estiver vazio, mete placeholder, e depois devolve vetor zero
    placeholders = [i for i,t in enumerate(texts) if t is None or t.strip()==""]
    effective = [t if (t and t.strip()) else " " for t in texts]

    backoff = 1.0
    while True:
        try:
            resp = client.embeddings.create(model=model, input=effective)
            vecs = [d.embedding for d in resp.data]

            usage = extract_usage_fields(resp)
            log_usage(
                source="embed_companies",
                model=model,
                prompt_tokens=usage["prompt_tokens"],
                completion_tokens=usage["completion_tokens"],
                metadata={"batch_size": len(effective)},
            )

            for i in placeholders:
                vecs[i] = [0.0]*1536
            return vecs
        except (RateLimitError, APIError) as e:
            # backoff exponencial com limite
            time.sleep(backoff)
            backoff = min(backoff * 2, 8.0)
        except Exception as e:
            # erro inesperado → re-lança (ou loga)
            raise

if __name__ == "__main__":
    main()
