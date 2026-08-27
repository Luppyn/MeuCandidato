"""Levantamento de materias jornalisticas por nome do candidato.

Usa o feed de busca do Google Noticias, que e publico e devolve XML - nao ha
raspagem de pagina aqui. Guarda a quantidade de materias e os primeiros
titulos, com link, para servir de ponto de partida a leitura.

Um termo de tema pode ser combinado ao nome (--tema), reproduzindo a busca
"nome do candidato + assunto" descrita no escopo.
"""

from __future__ import annotations

import urllib.parse
import xml.etree.ElementTree as ET

from . import rede
from .base import Candidato, Coletor as Base, Registro

FEED = ("https://news.google.com/rss/search?q={consulta}"
        "&hl=pt-BR&gl=BR&ceid=BR%3Apt-419")
MAXIMO_TITULOS = 5


class Coletor(Base):
    slug = "noticias"
    nome = "Busca de noticias"
    observacao_padrao = "Contagem do feed publico de busca de noticias."

    def __init__(self, tema: str = ""):
        self.tema = tema

    def coletar(self, candidato: Candidato) -> list[Registro]:
        termos = f'"{candidato.nome}"'
        if candidato.uf:
            termos += f" {candidato.uf}"
        if self.tema:
            termos += f" {self.tema}"

        url = FEED.format(consulta=urllib.parse.quote(termos))
        try:
            xml = rede.buscar(url)
            raiz = ET.fromstring(xml)
        except (rede.ErroDeColeta, ET.ParseError):
            return []

        itens = raiz.findall(".//item")
        pagina = ("https://news.google.com/search?q="
                  f"{urllib.parse.quote(termos)}&hl=pt-BR&gl=BR&ceid=BR%3Apt-419")

        campo = f"qtd_{self.tema.replace(' ', '_')}" if self.tema else "qtd"
        registros = [self.registro(
            candidato, campo, f"{len(itens)} materia(s)", valor_num=float(len(itens)),
            url=pagina,
            observacao=f"Busca por {termos}. "
                       "A contagem mede repercussao, nao veracidade nem gravidade.",
        )]

        titulos = []
        for item in itens[:MAXIMO_TITULOS]:
            titulo = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            if titulo:
                titulos.append(f"{titulo} — {link}" if link else titulo)
        if titulos:
            registros.append(self.registro(
                candidato, f"{campo}_titulos", " | ".join(titulos), url=pagina,
                observacao="Primeiros resultados da busca, sem curadoria editorial.",
            ))
        return registros
