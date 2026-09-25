# Órbita — operação local desta instalação

A interface foi aprovada pelo usuário para este ciclo. Não houve comparação
com as referências originais na execução inicial; a aprovação visual posterior
do usuário permanece válida. Mesa IA está pausada, sem conversa ou chamadas
externas pela interface. Os contratos e cálculos financeiros continuam na FastAPI.

## Pré-requisitos

- Python 3.13 e dependências do projeto no ambiente virtual existente.
- Node.js e npm, com dependências de `frontend_web/package-lock.json` instaladas.
- PostgreSQL existente, disponível e com schema compatível. Não criar outro banco
  nem executar migrações automaticamente para recuperar acesso.
- Configuração privada existente em `C:\Dev\MesaQuantMaster\backend\.env`.
- Portas locais 8000 (API) e 5180 (frontend) disponíveis.

Variáveis do backend: `DATABASE_URL`, `SECRET_KEY`, `SMTP_HOST`, `SMTP_PORT`,
`SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM_EMAIL`, `SMTP_FROM_NAME`,
`SMTP_USE_TLS`, `SMTP_TIMEOUT_SECONDS`, `FRONTEND_PUBLIC_URL`,
`FRONTEND_ORIGINS` e `AI_AGENT_ENABLED`. Não publique valores de credenciais.
No frontend, somente `VITE_API_BASE_URL` aponta para a API; credenciais de
provedores nunca devem ser configuradas como variáveis `VITE_*`.

## Iniciar nesta máquina

Antes de iniciar, confira as portas; não encerre processos de outras tarefas:

```powershell
Get-NetTCPConnection -LocalPort 8000,5180 -State Listen -ErrorAction SilentlyContinue |
    Select-Object LocalAddress,LocalPort,OwningProcess
```

Em um terminal PowerShell, inicie a API com o inicializador local já auditado:

```powershell
Set-Location C:\Dev\MesaQuantMaster-worktrees\orbita-interface-final\backend
& C:\Dev\MesaQuantMaster\backend\.venv\Scripts\python.exe -B C:\Dev\OrbitaCapturas\iniciar-api-local.py
```

Esse auxiliar é local, não é parte do repositório. Carrega a configuração privada
existente, verifica banco e schema antes de iniciar, usa `127.0.0.1:8000`,
desabilita a IA e configura a origem e a URL pública do frontend para a porta
5180. Variáveis herdadas têm precedência sobre o arquivo `.env`; confira o
ambiente se houver divergência. Se o auxiliar estiver ausente, não invente seu
conteúdo nem a configuração: consulte [STARTUP.md](STARTUP.md) e prepare o
ambiente antes de iniciar. O inicializador geral documentado ali usa a porta
5173, não a 5180 desta instalação.

Em outro terminal:

```powershell
Set-Location C:\Dev\MesaQuantMaster-worktrees\orbita-interface-final\frontend_web
$env:VITE_API_BASE_URL = 'http://127.0.0.1:8000'
npm.cmd run dev -- --host 127.0.0.1 --port 5180 --strictPort
```

Abra <http://127.0.0.1:5180/login> e use sua conta existente. Não há senha padrão
nem modo de autenticação alternativa. Para verificar disponibilidade:

```powershell
Invoke-WebRequest http://127.0.0.1:8000/health -UseBasicParsing
Invoke-WebRequest http://127.0.0.1:5180/login -UseBasicParsing
```

Encerre cada serviço com Ctrl+C no respectivo terminal. Serviços anteriormente
iniciados em segundo plano exigem identificar o PID pela porta e confirmar seu
comando antes de usar `Stop-Process -Id <PID-confirmado>`; nunca encerre todos os
processos Python ou Node. Para reiniciar, repita os comandos após liberar apenas
as portas dos serviços desta instalação.

## Recuperação de senha

Use <http://127.0.0.1:5180/esqueci-minha-senha>. Informe o e-mail cadastrado uma
única vez e confira entrada e spam. Abra o link recebido nesta mesma máquina e
defina sua senha pelo formulário; não compartilhe senha, token ou link no chat.
Links são temporários e de uso único. Uma nova solicitação pode invalidar o
anterior. Links expirados exigem nova solicitação, não alteração manual do banco.

A resposta pública é neutra e não confirma existência da conta nem entrega.
Falhas HTTP/rede aparecem como erro, não como sucesso. Ausência global de
configuração de envio retorna indisponibilidade sem revelar cadastro.

Na investigação local, a solicitação real recebeu HTTP 200; o SMTP retornou 250
após receber a mensagem, sem destinatários recusados. Banco, configuração e URL
local foram conferidos sem divulgar segredos. Posteriormente, o usuário confirmou
que recebeu o e-mail e conseguiu redefinir a senha. Isso confirma o desfecho desta
recuperação, não prova a causa da ausência dos e-mails anteriores.

## Testes e limitações

Vitest e E2E usam dados determinísticos somente nos testes. Não são modo de
demonstração da aplicação real. Execute os scripts de `frontend_web/package.json`:
`npm.cmd run typecheck`, `npm.cmd run lint`, `npm.cmd test -- --maxWorkers=1`,
`npm.cmd run build` e `npm.cmd run test:e2e`. O worker único reduz concorrência;
não altera asserções, retries ou timeouts. O E2E usa a porta 5173 e gera artefatos
em `test-results`; não copie esses artefatos por cima das capturas aprovadas.

Os testes Python devem usar exclusivamente banco isolado de testes, nunca o
PostgreSQL pessoal. O `tests/conftest.py` configura SQLite em memória.
Logs, bancos, `.env`, tokens, traces e capturas pessoais não devem entrar no Git.
As capturas aprovadas permanecem evidências externas ao repositório.

## Checkpoint de validação — 25/09/2026

- Typecheck e ESLint: passaram na execução anterior deste encerramento; desde
  então, somente documentação e formatação do teste Python foram alteradas.
- Recuperação de senha: 10 testes passaram, com código de saída zero registrado.
- Pytest completo: 962 passaram em uma única execução (35min12s).
- Vitest completo: 11 arquivos e 125 testes passaram, usando `--maxWorkers=1`.
- Build: concluído. Aviso do Vite: `PrismaPreviewPage` tem importação estática e
  dinâmica, portanto não é separado em outro chunk pela importação dinâmica.
- E2E completo: 31 testes passaram. Os cenários de detalhes verificaram 20
  células, sem células fora da viewport, e largura de documento igual à viewport.
- Ruff global: passou. Black restrito a `backend/app/api/auth.py`,
  `backend/app/services/auth_service.py` e `tests/unit/test_email_auth.py`: passou
  com alvo Python 3.13 e um worker.
- Black global: apontou 52 arquivos para formatação. Apenas o teste de recuperação
  desta tarefa foi formatado; os arquivos externos ao escopo foram preservados.
  Não se declara aprovação global do Black.
- `git diff --check`: sem erros; avisos LF/CRLF no ambiente Windows.

O pytest anterior interrompido em 44% não foi contado. Os resultados acima vêm
dos resumos completos dos logs locais, não de soma de execuções isoladas nem de
CI remoto. O executor auxiliar registrou códigos de saída nulos para as etapas
completas; a evidência é o resumo final de cada ferramenta. Não houve aumento de
timeouts, adição de retries ou enfraquecimento das asserções.
