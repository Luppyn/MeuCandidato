#!/usr/bin/env python3
"""Importa a base oficial de candidatos do TSE para o SQLite local.

Le os arquivos publicados em https://dadosabertos.tse.jus.br (consulta_cand e
bem_candidato), em ZIP ou CSV solto, e grava candidatos e bens declarados.

Cada arquivo lido vira uma linha na tabela `importacao` com data, tamanho e
SHA-256 do conteudo, de modo que qualquer pessoa possa recalcular o hash do
arquivo original do TSE e conferir que a base do site nao foi alterada.

Exemplos:
    python3 scripts/importar_tse.py --baixar --ano 2026
    python3 scripts/importar_tse.py dados/tse/consulta_cand_2026.zip
    python3 scripts/importar_tse.py dados/tse/            # pasta com os CSVs
"""

from __future__ import annotations

import _caminho  # noqa: F401  (ajusta o sys.path)

import argparse
import csv
import hashlib
import io
import json
import pathlib
import sys
import zipfile

import banco

RAIZ = pathlib.Path(__file__).resolve().parent.parent
CONFIG_LINKS = json.loads((RAIZ / "config" / "links.json").read_text(encoding="utf-8"))
CONFIG_FONTES = json.loads((RAIZ / "config" / "fontes.json").read_text(encoding="utf-8"))

CODIFICACAO = "latin-1"
SEPARADOR = ";"

# Coluna do banco -> coluna do CSV do TSE. Colunas ausentes no arquivo (o TSE
# muda o leiaute entre eleicoes, e ja removeu o CPF) sao simplesmente ignoradas.
DE_PARA_CANDIDATO = {
    "ano_eleicao": "ANO_ELEICAO",
    "cd_eleicao": "CD_ELEICAO",
    "ds_eleicao": "DS_ELEICAO",
    "nm_tipo_eleicao": "NM_TIPO_ELEICAO",
    "nr_turno": "NR_TURNO",
    "sq_candidato": "SQ_CANDIDATO",
    "nr_candidato": "NR_CANDIDATO",
    "nm_candidato": "NM_CANDIDATO",
    "nm_urna": "NM_URNA_CANDIDATO",
    "nm_social": "NM_SOCIAL_CANDIDATO",
    "cd_cargo": "CD_CARGO",
    "ds_cargo": "DS_CARGO",
    "sg_uf": "SG_UF",
    "sg_ue": "SG_UE",
    "nm_ue": "NM_UE",
    "nr_partido": "NR_PARTIDO",
    "sg_partido": "SG_PARTIDO",
    "nm_partido": "NM_PARTIDO",
    "sg_federacao": "SG_FEDERACAO",
    "nm_federacao": "NM_FEDERACAO",
    "nm_coligacao": "NM_COLIGACAO",
    "ds_composicao_coligacao": "DS_COMPOSICAO_COLIGACAO",
    "ds_situacao_candidatura": "DS_SITUACAO_CANDIDATURA",
    "ds_detalhe_situacao_cand": "DS_DETALHE_SITUACAO_CAND",
    "ds_situacao_candidato_tot": "DS_SITUACAO_CANDIDATO_TOT",
    "ds_genero": "DS_GENERO",
    "dt_nascimento": "DT_NASCIMENTO",
    "nr_idade_data_posse": "NR_IDADE_DATA_POSSE",
    "ds_estado_civil": "DS_ESTADO_CIVIL",
    "ds_cor_raca": "DS_COR_RACA",
    "ds_ocupacao": "DS_OCUPACAO",
    "ds_grau_instrucao": "DS_GRAU_INSTRUCAO",
    "ds_nacionalidade": "DS_NACIONALIDADE",
    "nm_municipio_nascimento": "NM_MUNICIPIO_NASCIMENTO",
    "sg_uf_nascimento": "SG_UF_NASCIMENTO",
    "st_reeleicao": "ST_REELEICAO",
    "st_declarar_bens": "ST_DECLARAR_BENS",
}

# Valores que o TSE usa para "campo nao informado".
VAZIOS = {"", "#NULO", "#NULO#", "#NE", "#NE#", "-1", "-3", "NAO DIVULGAVEL"}


def limpar(valor: str | None) -> str | None:
    if valor is None:
        return None
    valor = valor.strip()
    return None if valor.upper() in VAZIOS else valor


def para_numero(valor: str | None) -> float | None:
    """Converte '1.234,56' (formato do TSE) em float."""
    valor = limpar(valor)
    if valor is None:
        return None
    valor = valor.replace(".", "").replace(",", ".")
    try:
        return float(valor)
    except ValueError:
        return None


def para_inteiro(valor: str | None) -> int | None:
    valor = limpar(valor)
    if valor is None:
        return None
    try:
        return int(float(valor.replace(",", ".")))
    except ValueError:
        return None


def sha256_de(caminho: pathlib.Path) -> str:
    h = hashlib.sha256()
    with caminho.open("rb") as f:
        for bloco in iter(lambda: f.read(1024 * 256), b""):
            h.update(bloco)
    return h.hexdigest()


def sha256_bytes(dados: bytes) -> str:
    return hashlib.sha256(dados).hexdigest()


# ----------------------------------------------------------------------------
# Leitura dos arquivos
# ----------------------------------------------------------------------------

def csvs_de(origem: pathlib.Path):
    """Devolve (nome, bytes) de cada CSV encontrado em ZIP, pasta ou arquivo."""
    if origem.is_dir():
        for caminho in sorted(origem.rglob("*")):
            if caminho.is_file() and caminho.suffix.lower() in (".zip", ".csv", ".txt"):
                yield from csvs_de(caminho)
        return

    if origem.suffix.lower() == ".zip":
        with zipfile.ZipFile(origem) as z:
            for nome in sorted(z.namelist()):
                if nome.lower().endswith((".csv", ".txt")):
                    yield f"{origem.name}!{nome}", z.read(nome)
        return

    if origem.suffix.lower() in (".csv", ".txt"):
        yield origem.name, origem.read_bytes()


def linhas_do_csv(dados: bytes):
    texto = dados.decode(CODIFICACAO, errors="replace")
    leitor = csv.DictReader(io.StringIO(texto), delimiter=SEPARADOR)
    if leitor.fieldnames:
        leitor.fieldnames = [c.strip().upper().lstrip("﻿") for c in leitor.fieldnames]
    yield from leitor


# ----------------------------------------------------------------------------
# Gravacao
# ----------------------------------------------------------------------------

def montar_urls(linha: dict) -> tuple[str | None, str | None]:
    dados = {
        "ano": limpar(linha.get("ANO_ELEICAO")) or "",
        "cd_eleicao": limpar(linha.get("CD_ELEICAO")) or "",
        "sg_ue": limpar(linha.get("SG_UE")) or "",
        "sq_candidato": limpar(linha.get("SQ_CANDIDATO")) or "",
    }
    if not dados["sq_candidato"]:
        return None, None
    try:
        perfil = CONFIG_LINKS["perfil_candidato"].format(**dados)
        foto = CONFIG_LINKS["foto_candidato"].format(**dados)
    except KeyError:
        return None, None
    return perfil, foto


def importar_candidatos(con, nome_arquivo, dados, importacao_id, anos_aceitos=None):
    lidas = gravadas = 0
    colunas_banco = list(DE_PARA_CANDIDATO) + [
        "chave", "nm_busca", "vr_despesa_max_campanha",
        "url_divulgacand", "url_foto", "importacao_id",
    ]
    sql = (
        f"INSERT INTO candidato ({', '.join(colunas_banco)}) "
        f"VALUES ({', '.join('?' * len(colunas_banco))}) "
        f"ON CONFLICT(chave) DO UPDATE SET "
        + ", ".join(f"{c} = excluded.{c}" for c in colunas_banco if c != "chave")
    )

    lote = []
    for linha in linhas_do_csv(dados):
        lidas += 1
        ano = para_inteiro(linha.get("ANO_ELEICAO"))
        if ano is None:
            continue
        if anos_aceitos and ano not in anos_aceitos:
            continue

        chave = banco.chave_candidato(
            ano,
            para_inteiro(linha.get("CD_CARGO")),
            limpar(linha.get("SG_UF")),
            limpar(linha.get("SG_UE")),
            limpar(linha.get("NR_CANDIDATO")),
        )
        perfil, foto = montar_urls(linha)

        valores = []
        for coluna, origem in DE_PARA_CANDIDATO.items():
            bruto = linha.get(origem)
            if coluna in ("ano_eleicao", "cd_cargo", "nr_turno"):
                valores.append(para_inteiro(bruto))
            else:
                valores.append(limpar(bruto))

        valores += [
            chave,
            banco.normalizar(
                " ".join(filter(None, [limpar(linha.get("NM_CANDIDATO")),
                                       limpar(linha.get("NM_URNA_CANDIDATO")),
                                       limpar(linha.get("NM_SOCIAL_CANDIDATO"))]))
            ),
            para_numero(linha.get("VR_DESPESA_MAX_CAMPANHA")),
            perfil,
            foto,
            importacao_id,
        ]
        lote.append(valores)

        if len(lote) >= 5000:
            con.executemany(sql, lote)
            gravadas += len(lote)
            lote.clear()

    if lote:
        con.executemany(sql, lote)
        gravadas += len(lote)
    con.commit()
    print(f"  candidatos: {gravadas} gravados de {lidas} linhas ({nome_arquivo})")
    return lidas, gravadas


def importar_bens(con, nome_arquivo, dados, importacao_id, anos_aceitos=None):
    lidas = gravadas = 0
    # sq_candidato identifica o candidato dentro da mesma eleicao.
    mapa = {
        linha["sq_candidato"]: linha["id"]
        for linha in con.execute(
            "SELECT id, sq_candidato FROM candidato WHERE sq_candidato IS NOT NULL"
        )
    }
    if not mapa:
        print("  aviso: nenhum candidato na base; importe consulta_cand antes dos bens.")

    lote = []
    sql = (
        "INSERT INTO bem (candidato_id, nr_ordem, cd_tipo, ds_tipo, ds_bem, vr_bem, "
        "dt_atualizacao, importacao_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(candidato_id, nr_ordem) DO UPDATE SET "
        "cd_tipo = excluded.cd_tipo, ds_tipo = excluded.ds_tipo, ds_bem = excluded.ds_bem, "
        "vr_bem = excluded.vr_bem, dt_atualizacao = excluded.dt_atualizacao, "
        "importacao_id = excluded.importacao_id"
    )

    for linha in linhas_do_csv(dados):
        lidas += 1
        ano = para_inteiro(linha.get("ANO_ELEICAO"))
        if anos_aceitos and ano not in anos_aceitos:
            continue
        sq = limpar(linha.get("SQ_CANDIDATO"))
        candidato_id = mapa.get(sq)
        if candidato_id is None:
            continue
        lote.append((
            candidato_id,
            para_inteiro(linha.get("NR_ORDEM_BEM_CANDIDATO")),
            limpar(linha.get("CD_TIPO_BEM_CANDIDATO")),
            limpar(linha.get("DS_TIPO_BEM_CANDIDATO")),
            limpar(linha.get("DS_BEM_CANDIDATO")),
            para_numero(linha.get("VR_BEM_CANDIDATO")),
            limpar(linha.get("DT_ULTIMA_ATUALIZACAO")),
            importacao_id,
        ))
        if len(lote) >= 5000:
            con.executemany(sql, lote)
            gravadas += len(lote)
            lote.clear()

    if lote:
        con.executemany(sql, lote)
        gravadas += len(lote)
    con.commit()
    print(f"  bens: {gravadas} gravados de {lidas} linhas ({nome_arquivo})")
    return lidas, gravadas


def recalcular_patrimonio(con) -> None:
    con.execute("""
        UPDATE candidato SET
            qtd_bens   = COALESCE((SELECT COUNT(*)        FROM bem WHERE bem.candidato_id = candidato.id), 0),
            total_bens = COALESCE((SELECT SUM(vr_bem)     FROM bem WHERE bem.candidato_id = candidato.id), 0)
    """)
    con.commit()


def registrar_fontes(con) -> None:
    for f in CONFIG_FONTES["fontes"]:
        con.execute(
            "INSERT INTO fonte (slug, nome, url, categoria, tem_api, descricao, "
            "url_consulta_manual, licenca, atualizado_em) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(slug) DO UPDATE SET nome = excluded.nome, url = excluded.url, "
            "categoria = excluded.categoria, tem_api = excluded.tem_api, "
            "descricao = excluded.descricao, url_consulta_manual = excluded.url_consulta_manual, "
            "licenca = excluded.licenca, atualizado_em = excluded.atualizado_em",
            (f["slug"], f["nome"], f.get("url"), f.get("categoria"), int(f.get("tem_api", 0)),
             f.get("descricao"), f.get("url_consulta_manual"), f.get("licenca"), banco.agora()),
        )
    con.commit()


# ----------------------------------------------------------------------------
# Download opcional
# ----------------------------------------------------------------------------

def baixar(ano: int, destino: pathlib.Path) -> list[pathlib.Path]:
    import urllib.request

    destino.mkdir(parents=True, exist_ok=True)
    baixados = []
    for nome, modelo in CONFIG_LINKS["download_tse"].items():
        url = modelo.format(ano=ano)
        arquivo = destino / f"{nome}_{ano}.zip"
        print(f"baixando {url}")
        req = urllib.request.Request(url, headers={"User-Agent": "MeuCandidato/1.0"})
        with urllib.request.urlopen(req, timeout=300) as resposta, arquivo.open("wb") as saida:
            while bloco := resposta.read(1024 * 256):
                saida.write(bloco)
        print(f"  -> {arquivo} ({arquivo.stat().st_size / 1_000_000:.1f} MB)")
        baixados.append(arquivo)
    return baixados


# ----------------------------------------------------------------------------

def main() -> int:
    p = argparse.ArgumentParser(description="Importa a base de candidatos do TSE.")
    p.add_argument("origens", nargs="*", type=pathlib.Path,
                   help="arquivos ZIP/CSV ou pastas com os dados do TSE")
    p.add_argument("--baixar", action="store_true",
                   help="baixa os ZIPs do portal de dados abertos antes de importar")
    p.add_argument("--ano", type=int, default=2026, help="ano da eleicao (padrao: 2026)")
    p.add_argument("--todos-os-anos", action="store_true",
                   help="importa todos os anos presentes nos arquivos, nao so --ano")
    p.add_argument("--limpar", action="store_true",
                   help="apaga candidatos e bens antes de importar (dados externos sao mantidos)")
    args = p.parse_args()

    origens = list(args.origens)
    if args.baixar:
        origens += baixar(args.ano, RAIZ / "dados" / "tse")
    if not origens:
        p.error("informe ao menos um arquivo/pasta ou use --baixar")

    anos = None if args.todos_os_anos else {args.ano}

    con = banco.conectar()
    banco.criar_esquema(con)
    registrar_fontes(con)

    if args.limpar:
        con.execute("DELETE FROM bem")
        con.execute("DELETE FROM candidato")
        con.commit()
        print("base de candidatos e bens zerada")

    # Candidatos primeiro; os bens dependem do sq_candidato ja gravado.
    pendentes_bens = []
    total_lidas = total_gravadas = 0

    for origem in origens:
        if not origem.exists():
            print(f"aviso: {origem} nao existe, ignorando")
            continue
        for nome, dados in csvs_de(origem):
            impid = banco.abrir_importacao(
                con, tipo="tse", origem="TSE - dados abertos", arquivo=nome,
                sha256=sha256_bytes(dados), bytes_=len(dados),
            )
            base = nome.lower()
            if "consulta_cand" in base:
                lidas, gravadas = importar_candidatos(con, nome, dados, impid, anos)
            elif "bem_candidato" in base or "bens" in base:
                pendentes_bens.append((nome, dados, impid))
                continue
            else:
                print(f"  ignorado (nome nao reconhecido): {nome}")
                banco.fechar_importacao(con, impid, 0, 0, "arquivo ignorado")
                continue
            banco.fechar_importacao(con, impid, lidas, gravadas)
            total_lidas += lidas
            total_gravadas += gravadas

    for nome, dados, impid in pendentes_bens:
        lidas, gravadas = importar_bens(con, nome, dados, impid, anos)
        banco.fechar_importacao(con, impid, lidas, gravadas)
        total_lidas += lidas
        total_gravadas += gravadas

    recalcular_patrimonio(con)
    banco.definir_meta(con, "origem_base", "TSE")
    banco.definir_meta(con, "atualizado_em", banco.agora())
    con.commit()

    candidatos = con.execute("SELECT COUNT(*) c FROM candidato").fetchone()["c"]
    bens = con.execute("SELECT COUNT(*) c FROM bem").fetchone()["c"]
    print(f"\nbase: {candidatos} candidatos, {bens} bens declarados")
    print(f"arquivo: {banco.caminho_banco()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
