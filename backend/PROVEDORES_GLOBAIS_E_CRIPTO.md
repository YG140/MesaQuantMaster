# Provedores externos — CoinGecko e Twelve Data

O Mesa Quant Master agora inclui **conectores opcionais, exclusivamente no backend**
para cotações e histórico de criptomoedas e ações/ETFs internacionais. Eles
integram a **análise de ativos e montagem de carteiras**. Os endpoints
genéricos de mercado `/market/quote` ainda atendem ao provider BRAPI; não
apresentam automaticamente a nova origem externa.

## 1. Conseguir e guardar as chaves

1. Gerar uma **CoinGecko Demo API key** no painel CoinGecko (documentação
   oficial: https://support.coingecko.com/articles/9471335603-user-guide-how-to-sign-up-for-coingecko-demo-api-and-generate-an-api-key).
2. Gerar uma **Twelve Data API key** no painel Twelve Data
   (documentação: https://twelvedata.com/docs). O endpoint `/quote`
   atende cotação; `/time_series` atende históricos diários. A cobertura
   e os créditos disponíveis dependem do plano contratado.
3. No arquivo privado `backend/.env` da máquina/servidor, adicionar:
   ```env
   COINGECKO_DEMO_API_KEY=SUA_CHAVE_COINGECKO
   TWELVEDATA_API_KEY=SUA_CHAVE_TWELVEDATA
   ```
4. Reiniciar o backend. **Não enviar o .env ao GitHub.** Não colocar
   as chaves no React, no APK, em parâmetros de página, logs ou mensagens.

As chaves não são fornecidas por este repositório. Sem chave, a análise
externa avisa que está indisponível — não recorre a tickers similares da B3.

## 2. Cadastrar os ativos

O roteamento depende dos **campos persistidos do ativo**, não do formato
visual do ticker nem da preferência do usuário. Confirme `asset_type`
e `exchange` antes de analisar:

| Exemplo | `asset_type` | `ticker` | `exchange` |
|---|---|---|---|
| Bitcoin | `crypto` | `BTC` | `COINGECKO:bitcoin` (ou vazio: mapeamento fixo) |
| Ethereum | `crypto` | `ETH` | `COINGECKO:ethereum` (ou vazio: mapeamento fixo) |
| Outro token | `crypto` | Símbolo válido | **Obrigatório** `COINGECKO:<id>` |
| Microsoft | `international` | `MSFT` | `NASDAQ` |
| ETF exterior | `global_etf` | `QQQ` | `NASDAQ` |
| BDR na B3 | `bdr` | `AAPL34` | `B3` (mantém BRAPI, não usar Twelve Data diretamente) |

Para criptomoedas cujo símbolo é compartilhado entre múltiplos projetos,
é obrigatório indicar o CoinGecko ID correto no `exchange`. Os IDs fixos
conhecidos com exchange vazio são BTC, ETH, SOL, ADA e XRP. Sempre confira
ID, ticker e rede/contrato por conta própria antes de cadastrar um token.

Se o ativo tem `asset_type=stock` ou `etf` doméstico, ele continua na
BRAPI/B3. Uma ação estrangeira cadastrada como ação nacional **não será
automaticamente reinterpretada**; corrija o cadastro para evitar confusão.

## 3. Dados obtidos e critérios

### CoinGecko Demo
- `GET /coins/markets`: preço em **USD**, capitalização em USD, volume
  financeiro 24h em USD, timestamp do provedor e identidade pelo coin ID.
- `GET /coins/{id}/market_chart?vs_currency=usd&days=90`: histórico de
  preços; condensado por **dia UTC** (última observação do dia).
- Calcula volatilidade histórica anualizada a partir de retornos diários,
  queda máxima na janela e giro financeiro 24h / capitalização.
- Volume unitário mostrado na interface é **aproximação** de
  `volume financeiro USD / preço USD`. Não confundir com profundidade
  de livro ou quantidade exata executada em corretora.

### Twelve Data
- `GET /quote`: preço de fechamento, moeda e timestamp.
- `GET /time_series?interval=1day&outputsize=120`: fechamentos históricos
  e metadados de ticker, classe de instrumento, moeda e bolsa.
- Exige que cotação e série coincidam em ticker e moeda; a série também
  confirma `Common Stock`/`ETF`. Sem metadados suficientes, não usa
  cotação que poderia pertencer a outro tipo de instrumento.
- Calcula volatilidade histórica anualizada e queda máxima na janela.
- **Não** inventa balanços, preços justos, LPA, ROE nem demais índices
  fundamentalistas. Essas categorias continuam indisponíveis até chegarem
  de uma fonte fundamentada/licenciada.

### Restrições e segurança
- No mínimo **61 observações em datas distintas** para estimar volatilidade
  e drawdown. Cotação vencida, respostas inválidas, planos sem acesso,
  divergência de ticker/moeda ou falta de histórico impedem uso dos dados
  correspondentes.
- A chave nunca é enviada ao frontend. URL do provedor é fixa; IDs e
  tickers recebem validação sintática; HTTP timeout e cache de 5 minutos.
- Taxa/limite de créditos do plano podem impedir análise simultânea de
  muitos ativos; reduzir universo e aumentar cache persistente é uma
  evolução necessária para instalações com uso intenso.
- **O sistema não converte USD em BRL**. Posições externas não entram
  na avaliação de mercado da carteira em BRL sem câmbio validado; o
  custo de aquisição permanece visível como aproximação, não cotação.
- A análise de cripto é informativa; recomendações automáticas de compra
  seguem bloqueadas por risco/precificação e política do investidor.
- O aplicativo Android ainda exige backend remoto HTTPS ativo.

## 4. Testes
```bash
cd backend
python -m pytest -q ../tests/unit/test_external_market_data_service.py
```

Os testes com `httpx.MockTransport` não chamam as APIs reais e validam a
interpretação dos contratos. Testes fim a fim **com chaves reais e quotas**
precisam ser feitos na implantação, com licença e limites observados.
