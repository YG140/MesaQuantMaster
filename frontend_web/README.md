# Mesa Quant Master Web

Frontend React + TypeScript oficial da Mesa Quant Master a partir desta versao.

## Instalar

```powershell
npm install
```

## Rodar localmente

```powershell
npm run dev
```

Configure `VITE_API_BASE_URL` em um `.env` local se o backend nao estiver em
`http://127.0.0.1:8000`.

## Scripts

- `npm run lint`
- `npm run typecheck`
- `npm run test`
- `npm run build`
- `npm run test:e2e`
- `npm run api:types`

## Coexistencia com Streamlit

O diretorio `frontend/` continua preservado e congelado como prototipo
temporario. Novas funcionalidades devem evoluir em `frontend_web/` sem importar
codigo Python e sem replicar regras financeiras.

A remocao do Streamlit ocorrera somente apos confirmacao de paridade funcional.
