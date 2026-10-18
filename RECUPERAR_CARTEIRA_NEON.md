# Recuperar a conta e a carteira antigas do computador para Neon (sem apagar dados)

**Não crie uma conta nova, não redefina a senha no banco via SQL, não importe
posições manualmente sobre um banco que já contenha operações.** A Neon
está vazia nesta instalação; precisamos recuperar o banco correto do PC.

A recuperação preserva IDs, e-mail, **hash da senha original**, operações,
quantidades, preços, taxas, corretoras, watchlists, indicadores, políticas,
perfil e outros registros estruturados compatíveis. Não transfere o
`SECRET_KEY` local, sessões JWT ou arquivos de cache; nova autenticação
após a migração é esperada.

## Antes de começar: é SQLite ou outro banco?

O `backend/.env.example` usa SQLite no desenvolvimento
(`DATABASE_URL=sqlite:///./mesa_quant_master.db`). O SQLite real pode
estar tanto na raiz quanto na pasta `backend`, dependendo do diretório
em que o servidor antigo foi iniciado. **Nunca deduzir o arquivo a partir
do nome apenas**: o script `--inspect` permite conferir contagens,
sem revelar nomes, e-mails ou senhas.

Caso o computador use MySQL ou PostgreSQL local, **não executar este
script**: será preciso outro plano de cópia compatível. Não alterar
o `DATABASE_URL` do programa antigo para apontar para a Neon.

## 1. Localizar e preservar o banco antigo no Windows

No VS Code, abrir o terminal PowerShell em `C:\Dev\MesaQuantMaster`
(ou no diretório onde o repositório estiver salvo):

```powershell
cd C:\Dev\MesaQuantMaster
Get-ChildItem -Path . -Recurse -File |
  Where-Object { $_.Extension -in '.db','.sqlite','.sqlite3' } |
  Select-Object FullName,Length,LastWriteTime
```

Se não aparecer banco, conferir a configuração local `DATABASE_URL`
em `backend/.env` **sem copiá-la ao chat ou ao GitHub**. Banco remoto
MySQL/PostgreSQL exige um procedimento diferente.

Antes de atualizar código, realizar uma cópia de segurança do arquivo de
dados **em outra pasta** ou mídia privada. Não enviar `.env`, `.db`,
`*.sqlite` nem `*.sqlite3` ao GitHub, chat ou site público.

Atualizar código sem sobrescrever mudanças locais:

```powershell
git status --short
git fetch origin main
git pull --ff-only origin main
python -m pip install -r backend\requirements.txt
```

Se o `git pull` avisar conflitos ou alterações locais, **parar**.
Não usar `git reset --hard`.

## 2. Identificar qual arquivo guarda a conta

Substituir o caminho pelo arquivo SQLite real; por exemplo, se o
arquivo tiver sido encontrado em `backend`:

```powershell
python backend\scripts\migrate_local_sqlite_to_neon.py --source "C:\Dev\MesaQuantMaster\backend\mesa_quant_master.db" --inspect
```

A saída exibe só contagens por tabela. Exigimos ao menos um registro em
`users`. Se `users=0`, esse não é o banco da sua conta antiga; examine
outro arquivo sem apagar nada. Se sua carteira possuía investimentos,
normalmente deverão existir registros em `operations`, `assets` e/ou
`brokerages`. Confirme com a carteira antiga antes de importar.

## 3. Preparar conexão HTTPS/TLS Neon no computador

Entrar em <https://console.neon.tech/> → projeto `mesa-quant-master`
→ **Connect / Banco de dados Postgres**, usar **Direct connection**,
com `sslmode=require`. A URL contém a senha do banco: nunca mostre no
chat, print, GitHub ou APK.

No terminal PowerShell do PC, armazenar temporariamente a URL somente
na variável de ambiente do processo:

```powershell
$senhaTemporaria = Read-Host "Cole a string PostgreSQL da Neon" -AsSecureString
$ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($senhaTemporaria)
try {
  $env:MESA_NEON_DATABASE_URL = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)
} finally {
  [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)
}
Remove-Variable senhaTemporaria
```

**Não use** `DATABASE_URL` na etapa de recuperação (o sistema local
pode usá-la). A ferramenta usa exclusivamente `MESA_NEON_DATABASE_URL`
para o destino, nunca a API web da Neon.

## 4. Prévia obrigatória — não grava nada

```powershell
python backend\scripts\migrate_local_sqlite_to_neon.py --source "C:\Dev\MesaQuantMaster\backend\mesa_quant_master.db"
```

Troque o caminho de exemplo. Verifique as contagens de usuários, ativos,
operações etc. A ferramenta exige a Neon sem dados em tabelas da aplicação,
um esquema compatível e conexão Neon TLS. Se detectar divergência de
campos ou qualquer registro preexistente na Neon, **interrompe**:
não mistura carteiras nem descarta tabelas desconhecidas.

## 5. Aplicação — com backup automático e transação única

Feche o backend local para evitar novas operações no arquivo durante a
transferência. Somente se a prévia estiver correta, execute:

```powershell
python backend\scripts\migrate_local_sqlite_to_neon.py --source "C:\Dev\MesaQuantMaster\backend\mesa_quant_master.db" --apply
```

O script cria um **backup íntegro do SQLite no computador**, exibe o
caminho e o SHA-256, e solicita que você digite `MIGRAR`. Sem isso,
nenhuma escrita será feita no PostgreSQL.

Os registros são copiados em uma **única transação** com contagens
comparadas; se falhar, a Neon desfaz a transferência e os arquivos
locais não são alterados. O programa não executa `DELETE`,
`DROP`, `TRUNCATE` nem substitui dados existentes.

Depois de recuperar, abra o site:
<https://mesa-quant-master-web.onrender.com> ou o APK e faça login com o
e-mail e a senha **antigos**. Senhas continuam protegidas como hashes.
Se o e-mail aparecer como não verificado, será preciso habilitar um
serviço seguro de verificação por e-mail para concluir a ativação;
**não** alterar `is_email_verified` manualmente.

Valide quantidade de posições, total investido e histórico de compras
antes de confiar nos relatórios financeiros.

## Alertas

- **Não compartilhar** senhas, a connection string, hashes, arquivos
  `.db` ou backups nesta conversa.
- Não transferir credenciais `SECRET_KEY` e arquivos `.env`.
- Registros existentes na Neon bloqueiam a importação; peça uma estratégia
  de reconciliação segura, em vez de apagar tabelas.
- O script contempla origem **SQLite**. Para MySQL ou PostgreSQL local
  precisamos inspecionar o formato e criar caminho correspondente.
- O upload apenas de posições pelo app **não** preserva operações
  históricas ou credenciais antigas.
- O PostgreSQL Neon Free deve receber **backup remoto independente**
  posteriormente; o backup do SQLite serve para recuperação inicial.
