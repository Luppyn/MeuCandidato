# Colocar o site no ar

Do repositório recém-clonado até o site público, com coleta rodando sozinha.

## 1. Ligar o GitHub Pages (uma vez só)

**Settings → Pages → Source: GitHub Actions.**

Não escolha "Deploy from a branch" — a publicação é feita por workflow, e essa
opção o ignora.

O endereço será `https://luppyn.github.io/MeuCandidato/`.

## 2. Publicar a primeira versão

**Actions → Publicar site → Run workflow.**

O workflow baixa a base do TSE, aplica os dados externos que existirem, gera a
versão estática e publica. Uns 5 a 10 minutos na primeira vez — depois o
download do TSE fica em cache.

Ao terminar, o endereço aparece no resumo da execução.

Daí em diante ele roda sozinho:

- a cada push na `main` (para que uma correção de código apareça sem esperar
  coleta);
- ao fim de cada execução da **Coleta externa**.

## 3. Rodar a coleta

**Actions → Coleta externa → Run workflow**, escolhendo:

| Campo | O que é |
| --- | --- |
| `cargo` | código do TSE: `1` presidente, `3` governador, `5` senador, `6` deputado federal, `7` deputado estadual |
| `uf` | sigla, ex.: `SP` |
| `fontes` | vazio = todas as automáticas; ou uma lista, ex.: `tcu transparencia` |
| `navegador` | deixe ligado, salvo se estiver depurando |

Depois disso ela roda sozinha toda segunda às 4h (horário de Brasília).

### Antes de confiar na primeira coleta

Abra o log da execução no passo **"Confirmar por qual IP a coleta vai sair"**:

```
proxy configurado : sim
proxy             : host.do.proxy:8080
IP de saida       : 189.x.x.x
```

Se o IP for de datacenter (os runners do GitHub ficam na Azure), o proxy não
está sendo usado e as fontes vão recusar. Usuário e senha nunca são impressos.

### Comece pequeno

Na primeira vez, rode com `fontes: tcu` e um cargo só. O TCU é a fonte mais
importante e a mais simples — baixa arquivo aberto, sem chave e sem captcha. Se
ela funcionar, o caminho está de pé; aí vale soltar as outras.

## 4. Conferir o resultado

Cada coleta comita em `dados/externo/`. O histórico do git vira o registro
público: dá para ver, commit a commit, o que cada fonte devolveu e quando um
valor mudou.

No site, o painel **"Procedência dos dados"** mostra data, tamanho e SHA-256 de
cada arquivo importado, além da cobertura de cada coluna externa.

## Rodando na sua máquina

O mesmo site, com servidor local em vez de arquivos estáticos:

```bash
python3 scripts/gerar_exemplo.py    # base fictícia, para ver funcionando
python3 servidor.py                 # http://localhost:8000
```

Com dados reais:

```bash
python3 scripts/importar_tse.py --baixar --ano 2026
python3 scripts/coletar.py --fonte tcu --cargo 6 --uf SP
python3 scripts/importar_externos.py dados/externo/
python3 servidor.py
```

Para ver exatamente o que vai ao ar:

```bash
python3 scripts/gerar_estatico.py
cd publicar && python3 -m http.server 8000
```

## Os dois modos

O mesmo `web/app.js` roda de duas formas, e detecta sozinho qual é:

| | Servidor | Estático |
| --- | --- | --- |
| Quando | uso local | site publicado |
| Filtro por nome/partido | no servidor (SQL) | no navegador, dentro do recorte |
| Bens | rota por candidato | um arquivo por recorte, buscado ao expandir |
| CSV | gerado pelo servidor | montado no navegador |

A detecção é por tentativa: se `api/saude` responde, é o servidor; senão, é
estático. Em hospedagem estática essa rota devolve 404, o que é esperado e
aparece no console do navegador.

Os dois caminhos foram comparados lado a lado em navegador: mesma contagem,
mesma ordenação, mesma busca, mesmos bens.

## Por que particionar por cargo + UF

O site já exige cargo e UF antes de carregar qualquer coisa. Essa exigência, que
existe por outro motivo, dá de graça uma boa chave de partição: um arquivo JSON
por recorte, e o navegador busca só o que foi pedido.

Em cargo municipal o município entra na chave — uma lista de vereadores de um
estado inteiro não é recorte útil, e o site passa a exigir o município também.

## Custo

Zero. GitHub Pages e Actions são gratuitos em repositório público. O único custo
recorrente é o proxy residencial, que é seu e existe independente disto.

## Quando algo quebra

| Sintoma | Onde olhar |
| --- | --- |
| Site publicou sem dado externo | A coleta rodou? `dados/externo/` tem arquivo? |
| Coleta não traz nada de uma fonte | Log da execução: o coletor diz o que faltou (chave, arquivo fora do ar) |
| Fonte recusa a conexão | Passo do IP de saída: o proxy está valendo? |
| Endereço de uma fonte mudou | `config/apis.json` — corrija ali, sem tocar em código |
| Coluna some ou aparece errada | `config/colunas.json` |
