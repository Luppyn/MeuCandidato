"""Camara dos Deputados e Senado - dados abertos oficiais.

Esta e a unica fonte do grupo "indicador ideologico" que tem API publica e
documentada. Em vez de raspar um agregador de terceiros, o coletor vai direto a
fonte primaria: identifica o parlamentar na base oficial e, quando ha votacoes
curadas em config/votacoes.json, calcula o alinhamento por tema a partir dos
votos nominais registrados.

O indicador so existe para quem ja votou no Congresso. Para quem nunca exerceu
mandato nao ha equivalente objetivo, e o coletor nao devolve nada - a coluna
fica vazia, que e a resposta correta.
"""

from __future__ import annotations

import json
import pathlib
import urllib.parse

from . import rede
from .base import Candidato, Coletor as Base, Registro, parece_o_mesmo

RAIZ = pathlib.Path(__file__).resolve().parent.parent.parent
CONFIG = RAIZ / "config" / "votacoes.json"

API_CAMARA = "https://dadosabertos.camara.leg.br/api/v2"
API_SENADO = "https://legis.senado.leg.br/dadosabertos"

FAIXAS = [
    (-1.00, "Esquerda"),
    (-0.60, "Centro-esquerda"),
    (-0.20, "Centro"),
    (0.20, "Centro-direita"),
    (0.60, "Direita"),
]


def carregar_votacoes() -> dict:
    try:
        return json.loads(CONFIG.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"temas": []}


class Coletor(Base):
    slug = "congresso"
    nome = "Camara dos Deputados / Senado - dados abertos"
    observacao_padrao = "Calculado sobre votacoes nominais das APIs oficiais."

    def __init__(self):
        self.config = carregar_votacoes()
        self._votos_por_votacao: dict[str, dict[int, str]] = {}

    # -- identificacao -----------------------------------------------------
    def achar_deputado(self, candidato: Candidato) -> dict | None:
        url = (f"{API_CAMARA}/deputados?nome={urllib.parse.quote(candidato.nome)}"
               f"&ordem=ASC&ordenarPor=nome&itens=20")
        if candidato.uf:
            url += f"&siglaUf={candidato.uf}"
        try:
            resposta = rede.buscar_json(url)
        except rede.ErroDeColeta:
            return None

        for item in resposta.get("dados", []):
            if parece_o_mesmo(item.get("nome", ""), candidato.nome):
                return item
        # A API busca pelo nome parlamentar; tenta tambem pelo nome de urna.
        if candidato.nome_urna and candidato.nome_urna != candidato.nome:
            for item in resposta.get("dados", []):
                if parece_o_mesmo(item.get("nome", ""), candidato.nome_urna):
                    return item
        return None

    # -- votacoes ----------------------------------------------------------
    def votos_da_votacao(self, id_votacao: str) -> dict[int, str]:
        """Mapa {id do deputado: voto} de uma votacao, com cache em memoria."""
        if id_votacao in self._votos_por_votacao:
            return self._votos_por_votacao[id_votacao]

        votos: dict[int, str] = {}
        try:
            resposta = rede.buscar_json(f"{API_CAMARA}/votacoes/{id_votacao}/votos?itens=600")
            for item in resposta.get("dados", []):
                deputado = item.get("deputado_") or {}
                if deputado.get("id"):
                    votos[int(deputado["id"])] = (item.get("tipoVoto") or "").strip()
        except (rede.ErroDeColeta, ValueError, TypeError):
            pass

        self._votos_por_votacao[id_votacao] = votos
        return votos

    def alinhamento_do_tema(self, id_deputado: int, tema: dict) -> tuple[float, int] | None:
        """% de votos do parlamentar coincidentes com a posicao de referencia."""
        coincidencias = considerados = 0
        for votacao in tema.get("votacoes", []):
            voto = self.votos_da_votacao(str(votacao.get("id"))).get(id_deputado, "")
            if voto.lower() not in ("sim", "não", "nao"):
                continue  # ausencia, obstrucao e abstencao nao entram na conta
            considerados += 1
            referencia = (votacao.get("posicao_referencia") or "").lower()
            normalizado = "nao" if voto.lower() in ("não", "nao") else "sim"
            if normalizado == ("nao" if referencia in ("não", "nao") else "sim"):
                coincidencias += 1

        if not considerados:
            return None
        return coincidencias / considerados * 100, considerados

    @staticmethod
    def espectro(indice: float) -> str:
        rotulo = FAIXAS[0][1]
        for limite, nome in FAIXAS:
            if indice >= limite:
                rotulo = nome
        return rotulo

    # -- coleta ------------------------------------------------------------
    def coletar(self, candidato: Candidato) -> list[Registro]:
        deputado = self.achar_deputado(candidato)
        if not deputado:
            return []

        id_deputado = int(deputado["id"])
        url_perfil = f"https://www.camara.leg.br/deputados/{id_deputado}"

        registros = [self.registro(
            candidato, "identificacao",
            f"{deputado.get('nome', '')} ({deputado.get('siglaPartido', '')}-"
            f"{deputado.get('siglaUf', '')})",
            valor_num=float(id_deputado), url=url_perfil,
            observacao="Parlamentar localizado na base oficial da Camara. "
                       "Confirmacao de identidade por nome - sem CPF nas bases abertas.",
        )]

        temas = self.config.get("temas") or []
        if not temas:
            registros.append(self.registro(
                candidato, "indice_pendente", "sem votacoes curadas",
                url=url_perfil,
                observacao="config/votacoes.json ainda nao tem votacoes selecionadas; "
                           "sem curadoria publica das votacoes, nao ha indice a calcular.",
            ))
            return registros

        alinhamentos = []
        for tema in temas:
            resultado = self.alinhamento_do_tema(id_deputado, tema)
            if not resultado:
                continue
            percentual, considerados = resultado
            alinhamentos.append(percentual)
            registros.append(self.registro(
                candidato, f"tema_{tema['id']}", f"{percentual:.0f}%",
                valor_num=percentual, url=url_perfil,
                observacao=(f"{tema.get('nome', tema['id'])}: {considerados} votacao(oes) "
                            f"considerada(s). Posicao de referencia: "
                            f"{tema.get('posicao_descrita', 'ver config/votacoes.json')}."),
            ))

        if alinhamentos:
            media = sum(alinhamentos) / len(alinhamentos)
            indice = (media - 50) / 50  # -1 a 1
            registros.append(self.registro(
                candidato, "espectro", self.espectro(indice), valor_num=round(indice, 3),
                url=url_perfil,
                observacao=f"Media de {len(alinhamentos)} tema(s) curado(s) em "
                           "config/votacoes.json. O rotulo depende da posicao de "
                           "referencia escolhida ali, que e publica e auditavel.",
            ))
        return registros
