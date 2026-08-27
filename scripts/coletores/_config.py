"""Leitura da configuração de APIs oficiais.

Os endereços ficam em config/apis.json e as credenciais em variáveis de
ambiente. Nenhuma chave entra no repositório.
"""

from __future__ import annotations

import json
import os
import pathlib

RAIZ = pathlib.Path(__file__).resolve().parent.parent.parent
CAMINHO = RAIZ / "config" / "apis.json"

_cache: dict | None = None


def apis() -> dict:
    global _cache
    if _cache is None:
        try:
            _cache = json.loads(CAMINHO.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            _cache = {}
    return _cache


def config_de(nome: str) -> dict:
    return apis().get(nome, {})


def chave_de(nome: str) -> str | None:
    """Credencial da API, lida da variável de ambiente que a config nomeia."""
    variavel = config_de(nome).get("variavel_chave")
    return os.environ.get(variavel) if variavel else None


def cabecalho_de(nome: str) -> dict:
    """Cabeçalho de autenticação, ou {} quando não há chave configurada."""
    cfg = config_de(nome)
    chave = chave_de(nome)
    if not chave or not cfg.get("cabecalho_chave"):
        return {}
    return {cfg["cabecalho_chave"]: f"{cfg.get('prefixo_chave', '')}{chave}"}


def falta_chave(nome: str) -> str | None:
    """Mensagem explicando como obter a chave, ou None se ela já existe."""
    cfg = config_de(nome)
    if not cfg.get("variavel_chave") or chave_de(nome):
        return None
    return (f"defina {cfg['variavel_chave']} para usar esta fonte. "
            f"{cfg.get('como_obter', '')}").strip()
