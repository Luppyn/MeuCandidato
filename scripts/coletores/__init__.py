"""Coletores das fontes que nao publicam API.

Cada modulo aqui cuida de uma fonte e devolve registros no formato aceito por
scripts/importar_externos.py. Ver docs/automacao-externa.md.
"""

from .base import Candidato, Coletor, Registro  # noqa: F401

__all__ = ["Candidato", "Coletor", "Registro", "todos"]


def todos() -> dict:
    """Instancia todos os coletores disponiveis, indexados pelo slug."""
    from . import (atlas_politico, bnmp, checagem, cnia, comovotou, congresso,
                   excelencias, noticias, parlamentometro, placar_congresso,
                   tribunais)

    modulos = [cnia, bnmp, excelencias, tribunais, congresso, comovotou,
               atlas_politico, parlamentometro, placar_congresso, checagem, noticias]
    instancias = {}
    for modulo in modulos:
        coletor = modulo.Coletor()
        instancias[coletor.slug] = coletor
    return instancias
