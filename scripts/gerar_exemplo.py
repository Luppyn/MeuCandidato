#!/usr/bin/env python3
"""Gera uma base de demonstracao com dados ficticios.

Serve para abrir o site e testar filtros, grade e importacao sem precisar
baixar os arquivos do TSE. Os arquivos sao gravados no mesmo leiaute do TSE
(CSV latin-1 separado por ponto e virgula) e passam pelo importador real, de
modo que o caminho exercitado aqui e exatamente o de producao.

Os nomes sao inventados e todos os registros ficam marcados como base de
exemplo (meta.origem_base = EXEMPLO), o que faz o site exibir um aviso no topo
da tela. Nenhum dado aqui representa pessoa real.

    python3 scripts/gerar_exemplo.py
"""

from __future__ import annotations

import _caminho  # noqa: F401

import argparse
import csv
import io
import json
import pathlib
import random
import subprocess
import sys

import banco

RAIZ = pathlib.Path(__file__).resolve().parent.parent

CARGOS = [
    (1, "PRESIDENTE", "BR", 10),
    (3, "GOVERNADOR", "UF", 12),
    (5, "SENADOR", "UF", 14),
    (6, "DEPUTADO FEDERAL", "UF", 60),
    (7, "DEPUTADO ESTADUAL", "UF", 80),
    (8, "DEPUTADO DISTRITAL", "UF", 20),
    (11, "PREFEITO", "MUN", 16),
    (13, "VEREADOR", "MUN", 90),
]

UFS = ["SP", "RJ", "MG", "BA", "RS", "PE", "CE", "PR", "DF"]
MUNICIPIOS = {
    "SP": [("71072", "SAO PAULO"), ("62960", "CAMPINAS")],
    "RJ": [("60011", "RIO DE JANEIRO"), ("58637", "NITEROI")],
    "MG": [("41238", "BELO HORIZONTE")],
    "BA": [("38490", "SALVADOR")],
    "RS": [("88013", "PORTO ALEGRE")],
    "PE": [("25313", "RECIFE")],
    "CE": [("13897", "FORTALEZA")],
    "PR": [("75353", "CURITIBA")],
    "DF": [("97012", "BRASILIA")],
}

PARTIDOS = [
    ("10", "PARTIDO A", "PARTIDO DEMONSTRACAO A"),
    ("20", "PARTIDO B", "PARTIDO DEMONSTRACAO B"),
    ("30", "PARTIDO C", "PARTIDO DEMONSTRACAO C"),
    ("40", "PARTIDO D", "PARTIDO DEMONSTRACAO D"),
    ("50", "PARTIDO E", "PARTIDO DEMONSTRACAO E"),
]

PRENOMES = ["ANA", "BRUNO", "CARLA", "DANIEL", "ELISA", "FABIO", "GISELE", "HELIO",
            "IARA", "JOAO", "KATIA", "LUCAS", "MARINA", "NELSON", "OLGA", "PAULO",
            "QUEZIA", "RAFAEL", "SONIA", "TIAGO", "URSULA", "VITOR", "WILMA", "YASMIN"]
SOBRENOMES = ["ALMEIDA", "BARROS", "CAMPOS", "DUARTE", "ESTEVES", "FONTES", "GUIMARAES",
              "HENRIQUES", "ITAPUA", "JARDIM", "KLEIN", "LOBATO", "MARTINS", "NOGUEIRA",
              "OLIVAL", "PACHECO", "QUINTELA", "RAMALHO", "SIQUEIRA", "TAVORA"]

ESCOLARIDADE = ["ENSINO FUNDAMENTAL INCOMPLETO", "ENSINO FUNDAMENTAL COMPLETO",
                "ENSINO MEDIO INCOMPLETO", "ENSINO MEDIO COMPLETO",
                "SUPERIOR INCOMPLETO", "SUPERIOR COMPLETO", "LE E ESCREVE"]
OCUPACOES = ["ADVOGADO", "EMPRESARIO", "PROFESSOR", "MEDICO", "SERVIDOR PUBLICO",
             "COMERCIANTE", "AGRICULTOR", "ENGENHEIRO", "JORNALISTA", "APOSENTADO",
             "DEPUTADO", "VEREADOR", "OUTROS"]
COR_RACA = ["BRANCA", "PRETA", "PARDA", "AMARELA", "INDIGENA"]
ESTADO_CIVIL = ["SOLTEIRO(A)", "CASADO(A)", "DIVORCIADO(A)", "VIUVO(A)",
                "SEPARADO(A) JUDICIALMENTE"]
SITUACOES = [("2", "DEFERIDO", "16", "DEFERIDO"),
             ("2", "DEFERIDO", "17", "DEFERIDO COM RECURSO"),
             ("4", "INDEFERIDO", "6", "INDEFERIDO"),
             ("6", "AGUARDANDO JULGAMENTO", "2", "AGUARDANDO JULGAMENTO")]
TIPOS_BEM = [("12", "Casa"), ("13", "Apartamento"), ("21", "Veiculo automotor terrestre"),
             ("45", "Aplicacao de renda fixa"), ("61", "Deposito bancario em conta corrente"),
             ("31", "Acoes"), ("99", "Outros bens e direitos")]

CABECALHO_CAND = [
    "DT_GERACAO", "HH_GERACAO", "ANO_ELEICAO", "CD_TIPO_ELEICAO", "NM_TIPO_ELEICAO",
    "CD_ELEICAO", "DS_ELEICAO", "DT_ELEICAO", "TP_ABRANGENCIA", "SG_UF", "SG_UE", "NM_UE",
    "CD_CARGO", "DS_CARGO", "SQ_CANDIDATO", "NR_CANDIDATO", "NM_CANDIDATO",
    "NM_URNA_CANDIDATO", "NM_SOCIAL_CANDIDATO", "NR_TURNO", "CD_SITUACAO_CANDIDATURA",
    "DS_SITUACAO_CANDIDATURA", "CD_DETALHE_SITUACAO_CAND", "DS_DETALHE_SITUACAO_CAND",
    "TP_AGREMIACAO", "NR_PARTIDO", "SG_PARTIDO", "NM_PARTIDO", "SG_FEDERACAO",
    "NM_FEDERACAO", "NM_COLIGACAO", "DS_COMPOSICAO_COLIGACAO", "DS_NACIONALIDADE",
    "SG_UF_NASCIMENTO", "NM_MUNICIPIO_NASCIMENTO", "DT_NASCIMENTO", "NR_IDADE_DATA_POSSE",
    "DS_GENERO", "DS_GRAU_INSTRUCAO", "DS_ESTADO_CIVIL", "DS_COR_RACA", "DS_OCUPACAO",
    "VR_DESPESA_MAX_CAMPANHA", "ST_REELEICAO", "ST_DECLARAR_BENS",
    "DS_SITUACAO_CANDIDATO_TOT",
]

CABECALHO_BENS = [
    "DT_GERACAO", "HH_GERACAO", "ANO_ELEICAO", "CD_TIPO_ELEICAO", "NM_TIPO_ELEICAO",
    "CD_ELEICAO", "DS_ELEICAO", "DT_ELEICAO", "SG_UF", "SG_UE", "NM_UE", "SQ_CANDIDATO",
    "NR_ORDEM_BEM_CANDIDATO", "CD_TIPO_BEM_CANDIDATO", "DS_TIPO_BEM_CANDIDATO",
    "DS_BEM_CANDIDATO", "VR_BEM_CANDIDATO", "DT_ULTIMA_ATUALIZACAO", "HH_ULTIMA_ATUALIZACAO",
]


def moeda(valor: float) -> str:
    return f"{valor:,.2f}".replace(",", "@").replace(".", ",").replace("@", ".")


def gerar(ano: int, semente: int):
    rnd = random.Random(semente)
    candidatos, bens = [], []
    sequencial = int(f"{ano}0000001")
    usados: set[tuple] = set()
    cd_eleicao = "10000" if ano == 2026 else "10001"
    ds_eleicao = f"ELEICOES GERAIS {ano}" if ano % 4 == 2 else f"ELEICOES MUNICIPAIS {ano}"

    for cd_cargo, ds_cargo, abrangencia, quantidade in CARGOS:
        alvos = []
        if abrangencia == "BR":
            alvos = [("BR", "BR", "BRASIL")]
        elif abrangencia == "UF":
            alvos = [(uf, uf, uf) for uf in UFS]
        else:
            alvos = [(uf, cod, nome) for uf in UFS for cod, nome in MUNICIPIOS[uf]]

        for sg_uf, sg_ue, nm_ue in alvos:
            for _ in range(max(3, quantidade // max(1, len(alvos)))):
                nr_partido, sg_partido, nm_partido = rnd.choice(PARTIDOS)
                numero = f"{nr_partido}{rnd.randint(0, 999):03d}" if cd_cargo in (6, 7, 8, 13) else nr_partido
                if (cd_cargo, sg_uf, sg_ue, numero) in usados:
                    continue
                usados.add((cd_cargo, sg_uf, sg_ue, numero))

                sequencial += 1
                sq = str(sequencial)
                nome = f"{rnd.choice(PRENOMES)} {rnd.choice(SOBRENOMES)} {rnd.choice(SOBRENOMES)}"
                urna = " ".join(nome.split()[:2])
                cd_sit, ds_sit, cd_det, ds_det = rnd.choice(SITUACOES)
                nascimento = f"{rnd.randint(1,28):02d}/{rnd.randint(1,12):02d}/{rnd.randint(1955, 2004)}"

                candidatos.append({
                    "DT_GERACAO": f"01/09/{ano}", "HH_GERACAO": "03:00:00",
                    "ANO_ELEICAO": ano, "CD_TIPO_ELEICAO": "2",
                    "NM_TIPO_ELEICAO": "ELEICAO ORDINARIA", "CD_ELEICAO": cd_eleicao,
                    "DS_ELEICAO": ds_eleicao, "DT_ELEICAO": f"04/10/{ano}",
                    "TP_ABRANGENCIA": "FEDERAL" if abrangencia != "MUN" else "MUNICIPAL",
                    "SG_UF": sg_uf, "SG_UE": sg_ue, "NM_UE": nm_ue,
                    "CD_CARGO": cd_cargo, "DS_CARGO": ds_cargo,
                    "SQ_CANDIDATO": sq, "NR_CANDIDATO": numero,
                    "NM_CANDIDATO": nome, "NM_URNA_CANDIDATO": urna,
                    "NM_SOCIAL_CANDIDATO": "#NULO#", "NR_TURNO": "1",
                    "CD_SITUACAO_CANDIDATURA": cd_sit, "DS_SITUACAO_CANDIDATURA": ds_sit,
                    "CD_DETALHE_SITUACAO_CAND": cd_det, "DS_DETALHE_SITUACAO_CAND": ds_det,
                    "TP_AGREMIACAO": "PARTIDO ISOLADO" if rnd.random() < 0.5 else "COLIGACAO",
                    "NR_PARTIDO": nr_partido, "SG_PARTIDO": sg_partido, "NM_PARTIDO": nm_partido,
                    "SG_FEDERACAO": "#NULO#", "NM_FEDERACAO": "#NULO#",
                    "NM_COLIGACAO": rnd.choice(["PARTIDO ISOLADO", "UNIAO PELA DEMONSTRACAO",
                                                "FRENTE DE EXEMPLO"]),
                    "DS_COMPOSICAO_COLIGACAO": " / ".join(
                        sorted({p[1] for p in rnd.sample(PARTIDOS, rnd.randint(1, 3))})),
                    "DS_NACIONALIDADE": "BRASILEIRA NATA",
                    "SG_UF_NASCIMENTO": rnd.choice(UFS),
                    "NM_MUNICIPIO_NASCIMENTO": rnd.choice([m[1] for m in MUNICIPIOS[rnd.choice(UFS)]]),
                    "DT_NASCIMENTO": nascimento,
                    "NR_IDADE_DATA_POSSE": str(rnd.randint(21, 70)),
                    "DS_GENERO": rnd.choice(["MASCULINO", "FEMININO"]),
                    "DS_GRAU_INSTRUCAO": rnd.choice(ESCOLARIDADE),
                    "DS_ESTADO_CIVIL": rnd.choice(ESTADO_CIVIL),
                    "DS_COR_RACA": rnd.choice(COR_RACA),
                    "DS_OCUPACAO": rnd.choice(OCUPACOES),
                    "VR_DESPESA_MAX_CAMPANHA": moeda(rnd.randint(50_000, 5_000_000)),
                    "ST_REELEICAO": rnd.choice(["S", "N"]),
                    "ST_DECLARAR_BENS": "S",
                    "DS_SITUACAO_CANDIDATO_TOT": rnd.choice(["APTO", "INAPTO"]),
                })

                for ordem in range(1, rnd.randint(1, 7)):
                    cd_tipo, ds_tipo = rnd.choice(TIPOS_BEM)
                    bens.append({
                        "DT_GERACAO": f"01/09/{ano}", "HH_GERACAO": "03:00:00",
                        "ANO_ELEICAO": ano, "CD_TIPO_ELEICAO": "2",
                        "NM_TIPO_ELEICAO": "ELEICAO ORDINARIA", "CD_ELEICAO": cd_eleicao,
                        "DS_ELEICAO": ds_eleicao, "DT_ELEICAO": f"04/10/{ano}",
                        "SG_UF": sg_uf, "SG_UE": sg_ue, "NM_UE": nm_ue,
                        "SQ_CANDIDATO": sq, "NR_ORDEM_BEM_CANDIDATO": ordem,
                        "CD_TIPO_BEM_CANDIDATO": cd_tipo, "DS_TIPO_BEM_CANDIDATO": ds_tipo,
                        "DS_BEM_CANDIDATO": f"{ds_tipo} declarado (registro de exemplo {ordem})",
                        "VR_BEM_CANDIDATO": moeda(rnd.randint(1_000, 3_000_000)),
                        "DT_ULTIMA_ATUALIZACAO": f"15/08/{ano}",
                        "HH_ULTIMA_ATUALIZACAO": "10:00:00",
                    })

    return candidatos, bens


def gravar_csv(caminho: pathlib.Path, cabecalho: list[str], linhas: list[dict]) -> None:
    buffer = io.StringIO()
    escritor = csv.DictWriter(buffer, fieldnames=cabecalho, delimiter=";",
                              quoting=csv.QUOTE_ALL, lineterminator="\r\n")
    escritor.writeheader()
    for linha in linhas:
        escritor.writerow(linha)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_bytes(buffer.getvalue().encode("latin-1", errors="replace"))


def gerar_externos(con, semente: int) -> pathlib.Path:
    """Gera dados externos ficticios para demonstrar as colunas de fora do TSE."""
    rnd = random.Random(semente + 7)
    candidatos = [
        linha["chave"] for linha in con.execute(
            "SELECT chave FROM candidato ORDER BY chave"
        )
    ]
    amostra = rnd.sample(candidatos, max(1, len(candidatos) // 3))

    espectros = ["Esquerda", "Centro-esquerda", "Centro", "Centro-direita", "Direita"]
    registros = []
    for chave in amostra:
        registros.append({
            "chave": chave, "fonte": "cnia", "campo": "situacao",
            "valor": rnd.choice(["Nada consta", "Nada consta", "Nada consta",
                                 "1 condenacao registrada"]),
            "url": "https://www.cnj.jus.br/improbidade_adm/consultar_requerido.php",
            "observacao": "Registro de demonstracao",
        })
        if rnd.random() < 0.6:
            qtd = rnd.randint(0, 5)
            registros.append({
                "chave": chave, "fonte": "excelencias", "campo": "processos",
                "valor": f"{qtd} processo(s)", "valor_num": qtd,
                "url": "https://www.excelencias.org.br/",
                "observacao": "Registro de demonstracao",
            })
        if rnd.random() < 0.4:
            indice = round(rnd.uniform(-1, 1), 2)
            registros.append({
                "chave": chave, "fonte": "congresso", "campo": "espectro",
                "valor": espectros[min(4, int((indice + 1) / 0.4))], "valor_num": indice,
                "url": "https://dadosabertos.camara.leg.br/",
                "observacao": "Registro de demonstracao",
            })
        if rnd.random() < 0.5:
            qtd = rnd.randint(0, 40)
            registros.append({
                "chave": chave, "fonte": "noticias", "campo": "qtd",
                "valor": f"{qtd} materia(s)", "valor_num": qtd,
                "url": "https://news.google.com/",
                "observacao": "Registro de demonstracao",
            })

    destino = RAIZ / "dados" / "externo" / "exemplo_externo.json"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(registros, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{destino} ({len(registros)} registros externos de exemplo)")
    return destino


def main() -> int:
    p = argparse.ArgumentParser(description="Gera uma base de demonstracao ficticia.")
    p.add_argument("--ano", type=int, default=2026)
    p.add_argument("--semente", type=int, default=2026, help="semente do gerador (reproduzivel)")
    p.add_argument("--so-arquivos", action="store_true",
                   help="apenas grava os CSVs, sem importar para o banco")
    args = p.parse_args()

    destino = RAIZ / "dados" / "tse"
    candidatos, bens = gerar(args.ano, args.semente)

    arq_cand = destino / f"consulta_cand_{args.ano}_EXEMPLO.csv"
    arq_bens = destino / f"bem_candidato_{args.ano}_EXEMPLO.csv"
    gravar_csv(arq_cand, CABECALHO_CAND, candidatos)
    gravar_csv(arq_bens, CABECALHO_BENS, bens)
    print(f"{arq_cand} ({len(candidatos)} candidatos)")
    print(f"{arq_bens} ({len(bens)} bens)")

    if args.so_arquivos:
        return 0

    comando = [sys.executable, str(RAIZ / "scripts" / "importar_tse.py"),
               str(arq_cand), str(arq_bens), "--ano", str(args.ano), "--limpar"]
    resultado = subprocess.run(comando, cwd=RAIZ)
    if resultado.returncode != 0:
        return resultado.returncode

    con = banco.conectar()
    arquivo_externo = gerar_externos(con, args.semente)
    subprocess.run([sys.executable, str(RAIZ / "scripts" / "importar_externos.py"),
                    str(arquivo_externo)], cwd=RAIZ)

    banco.definir_meta(con, "origem_base", "EXEMPLO")
    banco.definir_meta(con, "aviso_base",
                       "Base de demonstração com dados fictícios. Nenhum nome, patrimônio "
                       "ou situação aqui corresponde a pessoa real. Rode "
                       "scripts/importar_tse.py --baixar para usar a base oficial do TSE.")
    con.commit()
    print("\nbase marcada como EXEMPLO (o site exibe o aviso no topo)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
