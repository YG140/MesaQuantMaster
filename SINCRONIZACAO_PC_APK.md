# Mesa Quant Master — usar o mesmo sistema no PC e no APK

## Objetivo

**Uma conta, uma carteira e um servidor.** O APK Android ja foi preparado para
chamar a API FastAPI pela internet, por HTTPS. O novo acesso *Sincronizado* no
Windows abre a mesma versao web hospedada na nuvem: ambas as interfaces fazem
login na mesma API e consultam a mesma base PostgreSQL na Neon.

```text
PC (navegador, modo Sincronizado) ---\
                                     -> site/React -> API HTTPS Render -> Neon PostgreSQL
APK Android (React/Capacitor) -------/
```

Nao se trata de sincronizacao entre dois bancos, nem de conexao direta com
PostgreSQL pelo APK. **Nao** coloque a URL/credenciais do banco no frontend.

## Como abrir no computador

- Novo atalho: duplo clique em `Abrir MesaQuantMaster Sincronizado.bat`.
  Ele abre `https://mesa-quant-master-web.onrender.com/`, endereco previsto
  na documentacao do deploy. **Confirme no painel Render que o site esta
  publicado nesse dominio**; a existencia desse dominio no codigo nao
  confirma que o deploy esteja online.
- Alternativa no PowerShell: `./start.ps1 -Cloud`.
- Se o dominio do site na Render for outro: `./start.ps1 -Cloud -CloudWebUrl "https://SEU-SITE-REAL.onrender.com/"`.
- O atalho anterior `Iniciar MesaQuantMaster.bat` **continua funcionando
  localmente**, com seu backend e seu banco antigos; esse modo local nao
  sincroniza automaticamente com o APK.

O modo sincronizado nao inicia servidor, PostgreSQL, npm ou Python locais.
Somente abre a pagina web segura do projeto na nuvem.

## Condicoes obrigatorias antes de tratar os dados como sincronizados

1. Na Render, verificar que o **site web** esta publicado e aponta para a
   **mesma API HTTPS** configurada no APK (`VITE_API_BASE_URL`). Se a
   configuracao mudar, refazer o deploy web e/ou recompilar o APK.
2. Na API, verificar a conexao a **Neon correta** (variavel privada
   `DATABASE_URL`), autenticacao JWT, endpoints `/health` e `/ready`.
3. **Recuperar a conta e a carteira antigas antes de comecar a operar na
   nuvem.** Primeiro identificar o banco local, produzir backup offline e
   uma previa da migracao sem escritas. Para PostgreSQL local, seguir
   `RECUPERAR_CONTA_LOCAL_NEON.md`; para SQLite, seguir
   `RECUPERAR_CARTEIRA_NEON.md`. Nao aplicar os dois metodos ao mesmo banco.
   Importadores sao conservadores e interrompem diante de conflitos.
4. Entrar no Windows (modo sincronizado) e no APK **com a mesma conta**.
5. Conferir no PC e no celular o mesmo numero de posicoes, saldos, operacoes,
   corretoras e perfil. So depois registrar uma operacao de teste (em
   ambiente adequado), verificar do outro lado e testar o caminho inverso.

## Importante: o que NAO acontece

- Abrir a nuvem **nao envia, funde nem substitui** automaticamente dados
  do PC. Se a conta antiga ainda esta so no computador, ela nao aparecera
  no APK ate concluir a migracao segura.
- Se o PC continuar usando o atalho **local**, alteracoes feitas nele
  ficarao no banco local — nao aparecerao no celular.
- Nao existe trabalho offline com reconciliacao posterior neste fluxo:
  cada aparelho precisa de internet e a API/banco remotos disponiveis.
- Nao apontar a API local para Neon sem revisar a conta, configuracoes,
  backups e concorrencia de escrita. O fluxo recomendado usa **uma unica
  API hospedada** para ambos os aparelhos.
- Nunca colocar senha do banco, .env, backups, tokens ou hashes no GitHub,
  APK ou mensagens. Guardar backup independente da Neon.

## Aceitacao funcional

- Mesmo usuario no PC e APK recebe a mesma carteira/historico.
- Operacao criada no PC fica visivel no APK apos nova consulta/atualizacao.
- Operacao criada no APK fica visivel no PC apos nova consulta/atualizacao.
- Nao aparece carteira de outro usuario.
- Modo local permanece intacto; nenhum dado legado e removido.
- Se a API ou a Neon estiver offline, exibir erro de conectividade, nunca
  fingir que a carteira foi sincronizada.

A sincronizacao aqui significa **persistencia centralizada** e consulta ao
mesmo servidor, nao atualizacao instantanea por WebSocket.
