# Mesa Quant Master no celular (Android/iPhone)

O frontend React é responsivo e possui manifesto de aplicativo web. **Não é
um APK nem publica automaticamente o sistema na internet**. A interface,
autenticação, carteira e cálculos continuam dependendo de um backend acessível.

## Testar pela mesma rede Wi-Fi (desenvolvimento)

1. Instale as dependências no computador conforme os READMEs, sem publicar
   senhas/chaves de mercado no frontend.
2. Descubra o IPv4 do computador na rede local (no Windows, `ipconfig`).
   Exemplo abaixo: `192.168.1.20` **substitua pelo IP real**.
3. No arquivo local `backend/.env`, mantenha suas credenciais atuais e
   adicione/ajuste somente a lista de origens permitidas, por exemplo:
   `FRONTEND_ORIGINS=["http://localhost:5173","http://127.0.0.1:5173","http://192.168.1.20:5173"]`.
   Também é possível configurar no ambiente de execução. Não use um `*`
   indiscriminado para liberar qualquer origem.
4. Inicie o backend no computador, em um terminal:
   ```powershell
   cd backend
   python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
   ```
5. Na pasta `frontend_web`, deixe `VITE_API_BASE_URL` vazio ou não definido
   no arquivo `.env`. Uma URL explícita `http://127.0.0.1:8000` não funciona
   para outros aparelhos. Em outro terminal:
   ```powershell
   cd frontend_web
   npm ci
   npm run dev:mobile
   ```
6. Com o celular **na mesma rede Wi-Fi**, abra
   `http://192.168.1.20:5173` (substituindo pelo IP real). A interface
   chamará automaticamente a API no mesmo host, porta 8000.

O firewall do Windows precisa permitir as portas 5173 e 8000 apenas na rede
privada em uso. Não encaminhe essas portas no roteador para a internet. No
ambiente de desenvolvimento, HTTP em Wi-Fi não é adequado a credenciais reais
ou dados sensíveis; utilize preferencialmente uma implantação HTTPS segura.

## Ícone na tela inicial e instalação como web app

A aplicação fornece manifesto, ícone e service worker **sem cache offline**:
informações financeiras e dados de sessão nunca são guardados no service worker.
Em uma implantação HTTPS:
- Android/Chrome: menu `⋮` > `Instalar app` (se disponível) ou
  `Adicionar à tela inicial`.
- iPhone/Safari: `Compartilhar` > `Adicionar à Tela de Início`.

Em HTTP na rede local, o navegador pode oferecer somente um atalho. Isso é
esperado: a instalação completa e vários recursos exigem HTTPS.

## Produção segura

Disponibilize o frontend em HTTPS e faça proxy reverso para o FastAPI sob o
mesmo domínio, ou configure `VITE_API_BASE_URL` para a URL **HTTPS** da API
com CORS restrito à origem real. Não deixe uma URL localhost no bundle.
Use autenticação forte, não exponha segredos e considere migrar o JWT do
`sessionStorage` para cookie HttpOnly antes do lançamento público.

Se o backend não estiver publicado/acessível, o celular verá a interface mas
não terá login, cotações, montagem de carteira nem persistência de operações.
Isso não deve ser apresentado como funcionalidade offline.
