"""Agencias de checagem - Aos Fatos, Agencia Lupa e Estadao Verifica.

Nenhuma publica API. O coletor abre a busca por nome em cada agencia e conta as
checagens que mencionam o candidato, guardando os links. O valor diz quantas
checagens existem, nao se o candidato mentiu: a leitura de cada peca continua
sendo do usuario.
"""

from __future__ import annotations

import urllib.parse

from . import rede
from .base import Candidato, Coletor as Base, Registro

AGENCIAS = [
    ("Aos Fatos", "https://www.aosfatos.org/busca/?q={nome_url}", "aosfatos.org"),
    ("Agencia Lupa", "https://lupa.uol.com.br/busca?q={nome_url}", "lupa.uol.com.br"),
    ("Estadao Verifica", "https://www.estadao.com.br/busca/?q={nome_url}", "estadao.com.br"),
]
MAXIMO_LINKS = 5


class Coletor(Base):
    slug = "checagem"
    nome = "Agencias de checagem"
    observacao_padrao = ("Quantidade de checagens que mencionam o nome. Nao e um "
                         "julgamento sobre o candidato: cada peca precisa ser lida.")

    def coletar(self, candidato: Candidato) -> list[Registro]:
        nome_url = urllib.parse.quote(candidato.nome)
        achados: list[str] = []
        total = 0

        for nome_agencia, modelo, dominio in AGENCIAS:
            url = modelo.format(nome_url=nome_url)
            try:
                html = rede.buscar(url)
            except rede.ErroDeColeta:
                continue

            vistos = set()
            for href, rotulo in rede.links_de(html, url):
                if dominio not in href or href in vistos or len(rotulo) < 25:
                    continue
                # Descarta menus e paginas de secao: interessa a peca em si.
                if href.rstrip("/").count("/") < 3:
                    continue
                vistos.add(href)
                if len(achados) < MAXIMO_LINKS:
                    achados.append(f"{nome_agencia}: {rotulo} — {href}")
            total += len(vistos)

        if not total:
            return []

        url_principal = AGENCIAS[0][1].format(nome_url=nome_url)
        registros = [self.registro(
            candidato, "verificacoes", f"{total} checagem(ns)",
            valor_num=float(total), url=url_principal,
        )]
        if achados:
            registros.append(self.registro(
                candidato, "verificacoes_links", " | ".join(achados), url=url_principal,
                observacao="Primeiros resultados encontrados nas buscas.",
            ))
        return registros
