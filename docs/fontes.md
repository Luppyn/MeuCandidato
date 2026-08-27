# Fontes de dados

De onde vem cada coluna da planilha, o que a fonte garante e o que ela não
garante. O mesmo conteúdo, em forma resumida, está no painel "Fontes" do site.

O registro que o código lê é `config/fontes.json`.

---

## 1. Dados cadastrais e situação eleitoral

**TSE — DivulgaCandContas e Portal de Dados Abertos**
`https://divulgacandcontas.tse.jus.br/divulga/#/`
`https://dadosabertos.tse.jus.br/dataset/candidatos-2026`

Nome, número, partido, coligação e composição, cargo, situação do registro,
gênero, data de nascimento, estado civil, cor/raça, ocupação declarada,
naturalidade, reeleição, limite de gasto declarado.

A base do site é o arquivo `consulta_cand_2026.zip` do portal de dados abertos —
não a raspagem do DivulgaCandContas. É a mesma informação, publicada pelo próprio
TSE em formato aberto, e permite conferir o hash. Cada linha da planilha traz o
link para o registro correspondente no DivulgaCandContas.

**O que é declaração, não verificação:** ocupação, estado civil e cor/raça são
autodeclarados no pedido de registro.

**Situação do registro muda.** Um "deferido" de hoje pode virar "indeferido"
depois de julgamento de recurso. A data da importação está no painel de
procedência — leia a coluna sabendo de quando ela é.

---

## 2. Patrimônio declarado

**TSE — mesma origem**, arquivo `bem_candidato_2026.zip`.

Descrição e valor de cada bem declarado no registro da candidatura. A planilha
mostra o total e a quantidade; o painel expandido de cada linha mostra item a
item.

**Limite conhecido:** não existe fonte pública que cruze o patrimônio declarado
com dados da Receita Federal — é sigilo fiscal. Nenhuma ferramenta pública faz
isso, e esta não é exceção. A comparação viável é entre declarações do próprio
candidato ao TSE ao longo do tempo: importe também os anos anteriores
(`--todos-os-anos`) e compare.

**O valor declarado é o de aquisição**, não o de mercado. Um imóvel comprado em
1998 aparece pelo valor de 1998. Comparar patrimônio entre candidatos de faixas
etárias diferentes sem levar isso em conta produz conclusão errada.

---

## 3. Grau de instrução

**TSE — mesmo registro de candidatura.** Campo `DS_GRAU_INSTRUCAO`.

**É autodeclarado, não é diploma verificado.** O comprovante de escolaridade fica
anexado ao processo de registro e pode ser conferido na Consulta Pública
Unificada do TSE, se for necessário confirmar um caso específico.

Para comparar com o conjunto da eleição, o TSE publica a distribuição agregada em
Estatísticas Eleitorais.

---

## 4. Condenações, processos e improbidade

Este era o item mais frágil do projeto, porque a fonte apontada originalmente —
o CNIA — é consulta com captcha, uma por vez. A saída não foi contornar o
captcha: foi procurar quem publica a mesma informação em massa.

### O que passou a ser coletado automaticamente

**TCU — Contas julgadas irregulares (Cadirreg)** · dados abertos
`https://sites.tcu.gov.br/dados-abertos/inidoneos-irregulares`

A melhor fonte pública para a coluna "ficha suja", e por um motivo direto: a
lista de responsáveis com contas julgadas irregulares **com possível implicação
eleitoral** é exatamente a que o TCU entrega ao TSE a cada eleição, por força da
Lei da Ficha Limpa (LC 135/2010).

É arquivo aberto, baixado inteiro: uma requisição para a base toda, sem captcha
e sem chave. O coletor indexa por nome e casa em memória.

Também entram as listas de inabilitados para função pública e de licitantes
inidôneos.

**Ressalva que a planilha repete em toda célula:** a correspondência é por nome,
sem CPF. Homônimo não é separável. E constar na lista **não é** ser inelegível —
quem decide isso é a Justiça Eleitoral, caso a caso.

**Portal da Transparência — sanções (CGU)** · API oficial
`https://api.portaldatransparencia.gov.br/`

API REST documentada em Swagger, chave gratuita liberada no ato do cadastro,
pessoa física incluída. Quatro cadastros:

- **CEAF** — expulsões da administração federal (demissão, cassação de
  aposentadoria, destituição de cargo em comissão). É o mais próximo de "ficha
  suja" para pessoa física.
- **CEIS** — inidôneas e suspensas de licitar.
- **CNEP** — punidas pela Lei Anticorrupção.
- **Acordos de leniência** firmados com a CGU.

Cobre **apenas a esfera federal**. Punição estadual ou municipal não aparece.

**CNJ — DataJud** · API pública nacional
`https://www.cnj.jus.br/sistemas/datajud/`

80 milhões de processos, todos os tribunais, gratuita. **Mas não resolve o
problema deste projeto:** a busca documentada é por número de processo ou por
classe + tribunal, e a resposta traz classe, assuntos, órgão julgador e
movimentos — **não traz nome das partes**. Não dá para perguntar "quais
processos esta pessoa tem".

O uso que sobra é real, ainda que modesto: o CSV do TSE traz o `NR_PROCESSO` do
próprio registro da candidatura, que é um processo da Justiça Eleitoral coberto
pelo DataJud. Com ele a planilha mostra em que pé está o registro — impugnado,
julgado, com recurso — direto da fonte. **Não é processo criminal**, e a coluna
diz isso.

### O que continua sem automação

**CNJ — CNIA** · `https://www.cnj.jus.br/improbidade_adm/consultar_requerido.php`
Condenações por improbidade e atos que geram inelegibilidade. Captcha a cada
busca, sem download em massa. A parte "inelegibilidade por contas irregulares"
está coberta pelo TCU acima; a parte "improbidade" não tem equivalente aberto.

**CNJ — BNMP** · `https://portalbnmp.cnj.jus.br/`
Mandados de prisão em aberto. Captcha, sem API, **e sem alternativa**: mandados
em aberto só existem ali. Procurei; não há segunda fonte.

**Tribunais de Justiça e TRFs**
Consulta processual por nome, tribunal a tribunal. O DataJud existe mas não
substitui, pelo motivo acima.

Para os três, o coletor gera a lista de trabalho com os links prontos
(`scripts/coletar.py --pendencias`), e o resultado preenchido volta pelo
importador normal.

**Existe caminho pago, e é honesto dizer qual:** Escavador, JUDIT, Digesto e
similares oferecem API de consulta processual por nome e CPF — foi exatamente
para isso que essas empresas existem. Se um dia essa coluna virar prioridade, é
esse o caminho realista, e o coletor para ele cabe no mesmo formato dos outros.

## 7. Indicador ideológico por tema

**Só existe para quem já votou no Congresso.** Para quem nunca exerceu mandato
não há equivalente objetivo — a coluna fica vazia, e isso é a resposta correta.

**Câmara e Senado — dados abertos** · `https://dadosabertos.camara.leg.br/`
Esta é a única fonte do grupo com API oficial e documentada. O coletor
`congresso` vai direto a ela: identifica o parlamentar na base oficial e calcula
o alinhamento por tema a partir dos votos nominais.

O cálculo depende de uma escolha editorial — quais votações contam e qual voto
representa a posição de referência de cada tema. Essa escolha está em
`config/votacoes.json`, versionada e legível. **Enquanto o arquivo não tiver
votações curadas, o coletor não calcula índice nenhum**, apenas identifica o
parlamentar. Um índice sem metodologia pública seria pior que nenhum índice.

**ComoVotou.org** · `https://comovotou.org/sobre` — índice de alinhamento por
tema sobre votações nominais reais.
**Atlas Político** · `http://atlaspolitico.com.br/metodologia` — eixos
esquerda–direita e governo–oposição (algoritmo Poole-Rosenthal) e Ranking 5D.
**Parlamentômetro** · `https://www.parlamentometro.com.br/` — votos, alinhamentos
e proposições.
**Placar Congresso** · `https://placarcongresso.com/pages/c-votos.html` —
classificação governo / centrão / oposição por percentual.

Os quatro são raspáveis e trazem metodologias diferentes entre si. Quando dois
discordam, isso não é erro de nenhum: é diferença de método. Por isso ficam em
colunas separadas, e não fundidos num número só.

---

## 8. Posicionamento público

**TSE — proposta de governo**, anexada ao registro. Obrigatória para presidente,
governador e prefeito.

**Agências de checagem** — Aos Fatos, Agência Lupa, Estadão Verifica.
O coletor `checagem` conta as peças que mencionam o nome e guarda os links. **A
contagem não é um julgamento sobre o candidato:** um nome muito checado pode ser
o de quem mais fala em público. Cada peça precisa ser lida.

**Busca de notícias** — feed público de busca do Google Notícias, que devolve XML
(não há raspagem de página). O coletor `noticias` aceita `--tema` para reproduzir
a busca "nome do candidato + assunto". **A contagem mede repercussão, não
veracidade nem gravidade.**

---

## Como a ferramenta trata o que não sabe

Três regras que valem para toda coluna vinda de fora:

1. **Célula sem dado mostra "sem dado" e o link da fonte**, montado com o nome do
   candidato. Nunca mostra zero, "nada consta" ou vazio no lugar de informação
   que não foi coletada — as três coisas seriam afirmações que ninguém fez.
2. **Coletor que não acha devolve vazio.** Nenhum coletor infere valor a partir
   de resultado parcial.
3. **Casamento de nome é conservador.** Exige coincidência de primeiro nome e
   último sobrenome, mais metade dos demais elementos. Sem CPF nas bases abertas,
   o pior erro possível aqui é atribuir a alguém um processo que não é dele.
