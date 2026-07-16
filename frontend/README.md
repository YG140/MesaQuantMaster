# Frontend Streamlit

Interface MVP do Mesa Quant Master para consumir a API FastAPI via HTTP.

## Configuracao

Crie um arquivo `.env` local a partir de `frontend/.env.example` se precisar alterar a URL da API.

```env
API_BASE_URL=http://127.0.0.1:8000
```

## Execucao

Backend:

```powershell
cd C:\Dev\MesaQuantMaster\backend
.\.venv\Scripts\Activate.ps1
python -m uvicorn app.main:app --reload
```

Frontend, em outro terminal:

```powershell
cd C:\Dev\MesaQuantMaster
.\backend\.venv\Scripts\Activate.ps1
streamlit run frontend/app.py
```

O frontend nao acessa banco, models, services, repositories ou engines do backend.
Toda comunicacao acontece pelos endpoints HTTP da API.
