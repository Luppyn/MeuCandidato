#!/usr/bin/env python3
"""Servidor do MeuCandidato.

Serve os arquivos estaticos da pasta web/ e uma API JSON de leitura sobre o
SQLite. Usa apenas a biblioteca padrao do Python - nenhum framework, nenhuma
dependencia para instalar.

    python3 servidor.py                 # http://localhost:8000
    python3 servidor.py --porta 9000 --host 0.0.0.0

A conexao com o banco e aberta em modo somente leitura: o servidor nao tem
como alterar nenhum dado. Toda escrita passa pelos scripts de importacao, que
registram origem, data e SHA-256 do arquivo importado.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import mimetypes
import pathlib
import re
import sqlite3
import urllib.parse
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import banco

RAIZ = pathlib.Path(__file__).resolve().parent
WEB = RAIZ / "web"
CONFIG_COLUNAS = json.loads((RAIZ / "config" / "colunas.json").read_text(encoding="utf-8"))
CONFIG_LINKS = json.loads((RAIZ / "config" / "links.json").read_text(encoding="utf-8"))

LIMITE_PADRAO = 100
LIMITE_MAXIMO = 1000
LIMITE_CSV = 20000

# Colunas do candidato que a API pode devolver e por quais e permitido ordenar.
COLUNAS_CANDIDATO = [
    "chave", "ano_eleicao", "nr_candidato", "nr_processo", "nm_candidato", "nm_urna",
    "nm_social",
    "cd_cargo", "ds_cargo", "sg_uf", "sg_ue", "nm_ue", "nr_partido", "sg_partido",
    "nm_partido", "sg_federacao", "nm_federacao", "nm_coligacao", "ds_composicao_coligacao",
    "ds_situacao_candidatura", "ds_detalhe_situacao_cand", "ds_situacao_candidato_tot",
    "ds_genero", "dt_nascimento", "nr_idade_data_posse", "ds_estado_civil", "ds_cor_raca",
    "ds_ocupacao", "ds_grau_instrucao", "ds_nacionalidade", "nm_municipio_nascimento",
    "sg_uf_nascimento", "st_reeleicao", "vr_despesa_max_campanha", "qtd_bens",
    "total_bens", "url_divulgacand", "url_foto",
]
ORDENACOES = set(COLUNAS_CANDIDATO)


class ErroDeUso(Exception):
    """Parametro invalido enviado pelo cliente."""


# ----------------------------------------------------------------------------
# Consultas
# ----------------------------------------------------------------------------

def filtro_para_sql(p: dict) -> tuple[str, list]:
    """Traduz os parametros da consulta em WHERE + valores.

    Cargo e UF sao obrigatorios: a tela inicial nao carrega nada em aberto, e a
    API segue a mesma regra para nao virar um dump da base inteira por acidente.
    """
    condicoes, valores = [], []

    ano = p.get("ano")
    if ano:
        condicoes.append("c.ano_eleicao = ?")
        valores.append(int(ano))

    cargo = p.get("cargo")
    if not cargo:
        raise ErroDeUso("informe o cargo")
    condicoes.append("c.cd_cargo = ?")
    valores.append(int(cargo))

    uf = (p.get("uf") or "").strip().upper()
    if not uf:
        raise ErroDeUso("informe a UF")
    condicoes.append("c.sg_uf = ?")
    valores.append(uf)

    ue = (p.get("ue") or "").strip().upper()
    if ue:
        condicoes.append("c.sg_ue = ?")
        valores.append(ue)

    partido = (p.get("partido") or "").strip().upper()
    if partido:
        condicoes.append("(c.sg_partido = ? OR c.nr_partido = ?)")
        valores += [partido, partido]

    nome = (p.get("nome") or "").strip()
    if nome:
        condicoes.append("c.nm_busca LIKE ?")
        valores.append(f"%{banco.normalizar(nome)}%")

    situacao = (p.get("situacao") or "").strip()
    if situacao:
        condicoes.append("c.ds_situacao_candidatura = ?")
        valores.append(situacao)

    return " AND ".join(condicoes), valores


def externos_por_chave(con, chaves: list[str]) -> dict[str, dict]:
    """Carrega os dados externos de um lote de candidatos de uma vez so."""
    if not chaves:
        return {}
    resultado: dict[str, dict] = {c: {} for c in chaves}
    # SQLite limita o numero de parametros; consulta em blocos.
    for inicio in range(0, len(chaves), 500):
        bloco = chaves[inicio:inicio + 500]
        marcadores = ", ".join("?" * len(bloco))
        for linha in con.execute(
            f"SELECT chave, fonte, campo, valor, valor_num, url, observacao, coletado_em "
            f"FROM dado_externo WHERE chave IN ({marcadores})",
            bloco,
        ):
            resultado[linha["chave"]][f"{linha['fonte']}.{linha['campo']}"] = {
                "valor": linha["valor"],
                "valor_num": linha["valor_num"],
                "url": linha["url"],
                "observacao": linha["observacao"],
                "coletado_em": linha["coletado_em"],
            }
    return resultado


def consultar_candidatos(con, p: dict, limite: int) -> dict:
    where, valores = filtro_para_sql(p)

    ordem = p.get("ordem") or "nm_urna"
    if ordem not in ORDENACOES:
        raise ErroDeUso(f"ordenacao invalida: {ordem}")
    direcao = "DESC" if (p.get("direcao") or "").lower() == "desc" else "ASC"

    pagina = max(1, int(p.get("pagina") or 1))
    deslocamento = (pagina - 1) * limite

    total = con.execute(
        f"SELECT COUNT(*) AS c FROM candidato c WHERE {where}", valores
    ).fetchone()["c"]

    colunas = ", ".join(f"c.{c}" for c in COLUNAS_CANDIDATO)
    linhas = con.execute(
        f"SELECT {colunas} FROM candidato c WHERE {where} "
        f"ORDER BY c.{ordem} {direcao}, c.nm_urna ASC LIMIT ? OFFSET ?",
        valores + [limite, deslocamento],
    ).fetchall()

    registros = [dict(linha) for linha in linhas]
    externos = externos_por_chave(con, [r["chave"] for r in registros])
    for registro in registros:
        registro["externos"] = externos.get(registro["chave"], {})

    return {
        "total": total,
        "pagina": pagina,
        "limite": limite,
        "paginas": (total + limite - 1) // limite if limite else 1,
        "candidatos": registros,
    }


def consultar_opcoes(con) -> dict:
    def lista(sql, *args):
        return [dict(l) for l in con.execute(sql, args)]

    return {
        "anos": [l["ano_eleicao"] for l in con.execute(
            "SELECT DISTINCT ano_eleicao FROM candidato ORDER BY ano_eleicao DESC")],
        "cargos": lista(
            "SELECT DISTINCT cd_cargo AS codigo, ds_cargo AS nome, ano_eleicao AS ano "
            "FROM candidato WHERE ds_cargo IS NOT NULL ORDER BY cd_cargo"),
        "ufs": lista(
            "SELECT DISTINCT sg_uf AS sigla, cd_cargo AS cargo, ano_eleicao AS ano "
            "FROM candidato WHERE sg_uf IS NOT NULL ORDER BY sg_uf"),
        "unidades": lista(
            "SELECT DISTINCT sg_ue AS codigo, nm_ue AS nome, sg_uf AS uf, "
            "cd_cargo AS cargo, ano_eleicao AS ano FROM candidato "
            "WHERE sg_ue IS NOT NULL ORDER BY nm_ue"),
        "partidos": lista(
            "SELECT DISTINCT sg_partido AS sigla, nm_partido AS nome "
            "FROM candidato WHERE sg_partido IS NOT NULL ORDER BY sg_partido"),
        "situacoes": [l["ds_situacao_candidatura"] for l in con.execute(
            "SELECT DISTINCT ds_situacao_candidatura FROM candidato "
            "WHERE ds_situacao_candidatura IS NOT NULL ORDER BY 1")],
    }


def consultar_candidato(con, chave: str) -> dict | None:
    colunas = ", ".join(f"c.{c}" for c in COLUNAS_CANDIDATO)
    linha = con.execute(
        f"SELECT {colunas} FROM candidato c WHERE c.chave = ?", (chave,)
    ).fetchone()
    if linha is None:
        return None

    candidato = dict(linha)
    candidato["bens"] = [dict(b) for b in con.execute(
        "SELECT nr_ordem, cd_tipo, ds_tipo, ds_bem, vr_bem, dt_atualizacao "
        "FROM bem WHERE candidato_id = (SELECT id FROM candidato WHERE chave = ?) "
        "ORDER BY nr_ordem", (chave,))]
    candidato["externos"] = externos_por_chave(con, [chave]).get(chave, {})
    return candidato


def consultar_fontes(con) -> list[dict]:
    return [dict(l) for l in con.execute(
        "SELECT slug, nome, url, categoria, tem_api, descricao, url_consulta_manual, "
        "licenca, atualizado_em FROM fonte ORDER BY categoria, nome")]


def consultar_procedencia(con, limite: int = 200) -> dict:
    importacoes = [dict(l) for l in con.execute(
        "SELECT id, iniciado_em, concluido_em, tipo, origem, arquivo, sha256, bytes, "
        "linhas_lidas, linhas_gravadas, observacao FROM importacao "
        "ORDER BY id DESC LIMIT ?", (limite,))]
    return {
        "origem_base": banco.ler_meta(con, "origem_base", "desconhecida"),
        "aviso_base": banco.ler_meta(con, "aviso_base"),
        "atualizado_em": banco.ler_meta(con, "atualizado_em"),
        "externos_atualizados_em": banco.ler_meta(con, "externos_atualizados_em"),
        "versao_esquema": banco.ler_meta(con, "versao_esquema"),
        "totais": {
            "candidatos": con.execute("SELECT COUNT(*) c FROM candidato").fetchone()["c"],
            "bens": con.execute("SELECT COUNT(*) c FROM bem").fetchone()["c"],
            "dados_externos": con.execute("SELECT COUNT(*) c FROM dado_externo").fetchone()["c"],
        },
        "cobertura_externa": [dict(l) for l in con.execute(
            "SELECT fonte, campo, COUNT(*) AS registros, MAX(coletado_em) AS ultimo "
            "FROM dado_externo GROUP BY fonte, campo ORDER BY fonte, campo")],
        "importacoes": importacoes,
    }


def montar_csv(dados: dict) -> bytes:
    colunas = [c for c in COLUNAS_CANDIDATO if c not in ("url_foto",)]
    externas = [c["id"] for c in CONFIG_COLUNAS["colunas"] if c["tipo"] == "externo"]

    buffer = io.StringIO()
    escritor = csv.writer(buffer, delimiter=";", quoting=csv.QUOTE_MINIMAL,
                          lineterminator="\r\n")
    escritor.writerow(colunas + externas)
    for candidato in dados["candidatos"]:
        linha = [candidato.get(c, "") for c in colunas]
        for chave in externas:
            item = candidato["externos"].get(chave)
            linha.append(item["valor"] if item else "")
        escritor.writerow(["" if v is None else v for v in linha])
    return buffer.getvalue().encode("utf-8-sig")


# ----------------------------------------------------------------------------
# HTTP
# ----------------------------------------------------------------------------

ROTA_CANDIDATO = re.compile(r"^/api/candidato/([A-Za-z0-9\-]{1,80})$")


class Manipulador(BaseHTTPRequestHandler):
    server_version = "MeuCandidato"
    sys_version = ""
    protocol_version = "HTTP/1.1"

    # ---------------------------------------------------------------- respostas
    def _responder(self, codigo, corpo: bytes, tipo: str, cache: str = "no-store"):
        self.send_response(codigo)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(corpo)))
        self.send_header("Cache-Control", cache)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(corpo)

    def _json(self, dados, codigo=HTTPStatus.OK):
        corpo = json.dumps(dados, ensure_ascii=False).encode("utf-8")
        self._responder(codigo, corpo, "application/json; charset=utf-8")

    def _erro(self, codigo, mensagem):
        self._json({"erro": mensagem}, codigo)

    # ------------------------------------------------------------------- rotas
    def do_HEAD(self):  # noqa: N802
        self.do_GET()

    def do_GET(self):  # noqa: N802
        partes = urllib.parse.urlsplit(self.path)
        caminho = urllib.parse.unquote(partes.path)
        consulta = {k: v[0] for k, v in urllib.parse.parse_qs(partes.query).items()}

        try:
            if caminho.startswith("/api/"):
                return self._api(caminho, consulta)
            return self._estatico(caminho)
        except ErroDeUso as erro:
            return self._erro(HTTPStatus.BAD_REQUEST, str(erro))
        except ValueError as erro:
            return self._erro(HTTPStatus.BAD_REQUEST, f"parametro invalido: {erro}")
        except sqlite3.Error as erro:
            return self._erro(HTTPStatus.INTERNAL_SERVER_ERROR, f"erro no banco: {erro}")

    def _api(self, caminho, consulta):
        con = self.server.conexao

        if caminho == "/api/saude":
            return self._json({"situacao": "ok", "banco": str(banco.caminho_banco())})

        if caminho == "/api/opcoes":
            return self._json(consultar_opcoes(con))

        if caminho == "/api/colunas":
            return self._json({"colunas": CONFIG_COLUNAS["colunas"]})

        if caminho == "/api/fontes":
            return self._json({"fontes": consultar_fontes(con),
                               "links": {k: v for k, v in CONFIG_LINKS.items()
                                         if not k.startswith("_")}})

        if caminho == "/api/procedencia":
            return self._json(consultar_procedencia(con))

        if caminho in ("/api/candidatos", "/api/candidatos.csv"):
            csv_pedido = caminho.endswith(".csv") or consulta.get("formato") == "csv"
            teto = LIMITE_CSV if csv_pedido else LIMITE_MAXIMO
            limite = min(int(consulta.get("limite") or (teto if csv_pedido else LIMITE_PADRAO)), teto)
            dados = consultar_candidatos(con, consulta, limite)
            if not csv_pedido:
                return self._json(dados)
            corpo = montar_csv(dados)
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/csv; charset=utf-8")
            self.send_header("Content-Length", str(len(corpo)))
            self.send_header("Content-Disposition",
                             'attachment; filename="meucandidato.csv"')
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(corpo)
            return None

        achado = ROTA_CANDIDATO.match(caminho)
        if achado:
            candidato = consultar_candidato(con, achado.group(1))
            if candidato is None:
                return self._erro(HTTPStatus.NOT_FOUND, "candidato nao encontrado")
            return self._json(candidato)

        return self._erro(HTTPStatus.NOT_FOUND, "rota nao encontrada")

    def _estatico(self, caminho):
        if caminho in ("/", ""):
            caminho = "/index.html"
        alvo = (WEB / caminho.lstrip("/")).resolve()
        # Impede sair da pasta web/ por caminhos como /../banco.py
        if not str(alvo).startswith(str(WEB.resolve())) or not alvo.is_file():
            return self._erro(HTTPStatus.NOT_FOUND, "arquivo nao encontrado")
        tipo, _ = mimetypes.guess_type(str(alvo))
        cache = "no-store" if alvo.name == "index.html" else "public, max-age=300"
        return self._responder(HTTPStatus.OK, alvo.read_bytes(),
                               tipo or "application/octet-stream", cache)

    def log_message(self, formato, *args):
        print(f"{self.address_string()} {formato % args}")


class Servidor(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, endereco, manipulador, conexao):
        super().__init__(endereco, manipulador)
        self.conexao = conexao


def main() -> int:
    p = argparse.ArgumentParser(description="Servidor do MeuCandidato.")
    p.add_argument("--porta", type=int, default=8000)
    p.add_argument("--host", default="127.0.0.1")
    args = p.parse_args()

    caminho = banco.caminho_banco()
    if not caminho.exists():
        print(f"banco nao encontrado em {caminho}\n"
              f"gere uma base antes de subir o servidor:\n"
              f"  python3 scripts/gerar_exemplo.py        (dados ficticios)\n"
              f"  python3 scripts/importar_tse.py --baixar (dados oficiais do TSE)")
        return 1

    conexao = banco.conectar(somente_leitura=True)
    servidor = Servidor((args.host, args.porta), Manipulador, conexao)
    print(f"MeuCandidato em http://{args.host}:{args.porta}  (banco: {caminho})")
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        print("\nencerrando")
    finally:
        servidor.server_close()
        conexao.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
