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

## Por que separar coleta de publicação

O runner do GitHub Actions tem IP de datacenter, compartilhado com o mundo
inteiro. Vários sites de transparência — e praticamente todo portal de tribunal
— tratam esse tipo de IP com desconfiança: respondem 403, devolvem página vazia
ou entregam um desafio. A coleta falha sem erro aparente, o que é pior do que
falhar com estrondo.

Tirar a coleta de lá resolve isso **se o serviço escolhido tiver IP melhor**.
Esse é o critério que separa as opções abaixo — não é sobre agendamento, que
todas fazem, é sobre de onde a requisição sai.

## O desenho

```
  ┌──────────────────────────┐
  │  serviço externo         │   agendado (ex.: toda segunda, 4h)
  │  roda scripts/coletar.py │
  └────────────┬─────────────┘
               │  1. gera JSON no formato de docs/automacao-externa.md
               │
               │  2. avisa o GitHub  (POST /repos/{dono}/{repo}/dispatches)
               ▼
  ┌──────────────────────────┐
  │  GitHub Actions          │   3. baixa o resultado
  │  .github/workflows/      │   4. importa e valida
  │    publicar.yml          │   5. regenera as páginas estáticas
  └────────────┬─────────────┘   6. commit
               ▼
  ┌──────────────────────────┐
  │  hospedagem estática     │   qualquer visitante, dados já prontos
  └──────────────────────────┘
```

O passo 2 é um `repository_dispatch`: a API do GitHub aceita uma chamada
externa que dispara um workflow e carrega um payload junto. Um token com escopo
`contents:write` basta.

```bash
curl -X POST \
  -H "Accept: application/vnd.github+json" \
  -H "Authorization: Bearer $GITHUB_TOKEN" \
  https://api.github.com/repos/Luppyn/MeuCandidato/dispatches \
  -d '{"event_type":"coleta-pronta","client_payload":{"execucao":"'"$ID"'"}}'
```

O workflow reage com:

```yaml
on:
  repository_dispatch:
    types: [coleta-pronta]
```

E busca o resultado usando o `client_payload` para saber qual execução ler.

## As opções

| Serviço | IP melhor que o GitHub? | Roda Python | Agenda | Custo | Veredito |
| --- | --- | --- | --- | --- | --- |
| **Apify** | **sim** (proxies gerenciados) | sim | sim | US$ 5/mês de crédito grátis | Melhor encaixe |
| **Runner self-hosted** | **sim** (IP residencial) | sim | sim (cron) | grátis | Melhor se você tem máquina ligada |
| **Oracle Cloud Always Free** | não (datacenter) | sim | sim (cron) | grátis | Boa VM, não resolve bloqueio |
| **Modal** | não | sim (nativo) | sim | crédito mensal grátis | Ótimo para Python, mesmo IP ruim |
| **Google Cloud Run Jobs** | não | sim | sim (Scheduler) | free tier | Idem |
| **Render Cron Job** | não | sim | sim | a partir de US$ 1/mês | Idem, e pago |
| **n8n Cloud** | não | não (nós/JS) | sim | plano pago | Só se você já usa n8n |

### Apify — a recomendação

É a única da lista feita exatamente para isto: executar raspagem agendada,
com proxies gerenciados, guardando o resultado num dataset que se lê por API,
e disparando webhook quando termina.

O encaixe com este projeto:

- O coletor vira um **Actor** (um container com `scripts/coletar.py` dentro);
  o `Dockerfile` do repositório já serve de base.
- **Schedules** cuidam do agendamento.
- Ao terminar, um **webhook** chama o `repository_dispatch` do passo 2.
- O workflow lê o resultado em
  `https://api.apify.com/v2/datasets/{id}/items?format=json`.

Os US$ 5/mês de crédito do plano grátis cobrem folgadamente uma coleta semanal
de alguns milhares de candidatos. O que consome crédito de verdade é proxy
residencial — use só nas fontes que realmente exigirem.

### Runner self-hosted — a alternativa grátis

Se você tem uma máquina que fica ligada (um PC velho, um Raspberry Pi, um
mini-PC), registre-a como runner do GitHub Actions. O workflow de coleta roda
nela, com IP residencial, e o de publicação continua no runner do GitHub.

```yaml
jobs:
  coletar:
    runs-on: self-hosted     # sua máquina, seu IP
  publicar:
    needs: coletar
    runs-on: ubuntu-latest   # runner do GitHub
```

Custo zero, IP residencial de verdade, integração nativa — sem
`repository_dispatch`, sem token extra, sem serviço terceiro. Em troca: a
máquina precisa estar ligada na hora, e um runner self-hosted em repositório
**público** exige cuidado, porque qualquer pull request poderia executar código
nela. Use `pull_request` desabilitado para esse job, ou mantenha o runner num
repositório privado que publica no público.

### As demais

Modal, Cloud Run Jobs, Render e Oracle rodam Python e agendam bem. Nenhuma
melhora o IP em relação ao GitHub, então só valem a pena se o problema não for
bloqueio — por exemplo, se você precisar de mais tempo de execução do que os
limites do Actions, ou quiser manter a coleta separada por outro motivo.

Se for esse o caso, prefira a mais simples: mantenha a coleta no próprio
GitHub Actions e economize um serviço.

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
