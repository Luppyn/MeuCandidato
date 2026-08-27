#!/usr/bin/env python3
"""Gera a versão estática do site, para hospedagem sem servidor.

O filtro obrigatório do site é cargo + UF. Isso é, convenientemente, uma boa
chave de partição: em vez de um servidor consultando o SQLite a cada acesso,
gera-se um arquivo JSON por recorte, e o navegador busca só o recorte pedido.

Resultado: hospedagem estática (GitHub Pages, Cloudflare Pages, Netlify), sem
servidor, sem banco rodando, e aguentando qualquer pico de acesso.

    python3 scripts/gerar_estatico.py                 # tudo
    python3 scripts/gerar_estatico.py --ano 2026      # só um ano
    python3 scripts/gerar_estatico.py --saida publicar

Estrutura gerada:

    publicar/
      index.html, estilo.css, app.js     cópia de web/
      dados/
        meta.json          modo, data de geração, origem da base
        colunas.json       definição da planilha
        fontes.json        registro público das fontes
        procedencia.json   histórico de importações com hash
        opcoes.json        recortes disponíveis (alimenta os filtros)
        grade/<recorte>.json   uma linha por candidato, com os dados externos
        bens/<recorte>.json    bens declarados, buscados ao expandir a linha
"""

from __future__ import annotations

import _caminho  # noqa: F401

import argparse
import json
import pathlib
import shutil
import sys

import banco
import servidor

RAIZ = pathlib.Path(__file__).resolve().parent.parent

# Prefeito, vice-prefeito e vereador: o recorte precisa do município, senão um
# arquivo de "vereador em SP" juntaria todas as cidades do estado.
CARGOS_MUNICIPAIS = {11, 12, 13}


def recorte_de(linha) -> tuple:
    """Chave de partição de um candidato."""
    if linha["cd_cargo"] in CARGOS_MUNICIPAIS:
        return (linha["ano_eleicao"], linha["cd_cargo"], linha["sg_uf"], linha["sg_ue"])
    return (linha["ano_eleicao"], linha["cd_cargo"], linha["sg_uf"], None)


def nome_do_recorte(chave: tuple) -> str:
    ano, cargo, uf, ue = chave
    partes = [str(ano), str(cargo), str(uf or "")]
    if ue:
        partes.append(str(ue))
    return "-".join(partes)


def gravar(caminho: pathlib.Path, dados) -> int:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    texto = json.dumps(dados, ensure_ascii=False, separators=(",", ":"))
    caminho.write_text(texto, encoding="utf-8")
    return len(texto.encode("utf-8"))


def main() -> int:
    p = argparse.ArgumentParser(description="Gera a versão estática do site.")
    p.add_argument("--saida", type=pathlib.Path, default=RAIZ / "publicar")
    p.add_argument("--ano", type=int, action="append", default=[],
                   help="limita a um ou mais anos (padrão: todos os da base)")
    p.add_argument("--base-url", default="",
                   help="prefixo do site quando hospedado em subpasta "
                        "(ex.: /MeuCandidato). Normalmente não é preciso.")
    args = p.parse_args()

    if not banco.caminho_banco().exists():
        print(f"banco não encontrado em {banco.caminho_banco()}\n"
              f"gere a base antes: python3 scripts/importar_tse.py --baixar --ano 2026")
        return 1

    con = banco.conectar(somente_leitura=True)
    saida = args.saida
    if saida.exists():
        shutil.rmtree(saida)
    destino_dados = saida / "dados"

    # --- arquivos estáticos do site -------------------------------------
    for arquivo in ("index.html", "estilo.css", "app.js"):
        origem = RAIZ / "web" / arquivo
        alvo = saida / arquivo
        alvo.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(origem, alvo)

    # --- metadados e configuração ---------------------------------------
    procedencia = servidor.consultar_procedencia(con)
    gravar(destino_dados / "meta.json", {
        "modo": "estatico",
        "gerado_em": banco.agora(),
        "base_url": args.base_url,
        "origem_base": procedencia["origem_base"],
        "aviso_base": procedencia["aviso_base"],
    })
    gravar(destino_dados / "colunas.json", {"colunas": servidor.CONFIG_COLUNAS["colunas"]})
    gravar(destino_dados / "fontes.json", {
        "fontes": servidor.consultar_fontes(con),
        "links": {k: v for k, v in servidor.CONFIG_LINKS.items() if not k.startswith("_")},
    })
    gravar(destino_dados / "procedencia.json", procedencia)

    # --- candidatos, particionados por recorte ---------------------------
    colunas = ", ".join(f"c.{coluna}" for coluna in servidor.COLUNAS_CANDIDATO)
    condicao, valores = "1 = 1", []
    if args.ano:
        marcadores = ", ".join("?" * len(args.ano))
        condicao, valores = f"c.ano_eleicao IN ({marcadores})", list(args.ano)

    linhas = con.execute(
        f"SELECT {colunas}, c.cd_cargo, c.ano_eleicao FROM candidato c "
        f"WHERE {condicao} ORDER BY c.nm_urna", valores
    ).fetchall()

    if not linhas:
        print("nenhum candidato na base para os anos pedidos")
        return 1

    por_recorte: dict[tuple, list[dict]] = {}
    for linha in linhas:
        por_recorte.setdefault(recorte_de(linha), []).append(dict(linha))

    # Os dados externos entram de uma vez, e não recorte a recorte.
    externos = servidor.externos_por_chave(con, [dict(l)["chave"] for l in linhas])

    # Bens de todos os candidatos, agrupados por chave.
    bens_por_chave: dict[str, list[dict]] = {}
    for bem in con.execute(
        "SELECT c.chave, b.nr_ordem, b.ds_tipo, b.ds_bem, b.vr_bem, b.dt_atualizacao "
        "FROM bem b JOIN candidato c ON c.id = b.candidato_id ORDER BY b.nr_ordem"
    ):
        bens_por_chave.setdefault(bem["chave"], []).append({
            k: bem[k] for k in ("nr_ordem", "ds_tipo", "ds_bem", "vr_bem", "dt_atualizacao")
        })

    bytes_totais = 0
    catalogo = []
    for chave, candidatos in sorted(por_recorte.items()):
        nome = nome_do_recorte(chave)
        for candidato in candidatos:
            candidato["externos"] = externos.get(candidato["chave"], {})

        bytes_totais += gravar(destino_dados / "grade" / f"{nome}.json", {
            "recorte": {"ano": chave[0], "cargo": chave[1], "uf": chave[2], "ue": chave[3]},
            "total": len(candidatos),
            "candidatos": candidatos,
        })
        bytes_totais += gravar(destino_dados / "bens" / f"{nome}.json", {
            c["chave"]: bens_por_chave.get(c["chave"], []) for c in candidatos
        })

        catalogo.append({
            "arquivo": nome,
            "ano": chave[0], "cargo": chave[1], "uf": chave[2], "ue": chave[3],
            "total": len(candidatos),
        })

    # --- opções dos filtros ----------------------------------------------
    opcoes = servidor.consultar_opcoes(con)
    opcoes["recortes"] = catalogo
    bytes_totais += gravar(destino_dados / "opcoes.json", opcoes)

    # Impede que o Jekyll do GitHub Pages ignore pastas iniciadas por _
    (saida / ".nojekyll").write_text("", encoding="utf-8")

    print(f"{len(linhas)} candidato(s) em {len(catalogo)} recorte(s)")
    print(f"{bytes_totais / 1_000_000:.1f} MB de JSON em {saida}")
    maiores = sorted(catalogo, key=lambda c: c["total"], reverse=True)[:3]
    for c in maiores:
        print(f"  maior recorte: {c['arquivo']} com {c['total']} candidato(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
