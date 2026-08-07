# SwingScore

Plataforma web de análise probabilística para swing trade na B3 e no exterior.
Dados de preço/fundamentos vêm do Yahoo Finance; indicadores (RSI, médias, ATR,
suportes/resistências, linhas de tendência) são calculados no backend.

A interface mostra o **SwingScore** (0–100) com três pilares — fundamentos (40%),
técnico (35%) e macro (25%) —, alvos sempre em faixas com probabilidades, e
comunicação estritamente estatística (sem "vai subir" ou "compre").

## Stack

- **Backend**: FastAPI + SQLAlchemy + pandas/yfinance (pasta `backend/`)
- **Frontend**: React + Vite + Lightweight Charts (pasta `frontend/`)
- **IA**: relatório em linguagem natural opcional via endpoint compatível com
  OpenAI (desligado por padrão em produção — usa template).

## Rodar localmente

### Backend

```bash
cd backend
pip install -r requirements.txt   # ou: uv sync
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

### Frontend (desenvolvimento)

```bash
cd frontend
npm install
npm run dev   # Vite faz proxy de /api para 127.0.0.1:8000
```

Abra http://localhost:5173.

## Produção (Render, serviço único)

O `frontend/dist` é versionado, então o Render só precisa de Python:
o backend serve o build estático e a API na mesma origem.

1. Crie um repositório público no GitHub e suba este código.
2. No Render, **New → Web Service**, aponte para o repositório.
3. Build: `pip install -r backend/requirements.txt`
4. Start: `cd backend && uvicorn app.main:app --host 0.0.0.0 --port $PORT`
5. Variáveis de ambiente: `SWING_LLM_ENABLED=false` (relatório por template).

Alternativamente, use o `render.yaml` incluído (Render Blueprint).

## Configuração (env vars, prefixo `SWING_`)

| Variável | Padrão | Descrição |
| --- | --- | --- |
| `SWING_LLM_ENABLED` | `true` | Liga/desliga o relatório via LLM |
| `SWING_LLM_BASE_URL` | `http://localhost:20128/v1` | Endpoint OpenAI-compatível |
| `SWING_LLM_MODEL` | `nvidia/deepseek-ai/deepseek-v4-pro` | Modelo do relatório |
| `SWING_MOCK_MODE` | `false` | Usa dados simulados (respostas marcadas como demo) |
| `SWING_CACHE_TTL_SECONDS` | `3600` | TTL do cache em memória |
| `SWING_DATABASE_URL` | vazio | PostgreSQL opcional (fallback: SQLite `swing.db`) |

## Aviso

Ferramenta educacional/experimental. Não é recomendação de investimento.
