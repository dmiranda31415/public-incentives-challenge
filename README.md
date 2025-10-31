Public Incentives – AI Challenge
Projeto desenvolvido para o AI Challenge | Public Incentives.
Objetivo: identificar automaticamente as 5 empresas mais adequadas para cada incentivo e disponibilizar um chatbot que responde com base na base de dados e nas correspondências.
🚀 Visão Geral
Matching automático entre incentivos e empresas, combinando embeddings (pgvector) e regras objetivas (CAE permitido, keywords obrigatórias).
Explicações geradas por LLM e guardadas em matches_with_explanation.csv.
Chatbot FastAPI + React/Tailwind com respostas em streaming.
🧱 Estrutura do Projeto
public_incentives/
├── app.py                      # API FastAPI (chatbot)
├── match.sql                   # Regra de matching (top-5)
├── run_match.py                # Executa match.sql via Python
├── explain_matches.py          # Reordena + gera explicações
├── audit_matches.py            # Auditoria a matches incoerentes
├── usage_logger.py / report_usage.py
├── matches_with_explanation.csv
├── data/                       # CSVs de empresas/incentivos
├── frontend/                   # UI (React + Vite + Tailwind)
├── requirements.txt
└── README.md
> augusta/, usage_log.csv, frontend/node_modules/, .env, etc., estão ignorados por .gitignore.
⚙️ Setup
Pré-requisitos
Python 3.9+
PostgreSQL com extensão pgvector
Node.js 18+
Chave OpenAI (OPENAI_API_KEY)
Variável de ambiente DATABASE_URL (ex.: postgres://user:pass@host/db)
git clone <repo>
cd public_incentives

python -m venv augusta
./augusta/Scripts/Activate.ps1   # Windows PowerShell
pip install -r requirements.txt

cd frontend
npm install
cd ..
