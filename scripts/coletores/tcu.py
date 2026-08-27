"""TCU — contas julgadas irregulares (dados abertos, em massa).

Esta é a melhor fonte pública para a coluna "ficha suja", e por um motivo
direto: a lista de responsáveis com contas julgadas irregulares e possível
implicação eleitoral é exatamente a que o TCU entrega ao TSE a cada eleição,
por força da Lei da Ficha Limpa (LC 135/2010).

Diferente do CNIA, não é consulta individual com captcha: é arquivo aberto,
baixado inteiro de uma vez. O coletor baixa a lista uma única vez por execução,
indexa por nome e casa com os candidatos em memória — o que significa uma
requisição para a base inteira, em vez de uma por candidato.

Quatro listas são consideradas:

    contas_irregulares_eleitoral  contas irregulares com implicação eleitoral
    contas_irregulares            Cadirreg completo
    inabilitados                  inabilitados para função pública
    inidoneos                     licitantes declarados inidôneos
"""

from __future__ import annotations

import csv
import io

from . import rede
from ._config import config_de
from .base import Candidato, Coletor as Base, Registro, normalizar, parece_o_mesmo

ROTULOS = {
    "contas_irregulares_eleitoral": "contas irregulares com implicação eleitoral",
    "contas_irregulares": "contas julgadas irregulares",
    "inabilitados": "inabilitado para função pública",
    "inidoneos": "licitante inidôneo",
}

# Nomes prováveis da coluna de nome nos arquivos do TCU.
COLUNAS_NOME = ("nome", "nome_responsavel", "nome do responsável", "responsavel",
                "nome_completo", "nome da pessoa", "razao_social", "nome_sancionado")


class Coletor(Base):
    slug = "tcu"
    nome = "TCU — contas julgadas irregulares"
    observacao_padrao = "Lista aberta do TCU, a mesma entregue ao TSE para fins de inelegibilidade."

    def __init__(self):
        self.cfg = config_de("tcu")
        self._indice: dict[str, list[tuple[str, str, dict]]] | None = None
        self._carregadas: list[str] = []
        self._falharam: list[str] = []

    # -- carga única -------------------------------------------------------
    def indice(self) -> dict[str, list[tuple[str, str, dict]]]:
        """Baixa as listas e indexa por primeiro+último nome.

        A chave do índice é grosseira de propósito: ela só reduz o universo a
        comparar. A decisão de identidade fica com `parece_o_mesmo`.
        """
        if self._indice is not None:
            return self._indice

        self._indice = {}
        for lista, url in (self.cfg.get("arquivos") or {}).items():
            try:
                texto = rede.buscar(url)
            except rede.ErroDeColeta as erro:
                self._falharam.append(lista)
                print(f"  {self.slug}: não foi possível baixar '{lista}' ({erro})")
                continue

            linhas = self.ler_tabela(texto)
            if not linhas:
                self._falharam.append(lista)
                print(f"  {self.slug}: '{lista}' veio vazia ou em formato não reconhecido")
                continue

            self._carregadas.append(lista)

            for linha in linhas:
                nome = self.nome_da_linha(linha)
                if not nome:
                    continue
                partes = normalizar(nome).split()
                if len(partes) < 2:
                    continue
                chave = f"{partes[0]} {partes[-1]}"
                self._indice.setdefault(chave, []).append((lista, nome, linha))

            print(f"  {self.slug}: '{lista}' com {len(linhas)} registro(s)")

        return self._indice

    @staticmethod
    def ler_tabela(texto: str) -> list[dict]:
        """Lê CSV do TCU tolerando separador e codificação variáveis."""
        amostra = texto[:5000]
        separador = ";" if amostra.count(";") > amostra.count(",") else ","
        try:
            leitor = csv.DictReader(io.StringIO(texto), delimiter=separador)
            linhas = [linha for linha in leitor if any(linha.values())]
        except csv.Error:
            return []
        return linhas

    @staticmethod
    def nome_da_linha(linha: dict) -> str:
        for coluna, valor in linha.items():
            if coluna and any(alvo in coluna.strip().lower() for alvo in COLUNAS_NOME):
                if isinstance(valor, str) and valor.strip():
                    return valor.strip()
        return ""

    # -- coleta ------------------------------------------------------------
    def coletar(self, candidato: Candidato) -> list[Registro]:
        indice = self.indice()
        if not indice:
            return []

        partes = normalizar(candidato.nome).split()
        if len(partes) < 2:
            return []
        chave = f"{partes[0]} {partes[-1]}"

        encontrados: list[tuple[str, str]] = []
        for lista, nome_na_lista, _linha in indice.get(chave, []):
            if parece_o_mesmo(nome_na_lista, candidato.nome):
                encontrados.append((lista, nome_na_lista))

        url = self.cfg.get("consulta_manual", "https://sites.tcu.gov.br/contas-julgadas-irregulares/")

        if not encontrados:
            # "Nada consta" só pode ser dito sobre as listas que realmente
            # baixaram. As que falharam entram como ressalva explícita, para
            # que uma falha de rede não vire uma afirmação sobre a pessoa.
            baixadas = "; ".join(ROTULOS.get(x, x) for x in self._carregadas)
            ressalva = ""
            if self._falharam:
                faltando = "; ".join(ROTULOS.get(x, x) for x in self._falharam)
                ressalva = (f" ATENÇÃO: não foi possível baixar {faltando} nesta "
                            f"execução, então esta resposta não cobre essa(s) lista(s).")
            return [self.registro(
                candidato, "contas", "Nada consta", valor_num=0.0, url=url,
                observacao=f"{self.observacao_padrao} Consultadas: {baixadas}. "
                           f"Nome não aparece em nenhuma delas. Homônimos não podem "
                           f"ser separados sem CPF.{ressalva}",
            )]

        listas = sorted({ROTULOS.get(lista, lista) for lista, _ in encontrados})
        nomes = sorted({nome for _, nome in encontrados})
        eleitoral = any(lista == "contas_irregulares_eleitoral" for lista, _ in encontrados)

        return [self.registro(
            candidato,
            "contas",
            ("Consta com implicação eleitoral" if eleitoral
             else f"Consta: {'; '.join(listas)}"),
            valor_num=float(len(encontrados)), url=url,
            observacao=(f"{self.observacao_padrao} Listas: {'; '.join(listas)}. "
                        f"Nome na lista: {'; '.join(nomes)}. "
                        f"ATENÇÃO: a correspondência é por nome, sem CPF — confirme na "
                        f"fonte antes de tratar como certo. A inelegibilidade em si é "
                        f"decidida pela Justiça Eleitoral, caso a caso."),
        )]
