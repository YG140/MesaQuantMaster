# Dependencias Python, JWT e interface legada - outubro de 2026

## Escopo da proposta

A instalacao principal **FastAPI + React** foi isolada da interface Streamlit
legada em `frontend/`. O Streamlit 1.66.0 exige `Pillow < 13` e, por isso,
nao pode coexistir no mesmo resolvedor com `Pillow == 13.0.0`, que corrige
vulnerabilidades. Este PR nao instala nem tenta forcar versões incompatíveis.
Os arquivos da interface Streamlit antiga permanecem no repositorio, mas
o seu ambiente deve ser tratado **separadamente** e nao faz parte do
caminho de implantacao atual. Nao instalar uma versao vulneravel do Pillow
para colocar o legado no mesmo ambiente de producao.

As duas listas (`pyproject.toml` e `backend/requirements.txt`) agora usam
FastAPI 0.149.0, PyJWT 2.15.1, python-dotenv 1.2.4 e OpenAI 3.1.0.
`pyproject.toml` tambem usa GitPython 3.2.1, Pillow 13.0.0 e Black 26.10.1.

## Compatibilidade da autenticacao

A codificacao e validacao JWT usa **PyJWT** com o algoritmo explicitamente
configurado (normalmente HS256). Permanecem os claims `sub`, `email`,
`ver` e `exp`; a chave secreta nao e modificada por esta alteracao.
Testes exercitam um JWT HS256 gerado pelo formato anterior e tokens
adulterados e expirados. **Nenhum script desta mudanca altera senhas,
e-mails ou conteudos das tabelas.**

O ambiente de implantacao deve continuar com o segredo existente.
Nao regenerar `SECRET_KEY` como parte de uma atualizacao, pois isso
revogaria tokens antigos.

## Checagens antes de atualizar o PC ou a nuvem

1. Fazer backup de banco, `backend/.env` e demais dados fora do Git,
   alem da copia de codigo ja criada.
2. Esperar os workflows CI passarem e revisar os diffs de cada PR.
3. No Windows, ativar a venv e consultar as dependencias antes de instalar
   versoes novas; nao usar comandos que apaguem dados ou migrem banco.
4. Validar login, token anterior, renovacao, `/users/me`, carteira e
   recuperacao de e-mail em ambiente de teste sem escrita em producao.
5. Verificar a sincronizacao com Neon e Android separadamente. **Este PR
   nao comprova a recuperacao da carteira ou o acesso real ao Neon.**

## Referencias

- Streamlit 1.66.0: dependencia de Pillow < 13
- PYSEC-2026-4298: vulnerabilidade python-jose ate 3.5.0
- PYSEC-2026-1325: vulnerabilidade ecdsa transitiva do python-jose
- CVE-2026-114134: versoes antigas do Black, corrigido com 26.10.1
