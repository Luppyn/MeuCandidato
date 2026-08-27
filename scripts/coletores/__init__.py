"""Coletores das fontes que nao publicam API.

Cada modulo aqui cuida de uma fonte e devolve registros no formato aceito por
scripts/importar_externos.py. Ver docs/automacao-externa.md.
"""

from .base import Candidato, Coletor, Registro  # noqa: F401

__all__ = ["Candidato", "Coletor", "Registro", "todos"]


def todos() -> dict:
    """Instancia todos os coletores disponiveis, indexados pelo slug."""
    from . import (atlas_politico, bnmp, checagem, cnia, comovotou, congresso,
                   datajud, excelencias, noticias, parlamentometro,
                   placar_congresso, transparencia, tcu, tribunais)

    # Ordem de execução: fontes oficiais primeiro (mais confiáveis e mais
    # baratas), depois as raspadas, e por último as que só geram pendência.
    modulos = [tcu, transparencia, datajud, congresso,
               excelencias, comovotou, atlas_politico, parlamentometro,
               placar_congresso, checagem, noticias,
               cnia, bnmp, tribunais]
    instancias = {}
    for modulo in modulos:
        coletor = modulo.Coletor()
        instancias[coletor.slug] = coletor
    return instancias
