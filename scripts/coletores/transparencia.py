"""Portal da Transparência — sanções e expulsões (API oficial).

Fonte oficial do governo federal, com API REST documentada em Swagger e chave
gratuita liberada no ato do cadastro. Cobre pessoa física, o que a torna útil
aqui — e, ao contrário do CNIA, não tem captcha nem limite de consulta manual.

Quatro cadastros entram na planilha:

    CEIS       inidôneas e suspensas de licitar com a administração
    CNEP       punidas pela Lei Anticorrupção
    CEAF       expulsões da administração federal (demissão, cassação de
               aposentadoria, destituição de cargo em comissão)
    Leniência  acordos de leniência firmados com a CGU

O CEAF é o mais próximo do que se procura em "ficha suja" para pessoa física:
são punições administrativas efetivamente aplicadas a servidores federais.

Sem a chave em CHAVE_PORTAL_TRANSPARENCIA, o coletor não inventa nada: avisa
como obtê-la e devolve lista vazia.
"""

from __future__ import annotations

import urllib.parse

from . import rede
from ._config import cabecalho_de, config_de, falta_chave
from .base import Candidato, Coletor as Base, Registro, parece_o_mesmo

# Campo na planilha -> (consulta na config, rótulo legível)
CADASTROS = [
    ("ceaf", "ceaf", "expulsão da administração federal"),
    ("ceis", "ceis", "inidoneidade/suspensão (CEIS)"),
    ("cnep", "cnep", "punição pela Lei Anticorrupção (CNEP)"),
    ("leniencia", "leniencia", "acordo de leniência"),
]

PAGINAS_MAXIMAS = 3


class Coletor(Base):
    slug = "transparencia"
    nome = "Portal da Transparência — sanções (CGU)"
    observacao_padrao = "Consulta à API oficial do Portal da Transparência."

    def __init__(self):
        self.cfg = config_de("portal_transparencia")
        self.aviso = falta_chave("portal_transparencia")

    def consultar(self, caminho: str, nome: str) -> tuple[list[dict], bool]:
        """Percorre as páginas de um cadastro.

        Devolve (registros, consultou), onde `consultou` diz se a API
        respondeu. A distinção é o ponto central: "consultei e não achei nada"
        é informação; "não consegui consultar" é ausência de informação. As
        duas não podem virar a mesma célula.
        """
        resultados: list[dict] = []
        consultou = False
        for pagina in range(1, PAGINAS_MAXIMAS + 1):
            url = self.cfg["base"] + caminho.format(
                nome=urllib.parse.quote(nome), pagina=pagina
            )
            try:
                dados = rede.buscar_json(url, cabecalhos=cabecalho_de("portal_transparencia"))
            except rede.ErroDeColeta:
                return resultados, consultou
            consultou = True
            if not isinstance(dados, list) or not dados:
                break
            resultados += dados
            if len(dados) < 15:  # página incompleta: acabou
                break
        return resultados, consultou

    @staticmethod
    def nome_do_registro(registro: dict) -> str:
        """Acha o nome da pessoa sancionada em qualquer um dos formatos."""
        for caminho in (("pessoa", "nome"), ("sancionado", "nome"), ("nome",),
                        ("pessoa", "nomePessoaFisica"), ("nomeSancionado",)):
            valor = registro
            for parte in caminho:
                valor = valor.get(parte) if isinstance(valor, dict) else None
                if valor is None:
                    break
            if isinstance(valor, str) and valor.strip():
                return valor
        return ""

    def coletar(self, candidato: Candidato) -> list[Registro]:
        if self.aviso:
            return []

        achados: list[str] = []
        detalhes: list[str] = []
        consultados: list[str] = []
        falharam: list[str] = []

        for campo, consulta, rotulo in CADASTROS:
            caminho = self.cfg["consultas"].get(consulta)
            if not caminho:
                continue

            # A API filtra por nome, mas de forma ampla: confere-se cada
            # resultado antes de atribuir a sanção a este candidato.
            registros_brutos, consultou = self.consultar(caminho, candidato.nome)
            (consultados if consultou else falharam).append(consulta.upper())

            for registro in registros_brutos:
                nome_sancionado = self.nome_do_registro(registro)
                if not parece_o_mesmo(nome_sancionado, candidato.nome):
                    continue
                achados.append(rotulo)
                descricao = (registro.get("tipoSancao", {}) or {}).get("descricaoResumida") \
                    or registro.get("descricaoFundamentacao") \
                    or registro.get("tipoPunicao") \
                    or rotulo
                detalhes.append(f"{rotulo}: {descricao}")
                break  # uma ocorrência por cadastro basta para a planilha

        url_consulta = "https://portaldatransparencia.gov.br/sancoes/consulta?cadastro=1"

        if not consultados:
            # Nenhum cadastro respondeu. Não há o que afirmar: devolver
            # "Nada encontrado" aqui seria apresentar uma falha de rede como
            # se fosse resultado de consulta.
            return []

        if not achados:
            # Agora sim: a consulta foi feita, na fonte oficial, e não
            # retornou sanção. Isso é informação.
            ressalva = (f" Não foi possível consultar {', '.join(falharam)} nesta "
                        f"execução." if falharam else "")
            return [self.registro(
                candidato, "sancoes", "Nada encontrado", valor_num=0.0,
                url=url_consulta,
                observacao=f"{self.observacao_padrao} Consultados "
                           f"{', '.join(consultados)} pelo nome completo. Cobre apenas "
                           f"a esfera federal.{ressalva}",
            )]

        return [
            self.registro(
                candidato, "sancoes",
                f"{len(achados)} sanção(ões): {', '.join(achados)}",
                valor_num=float(len(achados)), url=url_consulta,
                observacao=f"{self.observacao_padrao} " + " | ".join(detalhes),
            )
        ]
