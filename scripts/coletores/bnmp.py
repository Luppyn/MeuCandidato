"""CNJ - Banco Nacional de Mandados de Prisao.

Mesma situacao do CNIA: portal com captcha e sem API publica. O coletor entrega
o link de consulta, nao um valor.
"""

from ._manual import ColetorManual


class Coletor(ColetorManual):
    slug = "bnmp"
    nome = "CNJ - BNMP"
    campo = "situacao"
    modelo_url = "https://portalbnmp.cnj.jus.br/"
    observacao_padrao = ("Portal com captcha, sem API: o valor precisa vir de "
                         "conferencia na fonte.")
