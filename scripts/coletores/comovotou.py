"""ComoVotou.org - indice de alinhamento por tema.

Calcula alinhamento a partir de votacoes nominais reais, e por isso so se
aplica a quem ja exerceu mandato no Congresso. Sem API: o coletor procura o
perfil pelo nome e le os indices por tema exibidos nele.
"""

from __future__ import annotations

import re
import urllib.parse

from . import rede
from ._busca import buscar_perfil, percentual_perto_de
from .base import Candidato, Coletor as Base, Registro

BUSCA = "https://comovotou.org/busca?q={nome_url}"
BASE = "https://comovotou.org/"

# Temas procurados no perfil. Acrescente aqui para ampliar a cobertura.
TEMAS = [
    ("meio_ambiente", ("meio ambiente", "ambiental", "clima")),
    ("direitos_humanos", ("direitos humanos", "minorias")),
    ("economia", ("economia", "economico", "fiscal")),
    ("seguranca", ("seguranca publica", "seguranca")),
    ("saude", ("saude",)),
    ("educacao", ("educacao",)),
    ("costumes", ("costumes", "pauta de costumes")),
]


class Coletor(Base):
    slug = "comovotou"
    nome = "ComoVotou.org"
    observacao_padrao = "Indice do ComoVotou, calculado sobre votacoes nominais."

    def coletar(self, candidato: Candidato) -> list[Registro]:
        # So faz sentido para quem tem historico de voto no Congresso.
        if not re.search(r"DEPUTADO|SENADOR", candidato.cargo or "", re.IGNORECASE):
            return []

        url_busca = BUSCA.format(nome_url=urllib.parse.quote(candidato.nome))
        achado = buscar_perfil(url_busca, candidato, base=BASE)
        if not achado:
            return []
        url_perfil, _ = achado

        try:
            texto = rede.texto_de(rede.buscar(url_perfil))
        except rede.ErroDeColeta:
            return []

        registros: list[Registro] = []
        for campo, rotulos in TEMAS:
            resultado = percentual_perto_de(texto, *rotulos)
            if resultado:
                percentual, trecho = resultado
                registros.append(self.registro(
                    candidato, campo, f"{percentual:.0f}%", valor_num=percentual,
                    url=url_perfil,
                    observacao=f"{self.observacao_padrao} Trecho lido: \"{trecho}\".",
                ))

        if registros:
            media = sum(r.valor_num for r in registros) / len(registros)
            registros.append(self.registro(
                candidato, "indice", f"{media:.0f}% (media de {len(registros)} temas)",
                valor_num=media, url=url_perfil,
                observacao="Media simples dos temas reconhecidos no perfil.",
            ))
        return registros
