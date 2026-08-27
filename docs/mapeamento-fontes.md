# Mapeamento das fontes — pendências

Este documento existe porque uma parte das URLs do projeto foi **inferida, não
conferida**. O ambiente onde o código é escrito não tem acesso de rede aos sites
das fontes, então endereços e formatos vieram de documentação pública e de
padrões de versões anteriores — e pelo menos um já se provou errado.

Cada bloco abaixo diz o que está no código, o que se sabe que está errado, e
exatamente o que falta descobrir. Preenchido um bloco, o coletor correspondente
passa a funcionar sem mudança de arquitetura: quase tudo é configuração.

**Regra que o código segue:** modelo não conferido não vira link. Um link errado
é pior que link nenhum — leva o leitor a um 404 e passa a impressão de que a
informação não existe.

---

## 1. DivulgaCandContas — página do candidato

**Situação: errado, com exemplo correto em mãos.**

O que o código gerava (404):
```
https://divulgacandcontas.tse.jus.br/divulga/#/candidato/2026/6259/MG/130002543682
```

O que funciona:
```
https://divulgacandcontas.tse.jus.br/divulga/#/candidato/SUDESTE/MG/20322002026/130002543682/2026/MG
```

Decomposição:

| Posição | Valor | Origem |
| --- | --- | --- |
| 1 | `SUDESTE` | macrorregião — derivável da UF, tabela em `config/links.json` |
| 2 | `MG` | `SG_UF` do CSV |
| 3 | `20322002026` | **desconhecido** |
| 4 | `130002543682` | `SQ_CANDIDATO` do CSV |
| 5 | `2026` | `ANO_ELEICAO` |
| 6 | `MG` | `SG_UE` |

### O que falta

O segmento 3. O `CD_ELEICAO` que vem no CSV do TSE para essa eleição é `6259`, e
não é isso que a rota quer. O número tem 11 dígitos e termina em `2026`.

**Perguntas:**

1. Abra dois ou três candidatos de **UFs diferentes** e cole as URLs. Se o
   segmento 3 for igual em todas, é constante por eleição e basta fixá-lo. Se
   variar, preciso saber com o quê.
2. Abra um candidato de **cargo diferente** na mesma UF (deputado estadual, por
   exemplo). Mesma pergunta.
3. Se puder: abra o **DevTools → aba Network → filtro XHR**, clique num
   candidato e cole as URLs que a página chama. Isso é o item mais valioso do
   documento inteiro — ver a API por trás resolve de uma vez o link, a foto, a
   proposta de governo e possivelmente os bens, sem raspar nada.

---

## 2. DivulgaCandContas — foto do candidato

**Situação: nunca conferido. A foto não é exibida.**

Modelo no código:
```
https://divulgacandcontas.tse.jus.br/divulga/rest/arquivo/img/{cd_eleicao}/{sq_candidato}
```

**Pergunta:** com o DevTools aberto na página de um candidato, qual é a URL da
imagem? (Botão direito na foto → "Copiar endereço da imagem" também serve.)

---

## 3. Excelências (Transparência Brasil)

**Situação: inferido.**

```
busca:  https://www.excelencias.org.br/busca?q={nome}
```

O coletor abre a busca, procura no resultado um link cujo texto bata com o nome
do candidato, abre o perfil e lê números perto de rótulos como "processos" e
"contas rejeitadas".

**Perguntas:**
1. Qual é a URL real da busca por nome?
2. Cole a URL do perfil de um parlamentar qualquer.
3. Nesse perfil, quais são os rótulos exatos dos números que interessam?

---

## 4. ComoVotou.org

**Situação: inferido.**

```
busca:  https://comovotou.org/busca?q={nome}
```

O coletor procura percentuais por tema (meio ambiente, direitos humanos,
economia, segurança, saúde, educação, costumes).

**Perguntas:**
1. URL real da busca e de um perfil.
2. Os temas são esses? Como aparecem escritos na página?

---

## 5. Atlas Político

**Situação: inferido.**

```
base:   http://atlaspolitico.com.br/
busca:  http://atlaspolitico.com.br/busca?q={nome}
```

O coletor procura o parlamentar numa tabela e lê as colunas de posição
ideológica, eixo governo–oposição e Ranking 5D.

**Perguntas:**
1. Existe busca por nome? Qual a URL?
2. Os dados estão em tabela HTML ou vêm por JavaScript? (Se for JS, o coletor
   tem plano B de navegador, mas preciso saber o que esperar.)

---

## 6. Parlamentômetro

**Situação: inferido.**

```
página: https://www.parlamentometro.com.br/
```

Espera uma tabela com uma linha por parlamentar, com colunas de "alinhamento" e
"presença".

**Pergunta:** qual página tem essa tabela? A raiz do site provavelmente não é.

---

## 7. Placar Congresso

**Situação: inferido.**

```
página: https://placarcongresso.com/pages/c-votos.html
```

Espera tabela com classificação (governo / centrão / oposição) e percentual.

**Pergunta:** esse endereço ainda existe? A tabela está no HTML ou é montada por
JavaScript?

---

## 8. Agências de checagem

**Situação: inferido.**

```
Aos Fatos          https://www.aosfatos.org/busca/?q={nome}
Agência Lupa       https://lupa.uol.com.br/busca?q={nome}
Estadão Verifica   https://www.estadao.com.br/busca/?q={nome}
```

**Pergunta:** as URLs de busca estão certas? (Basta buscar um nome em cada site
e colar o endereço que aparece.)

---

## 9. TCU — contas julgadas irregulares

**Situação: inferido, e é a fonte mais importante do projeto.**

```
https://contas.tcu.gov.br/ords/condenacao/consulta/arquivo?tipo=eleitoral
https://contas.tcu.gov.br/ords/condenacao/consulta/arquivo?tipo=irregulares
https://contas.tcu.gov.br/ords/condenacao/consulta/arquivo?tipo=inabilitados
https://contas.tcu.gov.br/ords/condenacao/consulta/arquivo?tipo=inidoneos
```

**Perguntas:**
1. Em https://sites.tcu.gov.br/dados-abertos/inidoneos-irregulares, qual é o link
   de download de cada lista? (Botão direito → "Copiar endereço do link".)
2. Baixando uma delas, qual é o **cabeçalho do arquivo**? Preciso saber o nome
   exato da coluna com o nome da pessoa. Hoje o código tenta `nome`,
   `nome_responsavel`, `responsavel`, `nome_completo`, entre outros.
3. É CSV, XLSX ou outra coisa?

---

## 10. Portal da Transparência — sanções

**Situação: inferido a partir do Swagger.**

```
/ceis?nome={nome}&pagina={n}
/cnep?nome={nome}&pagina={n}
/ceaf?nome={nome}&pagina={n}
/acordos-leniencia?nome={nome}&pagina={n}
```

**Perguntas:**
1. Em https://api.portaldatransparencia.gov.br/swagger-ui/index.html, o parâmetro
   de busca por nome de pessoa física se chama mesmo `nome` em cada um?
2. Cole uma resposta de exemplo (pode ser com o nome de um político conhecido).
   Preciso ver onde fica o nome da pessoa dentro do JSON — hoje o código procura
   em `pessoa.nome`, `sancionado.nome`, `nome` e `nomeSancionado`.

---

## 11. DataJud

**Situação: parcialmente inferido.**

```
https://api-publica.datajud.cnj.jus.br/api_publica_{tribunal}/_search
```

**Perguntas:**
1. Com a chave configurada, cole **uma resposta de exemplo** de um processo.
2. A pergunta que decide muita coisa: **o retorno traz nome das partes?**
   (`partes`, `poloAtivo`, `poloPassivo`, ou nada disso.) Se trouxer de forma
   consistente, passa a ser possível descobrir processos por nome, e não só
   detalhar um número já conhecido — o que muda o alcance do projeto.

---

## Como responder

Não precisa ser tudo de uma vez, e a ordem importa mais que a quantidade:

1. **DivulgaCandContas** (blocos 1 e 2) — é o que está quebrado agora e o que
   todo visitante vê.
2. **TCU** (bloco 9) — a fonte mais importante que ainda não trouxe dado.
3. **Portal da Transparência** (bloco 10) — segunda fonte oficial.
4. O resto, conforme der.

Qualquer resposta vira configuração, não código novo: `config/links.json` para o
TSE, `config/apis.json` para as APIs, e as constantes no topo de cada coletor
para os sites raspados.
