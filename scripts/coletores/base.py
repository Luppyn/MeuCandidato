"""Contrato comum dos coletores.

Cada coletor recebe candidatos e devolve `Registro`s no mesmo formato que
scripts/importar_externos.py le. Isso mantem uma unica porta de entrada de
dados na base, venha o registro de um coletor deste repositorio, de um fluxo do
n8n ou de uma planilha preenchida a mao.
"""

from __future__ import annotations

import dataclasses
from datetime import datetime, timezone


@dataclasses.dataclass
class Candidato:
    """O minimo que um coletor precisa saber sobre quem esta pesquisando."""
    chave: str
    nome: str
    nome_urna: str = ""
    uf: str = ""
    cargo: str = ""
    partido: str = ""
    ano: int = 0
    nascimento: str = ""
    processo: str = ""

    @classmethod
    def de_linha(cls, linha) -> "Candidato":
        return cls(
            chave=linha["chave"],
            nome=linha["nm_candidato"] or "",
            nome_urna=linha["nm_urna"] or "",
            uf=linha["sg_uf"] or "",
            cargo=linha["ds_cargo"] or "",
            partido=linha["sg_partido"] or "",
            ano=linha["ano_eleicao"] or 0,
            nascimento=linha["dt_nascimento"] or "",
            processo=cls._campo(linha, "nr_processo"),
        )

    @staticmethod
    def _campo(linha, nome: str) -> str:
        """Lê uma coluna que pode não existir em bases antigas."""
        try:
            return linha[nome] or ""
        except (IndexError, KeyError):
            return ""


@dataclasses.dataclass
class Registro:
    """Uma celula da planilha vinda de fora do TSE."""
    chave: str
    fonte: str
    campo: str
    valor: str
    valor_num: float | None = None
    url: str | None = None
    observacao: str | None = None
    coletado_em: str = ""

    def para_dicionario(self) -> dict:
        dados = dataclasses.asdict(self)
        if not dados["coletado_em"]:
            dados["coletado_em"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        return dados


class Coletor:
    """Base dos coletores.

    Subclasses definem `slug`, `nome`, `automatico` e implementam `coletar`.
    `automatico = False` sinaliza uma fonte que nao da para raspar de forma
    confiavel (captcha, sessao com token, termo de uso que exige consulta
    individual). Esses coletores nao raspam nada: apenas produzem o link de
    consulta manual, para que a coluna traga um caminho util em vez de ficar
    muda.
    """

    slug: str = ""
    nome: str = ""
    automatico: bool = True
    observacao_padrao: str = ""

    def coletar(self, candidato: Candidato) -> list[Registro]:
        raise NotImplementedError

    def aviso_inicial(self) -> str | None:
        """Pendência que impede a coleta — chave ausente, arquivo fora do ar.

        Anunciada antes do laço, para não ser sobrescrita pela linha de
        progresso, que se reescreve sobre si mesma.
        """
        return getattr(self, "aviso", None)

    # -- utilitarios -------------------------------------------------------
    def registro(self, candidato: Candidato, campo: str, valor: str, **extra) -> Registro:
        extra.setdefault("observacao", self.observacao_padrao or None)
        return Registro(chave=candidato.chave, fonte=self.slug, campo=campo,
                        valor=valor, **extra)


# ---------------------------------------------------------------------------
# Comparacao de nomes
#
# Sem CPF nas bases abertas do TSE, cruzar candidato com fonte externa depende
# do nome - que aparece grafado de formas diferentes em cada site. As funcoes
# abaixo sao deliberadamente conservadoras: e melhor deixar a celula vazia com
# o link de conferencia do que atribuir a alguem um processo que nao e dele.
# ---------------------------------------------------------------------------

import unicodedata  # noqa: E402

PARTICULAS = {"DA", "DE", "DO", "DAS", "DOS", "E", "DI", "DU", "D", "LA", "VAN", "VON"}


def normalizar(texto: str | None) -> str:
    if not texto:
        return ""
    sem_acento = unicodedata.normalize("NFKD", texto)
    sem_acento = "".join(c for c in sem_acento if not unicodedata.combining(c))
    limpo = "".join(c if c.isalnum() or c.isspace() else " " for c in sem_acento)
    return " ".join(limpo.upper().split())


def partes_do_nome(nome: str) -> list[str]:
    return [p for p in normalizar(nome).split() if p not in PARTICULAS and len(p) > 1]


def parece_o_mesmo(nome_a: str, nome_b: str) -> bool:
    """Heuristica conservadora de identidade por nome.

    Exige que o primeiro nome e o ultimo sobrenome coincidam e que ao menos
    metade dos demais elementos do nome mais curto apareca no outro.
    """
    a, b = partes_do_nome(nome_a), partes_do_nome(nome_b)
    if len(a) < 2 or len(b) < 2:
        return False
    if a[0] != b[0] or a[-1] != b[-1]:
        return False
    menor, maior = (a, b) if len(a) <= len(b) else (b, a)
    comuns = sum(1 for parte in menor if parte in maior)
    return comuns >= max(2, (len(menor) + 1) // 2)
