"""CNJ — DataJud (API pública nacional de processos).

Base Nacional de Dados do Poder Judiciário: 80 milhões de processos, todos os
tribunais, API REST pública e gratuita.

**Limite decisivo, e a razão de este coletor ser modesto:** a busca documentada
é por número de processo ou por classe + tribunal, e a resposta traz classe,
assuntos, órgão julgador e movimentos — não traz nome das partes. Ou seja, o
DataJud **não serve para descobrir os processos de uma pessoa**. Serve para
detalhar um processo cujo número já se conhece.

E há um número que já se conhece: o `NR_PROCESSO` do próprio registro da
candidatura, que vem no CSV do TSE. É um processo da Justiça Eleitoral, coberto
pelo DataJud. Com ele dá para mostrar em que pé está o registro — se foi
impugnado, julgado, se houve recurso — direto da fonte, em vez de depender só
do rótulo de situação que o TSE publica.

Se algum dia a API passar a permitir busca por nome, o lugar de mudar é aqui.
"""

from __future__ import annotations

import json
import re

from . import rede
from ._config import cabecalho_de, config_de, falta_chave
from .base import Candidato, Coletor as Base, Registro

# Do número unificado CNJ (NNNNNNN-DD.AAAA.J.TR.OOOO) saem o segmento (J) e o
# tribunal (TR), que juntos formam o alias do índice no DataJud.
PADRAO_NUMERO = re.compile(
    r"(\d{7})-?(\d{2})\.?(\d{4})\.?(\d)\.?(\d{2})\.?(\d{4})"
)

# Segmento 6 = Justiça Eleitoral. O alias do TSE é 'tse'; os TREs seguem o
# padrão 'tre-<uf>', com a UF derivada do código do tribunal.
UF_POR_CODIGO_TRE = {
    "01": "ac", "02": "al", "03": "ap", "04": "am", "05": "ba", "06": "ce",
    "07": "df", "08": "es", "09": "go", "10": "ma", "11": "mt", "12": "ms",
    "13": "mg", "14": "pa", "15": "pb", "16": "pr", "17": "pe", "18": "pi",
    "19": "rj", "20": "rn", "21": "rs", "22": "ro", "23": "rr", "24": "sc",
    "25": "se", "26": "sp", "27": "to",
}


def alias_do_tribunal(numero: str) -> tuple[str, str] | None:
    """Devolve (alias do índice, número limpo) a partir do número unificado."""
    achado = PADRAO_NUMERO.search(numero or "")
    if not achado:
        return None
    sequencial, digito, ano, segmento, tribunal, origem = achado.groups()
    limpo = f"{sequencial}{digito}{ano}{segmento}{tribunal}{origem}"

    if segmento != "6":  # só a Justiça Eleitoral interessa aqui
        return None
    if tribunal == "00":
        return "tse", limpo
    uf = UF_POR_CODIGO_TRE.get(tribunal)
    return (f"tre-{uf}", limpo) if uf else None


class Coletor(Base):
    slug = "datajud"
    nome = "CNJ — DataJud"
    observacao_padrao = "Movimentação lida da API pública do DataJud (CNJ)."

    def __init__(self):
        self.cfg = config_de("datajud")
        self.aviso = falta_chave("datajud")

    def coletar(self, candidato: Candidato) -> list[Registro]:
        numero = getattr(candidato, "processo", "") or ""
        if not numero:
            return []

        destino = alias_do_tribunal(numero)
        if not destino:
            return []
        alias, limpo = destino

        if self.aviso:
            return []

        url = self.cfg["base"] + self.cfg["endpoint_tribunal"].format(tribunal=alias)
        consulta = json.dumps({
            "size": 1,
            "query": {"match": {"numeroProcesso": limpo}},
        }).encode("utf-8")

        try:
            resposta = rede.buscar_json(
                url, corpo=consulta,
                cabecalhos={**cabecalho_de("datajud"), "Content-Type": "application/json"},
            )
        except rede.ErroDeColeta:
            return []

        acertos = (resposta.get("hits") or {}).get("hits") or []
        if not acertos:
            return []
        processo = acertos[0].get("_source") or {}

        movimentos = processo.get("movimentos") or []
        ultimo = ""
        if movimentos:
            recente = max(movimentos, key=lambda m: m.get("dataHora") or "")
            ultimo = (recente.get("nome") or "").strip()

        url_publica = "https://www.cnj.jus.br/sistemas/datajud/"
        classe = (processo.get("classe") or {}).get("nome") or ""

        registros = [self.registro(
            candidato, "registro_movimentacao",
            ultimo or classe or "processo localizado",
            valor_num=float(len(movimentos)), url=url_publica,
            observacao=(f"{self.observacao_padrao} Processo de registro da candidatura "
                        f"{numero} ({alias.upper()}), classe \"{classe}\", "
                        f"{len(movimentos)} movimento(s). "
                        f"É a tramitação do registro — não é processo criminal."),
        )]

        assuntos = [a.get("nome") for a in (processo.get("assuntos") or []) if a.get("nome")]
        if assuntos:
            registros.append(self.registro(
                candidato, "registro_assuntos", "; ".join(assuntos[:4]),
                url=url_publica, observacao=self.observacao_padrao,
            ))
        return registros
