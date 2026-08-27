"""Camada de navegador para as fontes sem captcha.

Alguns sites de transparência renderizam o conteúdo por JavaScript, ou recusam
requisição HTTP simples vinda de IP de datacenter. Para esses, uma requisição
com `urllib` volta vazia mesmo estando tudo certo.

Este módulo abre a página num navegador real (Playwright + Chromium) e devolve
o HTML já renderizado. É estritamente um plano B: `rede.buscar` continua sendo
a primeira tentativa, porque é mais rápida e mais leve.

O Playwright é **opcional**. Sem ele instalado, `disponivel()` devolve False e
os coletores seguem só com HTTP — o site e os importadores continuam rodando
com a biblioteca padrão, sem nenhuma dependência.

    pip install playwright && playwright install chromium

Escopo deliberado: este módulo NÃO é usado em páginas com captcha. CNIA, BNMP e
as consultas processuais dos tribunais ficam fora — abrir um navegador não
resolve captcha moderno, que avalia fingerprint e comportamento, e contornar
isso em massa em site do Judiciário não é o que este projeto faz.
"""

from __future__ import annotations

import os
import urllib.parse

from .rede import AGENTE, ErroDeColeta

TEMPO_LIMITE = int(os.environ.get("COLETOR_NAVEGADOR_TIMEOUT", "45")) * 1000
ESPERA_REDE = os.environ.get("COLETOR_NAVEGADOR_ESPERA", "networkidle")

_navegador = None
_playwright = None


def disponivel() -> bool:
    """True se o Playwright está instalado neste ambiente."""
    try:
        import playwright.sync_api  # noqa: F401
    except ImportError:
        return False
    return True


def _abrir():
    """Sobe um Chromium só, reaproveitado por todas as páginas da execução."""
    global _navegador, _playwright
    if _navegador is not None:
        return _navegador

    from playwright.sync_api import sync_playwright

    _playwright = sync_playwright().start()
    argumentos = {"headless": True}
    # Em imagens que já trazem o Chromium pronto, aponta direto para ele.
    executavel = os.environ.get("COLETOR_NAVEGADOR_BINARIO")
    if executavel:
        argumentos["executable_path"] = executavel
    proxy = os.environ.get("COLETOR_PROXY")
    if proxy:
        argumentos["proxy"] = _proxy_para_playwright(proxy)

    _navegador = _playwright.chromium.launch(**argumentos)
    return _navegador


def _proxy_para_playwright(proxy: str) -> dict:
    """Separa usuário e senha da URL do proxy.

    O Chromium não aceita credencial embutida em `http://usuario:senha@host` —
    ele ignora e leva 407. O Playwright quer os três campos separados.
    """
    partes = urllib.parse.urlsplit(proxy)
    servidor = f"{partes.scheme}://{partes.hostname}"
    if partes.port:
        servidor += f":{partes.port}"

    configuracao = {"server": servidor}
    if partes.username:
        configuracao["username"] = urllib.parse.unquote(partes.username)
    if partes.password:
        configuracao["password"] = urllib.parse.unquote(partes.password)
    return configuracao


def fechar() -> None:
    global _navegador, _playwright
    if _navegador is not None:
        _navegador.close()
        _navegador = None
    if _playwright is not None:
        _playwright.stop()
        _playwright = None


def buscar(url: str, *, esperar_seletor: str | None = None) -> str:
    """Abre a URL num navegador real e devolve o HTML renderizado."""
    if not disponivel():
        raise ErroDeColeta(
            "Playwright não está instalado; instale com "
            "'pip install playwright && playwright install chromium' "
            "ou deixe o coletor usar apenas HTTP."
        )

    try:
        contexto = _abrir().new_context(
            user_agent=AGENTE,
            locale="pt-BR",
            viewport={"width": 1366, "height": 900},
        )
        pagina = contexto.new_page()
        try:
            pagina.goto(url, wait_until=ESPERA_REDE, timeout=TEMPO_LIMITE)
            if esperar_seletor:
                pagina.wait_for_selector(esperar_seletor, timeout=TEMPO_LIMITE)
            return pagina.content()
        finally:
            contexto.close()
    except Exception as erro:  # noqa: BLE001 - erros do Playwright são variados
        raise ErroDeColeta(f"{url}: navegador falhou ({erro})") from erro


def buscar_com_plano_b(url: str, *, minimo: int = 500,
                       esperar_seletor: str | None = None) -> str:
    """HTTP primeiro; navegador só se o HTTP vier vazio, curto ou falhar.

    `minimo` é o tamanho abaixo do qual a resposta HTTP é considerada suspeita
    — página de bloqueio e casca de aplicação JavaScript costumam ser curtas.
    """
    from . import rede

    try:
        html = rede.buscar(url)
        if len(html) >= minimo:
            return html
    except ErroDeColeta:
        html = ""

    if not disponivel():
        if html:
            return html
        raise ErroDeColeta(f"{url}: resposta vazia e sem navegador disponível")

    return buscar(url, esperar_seletor=esperar_seletor)
