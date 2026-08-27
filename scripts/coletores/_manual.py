"""Base das fontes que nao podem ser raspadas de forma confiavel.

CNIA, BNMP e as consultas processuais dos tribunais exigem captcha ou sessao
com token a cada consulta. Nao existe caminho automatico honesto para elas.

Estes coletores, portanto, nao produzem valor nenhum: `coletar` devolve lista
vazia, e a planilha continua mostrando "sem dado" com o link de conferencia na
fonte. O que eles oferecem e `pendencia()`, que monta a linha de trabalho -
candidato, campo a preencher e link ja pronto. O comando `--pendencias` junta
essas linhas num CSV que pode ser preenchido a mao (ou por qualquer outro
processo) e devolvido a base pelo importador de dados externos.
"""

from __future__ import annotations

import urllib.parse

from .base import Candidato, Coletor, Registro


class ColetorManual(Coletor):
    automatico = False
    campo = "situacao"
    modelo_url = ""

    def montar_url(self, candidato: Candidato) -> str:
        return self.modelo_url.format(
            nome_url=urllib.parse.quote(candidato.nome),
            nome=candidato.nome,
            uf=candidato.uf,
        )

    def coletar(self, candidato: Candidato) -> list[Registro]:
        return []

    def pendencia(self, candidato: Candidato) -> dict:
        """Linha do CSV de trabalho, com o campo `valor` vazio para preencher."""
        return {
            "chave": candidato.chave,
            "fonte": self.slug,
            "campo": self.campo,
            "valor": "",
            "url": self.montar_url(candidato),
            "observacao": self.observacao_padrao,
            "_nome": candidato.nome,
            "_uf": candidato.uf,
            "_cargo": candidato.cargo,
            "_partido": candidato.partido,
        }
