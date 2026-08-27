# Como rodar e como o projeto é feito

Documentação técnica. Para o que a ferramenta é e por que existe, o README.
Para de onde vem cada dado, [docs/fontes.md](fontes.md).

## Tecnologia

A premissa é usar o mínimo possível — sem framework, sem etapa de build, sem
serviço gerenciado, sem banco na nuvem.

| Camada | O que é usado |
| --- | --- |
| Front-end | HTML, CSS e JavaScript puros. Zero dependências. |
| Back-end | Python 3.11+, só a biblioteca padrão (`http.server`). |
| Banco | SQLite em arquivo único. |
| Coletores | Python, biblioteca padrão. Playwright é **opcional**. |
| Instalação | Nenhuma para rodar o site. Sem `pip install`, sem `npm install`. |

O site e os importadores rodam com um Python 3.11 e nada mais. O Playwright só
é necessário para as fontes que exigem navegador, e o coletor detecta sozinho se
ele está presente.

## Rodando

```bash
# Uma base para começar — dados fictícios, para ver a ferramenta funcionando
python3 scripts/gerar_exemplo.py

# Sobe o site
python3 servidor.py          # http://localhost:8000
```

Com os dados reais do TSE:

```bash
python3 scripts/importar_tse.py --baixar --ano 2026
```

Baixa `consulta_cand_2026.zip` e `bem_candidato_2026.zip` do portal de dados
abertos, importa candidatos e bens e registra o SHA-256 de cada arquivo. Para
usar arquivos já baixados, aponte o script para eles:

```bash
python3 scripts/importar_tse.py dados/tse/consulta_cand_2026.zip dados/tse/bem_candidato_2026.zip
```

## Coleta

```bash
python3 scripts/coletar.py --listar                        # o que existe
python3 scripts/coletar.py --fonte tcu --cargo 6 --uf SP    # uma fonte
python3 scripts/coletar.py --pendencias --cargo 6 --uf SP   # lista de trabalho
python3 scripts/importar_externos.py dados/externo/         # carrega na base
```

Coletor nenhum escreve direto na base: todos produzem arquivo, e o arquivo
passa pelo importador, que registra origem, data e hash.

### Chaves de API

Nenhuma credencial fica no repositório. Os endereços estão em
`config/apis.json`; as chaves vêm do ambiente:

```bash
export CHAVE_PORTAL_TRANSPARENCIA="..."   # grátis, liberada no ato do cadastro
export CHAVE_DATAJUD="..."                # chave pública divulgada pelo CNJ
```

Sem a chave, o coletor correspondente avisa como obtê-la e devolve vazio — não
inventa valor.

### Proxy

Várias fontes recusam requisição vinda de IP de datacenter. Um proxy residencial
resolve, e vale para o HTTP e para o navegador:

```bash
export COLETOR_PROXY="http://usuario:senha@host:porta"
python3 scripts/coletar.py --verificar-saida    # confirma o IP de saída
```

Quando `COLETOR_PROXY` está definido, a variável `no_proxy` do ambiente é
ignorada de propósito: o `urllib` a consulta mesmo com proxy explícito e
devolveria a requisição direta em silêncio, o que faria a coleta sair pelo IP
errado sem nenhum aviso.

Usuário e senha são apagados de qualquer mensagem de erro antes de ela ser
impressa.

### Navegador (opcional)

Algumas páginas renderizam por JavaScript ou recusam requisição de IP de
datacenter. Para elas há um plano B:

```bash
pip install playwright && playwright install chromium
```

O coletor tenta HTTP primeiro e só abre o navegador se a resposta vier vazia ou
curta demais. Sem o Playwright instalado, segue só com HTTP.

Este plano B **não é usado em páginas com captcha**. Abrir um navegador não
resolve captcha moderno — que avalia fingerprint e comportamento, não imagem — e
contornar isso em massa em site do Judiciário não é o que este projeto faz.

## Identificação de candidatos

O TSE removeu o CPF das bases abertas. A identidade usada é a combinação
**ano + cargo + UF + unidade eleitoral + número na urna** — por exemplo,
`2026-6-SP-SP-1234`. A unidade eleitoral entra na chave porque em pleitos
municipais o mesmo número se repete em municípios diferentes da mesma UF.

Essa chave é o que liga um dado externo ao candidato, e está documentada em
[docs/automacao-externa.md](automacao-externa.md).

## Estrutura

```
servidor.py               HTTP + API de leitura (abre o SQLite somente-leitura)
banco.py                  esquema, migração de colunas, proveniência
web/                      HTML, CSS e JS servidos como estão
config/
  fontes.json             registro público das fontes
  colunas.json            colunas da planilha (criar coluna nova = editar aqui)
  apis.json               endereços das APIs oficiais
  votacoes.json           curadoria do indicador ideológico
  links.json              modelos de URL do TSE
scripts/
  importar_tse.py         base oficial de candidatos e bens
  importar_externos.py    porta única de entrada dos dados de fora
  gerar_exemplo.py        base fictícia para demonstração
  coletar.py              executa os coletores
  coletores/              um módulo por fonte
docs/                     esta documentação
automacao/                fluxo importável do n8n
```

## Migração de esquema

`banco.criar_esquema` compara as colunas declaradas no `ESQUEMA` com as que a
base tem e acrescenta por `ALTER TABLE` as que faltam, preservando o conteúdo.
Base antiga continua funcionando depois de um `git pull` — as colunas novas
entram vazias e se preenchem na próxima importação.

A ordem importa: tabelas, migração e só então índices. Um índice sobre coluna
nova falharia se fosse criado antes de a coluna existir.

## Versão estática

```bash
python3 scripts/gerar_estatico.py       # gera publicar/
cd publicar && python3 -m http.server 8000
```

Gera um JSON por recorte (ano + cargo + UF, mais o município em cargo
municipal), que é exatamente o filtro obrigatório do site. O navegador busca só
o recorte pedido e faz nome, partido, ordenação e paginação localmente.

O `web/app.js` é o mesmo nos dois modos e detecta qual está rodando: se
`api/saude` responde, é o servidor; senão, é estático.

Como publicar está em [docs/publicar.md](publicar.md).

## Contribuindo com uma coluna nova

Não precisa mexer em código: registre a fonte em `config/fontes.json` e a coluna
em `config/colunas.json`. Os detalhes, com exemplos, estão em
[docs/automacao-externa.md](automacao-externa.md).
