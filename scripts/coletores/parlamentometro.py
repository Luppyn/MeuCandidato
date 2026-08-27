"""Parlamentometro - votos, alinhamentos e proposicoes.

Trabalha sobre os dados oficiais da Camara e do Senado, mas nao expoe API
propria: o coletor le a tabela de parlamentares e extrai a linha do candidato.
"""

from __future__ import annotations

import re

from . import navegador, rede
from ._busca import linha_da_tabela, valor_da_coluna
from .base import Candidato, Coletor as Base, Registro

PAGINA = "https://www.parlamentometro.com.br/"


class Coletor(Base):
    slug = "parlamentometro"
    nome = "Parlamentometro"
    observacao_padrao = "Lido da tabela publica do Parlamentometro."

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
        alinhamento = valor_da_coluna(cabecalho, linha, "alinhamento", "governismo")
        if alinhamento:
            numero = re.search(r"(\d{1,3}(?:[.,]\d+)?)", alinhamento)
            registros.append(self.registro(
                candidato, "alinhamento", alinhamento,
                valor_num=float(numero.group(1).replace(",", ".")) if numero else None,
                url=PAGINA,
            ))
        presenca = valor_da_coluna(cabecalho, linha, "presenca", "participacao")
        if presenca:
            registros.append(self.registro(candidato, "presenca", presenca, url=PAGINA))
        return registros
