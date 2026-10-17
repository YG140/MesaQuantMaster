# Mesa Quant Master no Android — Render Free + Neon Free (teste pessoal)

Esta configuração evita **mensalidades fixas obrigatórias**, respeitando as
cotas dos planos gratuitos. A API, o site React e o banco **não estão
automaticamente publicados** só por existir o `render.yaml`.

## O que é gratuito e o que não está garantido

| Peça | Provedor | Plano previsto |
| --- | --- | --- |
| FastAPI HTTPS | Render Web Service | **Free** (`plan: free`) |
| PostgreSQL persistente | Neon | **Free**, externo à Render |
| Site React HTTPS | Render Static Site | Grátis dentro das cotas |
| APK pessoal | GitHub Actions | Dentro das cotas do GitHub |

**Limites críticos e riscos:**
- Render Free suspende o serviço após **15 minutos sem acesso**; retornar
  pode demorar cerca de um minuto ou mais. Há limites mensais de horas,
  bandwidth e build minutes. Render pode cobrar tráfego/build excedente se
  sua conta tiver forma de pagamento cadastrada. Defina limites de gasto e
  monitore uso; "grátis" **não garante** zero em todos os cenários.
- O disco do Render Free é **temporário**: não armazenar SQLite,
  documentos, credenciais nem carteira financeira no disco local.
- Neon Free tem limite de armazenamento, computação e tráfego
  (consulte cotas atuais no painel). Não é backup garantido ou SLA de
  produção; exporte backups periódicos e teste restauração.
- Render Free não permite `preDeployCommand`; a API executa
  `python -m alembic upgrade head` a cada inicialização e **só depois**
  inicia o Uvicorn (veja `backend/scripts/start-free.sh`).
- Render Free bloqueia SMTP de saída nas portas 25, 465 e 587.
  O fluxo existente de verificação/recuperação por SMTP **não deve ser
  prometido** sem um serviço de e-mail autorizado via HTTPS.
- Provedores de dados externos (CoinGecko, Twelve Data) têm quotas
  independentes e podem exigir API key mesmo no nível gratuito.
- O APK debug para testes **não** é release assinado para Play Store.

## 1. Criar ou conectar Neon Free

1. Conectar o aplicativo **Neon** no ChatGPT, ou entrar em
   <https://console.neon.tech/> e criar um projeto PostgreSQL no plano
   **Free**. Escolher uma região próxima à API Render, se possível.
2. No painel Neon, copiar a **connection string Postgres** da base
   escolhida, com `sslmode=require` e hostname do Neon
   (`*.neon.tech`). Por exemplo:
   ```text
   postgresql://USUARIO:SENHA@ENDERECO-REAL.neon.tech/NOME_BANCO?sslmode=require
   ```
   Este texto é somente um **exemplo**, não funciona como credencial.
3. Não compartilhar, registrar em commit ou colocar o URL de conexão
   no site React, APK, README, mensagens ou logs. Inserir o valor somente
   na variável secreta `DATABASE_URL` da API no Render. Se a Neon
   sugerir URI pooled, conferir compatibilidade com migrações Alembic;
   usar URL direto TLS para migrações que exigem transações.

O código em `backend/app/core/database.py` usa pool pequeno, verificação
prévia da conexão e reciclagem de conexões, adequado à suspensão da Neon.
A API recusa SQLite em produção. O banco Neon persiste fora do disco
temporário da Render, mas exige backups próprios.

## 2. Criar os serviços gratuitos na Render

A Render já pode estar conectada à conversa; ainda é necessário que a
conta Render tenha permissão GitHub para ler o **repositório privado**
`YG140/MesaQuantMaster`. No painel da Render:

1. Ir em **New → Blueprint**, selecionar o repositório e a branch
   `main`. O `render.yaml` cria **somente**:
   - `mesa-quant-master-api`: serviço Python **Free**;
   - `mesa-quant-master-web`: site estático React.
   **Não** cria banco de dados, volume nem recurso pago.
2. Durante a configuração das variáveis `sync: false`, informar:
   - API → `DATABASE_URL`: **URI TLS Neon real, mantida secreta**.
   - API → `FRONTEND_PUBLIC_URL`: URL HTTPS real do site web.
   - Web → `VITE_API_BASE_URL`: URL HTTPS real da API.
   - API → `BRAPI_API_KEY`, `COINGECKO_DEMO_API_KEY`,
     `TWELVEDATA_API_KEY`: opcionais; valores ficam secretos no
     servidor, jamais no APK.
   - `SECRET_KEY` é gerada automaticamente pela Render.
3. Após a criação dos dois domínios, adicionar à variável
   `FRONTEND_ORIGINS` da API:
   ```text
   https://localhost,https://DOMINIO-WEB-REAL.onrender.com
   ```
   Substituir pelo domínio **real**. `https://localhost` é a origem
   interna do WebView Capacitor Android, não o endereço do computador.
4. Fazer novo deploy do site após configurar `VITE_API_BASE_URL`, pois
   Vite incorpora esse valor durante a compilação.
5. Testar API depois que ela acordar:
   - `GET /`: `application: Mesa Quant Master`;
   - `GET /health`: `status: healthy`;
   - `GET /ready`: `status: ready` se Neon responde a `SELECT 1`.
   Sem banco acessível, ela **não deve** indicar pronta.
6. Confirmar login/autenticação e endpoints no navegador. Cuidado com
   os fluxos de e-mail: SMTP 25/465/587 **não funciona** na Render Free.

O banco remoto começa **vazio**. As migrações criam o esquema, mas não
movem automaticamente usuários, transações nem dados da carteira local.
Planejar migração segura com backup se houver dados a preservar.

## 3. APK Android real

1. Depois que a API responder corretamente, abrir:
   <https://github.com/YG140/MesaQuantMaster/actions/workflows/android-apk.yml>
2. Selecionar **Run workflow** na `main`.
3. Informar `api_base_url` com a URL HTTPS verdadeira da API Render,
   sem barra final (ou usar variável de repositório `MESA_API_BASE_URL`).
4. O workflow verifica HTTPS, `/`, `/health` e `/ready` antes
   de disponibilizar o APK de uso pessoal. Compila React/Capacitor e
   produz o artifact `MesaQuantMaster-Android-debug`.
5. Baixar, extrair `app-debug.apk` e instalar no Android. O computador
   poderá ficar desligado; o celular ainda precisa de internet, Neon
   disponível e a API Render acordada.

Uma compilação Android de teste com URL substituta **não** comprova
funcionamento de ponta a ponta com o backend hospedado.

## 4. Cuidados com dados financeiros

- Não revelar credenciais ou importar carteira financeira real antes
  de validar autenticação e backups no ambiente gratuito.
- A PTAX BCB USD/BRL é **referência informativa**, não taxa de
  compra e venda, e não inclui IOF ou spread; ordens internacionais
  executáveis continuam bloqueadas até existir câmbio de execução e
  registro histórico da moeda de aquisição.
- Monitorar quotas de Render, Neon, CoinGecko e Twelve Data, ajustar
  universo de ativos conforme o plano e parar se atingir limites.
- Não usar ping artificial para impedir a hibernação grátis; aceitar
  a suspensão faz parte do acordo de uso do serviço.

## Documentação oficial

- [Render Free](https://render.com/docs/free)
- [Render Blueprints](https://render.com/docs/infrastructure-as-code)
- [Neon Free](https://neon.com/pricing)
- [Neon — conexão PostgreSQL](https://neon.com/docs/connect/connect-from-any-app)
