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

Nenhuma destas fontes tem API pública documentada.

**CNJ — CNIA** · `https://www.cnj.jus.br/improbidade_adm/consultar_requerido.php`
Condenações definitivas por improbidade administrativa e atos que geram
inelegibilidade. A consulta pública exige captcha a cada busca. **Não é
automatizável de forma confiável:** o coletor `cnia` gera a lista de trabalho com
os links prontos, e o valor precisa vir de conferência.

**CNJ — BNMP** · `https://portalbnmp.cnj.jus.br/`
Mandados de prisão em aberto. Mesma situação: portal com captcha, coletor de
lista de trabalho.

**Transparência Brasil — Excelências** · `https://www.excelencias.org.br/`
Processos no STF e no STJ, contas julgadas pelos Tribunais de Contas, histórico
de mandatos. Raspável. O coletor localiza o perfil pelo nome e lê os números.

**Tribunais de Justiça e TRFs**
**Não existe API nacional unificada de antecedentes criminais.** A consulta é
tribunal a tribunal, cada um com seu sistema e suas regras. O coletor
`tribunais` monta o link do tribunal da UF do candidato; a leitura é manual.

**Cuidado de leitura que a ferramenta não pode fazer por você:** processo em
andamento não é condenação, e condenação em primeira instância não é condenação
definitiva. A célula traz o que a fonte diz; o peso disso é julgamento de quem lê.

---

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
