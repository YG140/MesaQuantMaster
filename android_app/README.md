# Mesa Quant Master — aplicativo Android (APK)

## Arquitetura

```text
Android / Capacitor 8 (APK, interface React empacotada)
  |
  | HTTPS obrigatório, JSON, JWT Bearer
  v
API FastAPI Mesa Quant Master (servidor 24/7, fora do PC pessoal)
  |---- PostgreSQL persistente (usuários, perfil, operações e posições)
  |---- Provedores de mercado (BRAPI, B3, CVM, Tesouro)
  `---- Segurança, backup, monitoramento e autenticação
```

**Independente do computador não significa offline**. O APK inclui a interface,
mas os cálculos e dados seguem no FastAPI; este backend **ainda não foi
hospedado por esta mudança**. Sem API remota HTTPS, o aplicativo não consegue
fazer login, montar carteiras ou carregar cotações. Não configure a API com
`127.0.0.1`, `localhost`, IP do Wi-Fi ou o endereço da interface web.

## Projeto Android no repositório

- `android_app/package.json` — Capacitor 8, com versões fixas.
- `android_app/capacitor.config.json` — identidade Android, diretório do
  React compilado, WebView `https://localhost`, sem conteúdo remoto.
- `android_app/scripts/verify-api-url.mjs` — recusa HTTP, localhost e
  endereço de exemplo em builds instaláveis.
- `android_app/scripts/check-api-health.mjs` — confirma a API do Mesa Quant
  Master antes de gerar um APK instalável.
- `android_app/scripts/harden-android-manifest.mjs` — nega HTTP em claro e
  backup automático do armazenamento privado do app.
- `.github/workflows/android-apk.yml` — gera projeto Gradle Android com o
  Capacitor e compila via GitHub Actions. O diretório `android_app/android/`
  é gerado pelo Capacitor e não precisa ser enviado manualmente à PR.

Por segurança, não incluímos URLs públicas inventadas, chaves de API, tokens,
senhas, banco de dados ou credenciais de assinatura no repositório.

## Antes de gerar o APK para uso real

1. Hospedar **backend FastAPI** em um servidor sempre disponível (serviço
   cloud/VPS), com PostgreSQL persistente, HTTPS e domínio público, por
   exemplo `https://api.seudominio.com`. Essa URL é **um exemplo, não um
   servidor existente**.
2. Configurar no serviço cloud `DATABASE_URL`, `SECRET_KEY`,
   `APP_ENV=production`, `BRAPI_API_KEY` (quando usada) e demais variáveis
   existentes; guardar credenciais apenas no backend. Aplicar migrações,
   proteção de acesso, logs seguros e backups. Não usar SQLite efêmero.
3. Adicionar `https://localhost` à lista `FRONTEND_ORIGINS` do FastAPI,
   restrita às origens legítimas da sua aplicação. O Capacitor Android usa
   essa origem WebView. **CORS não substitui autenticação.**
4. Confirmar que `https://api.seudominio.com/health` retorna um JSON com
   `status: "healthy"` e a raiz da API identifica `Mesa Quant Master`.

## Gerar APK pelo GitHub Actions (sem Android Studio)

1. Abrir **GitHub → Actions → APK Android - Mesa Quant Master → Run workflow**.
2. Na caixa `api_base_url`, inserir a URL HTTPS pública e real do seu
   backend, sem caminho, por exemplo `https://api.seudominio.com`.
   Alternativamente, configurar a variável de Actions
   `MESA_API_BASE_URL` (Settings → Secrets and variables → Actions → Variables).
3. A ação verifica o endpoint, compila o React com o endereço correto,
   gera o projeto Android e executa o Gradle.
4. Após o sucesso, na execução da ação abrir **Artifacts** e baixar
   `MesaQuantMaster-Android-debug`. O arquivo ZIP contém o
   `app-debug.apk`.
5. Transferir o APK ao Android e instalar permitindo, quando necessário,
   instalação por essa fonte. Depois de instalado, basta conexão com
   a internet para falar com o backend que está hospedado, sem PC ligado.

A versão gerada é um **APK debug de testes pessoais**, assinado com a chave
de depuração do ambiente CI. Não usar como publicação na Play Store e não
confundir com release de produção. Um aplicativo de produção precisa de chave
de assinatura própria, processo de atualização seguro e revisão da segurança
do armazenamento de sessão (JWT permanece temporariamente em
`sessionStorage` no frontend).

**Ações de pull request** geram apenas um teste de compilação do projeto
Android usando um domínio `.invalid`. Nenhum APK funcional é publicado
nesses testes. O workflow manual se recusa a produzir o APK sem API real
HTTPS e sem confirmar o endpoint.

## Desenvolver localmente (quando houver backend HTTPS)

```bash
cd frontend_web
npm ci
VITE_API_BASE_URL=https://api.seudominio.com npm run build
cd ../android_app
npm install
npx cap add android
npx cap sync android
npx cap open android
```

O comando `VITE_API_BASE_URL=...` mostrado é sintaxe de shell Unix; no
PowerShell configure `$env:VITE_API_BASE_URL = "https://api.seudominio.com"`
antes de `npm run build`. Configure sua API pública real. Utilize Android
Studio para compilar/testar nativamente ou o GitHub Actions para gerar o APK
sem ambiente Android local.

## Segurança e limitações

- Dados da carteira, cotações e tokens **não são armazenados no service
  worker**. A interface e os cálculos não são offline.
- A URL de API é pública por natureza e fica no bundle JavaScript. Nunca
  inclua nela senha, chave de mercado ou token.
- Para uso financeiro real: recomendamos servidor HTTPS estável, TLS válido,
  backups, chaves fortes, limitações de requisições, monitoring e evolução
  da autenticação de `sessionStorage` para armazenamento nativo seguro/
  credenciais de curta duração após auditoria.
- O visual responsivo da montagem de carteira é reaproveitado no Android.
  A qualidade do ranking depende dos indicadores efetivamente disponíveis
  e dos modelos financeiros já implementados, não do empacotamento APK.
