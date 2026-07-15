# Mesa Quant Master - Frontend MVP

## Objetivo

O MVP em Streamlit permite usar autenticacao, dashboard, carteira, ativos,
operacoes e backtesting sem depender do Swagger.

## Instalar

```powershell
cd C:\Dev\MesaQuantMaster
.\backend\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

## Configurar

O frontend le a variavel `API_BASE_URL`.

```env
API_BASE_URL=http://127.0.0.1:8000
```

Existe apenas `frontend/.env.example`. Nao versionar `.env` real.

## Iniciar

Backend:

```powershell
cd C:\Dev\MesaQuantMaster\backend
.\.venv\Scripts\Activate.ps1
python -m uvicorn app.main:app --reload
```

Frontend:

```powershell
cd C:\Dev\MesaQuantMaster
.\backend\.venv\Scripts\Activate.ps1
streamlit run frontend/app.py
```

## Autenticacao

A tela inicial permite criar conta e fazer login. O token JWT fica apenas em
`st.session_state` e e enviado como Bearer Token pelo cliente HTTP centralizado.
Apos login, o frontend chama `GET /users/me` para validar a sessao.

## Paginas

- Dashboard: consome `/dashboard` e `/portfolio`.
- Carteira: consome `/portfolio`.
- Operacoes: consome `/operations` e `/assets`.
- Ativos: consome `/assets`.
- Backtesting: consome `/backtesting/run`.

## Limitacoes atuais

- A interface nao inicia backend automaticamente.
- O backtesting recebe serie historica manual em formato `data,fechamento`.
- Graficos usam os componentes nativos do Streamlit.
- O resumo de risco usa dados ja retornados pela carteira e dashboard.
