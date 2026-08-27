# Onde rodar o coletor

O site pode ser estático — mas alguém precisa ir buscar os dados, de tempos em
tempos, e devolvê-los para que as páginas sejam regeradas.

Este documento trata só disso: **qual serviço externo executa o coletor**, e
como o resultado volta para o workflow do GitHub que valida, importa e publica.
É diferente do workflow do GitHub fazer a coleta ele mesmo — separar as duas
coisas resolve um problema concreto, explicado logo abaixo.

> Nenhum dos serviços abaixo pôde ser testado de dentro do ambiente onde este
> código foi escrito: a política de rede bloqueia acesso externo. Preços e
> limites vêm da documentação pública das plataformas e **precisam ser
> confirmados** antes de você fechar com qualquer uma.

## Com proxy residencial próprio: o GitHub Actions basta

O runner do GitHub tem IP de datacenter, e é isso — só isso — que faz sites de
transparência responderem 403 ou devolverem página vazia. Com um proxy
residencial brasileiro configurado em secret, esse impedimento desaparece, e
não há mais motivo para manter um serviço externo só para a coleta.

É o caminho recomendado: menos peças, e o histórico do git continua sendo o
registro público da coleta.

### Configurando

Em **Settings → Secrets and variables → Actions → New repository secret**:

| Secret | Valor | Obrigatório |
| --- | --- | --- |
| `COLETOR_PROXY` | `http://usuario:senha@host.do.proxy:porta` | para as fontes que bloqueiam datacenter |
| `CHAVE_PORTAL_TRANSPARENCIA` | chave da API da CGU (gratuita) | para a coluna de sanções |
| `CHAVE_DATAJUD` | chave pública do CNJ | para a tramitação do registro |

O workflow `.github/workflows/coleta-externa.yml` já lê os três.

### Como saber que o proxy está mesmo valendo

Esta é a parte que costuma passar despercebida: se o proxy for ignorado, tudo
parece funcionar — quem vê o IP errado é a fonte, não você. Por isso o workflow
tem um passo que imprime o IP de saída antes de coletar:

```bash
python3 scripts/coletar.py --verificar-saida
```

```
proxy configurado : sim
proxy             : host.do.proxy:8080
IP de saida       : 189.x.x.x
```

Se o IP de saída for um endereço da Azure (os runners do GitHub rodam lá), o
proxy não está sendo usado. **Usuário e senha nunca são impressos** — só host e
porta.

### O que o código faz para o proxy não falhar em silêncio

Três cuidados, todos verificados em teste contra um proxy autenticado real:

- **HTTP e HTTPS passam pelo proxy**, inclusive o `CONNECT` do túnel TLS. Senha
  errada falha; não passa direto.
- **`no_proxy` é neutralizado quando há proxy configurado.** O `urllib` consulta
  essa variável mesmo com proxy explícito e, para os domínios listados ali,
  devolve a requisição direta sem avisar. Se `COLETOR_PROXY` foi definido, foi
  de propósito, e vale para tudo.
- **Credenciais são apagadas de qualquer mensagem de erro.** O mascaramento
  automático do GitHub Actions só cobre o valor exato do secret, e mensagem de
  erro costuma trazer só um pedaço dele. O código troca `usuario:senha@` por
  `***:***@` antes de qualquer texto sair.

O navegador também sai pelo proxy. O Chromium não aceita credencial embutida na
URL — ele ignora e leva 407 —, então usuário e senha vão em campos separados.

### Segurança do workflow

O workflow dispara **só** por agendamento e acionamento manual. Não use
`pull_request` nem `pull_request_target` nele: em repositório público, isso
exporia o proxy e as chaves a qualquer pessoa que abrisse um PR.

Pelo mesmo motivo, prefira `secrets` a `variables`, e não imprima o valor do
proxy em nenhum passo.

## Quando ainda faz sentido um serviço externo

Só em dois casos:

- **Volume acima do limite do Actions.** O plano grátis dá 2.000 minutos/mês em
  repositório privado, e é ilimitado em repositório público. Uma coleta semanal
  não chega perto disso.
- **Você quer o resultado fora do repositório.** Aí vale o desenho abaixo.

Nesse caso, o serviço externo executa o coletor e avisa o GitHub quando termina:

```
  ┌──────────────────────────┐
  │  serviço externo         │   agendado
  │  roda scripts/coletar.py │
  └────────────┬─────────────┘
               │  1. gera JSON no formato de docs/automacao-externa.md
               │  2. POST /repos/{dono}/{repo}/dispatches
               ▼
  ┌──────────────────────────┐
  │  GitHub Actions          │   3. baixa o resultado
  │  on: repository_dispatch │   4. importa, valida e publica
  └──────────────────────────┘
```

```bash
curl -X POST \
  -H "Accept: application/vnd.github+json" \
  -H "Authorization: Bearer $GITHUB_TOKEN" \
  https://api.github.com/repos/Luppyn/MeuCandidato/dispatches \
  -d '{"event_type":"coleta-pronta","client_payload":{"execucao":"'"$ID"'"}}'
```

O workflow reage com `on: repository_dispatch: types: [coleta-pronta]` e usa o
`client_payload` para saber qual execução ler.

Entre os serviços, **Apify** é o único feito exatamente para isto: Actor a
partir do `Dockerfile` do repositório, Schedules para agendar, webhook no fim e
dataset legível por API — com US$ 5/mês de crédito no plano grátis. Modal, Cloud
Run Jobs, Render e Oracle Cloud rodam Python e agendam bem, mas nenhum melhora o
IP em relação ao GitHub, então com proxy próprio não acrescentam nada.

Um **runner self-hosted** (um PC velho registrado no repositório) é a única
alternativa que dispensa proxy, porque já sai por IP residencial. Em repositório
público exige cuidado: desabilite `pull_request` para o job, senão qualquer PR
executaria código na sua máquina.

## O que já está pronto no repositório

- `scripts/coletar.py` — roda em qualquer lugar, sem dependência externa
  (o navegador é opcional).
- `Dockerfile` — base para empacotar o coletor como Actor ou job.
- `.github/workflows/coleta-externa.yml` — coleta pelo próprio Actions.
- Variáveis de ambiente para proxy e desbloqueio, documentadas em
  `docs/hospedagem.md`.

Falta, e depende de você escolher o serviço: o workflow que reage ao
`repository_dispatch` e a geração das páginas estáticas. Os dois são pequenos e
saem juntos assim que a escolha estiver feita.
