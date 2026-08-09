# techcaiu-bot — busca de ofertas Awin

Script que baixa o feed de produtos da Awin, filtra por desconto mínimo e
palavras-chave do nicho (tech), e salva o resultado em `output/ofertas.json`.

## Rodando localmente

```bash
# 1. instalar dependencias
pip install -r requirements.txt

# 2. configurar credenciais
cp .env.example .env
# edite o .env e preencha AWIN_PRODUCTDATA_KEY e AWIN_PUBLISHER_ID

# 3. descobrir os Feed IDs da sua conta e preencher AWIN_FEED_IDS no .env
python listar_feeds.py

# 4. rodar
python buscar_ofertas.py
```

### As duas credenciais da Awin

A Awin tem dois tipos de chave, e elas não são intercambiáveis:

| Credencial | Onde pegar | Para que serve |
|---|---|---|
| **Product Feed API key** | Toolbox > Create-a-Feed, embutida no link "Download list" | `productdata.awin.com` — é a que este projeto usa |
| Publisher API token | `ui.awin.com/awin-api` | `api.awin.com` (relatórios, transações) |

Usar o token da Publisher API no `productdata` retorna `500` na listagem de
feeds e `404` no download — sem mensagem que explique a causa.

### Feed ID != Advertiser ID

Essa é a pegadinha principal da Awin. A URL de download do datafeed usa o
parâmetro `fid`, que é o **Feed ID** — um número diferente do Advertiser ID
que aparece na URL do programa. Passar o Advertiser ID ali retorna `404`.

`listar_feeds.py` resolve isso: ele consulta a API da Awin e imprime os dois
IDs lado a lado, junto com o nome da loja e o número de produtos no feed.

O resultado fica em `output/ofertas.json`, algo como:

```json
{
  "gerado_em": "2026-08-08T12:00:00+00:00",
  "total_ofertas": 5,
  "ofertas": [
    {
      "nome": "Fone Bluetooth XYZ",
      "loja": "Nome da Loja",
      "categoria": "Eletronicos",
      "preco": 89.9,
      "preco_original": 129.9,
      "desconto_pct": 30.8,
      "link_afiliado": "https://www.awin1.com/cread.php?...",
      "imagem": "https://..."
    }
  ]
}
```

## Ajustando o filtro

No topo de `buscar_ofertas.py`:

- `DESCONTO_MINIMO_PCT`: desconto mínimo pra entrar na lista (padrão 20%)
- `PALAVRAS_CHAVE`: lista de termos que o nome do produto precisa conter
- `MAX_OFERTAS_POR_LOJA`: quantas ofertas trazer por loja, no máximo

## Adicionando mais lojas

1. No painel Awin, vá em "Anunciantes" e adere a mais programas (lojas)
2. Rode `python listar_feeds.py` — as lojas aprovadas que publicam feed
   aparecem na lista com seus Feed IDs
3. Adicione no `.env`, separado por vírgula:
   ```
   AWIN_FEED_IDS=12345,67890
   ```

## Automatizando com GitHub Actions

Este repositório já vem com um workflow em
`.github/workflows/buscar-ofertas.yml` que roda o script todo dia
automaticamente e salva o resultado como artefato do GitHub.

Passos para ativar:

1. Suba este projeto para um repositório no GitHub (**não suba o `.env`** —
   o `.gitignore` já bloqueia isso)
2. No repositório, vá em `Settings > Secrets and variables > Actions`
3. Clique em "New repository secret" e crie 3 secrets:
   - `AWIN_PRODUCTDATA_KEY`
   - `AWIN_PUBLISHER_ID`
   - `AWIN_FEED_IDS`

   Existe também o workflow `Listar feeds Awin`, que roda sob demanda em
   `Actions` e imprime os Feed IDs disponíveis no log — útil pra preencher
   `AWIN_FEED_IDS` sem precisar configurar nada localmente.
4. Pronto — o workflow roda sozinho todo dia às 06h (horário de Brasília).
   Você também pode rodar manualmente em `Actions > Buscar ofertas Awin > Run workflow`
5. O resultado (`ofertas.json`) fica disponível pra download na aba `Actions`,
   dentro da execução, em "Artifacts"

### Próximo passo de automação

Esse `ofertas.json` gerado é o input pra próxima etapa do pipeline: geração
de copy (texto do post) via API do Claude, e depois agendamento do post via
Buffer/Zapier. Ainda não está incluso aqui — é o próximo módulo a construir.

## Diagnosticando "0 ofertas"

O script loga cada etapa pra você saber onde o funil zerou:

- `feed baixado: N linhas` — se não aparece, o download falhou (o erro vem
  logo abaixo, com o tipo da exceção). `404` = Feed ID errado.
- `diagnostico: X/N linhas tem rrp_price preenchido | ...` — mostra quantas
  linhas passam em cada filtro separadamente. Se `rrp_price` vem zerado na
  maioria, o desconto não é calculável e nada passa no corte.
- `output/amostra_<feed_id>.csv` — as 50 primeiras linhas do feed cru, pra
  inspecionar na mão. Vem junto no artefato do Actions.

Pra testar afrouxando o filtro sem editar código:

```bash
DESCONTO_MINIMO_PCT=0 PALAVRAS_CHAVE=usb python buscar_ofertas.py
```

## Limitações conhecidas

- O feed reflete o que a loja publica na Awin — nem toda loja atualiza com
  a mesma frequência.
- Sem `rrp_price` (preço "de"), o cálculo de desconto fica zerado — algumas
  lojas não preenchem esse campo no feed.
