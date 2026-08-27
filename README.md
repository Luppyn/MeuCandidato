# MeuCandidato

Ferramenta em formato de planilha para consultar e cruzar informações públicas
sobre candidaturas às eleições no Brasil. O usuário escolhe cargo, UF e ano, e
recebe uma linha por candidato com os dados reunidos das fontes oficiais e de
transparência.

Não é um perfil por página: é uma grade, feita para comparar candidatos lado a
lado dentro do mesmo recorte.

## Por que o código é aberto

A ferramenta trata de reputação de pessoas reais em disputa eleitoral. Uma
afirmação sobre um candidato só vale o quanto vale a possibilidade de conferi-la.
Por isso, três coisas ficam públicas e são parte do produto, não anexos dele:

1. **Todo o código**, front-end e back-end. O JavaScript que roda no navegador é
   o arquivo que está neste repositório — não há etapa de build que possa
   introduzir diferença entre o que se lê aqui e o que roda lá.
2. **A procedência de cada dado.** Toda importação registra arquivo, data,
   tamanho e SHA-256 do conteúdo. Baixando o mesmo arquivo na fonte original e
   recalculando o hash, dá para verificar que a base carregada é idêntica ao que
   a fonte publicou. O painel "Procedência dos dados", no próprio site, mostra
   esse registro.
3. **A metodologia dos indicadores.** O indicador ideológico depende de escolher
   quais votações contam e qual voto representa a posição de referência de cada
   tema. Essa escolha é editorial, e fica em [`config/votacoes.json`](config/votacoes.json)
   — versionada, legível, discutível.

O servidor abre o banco em modo somente leitura. Ele não tem como alterar dado
nenhum: toda escrita passa pelos scripts de importação, que deixam rastro.

## Tecnologia

A premissa é usar o mínimo possível — sem framework, sem etapa de build, sem
serviço gerenciado, sem banco na nuvem.

| Camada       | O que é usado                                              |
| ------------ | ---------------------------------------------------------- |
| Front-end    | HTML, CSS e JavaScript puros. Zero dependências.           |
| Back-end     | Python 3.11+, só a biblioteca padrão (`http.server`).      |
| Banco        | SQLite em arquivo único.                                   |
| Coletores    | Python, só a biblioteca padrão (`urllib`, `html.parser`).  |
| Instalação   | Nenhuma. Não há `pip install`, não há `npm install`.       |

O repositório inteiro roda com um Python 3.11 e nada mais.

## Como rodar

```bash
# 1. Uma base para começar — dados fictícios, para ver a ferramenta funcionando
python3 scripts/gerar_exemplo.py

# 2. Sobe o site
python3 servidor.py
#    -> http://localhost:8000
```

Para usar os dados reais do TSE no lugar da base de demonstração:

```bash
python3 scripts/importar_tse.py --baixar --ano 2026
```

Isso baixa `consulta_cand_2026.zip` e `bem_candidato_2026.zip` do portal de dados
abertos, importa candidatos e bens declarados e registra o hash de cada arquivo.
Se preferir baixar à mão, aponte o script para os arquivos:

```bash
python3 scripts/importar_tse.py dados/tse/consulta_cand_2026.zip dados/tse/bem_candidato_2026.zip
```

## O que a planilha mostra

**Direto do TSE** (itens 1 a 3 do escopo), disponível assim que a base é
importada: nome, número, partido, coligação, cargo, situação do registro, gênero,
data de nascimento, estado civil, cor/raça, ocupação declarada, grau de instrução
e o patrimônio declarado — total, quantidade e a lista item a item de bens no
painel expandido de cada linha.

**De fontes sem API** (itens 4 a 8): condenações e processos, indicadores
ideológicos, checagens e notícias. Essas colunas chegam por importação externa.
Enquanto não houver dado importado, a célula mostra "sem dado" com o link direto
para a consulta manual naquela fonte, já montado com o nome do candidato.

As colunas mais pesadas ficam fora da grade principal e aparecem no painel
expandido da linha, ou ao marcar "Mostrar todas as colunas".

### Identificação de candidatos

O TSE removeu o CPF das bases abertas, o que dificulta separar homônimos. A
identidade usada aqui é a combinação **ano + cargo + UF + unidade eleitoral +
número na urna** — por exemplo, `2026-6-SP-SP-1234`. A unidade eleitoral entra na
chave porque em pleitos municipais o mesmo número se repete em municípios
diferentes da mesma UF.

Essa chave é o que liga um dado externo ao candidato. Está documentada em
[docs/automacao-externa.md](docs/automacao-externa.md).

## Coleta das fontes sem API

Nenhuma das fontes dos itens 4 a 8 publica API. O repositório traz coletores para
elas em [`scripts/coletores/`](scripts/coletores/), e eles se dividem em três
situações honestas:

| Situação | Fontes | O que acontece |
| --- | --- | --- |
| **Tem API oficial** | Câmara e Senado (dados abertos) | Coleta direto da fonte primária, sem raspagem. |
| **Dá para raspar** | Excelências, ComoVotou, Atlas Político, Parlamentômetro, Placar Congresso, checagens, notícias | Coletor lê a página pública. Como não há contrato de API, o formato pode mudar sem aviso — quando nada bate, o coletor devolve vazio em vez de chutar. |
| **Não dá para automatizar** | CNIA, BNMP, tribunais estaduais | Captcha ou sessão por consulta. Os coletores **não raspam nada**: geram a lista de trabalho com os links prontos, para conferência e preenchimento. |

```bash
python3 scripts/coletar.py --listar                          # o que existe
python3 scripts/coletar.py --fonte congresso --cargo 6 --uf SP
python3 scripts/coletar.py --pendencias --cargo 6 --uf SP    # lista de trabalho
python3 scripts/importar_externos.py dados/externo/          # carrega na base
```

Os coletores nunca escrevem direto na base. Eles produzem um arquivo, e o
arquivo passa pelo importador — que registra origem, data e hash. É o mesmo
caminho que um arquivo vindo de um fluxo do n8n ou de uma planilha preenchida à
mão. Uma porta de entrada só, com rastro.

Para agendar a coleta sem manter nenhum serviço rodando, há um workflow do
GitHub Actions pronto em
[`.github/workflows/coleta-externa.yml`](.github/workflows/coleta-externa.yml).
Para quem prefere n8n, há um fluxo importável em
[`automacao/n8n-coleta-externa.json`](automacao/n8n-coleta-externa.json). Os dois
caminhos estão comparados em [docs/hospedagem.md](docs/hospedagem.md).

## Documentação

- [docs/fontes.md](docs/fontes.md) — de onde vem cada coluna, o que a fonte
  garante e o que ela não garante.
- [docs/automacao-externa.md](docs/automacao-externa.md) — o formato de entrada
  dos dados externos, com exemplos.
- [docs/hospedagem.md](docs/hospedagem.md) — como publicar o site e onde rodar a
  automação de coleta.

## Limitações

São limites das fontes, não do código, e nenhum deles tem solução técnica dentro
deste projeto:

- **Homônimos.** Sem CPF nas bases abertas, cruzar candidato com fonte externa
  depende do nome. O casamento de nomes aqui é deliberadamente conservador:
  prefere deixar a célula vazia com o link de conferência a atribuir a alguém um
  processo que não é dele.
- **Patrimônio.** Não existe fonte pública que cruze o patrimônio declarado com
  dados da Receita Federal — é sigilo fiscal. A comparação viável é entre
  declarações do próprio candidato ao TSE ao longo do tempo.
- **Antecedentes.** Não há API nacional unificada. A consulta é tribunal a
  tribunal, e cada um tem suas próprias regras de acesso.
- **Indicador ideológico.** Só é objetivamente calculável para quem já votou no
  Congresso. Para quem nunca exerceu mandato, não existe equivalente — a coluna
  fica vazia, e isso é a resposta correta, não uma falha.
- **Escolaridade.** É autodeclarada no pedido de registro, não um diploma
  verificado. O comprovante fica anexado ao processo de registro e pode ser
  conferido na Consulta Pública Unificada do TSE.
- **Cargos municipais.** 2026 é eleição geral: presidente, governador, senador e
  deputados. Prefeito e vereador não são disputados neste ano — eles aparecem no
  código porque a estrutura é a mesma e serve para importar 2024 ou 2028 sem
  mudança nenhuma.
