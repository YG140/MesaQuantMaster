# Inicialização do Mesa Quant Master

## Pré-requisitos

- PostgreSQL local disponível e configurado em `backend/.env`.
- Ambiente virtual existente em `backend/.venv`.
- Node.js e `npm.cmd` disponíveis.
- Dependências Python e JavaScript previamente instaladas.
- Portas 8000 e 5173 livres.

O inicializador não instala dependências, não cria banco e não executa migrations.
O arquivo `backend/.env` permanece local e nunca deve ser enviado ao Git.

## Iniciar

No PowerShell, a partir de qualquer diretório:

```powershell
& "C:\caminho\do\MesaQuantMaster\start.ps1"
```

Na raiz do projeto, também é possível executar:

```powershell
.\start.ps1
```

Para iniciar com dois cliques, use `Iniciar MesaQuantMaster.bat`.

O frontend ficará em <http://127.0.0.1:5173/> e o backend em
<http://127.0.0.1:8000/>. Pressione Ctrl+C na janela do inicializador para
encerrar ambos.

## Parâmetros

- `-NoBrowser`: não abre o navegador após os dois serviços ficarem prontos.
- `-StartupTimeoutSeconds 90`: altera o limite de espera, entre 5 e 600 segundos.
- `-SkipDatabaseCheck`: ignora explicitamente apenas o preflight de PostgreSQL e
  migrations. Destina-se a testes controlados; portas, arquivos e executáveis
  continuam sendo validados.

## Erros comuns

- **Ambiente Python ausente:** crie `backend/.venv` e instale as dependências.
- **npm ausente:** instale o Node.js.
- **backend/.env ausente:** prepare a configuração local sem versioná-la.
- **PostgreSQL indisponível:** inicie o serviço e confira a configuração privada.
- **Migration pendente:** aplique conscientemente o procedimento de migration fora
  do inicializador. Nenhuma migration é executada automaticamente.
- **Porta ocupada:** encerre manualmente o processo que já usa a porta. O
  inicializador nunca o mata.
- **Serviço não ficou pronto:** consulte a saída visível do backend ou frontend.

## Desenvolvimento separado

Backend, a partir de `backend/`:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

Frontend, a partir de `frontend_web/`:

```powershell
npm.cmd run dev
```

O modo unificado não usa reload por padrão.
