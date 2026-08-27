"""Transparencia Brasil - Excelencias.

Reune processos no STF/STJ, contas julgadas pelos Tribunais de Contas e
historico de mandatos de parlamentares. Nao publica API: o coletor abre a busca
por nome, confere se o resultado e mesmo a pessoa e le os numeros do perfil.
"""

from __future__ import annotations

import urllib.parse

from . import rede
from ._busca import buscar_perfil, numero_perto_de
from .base import Candidato, Coletor as Base, Registro

BUSCA = "https://www.excelencias.org.br/busca?q={nome_url}"


class Coletor(Base):
    slug = "excelencias"
    nome = "Transparencia Brasil - Excelencias"
    observacao_padrao = "Lido do perfil publico no Excelencias."

    def coletar(self, candidato: Candidato) -> list[Registro]:
        url_busca = BUSCA.format(nome_url=urllib.parse.quote(candidato.nome))
        achado = buscar_perfil(url_busca, candidato,
                               base="https://www.excelencias.org.br/")
        if not achado:
            return []
        url_perfil, _ = achado

        try:
            texto = rede.texto_de(rede.buscar(url_perfil))
        except rede.ErroDeColeta:
            return []

        registros: list[Registro] = []

        processos = numero_perto_de(texto, "processos no STF", "processos no STJ",
                                    "processos", "acoes judiciais")
        if processos:
            quantidade, trecho = processos
            registros.append(self.registro(
                candidato, "processos",
                f"{int(quantidade)} processo(s)", valor_num=quantidade,
                url=url_perfil,
                observacao=f"{self.observacao_padrao} Trecho lido: \"{trecho}\".",
            ))

        contas = numero_perto_de(texto, "contas rejeitadas", "contas julgadas irregulares")
        if contas:
            quantidade, trecho = contas
            registros.append(self.registro(
                candidato, "contas_rejeitadas",
                f"{int(quantidade)} conta(s) rejeitada(s)", valor_num=quantidade,
                url=url_perfil,
                observacao=f"{self.observacao_padrao} Trecho lido: \"{trecho}\".",
            ))

        mandatos = numero_perto_de(texto, "mandatos", "legislaturas")
        if mandatos:
            quantidade, _ = mandatos
            registros.append(self.registro(
                candidato, "mandatos",
                f"{int(quantidade)} mandato(s)", valor_num=quantidade, url=url_perfil,
            ))

        # Achou o perfil mas nao reconheceu numero nenhum: guarda ao menos o link,
        # que ja poupa a busca manual.
        if not registros:
            registros.append(self.registro(
                candidato, "perfil", "perfil encontrado", url=url_perfil,
                observacao="Perfil localizado, mas nenhum indicador numerico reconhecido "
                           "no formato atual da pagina.",
            ))
        return registros
