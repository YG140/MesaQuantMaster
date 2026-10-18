# Recuperar conta antiga e carteira no APK (PostgreSQL local → Neon)

**Importante:** GitHub guarda o código, não os usuários, hashes de senha
ou compras e vendas do computador. O PostgreSQL local ainda precisa existir
(ou será necessário recuperar o backup). A Neon começou com 0 usuários.

O procedimento restaura **somente a conta que você escolher** e os ativos
que pertencem à sua carteira. Não transfere outras contas. Não coloca seus
dados financeiros ou senhas no GitHub/ChatGPT.

A configuração anterior conhecida era PostgreSQL local
**mesa_quant_master_v2**, usuário **mesa_quant_app**, em
**127.0.0.1:5432**. Confirme que continua sendo esse banco.
Arquivos antigos SQLite como database/carteira.db também devem ser
preservados. O importador abaixo aceita PostgreSQL local; não SQLite.

## 1. Faça o backup no PC primeiro

Feche o backend e o frontend do programa para impedir novas gravações.
Abra **PowerShell** e execute:

~~~powershell
& "C:\Program Files\PostgreSQL\17\bin\pg_dump.exe" --host 127.0.0.1 --port 5432 --username mesa_quant_app --dbname mesa_quant_master_v2 --format=custom --file "$env:USERPROFILE\Documents\mesa-quant-local-backup.dump"
~~~

Pode solicitar senha de PostgreSQL, que deve ser informada **somente no
computador**, nunca aqui. Se PostgreSQL estiver instalado em outro
diretório, localize pg_dump.exe. Se o comando falhar, pare. Confira o
arquivo na pasta Documentos e guarde outra cópia offline/criptografada.
Não envie o dump ao GitHub nem pelo chat.

## 2. Atualize os arquivos do projeto

No PowerShell:

~~~powershell
cd C:\Dev\MesaQuantMaster
git status
git pull --ff-only origin main
~~~

Se git pull avisar que existem alterações locais, **não** use git reset,
git clean ou apague arquivos. Peça ajuda para preservar seu trabalho.

O importador estará em
backend/scripts/migrate_local_account_to_neon.py. Ele lê o DATABASE_URL
do seu arquivo privado backend/.env para a **origem local**.
Se você tiver outra configuração, ajuste SOURCE_DATABASE_URL em variável
de ambiente local, sem colocar senha no chat.

## 3. Coloque o URL da Neon somente no PowerShell local

No painel Neon → Connect → Postgres, desative Connection pooling e copie
a **string PostgreSQL direta**, contendo sslmode=require.
Não use o URL da aba de API de dados.

Cole a conexão através do prompt seguro:

~~~powershell
$segredo = Read-Host "Cole a string PostgreSQL direta da Neon" -AsSecureString
$env:NEON_DATABASE_URL = [System.Net.NetworkCredential]::new("", $segredo).Password
Remove-Variable segredo
~~~

Isso não grava a senha em código, histórico de comandos ou GitHub.
Uma string Neon válida começa com postgresql:// e aponta para
um hostname terminado em .neon.tech.

## 4. Prévia sem modificar o banco

~~~powershell
python backend\scripts\migrate_local_account_to_neon.py
~~~

Digite o **e-mail antigo de login** quando o computador pedir.
Nenhum e-mail, hash ou segredo é enviado ao ChatGPT. O programa
apenas apresentará os totais por tabela para a conta escolhida.

Verifique sobretudo:
- users: exatamente 1;
- operations: compras e vendas antigas;
- assets: ativos da sua carteira;
- brokerages, watchlists, alerts: corretoras, favoritos e alertas;
- portfolio_policies, portfolio_policy_allocations, investor_profiles;
- manual_indicators e portfolio_action_audits.

A prévia não realiza nenhuma escrita na Neon. O importador recusa
conta inexistente, origem que não seja local, destino que não seja
Neon TLS, dados conflitantes no destino ou tabelas incompatíveis.

Você pode me enviar **somente o resultado com as quantidades**,
nunca e-mail, hash, senha nem strings de conexão.

## 5. Importar apenas após revisar o backup e a prévia

~~~powershell
python backend\scripts\migrate_local_account_to_neon.py --apply
~~~

Digite novamente seu e-mail e confirme com a palavra MIGRAR. A
importação preserva IDs, hash da senha original, operações, quantidades,
preços de compra, taxas, corretoras, perfil de investidor e política
da carteira; o destino é modificado em uma **única transação**.
Se houver erro, as escritas da tentativa são revertidas.
Não mescla ou sobrescreve uma Neon que já tenha dados.

**Senhas:** o hash original é preservado, não há senhas legíveis para
copiar. O login exige que o algoritmo antigo seja compatível.
Contas que já tinham e-mail não confirmado continuam nessa condição.
Se a versão local antecede a verificação por e-mail, o importador usa
a mesma compatibilidade das migrações anteriores que consideravam
esses usuários antigos confirmados.

## 6. Conferir e remover segredo temporário

~~~powershell
Remove-Item Env:\NEON_DATABASE_URL
Remove-Item Env:\SOURCE_DATABASE_URL -ErrorAction SilentlyContinue
~~~

Entre no APK com o e-mail e senha anteriores e confira **quantidade
de ativos, operações, histórico, perfil e corretoras**. Não faça novas
operações antes dessa conferência. Preserve o banco local e o backup.

Apenas para confirmar quantidade de contas (Neon SQL Editor):

~~~sql
SELECT COUNT(*) AS usuarios,
       COUNT(*) FILTER (WHERE is_email_verified) AS confirmados
FROM users;
~~~

Tokens antigos de recuperação não são transferidos; caches de dados
públicos (indicadores e documentos CVM etc.) são reobtidos via
provedores. Carteira, histórico pessoal e informações vinculadas à
conta serão preservados.

Se o banco local não existir mais, procure primeiro backups .dump,
.backup e antigos bancos SQLite. Não crie um banco vazio sobre o antigo.
