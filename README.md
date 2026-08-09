# techcaiu-bot — busca de ofertas Awin

Script que baixa o feed de produtos da Awin, filtra por desconto mínimo e
palavras-chave do nicho (tech), e salva o resultado em `output/ofertas.json`.

## Rodando localmente

```bash
# 1. instalar dependencias
pip install -r requirements.txt

# 2. configurar credenciais
cp .env.example .env
# edite o .env e preencha AWIN_TOKEN, AWIN_PUBLISHER_ID, AWIN_ADVERTISER_IDS

# 3. rodar
python buscar_ofertas.py
```

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
2. Pegue o Advertiser ID de cada uma aprovada (aparece na URL do programa)
3. Adicione no `.env`, separado por vírgula:
   ```
   AWIN_ADVERTISER_IDS=128601,999999,888888
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
   - `AWIN_TOKEN`
   - `AWIN_PUBLISHER_ID`
   - `AWIN_ADVERTISER_IDS`
4. Pronto — o workflow roda sozinho todo dia às 06h (horário de Brasília).
   Você também pode rodar manualmente em `Actions > Buscar ofertas Awin > Run workflow`
5. O resultado (`ofertas.json`) fica disponível pra download na aba `Actions`,
   dentro da execução, em "Artifacts"

### Próximo passo de automação

Esse `ofertas.json` gerado é o input pra próxima etapa do pipeline: geração
de copy (texto do post) via API do Claude, e depois agendamento do post via
Buffer/Zapier. Ainda não está incluso aqui — é o próximo módulo a construir.

## Limitações conhecidas

- O feed reflete o que a loja publica na Awin — nem toda loja atualiza com
  a mesma frequência.
- Sem `rrp_price` (preço "de"), o cálculo de desconto fica zerado — algumas
  lojas não preenchem esse campo no feed.
- Se `fid` (feed id) for diferente do Advertiser ID pra alguma loja, ajuste
  isso em `FEED_URL_TEMPLATE` — confirme no painel Awin em
  `Anunciante > Ferramentas > Feed de produtos`.
