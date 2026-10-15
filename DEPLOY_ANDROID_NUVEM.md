# Publicar o Mesa Quant Master no celular (Render + APK)

## Estado da entrega

O repositório inclui o código para a nuvem: FastAPI em HTTPS, PostgreSQL
persistente, migrações de banco, site React para verificação de e-mails e
recuperação de senha, e o workflow para gerar o APK Android usando a URL
HTTPS real da API. **Nenhuma hospedagem é criada só por adicionar o YAML ao
GitHub**: a conta Render deve autorizar a implantação.

O Blueprint usa **planos pagos** (API 0.5c-512mb e banco 0.1c-256mb).
Verifique o preço e os limites atuais no painel Render antes de confirmar a
cobrança. O site estático React tem plano próprio e pode usar nível gratuito.
Não usar PostgreSQL gratuito que expira ou serviços que suspendem acesso para
armazenar uma carteira pessoal. Configure e teste backups.

## 1. Vincular o repositório privado ao Render

1. Entrar em <https://dashboard.render.com/> e conectar a conta GitHub com
   permissão ao repositório privado `YG140/MesaQuantMaster`.
2. Usar **New → Blueprint**, selecionar o projeto na branch `main`.
   O arquivo `render.yaml` criará os recursos:
   - `mesa-quant-master-api` (FastAPI, HTTPS);
   - `mesa-quant-master-db` (PostgreSQL persistente, acesso interno);
   - `mesa-quant-master-web` (React/HTTPS para acesso no computador,
     recuperação de senha e confirmação de e-mail).
3. Informar no painel Render os valores solicitados **sem colocar segredos
   no GitHub**:
   - `FRONTEND_PUBLIC_URL`: URL real do site web depois de criada;
   - `VITE_API_BASE_URL`: URL **real da API HTTPS** no serviço estático;
   - `BRAPI_API_KEY`, `COINGECKO_DEMO_API_KEY`, `TWELVEDATA_API_KEY`:
     chaves obtidas nos respectivos provedores. Podem continuar vazias
     temporariamente, mas análises que dependem delas falharão claramente.
   - `SECRET_KEY` será gerada automaticamente pelo Render; não alterar
     sem planejamento (invalida sessões existentes).
4. O banco é privado no Render, com `DATABASE_URL` injetada
   automaticamente (não digite nem compartilhe a senha). O deploy instala
   Python e dependências, executa `alembic upgrade head` **antes** de
   disponibilizar a versão, e inicia o FastAPI na porta atribuída.

## 2. Domínios e autenticação

Quando o Render informar as URLs **reais** (sem presumir que uma URL
de exemplo esteja livre):

1. Em `mesa-quant-master-api` → Environment, alterar
   `FRONTEND_ORIGINS` para duas origens, separadas por vírgula:
   ```text
   https://localhost,https://DOMINIO-WEB-REAL.onrender.com
   ```
   `https://localhost` é o origin do WebView Capacitor Android, **não**
   indica que o backend roda no computador. Use somente domínios reais;
   sem `/` final.
2. Configurar `FRONTEND_PUBLIC_URL` com a URL exata HTTPS do site web,
   e `VITE_API_BASE_URL` no serviço web com a URL exata HTTPS da API.
   O React lê esse último valor **durante o build**: faça deploy novo após
   alterar a variável.
3. Reiniciar API após alterar origens; confirmar site, cadastro,
   recuperação de conta e chamadas autenticadas. A URL pública da API
   deve responder:
   - `GET /`: `application = "Mesa Quant Master"`;
   - `GET /health`: `status = "healthy"`;
   - `GET /ready`: `status = "ready"` **somente com PostgreSQL acessível**.
4. Criar uma conta (ou usar o fluxo existente de autenticação do sistema).
   **O banco cloud inicia vazio.** `alembic` cria a estrutura, mas não
   importa automaticamente usuários, transações, carteiras e perfis locais
   do computador. Usar a importação da carteira com revisão das posições,
   ou realizar uma migração segura e explicitamente autorizada com backup.

## 3. Gerar o APK que funciona sem o computador

1. Abrir <https://github.com/YG140/MesaQuantMaster/actions/workflows/android-apk.yml>
   no GitHub, entrar em **Run workflow** na branch `main`.
2. Preencher `api_base_url` com a **URL real HTTPS** da API (sem barra
   final), ou configurar a variável do repositório `MESA_API_BASE_URL`.
3. O pipeline exige URL HTTPS pública, verifica raiz + `/health`,
   compila a interface com o servidor correto, gera o projeto Android
   Capacitor e disponibiliza o APK de testes na seção **Artifacts**.
4. Baixar o ZIP `MesaQuantMaster-Android-debug`, extrair
   `app-debug.apk` e instalar no aparelho Android. O computador poderá
   ficar desligado; o app continuará dependendo de internet, do Render
   ativo e das chaves que habilitam as fontes financeiras.

**Limite de distribuição:** APK debug é para teste pessoal, não para Play
Store. A chave de debug do runner GitHub pode mudar entre builds. Para
atualizações estáveis/Play Store ainda é necessário adicionar um processo
de assinatura de release com chave privada persistente e armazenamento
seguro de sessão no Android. Não use dados altamente sensíveis antes de
revisão de segurança da autenticação.

## 4. Banco e saúde operacional

- `APP_ENV=production` impede iniciar com SQLite, segredo inseguro,
  Swagger ligado, DEBUG habilitado ou frontend HTTP.
- Exigir HTTPS e origem do app, não aceitar CORS `*`.
- `/ready` verifica `SELECT 1` no banco; sem acesso retorna 503.
- Verificar backups automáticos oferecidos pelo plano, política de
  retenção, restauração de teste, métricas, alarmes e limite de custo.
- As APIs públicas de mercado podem exigir planos/quotas. Não colocar
  chaves em React, GitHub, APK, comentários ou código.
- Não migrar dados reais por simples importação de banco SQLite diretamente
  sobre uma base PostgreSQL existente. Revisar antes o esquema e backups.

## 5. Câmbio oficial (referência de leitura)

`GET /market/fx/usd-brl` autentica o usuário e consulta a PTAX venda de
fechamento do Banco Central do Brasil, selecionando o último registro
válido de até seis dias. Na interface de ativos internacionais em USD,
exibe a taxa e o preço por unidade convertido **apenas como referência**.
A taxa **não** inclui spread de corretora, IOF, taxas e impostos e não
pode ser confundida com preço executável.

A conversão FX **não foi acoplada às ordens e aos saldos realizados**, pois
as operações antigas não registram explicitamente moeda histórica de
aquisição. Alterar preços sem migrar essa informação produziria
lucros/perdas falsos. A compra automática de ativos precificados em
moeda estrangeira segue bloqueada até essa evolução; a cotação informativa
é verificável, não um atalho inseguro para aportes em BRL.

## Links

- [Render — Blueprints](https://render.com/docs/infrastructure-as-code)
- [Render — referência de render.yaml](https://render.com/docs/blueprint-spec)
- [BCB — PTAX oficial](https://dadosabertos.bcb.gov.br/dataset/dolar-americano-usd-todos-os-boletins-diarios)
- [Guia de mercado internacional](backend/PROVEDORES_GLOBAIS_E_CRIPTO.md)
