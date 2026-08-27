"""Placar Congresso - classificacao governo / centrao / oposicao.

Pagina estatica com a tabela de parlamentares e o percentual de votacoes em que
cada um acompanhou o governo.
"""

from __future__ import annotations

import re

from . import navegador, rede
from ._busca import linha_da_tabela, valor_da_coluna
from .base import Candidato, Coletor as Base, Registro

PAGINA = "https://placarcongresso.com/pages/c-votos.html"


class Coletor(Base):
    slug = "placar_congresso"
    nome = "Placar Congresso"
    observacao_padrao = "Lido da tabela publica do Placar Congresso."

    def coletar(self, candidato: Candidato) -> list[Registro]:
        if not re.search(r"DEPUTADO|SENADOR", candidato.cargo or "", re.IGNORECASE):
            return []

        try:
            html = navegador.buscar_com_plano_b(PAGINA)
        except rede.ErroDeColeta:
            return []

        tabela = linha_da_tabela(html, candidato)
        if not tabela:
            return []
        cabecalho, linha = tabela

        registros: list[Registro] = []
        classificacao = valor_da_coluna(cabecalho, linha, "classifica", "grupo", "bloco")
        if classificacao:
            registros.append(self.registro(candidato, "classificacao", classificacao,
                                           url=PAGINA))
        percentual = valor_da_coluna(cabecalho, linha, "%", "percentual", "votos com o governo")
        if percentual:
            numero = re.search(r"(\d{1,3}(?:[.,]\d+)?)", percentual)
            registros.append(self.registro(
                candidato, "percentual_governo", percentual,
                valor_num=float(numero.group(1).replace(",", ".")) if numero else None,
                url=PAGINA,
            ))
        return registros
