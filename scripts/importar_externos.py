#!/usr/bin/env python3
"""Importa para a base os dados que vem de fora do TSE.

E o unico ponto de entrada dos campos sem API oficial (CNIA, Excelencias,
tribunais, indicadores ideologicos, checagens, noticias). Aceita CSV ou JSON,
venha de onde vier: dos coletores deste repositorio, de um fluxo do n8n ou de
uma planilha preenchida a mao.

Formato esperado (mesmas colunas em CSV e JSON):

    chave       identificador do candidato: ano-cargo-uf-ue-numero
                (ex.: 2026-6-SP-SP-1234). Alternativa: informar
                ano, cargo, uf, ue e numero em colunas separadas.
    fonte       slug da fonte, conforme config/fontes.json (ex.: cnia)
    campo       nome do campo dentro da fonte (ex.: situacao)
    valor       texto exibido na planilha
    valor_num   opcional, valor numerico para ordenacao
    url         opcional, link para a evidencia na fonte original
    observacao  opcional, nota de metodologia ou ressalva
    coletado_em opcional, data/hora da coleta (ISO 8601)

Exemplos:
    python3 scripts/importar_externos.py dados/externo/cnia.json
    python3 scripts/importar_externos.py dados/externo/      # pasta inteira
    python3 scripts/importar_externos.py --substituir-fonte cnia dados/externo/cnia.csv
"""

from __future__ import annotations

import _caminho  # noqa: F401

import argparse
import csv
import hashlib
import io
import json
import pathlib
import sys

import banco

RAIZ = pathlib.Path(__file__).resolve().parent.parent
FONTES_CONHECIDAS = {
    f["slug"] for f in json.loads((RAIZ / "config" / "fontes.json").read_text(encoding="utf-8"))["fontes"]
}

CAMPOS_OBRIGATORIOS = ("fonte", "campo")


def sha256_bytes(dados: bytes) -> str:
    return hashlib.sha256(dados).hexdigest()


def registros_de(caminho: pathlib.Path):
    """Le um arquivo CSV ou JSON e devolve (registros, bytes_do_arquivo)."""
    dados = caminho.read_bytes()
    texto = dados.decode("utf-8-sig", errors="replace")

    if caminho.suffix.lower() == ".json":
        conteudo = json.loads(texto)
        if isinstance(conteudo, dict):
            conteudo = conteudo.get("registros") or conteudo.get("dados") or []
        if not isinstance(conteudo, list):
            raise ValueError(f"{caminho}: JSON precisa ser uma lista de registros")
        return conteudo, dados

    delimitador = ";" if texto.count(";") > texto.count(",") else ","
    return list(csv.DictReader(io.StringIO(texto), delimiter=delimitador)), dados


def resolver_chave(registro: dict) -> str | None:
    chave = (registro.get("chave") or "").strip()
    if chave:
        return chave
    partes = (registro.get("ano"), registro.get("cargo") or registro.get("cd_cargo"),
              registro.get("uf") or registro.get("sg_uf"),
              registro.get("ue") or registro.get("sg_ue"),
              registro.get("numero") or registro.get("nr_candidato"))
    if all(p not in (None, "") for p in partes):
        return banco.chave_candidato(*partes)
    return None


def para_float(valor) -> float | None:
    if valor in (None, ""):
        return None
    if isinstance(valor, (int, float)):
        return float(valor)
    texto = str(valor).strip().replace("%", "")
    if texto.count(",") == 1 and texto.count(".") != 1:
        texto = texto.replace(".", "").replace(",", ".")
    try:
        return float(texto)
    except ValueError:
        return None


def texto_ou_none(valor) -> str | None:
    if valor is None:
        return None
    if isinstance(valor, (dict, list)):
        return json.dumps(valor, ensure_ascii=False)
    texto = str(valor).strip()
    return texto or None


def importar_arquivo(con, caminho: pathlib.Path, estrito: bool) -> tuple[int, int, int]:
    registros, dados = registros_de(caminho)
    impid = banco.abrir_importacao(
        con, tipo="externo", origem="automacao externa", arquivo=caminho.name,
        sha256=sha256_bytes(dados), bytes_=len(dados),
    )

    sql = (
        "INSERT INTO dado_externo (chave, fonte, campo, valor, valor_num, url, "
        "observacao, coletado_em, importacao_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(chave, fonte, campo) DO UPDATE SET "
        "valor = excluded.valor, valor_num = excluded.valor_num, url = excluded.url, "
        "observacao = excluded.observacao, coletado_em = excluded.coletado_em, "
        "importacao_id = excluded.importacao_id"
    )

    lidos = gravados = ignorados = 0
    lote = []
    for registro in registros:
        lidos += 1
        if not isinstance(registro, dict):
            ignorados += 1
            continue

        faltando = [c for c in CAMPOS_OBRIGATORIOS if not (registro.get(c) or "").strip()]
        chave = resolver_chave(registro)
        if faltando or not chave:
            ignorados += 1
            if estrito:
                raise ValueError(
                    f"{caminho.name}: registro sem {'/'.join(faltando) or 'chave'}: {registro!r}"
                )
            continue

        valor = texto_ou_none(registro.get("valor"))
        if valor is None:
            # Linha de trabalho ainda em branco (ex.: pendencia nao conferida).
            # Nao vira celula vazia na base: a planilha ja mostra "sem dado"
            # com o link da fonte quando nao ha registro nenhum.
            ignorados += 1
            continue

        fonte = str(registro["fonte"]).strip()
        if fonte not in FONTES_CONHECIDAS:
            ignorados += 1
            print(f"  aviso: fonte desconhecida '{fonte}' (registre em config/fontes.json)")
            continue

        lote.append((
            chave,
            fonte,
            str(registro["campo"]).strip(),
            valor,
            para_float(registro.get("valor_num", registro.get("valor"))),
            texto_ou_none(registro.get("url")),
            texto_ou_none(registro.get("observacao")),
            texto_ou_none(registro.get("coletado_em")) or banco.agora(),
            impid,
        ))
        if len(lote) >= 2000:
            con.executemany(sql, lote)
            gravados += len(lote)
            lote.clear()

    if lote:
        con.executemany(sql, lote)
        gravados += len(lote)
    con.commit()

    banco.fechar_importacao(con, impid, lidos, gravados,
                            f"{ignorados} registro(s) ignorado(s)" if ignorados else None)
    print(f"{caminho.name}: {gravados} gravados, {ignorados} ignorados, {lidos} lidos")
    return lidos, gravados, ignorados


def main() -> int:
    p = argparse.ArgumentParser(description="Importa dados externos (fontes sem API oficial).")
    p.add_argument("origens", nargs="+", type=pathlib.Path, help="arquivos CSV/JSON ou pastas")
    p.add_argument("--substituir-fonte", metavar="SLUG", action="append", default=[],
                   help="apaga tudo o que existe dessa fonte antes de importar (pode repetir)")
    p.add_argument("--estrito", action="store_true",
                   help="aborta no primeiro registro invalido em vez de ignora-lo")
    args = p.parse_args()

    con = banco.conectar()
    banco.criar_esquema(con)

    for slug in args.substituir_fonte:
        apagados = con.execute("DELETE FROM dado_externo WHERE fonte = ?", (slug,)).rowcount
        print(f"fonte '{slug}': {apagados} registro(s) removido(s) antes da importacao")
    if args.substituir_fonte:
        con.commit()

    arquivos: list[pathlib.Path] = []
    for origem in args.origens:
        if origem.is_dir():
            arquivos += sorted(
                c for c in origem.rglob("*")
                if c.is_file() and c.suffix.lower() in (".csv", ".json")
            )
        elif origem.exists():
            arquivos.append(origem)
        else:
            print(f"aviso: {origem} nao existe, ignorando")

    if not arquivos:
        print("nenhum arquivo CSV/JSON encontrado")
        return 1

    totais = [0, 0, 0]
    for arquivo in arquivos:
        try:
            resultado = importar_arquivo(con, arquivo, args.estrito)
        except (ValueError, json.JSONDecodeError) as erro:
            print(f"erro em {arquivo}: {erro}")
            if args.estrito:
                return 1
            continue
        totais = [a + b for a, b in zip(totais, resultado)]

    banco.definir_meta(con, "externos_atualizados_em", banco.agora())
    con.commit()

    print(f"\ntotal: {totais[1]} registro(s) gravado(s) de {totais[0]} lido(s), "
          f"{totais[2]} ignorado(s)")
    orfaos = con.execute(
        "SELECT COUNT(*) c FROM dado_externo d "
        "WHERE NOT EXISTS (SELECT 1 FROM candidato c2 WHERE c2.chave = d.chave)"
    ).fetchone()["c"]
    if orfaos:
        print(f"aviso: {orfaos} registro(s) externo(s) sem candidato correspondente na base. "
              f"Eles ficam guardados e passam a aparecer assim que o candidato for importado.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
