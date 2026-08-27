"""Consulta processual nos tribunais estaduais e federais.

Nao existe API nacional unificada de antecedentes: a consulta e tribunal a
tribunal, cada um com seu sistema, suas regras de captcha e sua propria
definicao de o que e publico. O coletor monta o link do tribunal da UF do
candidato e deixa a celula pronta para receber o resultado.
"""

from __future__ import annotations

import urllib.parse

from ._manual import ColetorManual
from .base import Candidato

# Portais de consulta processual por UF. Corrija aqui quando um tribunal mudar
# de endereco - nenhum outro arquivo depende desta tabela.
PORTAIS = {
    "AC": "https://esaj.tjac.jus.br/cpopg/open.do",
    "AL": "https://www2.tjal.jus.br/cpopg/open.do",
    "AM": "https://consultasaj.tjam.jus.br/cpopg/open.do",
    "AP": "https://tucujuris.tjap.jus.br/tucujuris/pages/consultar-processo/consultar-processo.html",
    "BA": "https://esaj.tjba.jus.br/cpopg/open.do",
    "CE": "https://esaj.tjce.jus.br/cpopg/open.do",
    "DF": "https://cesar1.tjdft.jus.br/consultaprocessual/",
    "ES": "https://sistemas.tjes.jus.br/ediario/",
    "GO": "https://projudi.tjgo.jus.br/",
    "MA": "https://pje.tjma.jus.br/pje/ConsultaPublica/listView.seam",
    "MG": "https://www4.tjmg.jus.br/juridico/sf/proc_pesquisa.jsp",
    "MS": "https://esaj.tjms.jus.br/cpopg5/open.do",
    "MT": "https://pjepg.tjmt.jus.br/pje/ConsultaPublica/listView.seam",
    "PA": "https://pje.tjpa.jus.br/pje/ConsultaPublica/listView.seam",
    "PB": "https://pje.tjpb.jus.br/pje/ConsultaPublica/listView.seam",
    "PE": "https://pje.tjpe.jus.br/1g/ConsultaPublica/listView.seam",
    "PI": "https://pje.tjpi.jus.br/1g/ConsultaPublica/listView.seam",
    "PR": "https://projudi.tjpr.jus.br/projudi/",
    "RJ": "https://www3.tjrj.jus.br/consultaprocessual/",
    "RN": "https://pje.tjrn.jus.br/pje1grau/ConsultaPublica/listView.seam",
    "RO": "https://pjepg.tjro.jus.br/consulta/ConsultaPublica/listView.seam",
    "RR": "https://projudi.tjrr.jus.br/projudi/",
    "RS": "https://www.tjrs.jus.br/novo/busca/?return=proc",
    "SC": "https://esaj.tjsc.jus.br/cpopg/open.do",
    "SE": "https://www.tjse.jus.br/portal/consultas/consulta-processual",
    "SP": "https://esaj.tjsp.jus.br/cpopg/open.do",
    "TO": "https://consultaeproc.tjto.jus.br/eprocV2_prod_1grau/externo_controlador.php?acao=processo_consulta_publica",
}

BUSCA_UNIFICADA = "https://www.jusbrasil.com.br/busca?q={nome_url}"


class Coletor(ColetorManual):
    slug = "tribunais"
    nome = "Tribunais de Justica e TRFs"
    campo = "processos"
    observacao_padrao = ("Nao ha API nacional unificada: a consulta e tribunal a "
                         "tribunal, e cada portal tem suas proprias regras de acesso.")

    def montar_url(self, candidato: Candidato) -> str:
        portal = PORTAIS.get((candidato.uf or "").upper())
        if portal:
            return portal
        return BUSCA_UNIFICADA.format(nome_url=urllib.parse.quote(candidato.nome))
