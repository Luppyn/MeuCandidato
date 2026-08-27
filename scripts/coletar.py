#!/usr/bin/env python3
"""Executa os coletores das fontes sem API e grava o resultado em disco.

Nada e escrito direto na base: a saida e um arquivo no mesmo formato que
scripts/importar_externos.py le. Assim o caminho e sempre o mesmo, venha o dado
de um coletor daqui, de um fluxo do n8n ou de uma planilha preenchida a mao - e
toda entrada de dado fica registrada com arquivo, data e hash.

    # o que existe e o que da para automatizar
    python3 scripts/coletar.py --listar

    # coleta uma fonte para um recorte da base
    python3 scripts/coletar.py --fonte congresso --cargo 6 --uf SP

    # lista de trabalho das fontes que so podem ser conferidas a mao
    python3 scripts/coletar.py --pendencias --cargo 6 --uf SP

    # importa o que foi coletado
    python3 scripts/importar_externos.py dados/externo/
"""

from __future__ import annotations

import _caminho  # noqa: F401

import argparse
import csv
import json
import pathlib
import sys
import traceback

import banco
from coletores import todos
from coletores.base import Candidato

RAIZ = pathlib.Path(__file__).resolve().parent.parent
SAIDA = RAIZ / "dados" / "externo"


def candidatos_da_base(con, args) -> list[Candidato]:
    condicoes, valores = [], []
    if args.ano:
        condicoes.append("ano_eleicao = ?")
        valores.append(args.ano)
    if args.cargo:
        condicoes.append("cd_cargo = ?")
        valores.append(args.cargo)
    if args.uf:
        condicoes.append("sg_uf = ?")
        valores.append(args.uf.upper())
    if args.partido:
        condicoes.append("sg_partido = ?")
        valores.append(args.partido.upper())
    if args.nome:
        condicoes.append("nm_busca LIKE ?")
        valores.append(f"%{banco.normalizar(args.nome)}%")
    if args.somente_deferidos:
        condicoes.append("ds_situacao_candidatura LIKE 'DEFERIDO%'")

    where = " AND ".join(condicoes) if condicoes else "1 = 1"
    sql = (f"SELECT chave, nm_candidato, nm_urna, sg_uf, ds_cargo, sg_partido, "
           f"ano_eleicao, dt_nascimento, nr_processo FROM candidato WHERE {where} "
           f"ORDER BY nm_candidato")
    if args.limite:
        sql += f" LIMIT {int(args.limite)}"
    return [Candidato.de_linha(linha) for linha in con.execute(sql, valores)]


def gravar_json(caminho: pathlib.Path, registros: list[dict]) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(json.dumps(registros, ensure_ascii=False, indent=2), encoding="utf-8")


def gravar_csv(caminho: pathlib.Path, linhas: list[dict]) -> None:
    if not linhas:
        return
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with caminho.open("w", encoding="utf-8-sig", newline="") as arquivo:
        escritor = csv.DictWriter(arquivo, fieldnames=list(linhas[0]), delimiter=";")
        escritor.writeheader()
        escritor.writerows(linhas)


def listar(coletores) -> None:
    print(f"{'fonte':<20} {'automatico':<11} nome")
    print("-" * 78)
    for slug, coletor in coletores.items():
        print(f"{slug:<20} {'sim' if coletor.automatico else 'nao':<11} {coletor.nome}")
    print("\nFontes marcadas como nao automaticas exigem captcha ou sessao por consulta.")
    print("Para elas, use --pendencias: gera a lista de trabalho com os links prontos.")


def main() -> int:
    p = argparse.ArgumentParser(description="Coleta dados das fontes sem API oficial.")
    p.add_argument("--listar", action="store_true", help="mostra as fontes disponiveis e sai")
    p.add_argument("--verificar-saida", action="store_true",
                   help="mostra por qual IP a coleta esta saindo e sai "
                        "(confirma que o proxy esta valendo)")
    p.add_argument("--fonte", action="append", default=[],
                   help="slug da fonte a coletar (pode repetir; padrao: todas as automaticas)")
    p.add_argument("--pendencias", action="store_true",
                   help="gera o CSV de trabalho das fontes que exigem conferencia manual")
    p.add_argument("--tema", default="", help="termo de tema para a busca de noticias")

    p.add_argument("--ano", type=int, default=2026)
    p.add_argument("--cargo", type=int, help="codigo do cargo no TSE (ex.: 6 = deputado federal)")
    p.add_argument("--uf")
    p.add_argument("--partido")
    p.add_argument("--nome", help="filtra por parte do nome")
    p.add_argument("--limite", type=int, help="maximo de candidatos a processar")
    p.add_argument("--somente-deferidos", action="store_true",
                   help="ignora registros indeferidos, cassados ou pendentes")
    p.add_argument("--saida", type=pathlib.Path, default=SAIDA)
    args = p.parse_args()

    coletores = todos()
    if args.tema:
        from coletores import noticias
        coletores["noticias"] = noticias.Coletor(tema=args.tema)

    if args.listar:
        listar(coletores)
        return 0

    if args.verificar_saida:
        from coletores import rede
        situacao = rede.verificar_saida()
        print(f"proxy configurado : {'sim' if situacao['proxy_configurado'] else 'nao'}")
        if situacao["proxy_host"]:
            # Só host e porta: usuário e senha nunca são impressos.
            print(f"proxy             : {situacao['proxy_host']}")
        print(f"IP de saida       : {situacao['ip_de_saida'] or '(nao identificado)'}")
        if situacao["erro"]:
            print(f"aviso             : {situacao['erro']}")
        if situacao["proxy_configurado"] and not situacao["ip_de_saida"]:
            print("\nO proxy esta configurado mas o IP de saida nao pode ser confirmado. "
                  "Rode de novo antes de confiar numa coleta longa.")
            return 1
        return 0

    if not (args.cargo and args.uf):
        p.error("informe pelo menos --cargo e --uf (a coleta e sempre sobre um recorte)")

    con = banco.conectar(somente_leitura=True)
    candidatos = candidatos_da_base(con, args)
    if not candidatos:
        print("nenhum candidato bateu com esses filtros")
        return 1
    print(f"{len(candidatos)} candidato(s) selecionado(s)\n")

    # --- lista de trabalho das fontes manuais ------------------------------
    if args.pendencias:
        total = 0
        for slug, coletor in coletores.items():
            if coletor.automatico or (args.fonte and slug not in args.fonte):
                continue
            linhas = [coletor.pendencia(c) for c in candidatos]
            destino = args.saida / f"pendencias_{slug}.csv"
            gravar_csv(destino, linhas)
            total += len(linhas)
            print(f"{slug}: {len(linhas)} linha(s) para conferir -> {destino}")
        if not total:
            print("nenhuma fonte manual selecionada")
        else:
            print("\nPreencha a coluna 'valor' e importe com:\n"
                  f"  python3 scripts/importar_externos.py {args.saida}")
        return 0

    # --- coleta automatica --------------------------------------------------
    escolhidas = args.fonte or [s for s, c in coletores.items() if c.automatico]
    desconhecidas = [s for s in escolhidas if s not in coletores]
    if desconhecidas:
        p.error(f"fonte desconhecida: {', '.join(desconhecidas)} (use --listar)")

    codigo_saida = 0
    for slug in escolhidas:
        coletor = coletores[slug]
        if not coletor.automatico:
            print(f"{slug}: exige conferencia manual, use --pendencias. Ignorando.")
            continue

        pendencia = coletor.aviso_inicial()
        if pendencia:
            print(f"{slug}: {pendencia}")
            print(f"  pulando {slug} — a coluna fica sem dado, com link para a fonte.\n")
            codigo_saida = max(codigo_saida, 2)
            continue

        try:
            coletor.preparar(candidatos)
        except Exception:  # noqa: BLE001 - preparação falha não derruba as outras fontes
            traceback.print_exc(limit=1)

        registros: list[dict] = []
        falhas = 0
        for indice, candidato in enumerate(candidatos, 1):
            try:
                for registro in coletor.coletar(candidato):
                    registros.append(registro.para_dicionario())
            except Exception:  # noqa: BLE001 - uma fonte fora do ar nao derruba as outras
                falhas += 1
                if falhas <= 3:
                    traceback.print_exc(limit=1)
            print(f"\r{slug}: {indice}/{len(candidatos)} "
                  f"({len(registros)} registro(s), {falhas} falha(s))",
                  end="", flush=True)
        print()

        if registros:
            destino = args.saida / f"{slug}.json"
            gravar_json(destino, registros)
            print(f"  -> {destino}")
        else:
            print(f"  nenhum registro obtido de {slug}")
            codigo_saida = max(codigo_saida, 2)
        if falhas:
            print(f"  {falhas} candidato(s) falharam nesta fonte")

    print("\nPara carregar na base:\n"
          f"  python3 scripts/importar_externos.py {args.saida}")
    return codigo_saida


if __name__ == "__main__":
    sys.exit(main())
