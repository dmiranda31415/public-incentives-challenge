"""Ferramenta rápida para auditar correspondências incoerentes.

Lista incentivos onde os matches gravados têm rule_pass = false ou
explicações ausentes, ajudando a validar a qualidade do top-5.
"""

import os
import psycopg2
from dotenv import load_dotenv


def main(limit: int = 20) -> None:
    load_dotenv()
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise SystemExit("DATABASE_URL não definido")

    conn = psycopg2.connect(db_url)
    cur = conn.cursor()

    cur.execute(
        """
        SELECT i.incentive_pk,
               i.title,
               m.company_id,
               c.company_name,
               m.score,
               m.rank,
               COALESCE(m.rule_pass::text, 'null') AS rule_pass_json,
               COALESCE(m.explanation, '')
        FROM matches m
        JOIN incentives i ON i.incentive_pk = m.incentive_id
        JOIN companies  c ON c.id = m.company_id
        WHERE COALESCE(m.rule_pass::text, 'false') NOT IN ('true', '"true"')
        ORDER BY m.score DESC
        LIMIT %s
        """,
        (limit,)
    )

    rows = cur.fetchall()
    if not rows:
        print("🎉 Todos os matches passaram nas regras.")
    else:
        for (iid, title, cid, cname, score, rank, rp, exp) in rows:
            print(f"Incentivo {iid} — {title}")
            print(f"  Empresa {cid} — {cname}")
            print(f"  score={score:.3f} rank={rank} rule_pass={rp}")
            if exp:
                print(f"  explicação: {exp}")
            print("-")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()


