"""Ferramentas comuns aos coletores que leem paginas HTML.

Os sites das fontes dos itens 4 a 8 nao tem contrato de API: o HTML pode mudar
sem aviso. Em vez de depender de seletores rigidos, estes coletores procuram o
candidato pelo nome nos links e nas tabelas da pagina e extraem numeros pelo
rotulo que os acompanha. Quando nada bate, devolvem lista vazia - a planilha
mostra "sem dado" e o link de conferencia, que e o comportamento correto.
"""

from __future__ import annotations

import re
import urllib.parse

from . import navegador, rede
from .base import Candidato, parece_o_mesmo


def buscar_perfil(url_busca: str, candidato: Candidato, *,
                  base: str | None = None, desbloquear: bool = False,
                  filtro_href: str | None = None) -> tuple[str, str] | None:
    """Abre uma pagina de busca e devolve (url, rotulo) do link do candidato."""
    try:
        # HTTP primeiro; navegador só se a resposta vier vazia ou bloqueada.
        html = (navegador.buscar_com_plano_b(url_busca)
                if not desbloquear
                else rede.buscar(url_busca, desbloquear=True))
    except rede.ErroDeColeta:
        return None

    padrao = re.compile(filtro_href) if filtro_href else None
    for href, rotulo in rede.links_de(html, base or url_busca):
        if padrao and not padrao.search(href):
            continue
        if rotulo and parece_o_mesmo(rotulo, candidato.nome):
            return href, rotulo
        if rotulo and candidato.nome_urna and parece_o_mesmo(rotulo, candidato.nome_urna):
            return href, rotulo
    return None


def numero_perto_de(texto: str, *rotulos: str) -> tuple[float, str] | None:
    """Acha um numero associado a um rotulo, antes ou depois dele.

    Cobre as duas formas usuais de escrita: "Processos: 3" e "3 processos".
    """
    for rotulo in rotulos:
        escapado = re.escape(rotulo)
        for padrao in (rf"{escapado}\s*[:\-–]?\s*(\d[\d.]*)",
                       rf"(\d[\d.]*)\s+{escapado}"):
            achado = re.search(padrao, texto, re.IGNORECASE)
            if achado:
                bruto = achado.group(1).replace(".", "")
                try:
                    return float(bruto), achado.group(0).strip()
                except ValueError:
                    continue
    return None


def percentual_perto_de(texto: str, *rotulos: str) -> tuple[float, str] | None:
    for rotulo in rotulos:
        escapado = re.escape(rotulo)
        for padrao in (rf"{escapado}[^0-9%]{{0,40}}?(\d{{1,3}}(?:[.,]\d+)?)\s*%",
                       rf"(\d{{1,3}}(?:[.,]\d+)?)\s*%[^0-9%]{{0,40}}?{escapado}"):
            achado = re.search(padrao, texto, re.IGNORECASE)
            if achado:
                try:
                    return float(achado.group(1).replace(",", ".")), achado.group(0).strip()
                except ValueError:
                    continue
    return None


def linha_da_tabela(html: str, candidato: Candidato) -> tuple[list[str], list[str]] | None:
    """Procura o candidato nas tabelas da pagina; devolve (cabecalho, linha)."""
    for tabela in rede.tabelas_de(html):
        if len(tabela) < 2:
            continue
        cabecalho = tabela[0]
        for linha in tabela[1:]:
            for celula in linha[:3]:  # o nome costuma vir nas primeiras colunas
                if celula and (parece_o_mesmo(celula, candidato.nome)
                               or (candidato.nome_urna
                                   and parece_o_mesmo(celula, candidato.nome_urna))):
                    return cabecalho, linha
    return None


def valor_da_coluna(cabecalho: list[str], linha: list[str], *rotulos: str) -> str | None:
    for indice, titulo in enumerate(cabecalho):
        for rotulo in rotulos:
            if rotulo.lower() in (titulo or "").lower() and indice < len(linha):
                return linha[indice] or None
    return None


def montar(url: str, **parametros) -> str:
    partes = urllib.parse.urlsplit(url)
    consulta = dict(urllib.parse.parse_qsl(partes.query))
    consulta.update({k: v for k, v in parametros.items() if v})
    return urllib.parse.urlunsplit(
        partes._replace(query=urllib.parse.urlencode(consulta))
    )
