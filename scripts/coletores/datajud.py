"""CNJ — DataJud (API pública nacional de processos).

Base Nacional de Dados do Poder Judiciário: 80 milhões de processos, todos os
tribunais, API REST pública e gratuita.

**Limite decisivo:** a busca documentada é por número de processo ou por
classe + tribunal. Se a resposta não trouxer nome das partes, o DataJud **não
serve para descobrir os processos de uma pessoa** — serve para detalhar um
processo cujo número já se conhece. O coletor lê nomes de parte quando eles
aparecem no retorno (`partes`, `poloAtivo`, `poloPassivo`) e ignora o assunto
quando não aparecem; é o teste real que decide, e ele depende de uma chave.

A API é Elasticsearch, então aceita consulta em lote e paginação. Isso muda a
economia da coleta: em vez de uma requisição por candidato, os números de
processo vão em blocos de até 500 numa única `terms` query, com `search_after`
quando o resultado passa de uma página. Para uma UF com mil candidatos, são
duas ou três requisições em vez de mil.

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
from .base import Candidato, Coletor as Base, Registro, parece_o_mesmo

# A API é Elasticsearch: aceita lote e paginação.
TAMANHO_DO_LOTE = 500      # números de processo por `terms` query
TAMANHO_DA_PAGINA = 500    # resultados por página (o teto documentado é 10.000)

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


def nomes_das_partes(processo: dict) -> list[str]:
    """Extrai nomes de parte do retorno, se eles existirem.

    A documentação da API pública não promete esse campo, e o leiaute varia
    entre tribunais. A função procura nos formatos conhecidos e devolve lista
    vazia quando não acha — sem tratar ausência como erro.
    """
    nomes: list[str] = []

    def recolher(valor):
        if isinstance(valor, dict):
            for chave in ("nome", "nomeParte", "nomeRazaoSocial"):
                if isinstance(valor.get(chave), str) and valor[chave].strip():
                    nomes.append(valor[chave].strip())
                    return
            for interno in valor.values():
                recolher(interno)
        elif isinstance(valor, list):
            for item in valor:
                recolher(item)

    for campo in ("partes", "poloAtivo", "poloPassivo", "polos", "dadosBasicos"):
        if campo in processo:
            recolher(processo[campo])

    vistos, unicos = set(), []
    for nome in nomes:
        if nome.upper() not in vistos:
            vistos.add(nome.upper())
            unicos.append(nome)
    return unicos


class Coletor(Base):
    slug = "datajud"
    nome = "CNJ — DataJud"
    observacao_padrao = "Movimentação lida da API pública do DataJud (CNJ)."

    def __init__(self):
        self.cfg = config_de("datajud")
        self.aviso = falta_chave("datajud")
        self._processos: dict[str, dict] = {}

    # -- consulta em lote --------------------------------------------------
    def preparar(self, candidatos) -> None:
        """Busca todos os processos de uma vez, agrupados por tribunal."""
        if self.aviso:
            return

        por_tribunal: dict[str, list[str]] = {}
        for candidato in candidatos:
            destino = alias_do_tribunal(getattr(candidato, "processo", "") or "")
            if destino:
                alias, limpo = destino
                por_tribunal.setdefault(alias, []).append(limpo)

        if not por_tribunal:
            return

        total_pedidos = sum(len(n) for n in por_tribunal.values())
        requisicoes = 0
        for alias, numeros in por_tribunal.items():
            for inicio in range(0, len(numeros), TAMANHO_DO_LOTE):
                bloco = numeros[inicio:inicio + TAMANHO_DO_LOTE]
                requisicoes += self._buscar_lote(alias, bloco)

        print(f"  {self.slug}: {len(self._processos)} de {total_pedidos} processo(s) "
              f"localizado(s) em {requisicoes} requisição(ões)")

    def _buscar_lote(self, alias: str, numeros: list[str]) -> int:
        """Uma `terms` query por bloco, paginada com search_after."""
        url = self.cfg["base"] + self.cfg["endpoint_tribunal"].format(tribunal=alias)
        cabecalhos = {**cabecalho_de("datajud"), "Content-Type": "application/json"}

        requisicoes = 0
        depois = None
        while True:
            consulta = {
                "size": min(len(numeros), TAMANHO_DA_PAGINA),
                "query": {"terms": {"numeroProcesso": numeros}},
                # search_after exige ordenação estável e única.
                "sort": [{"numeroProcesso.keyword": "asc"}],
            }
            if depois:
                consulta["search_after"] = depois

            try:
                resposta = rede.buscar_json(
                    url, corpo=json.dumps(consulta).encode("utf-8"),
                    cabecalhos=cabecalhos,
                )
            except rede.ErroDeColeta as erro:
                print(f"  {self.slug}: lote de {alias} falhou ({erro})")
                return requisicoes
            requisicoes += 1

            acertos = (resposta.get("hits") or {}).get("hits") or []
            if not acertos:
                return requisicoes

            for acerto in acertos:
                fonte = acerto.get("_source") or {}
                numero = str(fonte.get("numeroProcesso") or "")
                if numero:
                    self._processos[numero] = fonte

            if len(acertos) < consulta["size"]:
                return requisicoes
            depois = acertos[-1].get("sort")
            if not depois:
                return requisicoes

    # -- leitura -----------------------------------------------------------
    def coletar(self, candidato: Candidato) -> list[Registro]:
        numero = getattr(candidato, "processo", "") or ""
        if not numero or self.aviso:
            return []

        destino = alias_do_tribunal(numero)
        if not destino:
            return []
        alias, limpo = destino

        processo = self._processos.get(limpo)
        if not processo:
            return []

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

        # Se o retorno trouxer partes, confirma que o processo é mesmo deste
        # candidato — e passa a valer como identificação, não só como número.
        partes = nomes_das_partes(processo)
        if partes:
            bate = any(parece_o_mesmo(nome, candidato.nome) for nome in partes)
            registros.append(self.registro(
                candidato, "registro_partes",
                "confere com o candidato" if bate else "partes não conferem",
                url=url_publica,
                observacao=(f"{self.observacao_padrao} Partes no retorno: "
                            f"{'; '.join(partes[:6])}."
                            + ("" if bate else " O nome do candidato não aparece "
                                              "entre as partes — verifique o número.")),
            ))

        assuntos = [a.get("nome") for a in (processo.get("assuntos") or []) if a.get("nome")]
        if assuntos:
            registros.append(self.registro(
                candidato, "registro_assuntos", "; ".join(assuntos[:4]),
                url=url_publica, observacao=self.observacao_padrao,
            ))
        return registros
