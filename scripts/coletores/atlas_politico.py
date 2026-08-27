"""Atlas Politico - mapa ideologico e Ranking 5D.

Posiciona parlamentares nos eixos esquerda-direita e governo-oposicao a partir
de votacoes nominais (algoritmo Poole-Rosenthal). Sem API publica.
"""

from __future__ import annotations

import re
import urllib.parse

from . import navegador, rede
from ._busca import buscar_perfil, linha_da_tabela, valor_da_coluna
from .base import Candidato, Coletor as Base, Registro

BASE = "http://atlaspolitico.com.br/"
BUSCA = "http://atlaspolitico.com.br/busca?q={nome_url}"


class Coletor(Base):
    slug = "atlas_politico"
    nome = "Atlas Politico"
    observacao_padrao = "Posicao calculada pelo Atlas Politico sobre votacoes nominais."

    def coletar(self, candidato: Candidato) -> list[Registro]:
        if not re.search(r"DEPUTADO|SENADOR", candidato.cargo or "", re.IGNORECASE):
            return []

        url_busca = BUSCA.format(nome_url=urllib.parse.quote(candidato.nome))
        achado = buscar_perfil(url_busca, candidato, base=BASE)
        url_pagina = achado[0] if achado else BASE

        try:
            html = navegador.buscar_com_plano_b(url_pagina)
        except rede.ErroDeColeta:
            return []

        registros: list[Registro] = []
        tabela = linha_da_tabela(html, candidato)
        if tabela:
            cabecalho, linha = tabela
            posicao = valor_da_coluna(cabecalho, linha, "ideolog", "espectro", "posicao")
            if posicao:
                registros.append(self.registro(candidato, "posicao", posicao, url=url_pagina))
            eixo = valor_da_coluna(cabecalho, linha, "governo", "oposicao")
            if eixo:
                registros.append(self.registro(candidato, "eixo_governo", eixo, url=url_pagina))
            ranking = valor_da_coluna(cabecalho, linha, "ranking", "5d")
            if ranking:
                registros.append(self.registro(candidato, "ranking_5d", ranking, url=url_pagina))
        return registros
