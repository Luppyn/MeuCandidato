"""Camada de rede dos coletores.

Um cliente HTTP pequeno, com cache em disco, intervalo minimo entre requisicoes
ao mesmo dominio e novas tentativas com espera crescente. Nada alem da
biblioteca padrao.

Nenhuma das fontes dos itens 4 a 8 do escopo publica API. Algumas respondem bem
a uma requisicao HTTP comum; outras exigem sair de um IP residencial ou resolver
captcha. Para essas, existe um ponto de extensao opcional: se as variaveis de
ambiente abaixo estiverem definidas, a requisicao passa por um servico de
desbloqueio em vez de ir direto.

    COLETOR_PROXY            proxy HTTP(S) comum, ex.: http://usuario:senha@host:porta
    COLETOR_UNLOCKER_URL     endpoint da API de desbloqueio
                             (padrao: https://api.brightdata.com/request)
    COLETOR_UNLOCKER_TOKEN   token enviado como Bearer
    COLETOR_UNLOCKER_ZONA    nome da zona/perfil no servico

O formato do payload segue a Web Unlocker API da Bright Data
({"zone": ..., "url": ..., "format": "raw"}), que outros servicos tambem
adotam. Sem essas variaveis nada muda: o coletor faz a requisicao direta.

Nenhuma credencial fica no repositorio - tudo vem do ambiente.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import pathlib
import random
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser

RAIZ = pathlib.Path(__file__).resolve().parent.parent.parent
CACHE = pathlib.Path(os.environ.get("COLETOR_CACHE", str(RAIZ / "dados" / "cache")))

AGENTE = os.environ.get(
    "COLETOR_AGENTE",
    "MeuCandidato/1.0 (ferramenta de consulta a dados publicos; "
    "https://github.com/Luppyn/MeuCandidato)",
)

# Alguns servidores publicos ficam atras de WAF que recusa qualquer
# User-Agent que nao pareca navegador - inclusive para baixar arquivo que o
# proprio orgao publica como dado aberto. A ordem abaixo tenta primeiro o
# agente que identifica o projeto, e so recua quando levar 403.
AGENTES = [
    AGENTE,
    f"Mozilla/5.0 (compatible; {AGENTE})",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36",
]
INTERVALO = float(os.environ.get("COLETOR_INTERVALO", "1.5"))   # segundos por dominio
TENTATIVAS = int(os.environ.get("COLETOR_TENTATIVAS", "3"))
TEMPO_LIMITE = int(os.environ.get("COLETOR_TIMEOUT", "45"))
VALIDADE_CACHE = int(os.environ.get("COLETOR_CACHE_HORAS", "72")) * 3600

_ultimo_acesso: dict[str, float] = {}


def esconder_credenciais(texto: str) -> str:
    """Troca usuario:senha de qualquer URL por ***.

    O proxy residencial chega como http://usuario:senha@host:porta. Essa
    string nao pode vazar em log nem em mensagem de erro - inclusive porque o
    mascaramento automatico do GitHub Actions só cobre o valor exato do
    secret, e uma mensagem de erro costuma trazer só um pedaço dele.
    """
    # Guloso ate o ULTIMO @ antes do caminho: senha com @ dentro (comum, e
    # raramente percent-encoded) tambem precisa ser coberta.
    return re.sub(r"://[^/\s]+@", "://***:***@", str(texto))


class ErroDeColeta(Exception):
    """A fonte nao respondeu, mudou de formato ou bloqueou a requisicao."""

    def __init__(self, mensagem):
        super().__init__(esconder_credenciais(mensagem))


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

def _arquivo_cache(url: str, corpo: bytes | None) -> pathlib.Path:
    digest = hashlib.sha256(url.encode("utf-8") + (corpo or b"")).hexdigest()[:32]
    return CACHE / digest[:2] / f"{digest}.gz"


def _ler_cache(caminho: pathlib.Path) -> str | None:
    if not caminho.is_file():
        return None
    if VALIDADE_CACHE and time.time() - caminho.stat().st_mtime > VALIDADE_CACHE:
        return None
    try:
        return gzip.decompress(caminho.read_bytes()).decode("utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def _gravar_cache(caminho: pathlib.Path, texto: str) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_bytes(gzip.compress(texto.encode("utf-8")))


# ---------------------------------------------------------------------------
# Requisicoes
# ---------------------------------------------------------------------------

def _esperar_a_vez(url: str) -> None:
    dominio = urllib.parse.urlsplit(url).netloc
    passou = time.time() - _ultimo_acesso.get(dominio, 0.0)
    if passou < INTERVALO:
        time.sleep(INTERVALO - passou + random.uniform(0, 0.4))
    _ultimo_acesso[dominio] = time.time()


_bypass_limpo = False


def _garantir_proxy_valendo() -> None:
    """Remove `no_proxy` do ambiente quando há proxy configurado.

    O urllib consulta `no_proxy` mesmo quando o proxy é passado explicitamente:
    para os domínios listados ali, ele devolve a requisição direta, em
    silêncio. Numa coleta que depende de sair por IP residencial, isso é o pior
    tipo de falha - tudo parece funcionar, e a fonte é quem vê o IP errado.

    Se COLETOR_PROXY foi definido, foi de propósito. O desvio sai da frente.
    """
    global _bypass_limpo
    if _bypass_limpo or not os.environ.get("COLETOR_PROXY"):
        return
    removidos = [v for v in ("no_proxy", "NO_PROXY") if os.environ.pop(v, None)]
    if removidos:
        print(f"  rede: {' e '.join(removidos)} ignorado(s) — COLETOR_PROXY vale "
              f"para todos os domínios.")
    _bypass_limpo = True


def _abridor() -> urllib.request.OpenerDirector:
    proxy = os.environ.get("COLETOR_PROXY")
    if not proxy:
        return urllib.request.build_opener()

    _garantir_proxy_valendo()
    return urllib.request.build_opener(
        urllib.request.ProxyHandler({"http": proxy, "https": proxy})
    )


def _via_desbloqueador(url: str) -> str | None:
    """Usa o servico de desbloqueio, se estiver configurado no ambiente."""
    token = os.environ.get("COLETOR_UNLOCKER_TOKEN")
    zona = os.environ.get("COLETOR_UNLOCKER_ZONA")
    if not (token and zona):
        return None

    endpoint = os.environ.get("COLETOR_UNLOCKER_URL", "https://api.brightdata.com/request")
    corpo = json.dumps({"zone": zona, "url": url, "format": "raw"}).encode("utf-8")
    requisicao = urllib.request.Request(endpoint, data=corpo, method="POST", headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "User-Agent": AGENTE,
    })
    with urllib.request.urlopen(requisicao, timeout=TEMPO_LIMITE * 2) as resposta:
        return resposta.read().decode("utf-8", errors="replace")


def buscar(url: str, *, cabecalhos: dict | None = None, corpo: bytes | None = None,
           usar_cache: bool = True, desbloquear: bool = False) -> str:
    """Busca uma URL e devolve o texto da resposta.

    `desbloquear=True` faz a requisicao passar pelo servico de desbloqueio
    quando ele estiver configurado; sem configuracao, cai na requisicao direta.
    """
    caminho = _arquivo_cache(url, corpo)
    if usar_cache:
        guardado = _ler_cache(caminho)
        if guardado is not None:
            return guardado

    erro_final: Exception | None = None
    for tentativa in range(1, TENTATIVAS + 1):
        try:
            _esperar_a_vez(url)

            if desbloquear:
                texto = _via_desbloqueador(url)
                if texto is not None:
                    if usar_cache:
                        _gravar_cache(caminho, texto)
                    return texto

            requisicao = urllib.request.Request(url, data=corpo, headers={
                "User-Agent": AGENTE,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,"
                          "application/json;q=0.9,*/*;q=0.8",
                "Accept-Language": "pt-BR,pt;q=0.9",
                **(cabecalhos or {}),
            })
            with _abridor().open(requisicao, timeout=TEMPO_LIMITE) as resposta:
                dados = resposta.read()
                if resposta.headers.get("Content-Encoding") == "gzip":
                    dados = gzip.decompress(dados)
                codificacao = resposta.headers.get_content_charset() or "utf-8"
                texto = dados.decode(codificacao, errors="replace")

            if usar_cache:
                _gravar_cache(caminho, texto)
            return texto

        except urllib.error.HTTPError as erro:
            erro_final = erro
            # 4xx (fora 429) nao melhora com nova tentativa.
            if erro.code not in (408, 429) and erro.code < 500:
                break
        except (urllib.error.URLError, TimeoutError, OSError) as erro:
            erro_final = erro

        if tentativa < TENTATIVAS:
            time.sleep(2 ** tentativa + random.uniform(0, 1))

    raise ErroDeColeta(f"{url}: {erro_final}")


def baixar_arquivo(url: str, destino: pathlib.Path, *, rotular="") -> int:
    """Baixa um arquivo grande direto para o disco.

    Usa a mesma camada das demais requisicoes - proxy, novas tentativas,
    credencial escondida em erro - e, diante de 403, tenta os outros
    User-Agents antes de desistir.

    Devolve o tamanho em bytes. Levanta ErroDeColeta com o que foi tentado.
    """
    destino.parent.mkdir(parents=True, exist_ok=True)
    tentativas: list[str] = []

    for agente in AGENTES:
        for tentativa in range(1, TENTATIVAS + 1):
            try:
                _esperar_a_vez(url)
                requisicao = urllib.request.Request(url, headers={
                    "User-Agent": agente,
                    "Accept": "application/zip,application/octet-stream,*/*",
                    "Accept-Language": "pt-BR,pt;q=0.9",
                })
                parcial = destino.with_suffix(destino.suffix + ".parcial")
                with _abridor().open(requisicao, timeout=TEMPO_LIMITE * 10) as resposta, \
                        parcial.open("wb") as saida:
                    total = 0
                    while bloco := resposta.read(1024 * 256):
                        saida.write(bloco)
                        total += len(bloco)
                        if (rotular and total >= 1024 * 1024 * 20
                                and total % (1024 * 1024 * 20) < 1024 * 256):
                            print(f"    {rotular}: {total / 1_000_000:.0f} MB", flush=True)
                if total == 0:
                    parcial.unlink(missing_ok=True)
                    raise ErroDeColeta(f"{url}: resposta vazia")
                parcial.replace(destino)
                return total

            except urllib.error.HTTPError as erro:
                tentativas.append(f"{erro.code} com agente {agente[:40]}...")
                if erro.code in (403, 406):
                    break          # WAF recusou este agente; tenta o proximo
                if erro.code < 500 and erro.code != 429:
                    raise ErroDeColeta(f"{url}: HTTP {erro.code}") from erro
            except (urllib.error.URLError, TimeoutError, OSError) as erro:
                tentativas.append(f"{type(erro).__name__} com agente {agente[:40]}...")

            if tentativa < TENTATIVAS:
                time.sleep(2 ** tentativa + random.uniform(0, 1))

    raise ErroDeColeta(f"{url}: nao foi possivel baixar. Tentado: "
                       + "; ".join(tentativas))


def buscar_json(url: str, **kwargs) -> dict | list:
    texto = buscar(url, **kwargs)
    try:
        return json.loads(texto)
    except json.JSONDecodeError as erro:
        raise ErroDeColeta(f"{url}: resposta nao e JSON ({erro})") from erro


# ---------------------------------------------------------------------------
# Leitura de HTML (html.parser da biblioteca padrao)
# ---------------------------------------------------------------------------

class _Texto(HTMLParser):
    IGNORAR = {"script", "style", "noscript", "template"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.partes: list[str] = []
        self._pular = 0

    def handle_starttag(self, tag, attrs):
        if tag in self.IGNORAR:
            self._pular += 1
        elif tag in ("br", "p", "tr", "li", "div", "h1", "h2", "h3", "h4"):
            self.partes.append("\n")

    def handle_endtag(self, tag):
        if tag in self.IGNORAR and self._pular:
            self._pular -= 1

    def handle_data(self, dados):
        if not self._pular:
            self.partes.append(dados)


def texto_de(html: str) -> str:
    """Extrai o texto visivel de um HTML, com quebras de linha preservadas."""
    leitor = _Texto()
    leitor.feed(html)
    bruto = "".join(leitor.partes)
    linhas = [" ".join(linha.split()) for linha in bruto.splitlines()]
    return "\n".join(linha for linha in linhas if linha)


class _Links(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, str]] = []
        self._href: str | None = None
        self._rotulo: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self._href = dict(attrs).get("href")
            self._rotulo = []

    def handle_data(self, dados):
        if self._href is not None:
            self._rotulo.append(dados)

    def handle_endtag(self, tag):
        if tag == "a" and self._href:
            self.links.append((self._href, " ".join("".join(self._rotulo).split())))
            self._href = None


def links_de(html: str, base: str | None = None) -> list[tuple[str, str]]:
    """Devolve [(url, rotulo)] de todos os <a> do documento."""
    leitor = _Links()
    leitor.feed(html)
    if base is None:
        return leitor.links
    return [(urllib.parse.urljoin(base, href), rotulo) for href, rotulo in leitor.links]


class _Tabelas(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tabelas: list[list[list[str]]] = []
        self._tabela = None
        self._linha = None
        self._celula = None

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self._tabela = []
        elif tag == "tr" and self._tabela is not None:
            self._linha = []
        elif tag in ("td", "th") and self._linha is not None:
            self._celula = []

    def handle_data(self, dados):
        if self._celula is not None:
            self._celula.append(dados)

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._celula is not None:
            self._linha.append(" ".join("".join(self._celula).split()))
            self._celula = None
        elif tag == "tr" and self._linha is not None:
            if any(self._linha):
                self._tabela.append(self._linha)
            self._linha = None
        elif tag == "table" and self._tabela is not None:
            self.tabelas.append(self._tabela)
            self._tabela = None


def tabelas_de(html: str) -> list[list[list[str]]]:
    """Devolve todas as <table> como listas de linhas de celulas em texto."""
    leitor = _Tabelas()
    leitor.feed(html)
    return leitor.tabelas


SERVICOS_DE_IP = (
    "https://api.ipify.org?format=json",
    "https://ifconfig.co/json",
)


def verificar_saida() -> dict:
    """Diz por qual IP a coleta está saindo. Não imprime credencial nenhuma.

    Serve para confirmar, no log do GitHub Actions, que a coleta realmente
    passou pelo proxy residencial - sem o que a única forma de descobrir seria
    a fonte bloquear.
    """
    proxy = os.environ.get("COLETOR_PROXY")
    resultado = {
        "proxy_configurado": bool(proxy),
        "proxy_host": None,
        "ip_de_saida": None,
        "erro": None,
    }
    if proxy:
        partes = urllib.parse.urlsplit(proxy)
        # Só host e porta: usuário e senha ficam de fora de propósito.
        resultado["proxy_host"] = f"{partes.hostname}:{partes.port or ''}".rstrip(":")

    for servico in SERVICOS_DE_IP:
        try:
            dados = json.loads(buscar(servico, usar_cache=False))
        except (ErroDeColeta, json.JSONDecodeError):
            continue
        resultado["ip_de_saida"] = dados.get("ip")
        if resultado["ip_de_saida"]:
            return resultado

    resultado["erro"] = "nenhum serviço de eco de IP respondeu"
    return resultado


def limpar_cache() -> int:
    if not CACHE.exists():
        return 0
    apagados = 0
    for arquivo in CACHE.rglob("*.gz"):
        arquivo.unlink()
        apagados += 1
    return apagados
