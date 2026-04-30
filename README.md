# EcoTrace

EcoTrace has a FastAPI backend and a Vite/React frontend.

## Backend

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r backend\requirements.txt
uvicorn backend.main:app --reload
```

Run backend checks from the repository root:

```powershell
python -B -m unittest backend.test_ecotrace_pipeline
```

## Frontend

The frontend folder is currently named `fronend`.

```powershell
cd fronend
npm install
npm run dev
```

Build check:

```powershell
npm run build
```

## Environment

Put all local backend, API, database, news, and LLM keys in `backend/.env`.
Keep real `.env` files out of git.
