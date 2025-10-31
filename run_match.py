import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()
SQL_PATH = "match.sql"
DB_URL = os.getenv("DATABASE_URL")

if not DB_URL:
    raise SystemExit("DATABASE_URL não definido no .env")

if not os.path.exists(SQL_PATH):
    raise SystemExit(f"Ficheiro {SQL_PATH} não encontrado")

with open(SQL_PATH, encoding="utf-8") as fh:
    sql = fh.read()

conn = psycopg2.connect(DB_URL)
cur = conn.cursor()
cur.execute(sql)
conn.commit()
cur.close()
conn.close()

print("✅ match.sql executado com sucesso")
