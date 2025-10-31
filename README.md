<<<<<<< HEAD

=======
# Public Incentives – AI Challenge

Projeto desenvolvido para o **AI Challenge | Public Incentives**.  
Objetivo: identificar automaticamente as 5 empresas mais adequadas por incentivo e disponibilizar um chatbot que responde com base na base de dados já enriquecida.

---

## 🚀 Visão Geral

- Matching automático entre incentivos e empresas, combinando embeddings (pgvector) e regras objetivas (CAE permitido, keywords obrigatórias).
- Explicações para cada correspondência geradas via LLM e guardadas em `matches_with_explanation.csv`.
- Chatbot (FastAPI + React/Tailwind) com respostas em streaming e sugestões de perguntas.

---

## 🧱 Estrutura do Projeto

```
public_incentives/
├── app.py                      # API FastAPI (chatbot)
├── match.sql                   # Regras do matching (top-5 por incentivo)
├── run_match.py                # Executa match.sql sem precisar de psql
├── explain_matches.py          # Reordena + gera explicações com LLM
├── audit_matches.py            # Auditoria de correspondências incoerentes
├── usage_logger.py / report_usage.py
├── matches_with_explanation.csv
├── data/                       # CSVs de empresas/incentivos (limpos)
├── frontend/                   # UI (React + Vite + Tailwind)
├── requirements.txt
└── README.md
```

`augusta/`, `usage_log.csv`, `frontend/node_modules/`, `.env`, etc., estão ignorados por `.gitignore`.

---

## ⚙️ Setup

### Pré-requisitos
- Python 3.9+
- PostgreSQL com extensão `pgvector`
- Node.js 18+
- Chave OpenAI (`OPENAI_API_KEY`)
- Variável `DATABASE_URL` (ex.: `postgres://user:pass@host/db`)

### Instalação

```bash
git clone <repo>
cd public_incentives

python -m venv augusta
./augusta/Scripts/Activate.ps1   # (PowerShell no Windows)
pip install -r requirements.txt

cd frontend
npm install
cd ..
```

---

## 📦 Base de Dados

1. Criar as tabelas necessárias.
2. Carregar `data/companies_clean.csv` e `data/incentives_clean.csv`.
3. (Opcional) Recalcular embeddings/eligibilidade com `embed_companies.py` e `embed_incentives_and_eligibility.py` se quiseres reprocessar a partir do texto original.

---

## 🔄 Pipeline de Matching

> Necessita de `.env` com `DATABASE_URL` e `OPENAI_API_KEY`.

1. **Recalcular top-5 (regras + embeddings)**
   ```bash
   python run_match.py
   ```
   - Executa `match.sql`, faz `TRUNCATE matches` e grava o novo top‑5 com a flag `rule_pass`.

2. **Gerar explicações com LLM**
   ```bash
   python explain_matches.py
   ```
   - Dá prioridade a empresas `rule_pass=true` e regista tokens/custos.

3. **Auditar resultados (opcional)**
   ```bash
   python audit_matches.py
   ```
   - Lista incentivos em que nenhum candidato cumpre todas as regras (útil para documentação).

4. **CSV final**
   - `matches_with_explanation.csv`

---

## 📈 Monitorização de Custos

Cada chamada à OpenAI é registada em `usage_log.csv`.  
Para obter um resumo:

```bash
python report_usage.py
```

---

## 💬 Chatbot

### Backend (FastAPI)
```bash
uvicorn app:app --reload
```

### Frontend (React/Vite)
```bash
cd frontend
npm run dev
```

- O frontend corre em `http://localhost:5173`, o backend em `http://localhost:8000`.
- O CORS já permite esta origem; ajusta `app.py` se mudares as portas.
- UI com sugestões de perguntas e respostas em streaming (markdown).

---

## 📝 Notas

- Alguns incentivos podem não ter empresas perfeitamente elegíveis (dados incompletos). Nesses casos, o pipeline penaliza os candidatos e a explicação indica a limitação (ex.: “Não cumpre as regras de elegibilidade devido ao CAE”).
- `matches_with_explanation.csv` é o artefacto final a entregar.
- `usage_log.csv`, `augusta/`, `frontend/node_modules/`, `.env`, etc., estão listados em `.gitignore`.


