"""Acesso ao banco SQLite do MeuCandidato.

Um unico arquivo SQLite guarda tudo: a base do TSE (candidatos e bens), os
dados que chegam de fora (colunas sem API oficial) e o registro de
proveniencia de cada importacao.

Nada aqui depende de biblioteca externa: apenas a biblioteca padrao do Python.
"""

from __future__ import annotations

import os
import pathlib
import sqlite3
import unicodedata
from datetime import datetime, timezone

RAIZ = pathlib.Path(__file__).resolve().parent
CAMINHO_PADRAO = RAIZ / "dados" / "meucandidato.sqlite"
VERSAO_ESQUEMA = 1

ESQUEMA = """
CREATE TABLE IF NOT EXISTS candidato (
    id                        INTEGER PRIMARY KEY,
    chave                     TEXT    NOT NULL UNIQUE,
    ano_eleicao               INTEGER NOT NULL,
    cd_eleicao                TEXT,
    ds_eleicao                TEXT,
    nm_tipo_eleicao           TEXT,
    nr_turno                  INTEGER,
    sq_candidato              TEXT,
    nr_candidato              TEXT,
    nm_candidato              TEXT,
    nm_urna                   TEXT,
    nm_social                 TEXT,
    nm_busca                  TEXT,
    cd_cargo                  INTEGER,
    ds_cargo                  TEXT,
    sg_uf                     TEXT,
    sg_ue                     TEXT,
    nm_ue                     TEXT,
    nr_partido                TEXT,
    sg_partido                TEXT,
    nm_partido                TEXT,
    sg_federacao              TEXT,
    nm_federacao              TEXT,
    nm_coligacao              TEXT,
    ds_composicao_coligacao   TEXT,
    ds_situacao_candidatura   TEXT,
    ds_detalhe_situacao_cand  TEXT,
    ds_situacao_candidato_tot TEXT,
    ds_genero                 TEXT,
    dt_nascimento             TEXT,
    nr_idade_data_posse       TEXT,
    ds_estado_civil           TEXT,
    ds_cor_raca               TEXT,
    ds_ocupacao               TEXT,
    ds_grau_instrucao         TEXT,
    ds_nacionalidade          TEXT,
    nm_municipio_nascimento   TEXT,
    sg_uf_nascimento          TEXT,
    st_reeleicao              TEXT,
    st_declarar_bens          TEXT,
    vr_despesa_max_campanha   REAL,
    qtd_bens                  INTEGER NOT NULL DEFAULT 0,
    total_bens                REAL    NOT NULL DEFAULT 0,
    url_divulgacand           TEXT,
    url_foto                  TEXT,
    importacao_id             INTEGER
);

CREATE INDEX IF NOT EXISTS ix_candidato_filtro
    ON candidato (ano_eleicao, cd_cargo, sg_uf, sg_ue);
CREATE INDEX IF NOT EXISTS ix_candidato_busca  ON candidato (nm_busca);
CREATE INDEX IF NOT EXISTS ix_candidato_partido ON candidato (sg_partido);

CREATE TABLE IF NOT EXISTS bem (
    id            INTEGER PRIMARY KEY,
    candidato_id  INTEGER NOT NULL REFERENCES candidato(id) ON DELETE CASCADE,
    nr_ordem      INTEGER,
    cd_tipo       TEXT,
    ds_tipo       TEXT,
    ds_bem        TEXT,
    vr_bem        REAL,
    dt_atualizacao TEXT,
    importacao_id INTEGER,
    UNIQUE (candidato_id, nr_ordem)
);

CREATE INDEX IF NOT EXISTS ix_bem_candidato ON bem (candidato_id);

-- Dados que nao vem do TSE. Ligados pela chave textual do candidato (e nao
-- por FK) para que possam ser carregados antes da base do TSE e sobreviver a
-- uma reimportacao completa dela.
CREATE TABLE IF NOT EXISTS dado_externo (
    id            INTEGER PRIMARY KEY,
    chave         TEXT NOT NULL,
    fonte         TEXT NOT NULL,
    campo         TEXT NOT NULL,
    valor         TEXT,
    valor_num     REAL,
    url           TEXT,
    observacao    TEXT,
    coletado_em   TEXT,
    importacao_id INTEGER,
    UNIQUE (chave, fonte, campo)
);

CREATE INDEX IF NOT EXISTS ix_dado_externo_chave ON dado_externo (chave);

CREATE TABLE IF NOT EXISTS fonte (
    slug                TEXT PRIMARY KEY,
    nome                TEXT NOT NULL,
    url                 TEXT,
    categoria           TEXT,
    tem_api             INTEGER NOT NULL DEFAULT 0,
    descricao           TEXT,
    url_consulta_manual TEXT,
    licenca             TEXT,
    atualizado_em       TEXT
);

-- Registro de proveniencia: toda linha do banco pode ser rastreada ate o
-- arquivo de origem, com data e hash do conteudo importado.
CREATE TABLE IF NOT EXISTS importacao (
    id              INTEGER PRIMARY KEY,
    iniciado_em     TEXT,
    concluido_em    TEXT,
    tipo            TEXT,
    origem          TEXT,
    arquivo         TEXT,
    sha256          TEXT,
    bytes           INTEGER,
    linhas_lidas    INTEGER DEFAULT 0,
    linhas_gravadas INTEGER DEFAULT 0,
    observacao      TEXT
);

CREATE TABLE IF NOT EXISTS meta (
    chave TEXT PRIMARY KEY,
    valor TEXT
);
"""


def caminho_banco() -> pathlib.Path:
    """Caminho do arquivo SQLite (sobrescrevivel por MC_BANCO)."""
    return pathlib.Path(os.environ.get("MC_BANCO", str(CAMINHO_PADRAO)))


def conectar(somente_leitura: bool = False) -> sqlite3.Connection:
    caminho = caminho_banco()
    if somente_leitura:
        if not caminho.exists():
            raise FileNotFoundError(caminho)
        con = sqlite3.connect(f"file:{caminho}?mode=ro", uri=True, check_same_thread=False)
    else:
        caminho.parent.mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(caminho, check_same_thread=False)
        con.execute("PRAGMA journal_mode = WAL")
        con.execute("PRAGMA foreign_keys = ON")
    con.row_factory = sqlite3.Row
    return con


def criar_esquema(con: sqlite3.Connection) -> None:
    con.executescript(ESQUEMA)
    definir_meta(con, "versao_esquema", str(VERSAO_ESQUEMA))
    con.commit()


def agora() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def definir_meta(con: sqlite3.Connection, chave: str, valor: str) -> None:
    con.execute(
        "INSERT INTO meta (chave, valor) VALUES (?, ?) "
        "ON CONFLICT(chave) DO UPDATE SET valor = excluded.valor",
        (chave, valor),
    )


def ler_meta(con: sqlite3.Connection, chave: str, padrao: str | None = None) -> str | None:
    linha = con.execute("SELECT valor FROM meta WHERE chave = ?", (chave,)).fetchone()
    return linha["valor"] if linha else padrao


def normalizar(texto: str | None) -> str:
    """Maiusculas, sem acentos - usado para busca por nome."""
    if not texto:
        return ""
    sem_acento = unicodedata.normalize("NFKD", texto)
    sem_acento = "".join(c for c in sem_acento if not unicodedata.combining(c))
    return " ".join(sem_acento.upper().split())


def chave_candidato(ano, cd_cargo, sg_uf, sg_ue, nr_candidato) -> str:
    """Identificador estavel de um candidato.

    O TSE removeu o CPF das bases abertas, entao a identidade e a combinacao
    eleicao + cargo + UF + unidade eleitoral + numero na urna. A unidade
    eleitoral (SG_UE) entra na chave porque em pleitos municipais o mesmo
    numero se repete em municipios diferentes da mesma UF.
    """
    partes = [
        str(ano or "").strip(),
        str(cd_cargo or "").strip(),
        (sg_uf or "").strip().upper(),
        (sg_ue or "").strip().upper(),
        str(nr_candidato or "").strip(),
    ]
    return "-".join(partes)


def abrir_importacao(con, tipo, origem, arquivo=None, sha256=None, bytes_=None, observacao=None) -> int:
    cur = con.execute(
        "INSERT INTO importacao (iniciado_em, tipo, origem, arquivo, sha256, bytes, observacao) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (agora(), tipo, origem, arquivo, sha256, bytes_, observacao),
    )
    con.commit()
    return int(cur.lastrowid)


def fechar_importacao(con, importacao_id, linhas_lidas=0, linhas_gravadas=0, observacao=None) -> None:
    con.execute(
        "UPDATE importacao SET concluido_em = ?, linhas_lidas = ?, linhas_gravadas = ?, "
        "observacao = COALESCE(?, observacao) WHERE id = ?",
        (agora(), linhas_lidas, linhas_gravadas, observacao, importacao_id),
    )
    con.commit()
