# Formato de entrada dos dados externos

Tudo que não vem do TSE entra na base por um caminho só:
`scripts/importar_externos.py`. Não importa se o arquivo foi gerado por um
coletor deste repositório, por um fluxo do n8n, por um script seu ou por alguém
preenchendo uma planilha à mão — o formato é o mesmo, e toda importação fica
registrada com nome do arquivo, data, tamanho e SHA-256.

## O registro

Cada registro é **uma célula da planilha**: um campo, de uma fonte, para um
candidato.

| Campo | Obrigatório | O que é |
| --- | --- | --- |
| `chave` | sim | Identificador do candidato: `ano-cargo-uf-ue-numero`. |
| `fonte` | sim | Slug da fonte, conforme `config/fontes.json` (ex.: `cnia`). |
| `campo` | sim | Nome do campo dentro da fonte (ex.: `situacao`). |
| `valor` | sim | O texto que aparece na célula. Registro sem valor é ignorado. |
| `valor_num` | não | Valor numérico, para ordenar e comparar. |
| `url` | não | Link para a evidência na fonte. A célula vira link. |
| `observacao` | não | Ressalva de método. Aparece como dica na célula. |
| `coletado_em` | não | Data/hora ISO 8601. Sem isso, usa o momento da importação. |

Em vez de `chave`, dá para mandar as partes separadas: `ano`, `cargo`, `uf`,
`ue`, `numero`. O importador monta a chave.

### A chave

`ano-cargo-uf-ue-numero`, por exemplo `2026-6-SP-SP-1234`:

- `ano` — ano da eleição (`2026`)
- `cargo` — código do cargo no TSE (`1` presidente, `3` governador, `5` senador,
  `6` deputado federal, `7` deputado estadual, `8` distrital, `11` prefeito,
  `13` vereador)
- `uf` — sigla da UF (`SP`); `BR` para presidente
- `ue` — unidade eleitoral: a própria UF em pleito geral, o código do município
  em pleito municipal
- `numero` — número do candidato na urna

O TSE removeu o CPF das bases abertas, então essa combinação é o identificador
disponível. A unidade eleitoral entra porque em eleição municipal o mesmo número
se repete em municípios diferentes da mesma UF.

A forma mais segura de obter a chave é perguntar ao próprio site, em vez de
montá-la: `GET /api/candidatos?ano=2026&cargo=6&uf=SP` devolve a chave de cada
candidato do recorte. É o que o fluxo do n8n faz.

## Os arquivos

### JSON

```json
[
  {
    "chave": "2026-6-SP-SP-1234",
    "fonte": "cnia",
    "campo": "situacao",
    "valor": "Nada consta",
    "url": "https://www.cnj.jus.br/improbidade_adm/consultar_requerido.php",
    "observacao": "Consulta por nome completo",
    "coletado_em": "2026-08-27T10:00:00-03:00"
  }
]
```

Também aceita `{"registros": [...]}` — que é o que alguns nós do n8n produzem.

### CSV

Ponto e vírgula ou vírgula, com cabeçalho. Há um modelo pronto em
`dados/externo/modelo.csv`.

```csv
chave;fonte;campo;valor;valor_num;url;observacao;coletado_em
2026-6-SP-SP-1234;excelencias;processos;2 processos no STF;2;https://www.excelencias.org.br/;;2026-08-27T10:00:00-03:00
```

## Importando

```bash
python3 scripts/importar_externos.py dados/externo/cnia.json
python3 scripts/importar_externos.py dados/externo/            # pasta inteira
python3 scripts/importar_externos.py --substituir-fonte cnia dados/externo/cnia.csv
python3 scripts/importar_externos.py --estrito dados/externo/  # aborta no 1º erro
```

Comportamento:

- A importação é **incremental**. Um registro com a mesma `chave` + `fonte` +
  `campo` substitui o anterior; os demais ficam intactos.
- `--substituir-fonte` apaga tudo daquela fonte antes de importar, para o caso de
  uma recoleta completa em que registros antigos precisam sumir.
- Registro com `valor` vazio é **ignorado**, não gravado como célula em branco. A
  planilha já mostra "sem dado" com o link da fonte quando não há registro — uma
  célula vazia importada só apagaria essa informação.
- Registro cuja `chave` ainda não existe na base é **guardado assim mesmo**, e
  passa a aparecer quando o candidato for importado. Isso permite coletar antes
  de a base do TSE estar pronta, e faz o dado externo sobreviver a uma
  reimportação completa da base do TSE.
- Fonte não registrada em `config/fontes.json` é recusada com aviso. Isso é
  proposital: toda fonte que aparece na planilha precisa estar declarada, com
  descrição e link, no registro público de fontes.

## Criando uma coluna nova

Não precisa mexer em código. Duas edições de configuração:

1. Registre a fonte em `config/fontes.json`, se ela ainda não existir:

```json
{
  "slug": "minha_fonte",
  "nome": "Nome que aparece no painel de fontes",
  "url": "https://exemplo.org",
  "categoria": "Judicial",
  "tem_api": 0,
  "descricao": "O que essa fonte traz e o que ela não garante.",
  "url_consulta_manual": "https://exemplo.org/busca?q={nome_url}"
}
```

`url_consulta_manual` aceita os marcadores `{nome}`, `{nome_url}`, `{uf}`,
`{cargo}` e `{ano}`. É o link que a planilha oferece nas células sem dado.

2. Declare a coluna em `config/colunas.json`:

```json
{
  "id": "minha_fonte.meu_campo",
  "titulo": "Título da coluna",
  "grupo": "Judicial",
  "tipo": "externo",
  "largura": 150,
  "peso": "pesada",
  "fonte": "minha_fonte"
}
```

O `id` é sempre `fonte.campo`. `"peso": "pesada"` tira a coluna da grade
principal e a joga para o painel expandido da linha — use para o que é longo ou
raramente consultado.

Reinicie o servidor e a coluna existe, pronta para receber dado.

## Escrevendo um coletor

Se preferir automatizar dentro do repositório em vez de por fora, crie um módulo
em `scripts/coletores/`:

```python
from .base import Candidato, Coletor as Base, Registro


class Coletor(Base):
    slug = "minha_fonte"
    nome = "Nome da fonte"

    def coletar(self, candidato: Candidato) -> list[Registro]:
        return [self.registro(candidato, "meu_campo", "valor", url="https://...")]
```

Registre o módulo em `scripts/coletores/__init__.py` e ele aparece no
`--listar`. Duas regras que a base já sustenta e vale manter:

- **Quando não achar, devolva lista vazia.** Nunca chute. "Sem dado" com link de
  conferência é uma resposta melhor do que um valor errado.
- **Use `parece_o_mesmo` para casar nomes.** Ela exige coincidência de primeiro
  nome e último sobrenome, e é deliberadamente conservadora — sem CPF nas bases
  abertas, atribuir um processo à pessoa errada é o pior erro possível aqui.
