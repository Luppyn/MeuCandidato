"""CNJ - Cadastro Nacional de Condenacoes por Improbidade Administrativa.

A consulta publica (consultar_requerido.php) exige captcha a cada busca e nao
publica API. Por isso este coletor nao raspa: monta o link da consulta por nome
e deixa a coluna pronta para receber o resultado.

Para preencher a coluna de fato, grave um arquivo no formato de
docs/automacao-externa.md com fonte "cnia" e campo "situacao" - seja a partir
de conferencia manual, seja de um processo externo que resolva o captcha.
"""

from ._manual import ColetorManual


class Coletor(ColetorManual):
    slug = "cnia"
    nome = "CNJ - CNIA"
    campo = "situacao"
    modelo_url = "https://www.cnj.jus.br/improbidade_adm/consultar_requerido.php"
    observacao_padrao = ("Consulta publica com captcha, sem API: o valor precisa vir "
                         "de conferencia na fonte.")
