# market-filter — monitor de preços de feeds Awin

Baixa os feeds de produto da Awin diariamente, mantém um histórico de preços
e sinaliza quedas. Também gera um panorama do catálogo, para escolher nicho
olhando o inventário real.

## Como a detecção de oferta funciona

Os feeds Awin usados aqui **não publicam `rrp_price`** (o preço "de"). Foi
verificado: o campo vem vazio em 100% das linhas — não é dado mal preenchido,
a coluna não faz parte do que essas lojas publicam. Logo, não existe desconto
calculável olhando só a foto de hoje.

O sinal usado é **queda em relação ao maior preço já observado**. O workflow
roda todo dia e guarda os preços em `historico/precos.csv`; quando um produto
cai `QUEDA_MINIMA_PCT` abaixo do seu máximo histórico, vira oferta.

Duas consequências disso:

- **A primeira execução nunca gera ofertas.** Ela só cria o histórico. Isso é
  esperado, e o script diz isso explicitamente no log. Produto visto pela
  primeira vez hoje também não vira oferta — não há com o que comparar.
- O histórico é versionado no git de propósito — é a memória do projeto. Sem
  ele, cada execução começaria do zero.

O CSV não guarda nenhum campo do tipo "visto hoje". Se guardasse, as 11,5 mil
linhas seriam reescritas em toda execução e o commit diário viraria ruído.
Do jeito atual, **uma linha só muda quando o preço muda** — o diff do dia é
exatamente a lista de variações de preço.

Usar o máximo histórico como referência (em vez do preço de ontem) faz uma
promoção continuar aparecendo enquanto durar, em vez de sumir no dia seguinte
por "não ter mudado desde ontem".

## Página de filtros

**https://diegotesch.github.io/market-filter/**

Carrega o catálogo inteiro e filtra no navegador, sem servidor: busca por
nome (ignora acento), público (masculino/feminino/infantil), loja, marca,
faixa de preço, queda de preço e **somente lojas em que você é afiliado**.
Ordena por qualquer coluna, mostra miniatura do produto e exporta o resultado
filtrado em CSV.

### Filtro de afiliação

Vem do campo `Membership Status` da lista de feeds da Awin: só `active` conta
como afiliado. As lojas aceitas aparecem primeiro na lista, com selo, e o
painel mostra quantas são — se nenhuma estiver aceita, o filtro é desabilitado
com aviso, em vez de devolver uma lista vazia que pareceria bug.

Situação em 2026-08-09: **Lauri Esporte** (1.514 produtos, tênis esportivos) é
a única loja BR aceita. Há também a Aussui (GB, 64.740 produtos), fora da
região coletada.

Publicada pelo mesmo workflow da coleta, como segundo job — reaproveita os
feeds já baixados em vez de baixá-los de novo.

### Autenticação

Definindo o secret `SITE_SENHA`, o dataset é **cifrado** e a página pede a
senha antes de carregar qualquer coisa.

Por que cifrar em vez de fazer uma tela de login: o Pages serve arquivos
estáticos, sem servidor. Qualquer verificação de senha em JavaScript é
decorativa — o visitante lê o código-fonte, ou baixa `/dados.json` direto,
ignorando a tela. Cifrando, o que o servidor entrega é inútil sem a senha.

Como funciona:

- `dados.json` é comprimido com gzip e cifrado com **AES-256-GCM**
- a chave vem da senha via **PBKDF2-HMAC-SHA256, 600 mil iterações**
  (recomendação OWASP), derivada no navegador pela WebCrypto
- senha errada faz o GCM falhar na verificação de integridade — não há como
  decifrar parcialmente
- o JSON em claro é apagado, para não ser publicado junto
- a senha fica em `sessionStorage`, então recarregar a aba não pede de novo

A compressão vem **antes** da cifra de propósito: dado cifrado não comprime,
então o gzip do servidor não ajudaria. Sem isso, o download voltaria de
~190 KB para 1,3 MB.

Para configurar:

```bash
gh secret set SITE_SENHA --repo diegotesch/market-filter
```

Sem o secret, o site é publicado em claro (e o workflow avisa no log).

**Limites honestos desta proteção:**

- É uma senha só, compartilhada — não há usuários nem revogação individual.
  Trocar a senha exige rodar o workflow de novo.
- A força real depende da senha escolhida. Decifrar leva ~300 ms, o que
  também limita quem tentar força bruta, mas uma senha curta cai rápido. Use
  uma frase longa.
- Quem já baixou o `dados.bin` e tem a senha fica com aquela cópia para
  sempre. Trocar a senha protege só as publicações seguintes.
- `historico/precos.csv` e `output/panorama.md` **continuam versionados no
  repositório, que é público** — quem abrir o repo vê preços, lojas, marcas e
  exemplos de produto. Se o objetivo for privacidade real, o repositório
  precisa ser privado.

### Sobre o peso do dataset

São 11,5 mil produtos carregados de uma vez, e o arquivo final tem **579 KB**.
Três decisões seguram esse número:

- Loja e marca viram índices para listas separadas, em vez de repetir a
  string em cada produto.
- O link de afiliado não é armazenado. Todo link do feed segue o padrão
  `awin1.com/pclick.php?p=<produto>&a=<publisher>&m=<merchant>`, então a
  página remonta a URL a partir do id do produto e do merchant da loja.
  Economiza ~700 KB. Verificado que o link remontado redireciona para a página
  certa, com o parâmetro `awc=` de rastreamento intacto.
- O prefixo de URL de imagem mais comum de cada loja é guardado uma vez só, e
  cada produto guarda apenas o sufixo — corta o dataset de 3.355 KB para
  2.256 KB antes da compressão.

### Por que a miniatura usa o proxy da Awin

O feed traz duas URLs de imagem, e a escolha não é óbvia:

| | Tamanho da URL | Peso da imagem | Dataset final |
|---|---|---|---|
| `aw_image_url` (proxy Awin, 200×200) | ~278 chars | **5,9 KB** | 579 KB |
| `merchant_image_url` (CDN da loja) | ~134 chars | 84 KB | **272 KB** |

A URL da loja gera um dataset bem menor, mas serve a imagem em tamanho cheio.
Para 100 produtos na tela: **1,2 MB de tráfego total com o proxy contra
8,7 MB com a URL da loja**. O JSON maior se paga com folga.

Alguns CDNs têm variantes menores (`-thumb.jpg` na Yampi, por exemplo), mas
depender do padrão de nome de cada loja quebra silenciosamente quando uma
delas muda. O proxy funciona igual para todas.

Os ~230 KB do hash `k=` nas URLs do proxy são incompressíveis por natureza —
esse é o piso do arquivo.

O `dados.json` **não é commitado** — vai direto como artefato do Pages, para
não reescrever alguns MB no repositório todo dia.

## Rodando localmente

```bash
pip install -r requirements.txt
cp .env.example .env      # preencha AWIN_PRODUCTDATA_KEY
python listar_feeds.py    # confere o que a conta enxerga
python buscar_ofertas.py
```

Saídas:

| Arquivo | O que é |
|---|---|
| `historico/precos.csv` | memória de preços, um produto por linha (versionado) |
| `output/ofertas.json` | produtos que caíram de preço |
| `output/panorama.md` | visão do catálogo: lojas, faixas de preço, marcas |

## As duas credenciais da Awin

A pegadinha que custou as primeiras execuções. São chaves diferentes e não
intercambiáveis:

| Credencial | Onde pegar | Serve para |
|---|---|---|
| **Product Feed API key** | Toolbox > Create-a-Feed, na caixa "Feed List Download" | `productdata.awin.com` — é a que este projeto usa |
| Publisher API token | `ui.awin.com/awin-api` | `api.awin.com` (relatórios, transações) |

Usar o token da Publisher API no `productdata` retorna `500` na listagem e
`404` no download, sem mensagem que explique a causa.

## Feed ID != Advertiser ID

Segunda pegadinha. A URL de download usa `fid`, que é o **Feed ID** — número
diferente do Advertiser ID que aparece na URL do programa. Passar o Advertiser
ID retorna `404`.

`listar_feeds.py` mostra os dois lado a lado. Se `AWIN_FEED_IDS` ficar vazio,
o script descobre sozinho todos os feeds da região em `AWIN_REGIAO`.

## O catálogo brasileiro é pequeno

Levantamento de 2026-08-09: dos 582 feeds da conta, **10 são do Brasil**,
somando ~11,5 mil produtos, concentrados assim:

| Loja | Produtos | Segmento |
|---|---|---|
| Clovis Calçados | 8.198 | calçados |
| Lauri Esporte | 1.514 | tênis esportivos |
| Carraro | 456 | móveis |
| Alianças Imperiais | 451 | joias |
| Legale Lover | 361 | cursos de direito |
| Leveros | 250 | ar-condicionado |

**Não há loja de tech/eletrônicos com feed no Brasil.** No catálogo global
inteiro só existem 4 feeds com cara de tech, todos GB/US. Se o nicho pretendido
for tech nacional, a Awin não é a rede — o caminho seria outra rede
(Amazon Associates, Shopee, Magalu, Mercado Livre).

Vale notar também que `category_name` vem vazio em ~97% dos produtos: para
segmentar, **marca** funciona, categoria não.

## Configuração

Tudo por variável de ambiente, sem editar código — ver `.env.example`.

| Variável | Padrão | O que faz |
|---|---|---|
| `AWIN_PRODUCTDATA_KEY` | — | chave do Product Feed (obrigatória) |
| `AWIN_FEED_IDS` | vazio | feeds específicos; vazio = descobre pela região |
| `AWIN_REGIAO` | `BR` | região usada na descoberta automática |
| `QUEDA_MINIMA_PCT` | `10` | queda mínima para virar oferta |
| `PALAVRAS_CHAVE` | vazio | inclui por nome; vazio = não filtra |
| `PALAVRAS_EXCLUIR` | vazio | remove por nome; exclusão vence inclusão |
| `PRECO_MIN` / `PRECO_MAX` | `0` | faixa de preço; 0 = sem limite |

Os filtros valem **apenas para montar as ofertas**. O histórico sempre
acompanha o catálogo inteiro, de propósito: trocar de nicho depois não joga
fora os preços acumulados, que são o único ativo do projeto impossível de
reconstruir.

### Nicho masculino/esportivo

Recorte escolhido, com o que existe hoje no catálogo:

```
PALAVRAS_CHAVE=masculin
PALAVRAS_EXCLUIR=infantil,feminin,menino,bebê,bebe,juvenil
```

Isso dá **2.381 produtos**: 1.417 da Clovis Calçados e 962 da Lauri Esporte.
Preço mediano R$ 299,99 (p10 R$ 99,99, p90 R$ 1.199). Só `masculin` traria
470 itens infantis junto — daí a lista de exclusão.

Recorte só de tênis masculino: 1.953 produtos, mediana R$ 349,99, com On
Running, New Balance, Asics, Adidas, Nike, Skechers, Fila e Olympikus como
marcas mais frequentes.

## Automação no GitHub Actions

`Buscar ofertas Awin` roda todo dia às 06h (Brasília) e commita o histórico
atualizado. Precisa do secret `AWIN_PRODUCTDATA_KEY`.

`Listar feeds Awin` roda sob demanda e aceita a região como input — útil para
inspecionar o catálogo de outros países sem mexer em nada.

## Estrutura

| Arquivo | Responsabilidade |
|---|---|
| `awin.py` | cliente do Product Feed: lista e baixa feeds |
| `historico.py` | memória de preços entre execuções e cálculo de queda |
| `panorama.py` | relatório do catálogo em markdown |
| `exportar.py` | dataset compacto consumido pela página |
| `web/index.html` | página de filtros (estática, sem dependências) |
| `buscar_ofertas.py` | orquestra tudo |
| `listar_feeds.py` | diagnóstico: o que a conta enxerga |

## Próximo passo

Com nicho escolhido a partir do panorama, o `ofertas.json` vira input da
geração de copy (API do Claude) e do agendamento de post. Ainda não construído.

## Limitações conhecidas

- Todos os feeds aparecem como `Not Joined` e mesmo assim baixam. O
  `aw_deep_link` já vem com o publisher ID, mas **vale confirmar com a Awin se
  há comissão sem adesão formal ao programa** — é questão comercial, não
  técnica.
- O histórico só enxerga o que já observou: um produto que só cai de preço
  não tem "máximo" real, e a queda aparece subestimada.
- Produtos que somem do feed ficam parados no histórico com a última cotação.
