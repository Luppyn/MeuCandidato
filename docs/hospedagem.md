# Hospedagem

Duas perguntas separadas, que costumam ser tratadas como uma só:

1. Onde fica **o site** (servidor + banco SQLite + páginas).
2. Onde roda **a coleta** das fontes que não têm API.

O site é pequeno e sem estado: um processo Python e um arquivo SQLite. A coleta é
que puxa infraestrutura, porque precisa rodar sozinha em horário marcado e sair
para a internet.

## Onde fica o site

O servidor é `python3 servidor.py`, sem dependência nenhuma. Serve em qualquer
lugar que rode Python e aceite um processo de longa duração:

| Opção | Serve o site | Roda n8n junto | Observação |
| --- | --- | --- | --- |
| VPS (Hetzner, DigitalOcean, Contabo, Oracle Free) | sim | **sim** | Uma máquina, dois containers. O caminho mais direto se você quer n8n. |
| Fly.io / Render / Railway | sim | sim, como segundo serviço | Precisa de volume persistente para o SQLite. |
| Hospedagem compartilhada com Python | sim | não | Costuma barrar processos em segundo plano. |
| GitHub Pages, Netlify, Vercel (estático) | **não** | não | Só serve arquivo; não roda o servidor nem o SQLite. |

O SQLite precisa de disco que sobreviva ao restart. Em plataformas que reciclam o
sistema de arquivos, monte um volume — ou reconstrua a base no boot rodando os
importadores, que é rápido e tem a vantagem de deixar o registro de importação
sempre fresco.

O site não tem login, não escreve nada e não guarda dado de usuário. Publicá-lo
aberto na internet é seguro do ponto de vista de dados: tudo que ele mostra já é
público na origem.

## Onde roda a coleta

Sim, **dá para hospedar o n8n na mesma máquina do site** — desde que a
hospedagem seja uma VPS ou algo que rode containers. Não dá em hospedagem
estática, e em plano compartilhado costuma esbarrar em limite de memória: o n8n
sozinho quer uns 512 MB a 1 GB, bem mais do que o site inteiro.

Antes de decidir, vale comparar com a alternativa sem servidor nenhum.

### Opção A — GitHub Actions (recomendada)

Está pronta em `.github/workflows/coleta-externa.yml`. O GitHub roda os coletores
no horário marcado e comita o resultado em `dados/externo/`.

- **Custo:** zero em repositório público.
- **Infraestrutura:** nenhuma. Nada para instalar, atualizar ou vigiar.
- **Transparência:** esta é a vantagem que importa aqui. O histórico do git vira o
  registro público da coleta — dá para ver, commit a commit, o que cada fonte
  devolveu, quando, e quando um valor mudou. Num projeto cujo ponto é provar que
  ninguém mexeu na informação, isso não é detalhe.
- **Limitação:** o IP dos runners do GitHub é de datacenter, e algumas fontes
  bloqueiam. Para essas, configure os segredos `COLETOR_PROXY` ou
  `COLETOR_UNLOCKER_*` no repositório (ver abaixo).

### Opção B — n8n na mesma máquina

Faz sentido se você já usa n8n para outras coisas, quer montar os fluxos
visualmente, ou precisa de algo que o cron não dá — retentativa por item,
fila, notificação de falha.

```yaml
# docker-compose.yml
services:
  meucandidato:
    build: .
    command: python3 servidor.py --host 0.0.0.0 --porta 8000
    volumes:
      - ./dados:/app/dados
    ports:
      - "8000:8000"

  n8n:
    image: docker.n8n.io/n8nio/n8n
    environment:
      - N8N_HOST=n8n.seudominio.com.br
      - WEBHOOK_URL=https://n8n.seudominio.com.br/
      - GENERIC_TIMEZONE=America/Sao_Paulo
      # opcional, só se alguma fonte exigir desbloqueio:
      # - COLETOR_PROXY=${COLETOR_PROXY}
    volumes:
      - n8n_dados:/home/node/.n8n
      - ./dados/externo:/dados/externo   # o fluxo grava aqui
    ports:
      - "5678:5678"

volumes:
  n8n_dados:
```

O fluxo em `automacao/n8n-coleta-externa.json` já está montado nesse desenho: ele
lê a lista de candidatos da API do próprio site, consulta a fonte, mapeia para o
formato do importador e grava o JSON na pasta compartilhada. Depois, um
`python3 scripts/importar_externos.py dados/externo/` carrega na base.

Requisitos reais: cerca de 1 GB de RAM a mais e um subdomínio com HTTPS para o
painel do n8n. Uma VPS de 2 GB dá conta dos dois com folga.

### Opção C — cron na própria máquina

O caminho mais enxuto se você não quer painel nenhum:

```cron
0 4 * * 1 cd /opt/meucandidato && python3 scripts/coletar.py --fonte congresso --fonte noticias --cargo 6 --uf SP && python3 scripts/importar_externos.py dados/externo/
```

Faz o mesmo que as outras duas opções, sem nada para manter. O que se perde é
visibilidade: sem o histórico do git da opção A, e sem o painel de execuções da
opção B, uma coleta que falha em silêncio passa despercebida.

## Quando a fonte bloqueia a requisição

Algumas fontes recusam requisições de IP de datacenter ou exigem captcha. Os
coletores têm um ponto de extensão para isso, ativado por variáveis de ambiente —
sem nenhuma credencial no repositório:

```bash
# proxy HTTP(S) comum
export COLETOR_PROXY="http://usuario:senha@host:porta"

# ou um serviço de desbloqueio com API
export COLETOR_UNLOCKER_URL="https://api.brightdata.com/request"
export COLETOR_UNLOCKER_TOKEN="..."
export COLETOR_UNLOCKER_ZONA="..."
```

O formato do payload segue a Web Unlocker API da Bright Data
(`{"zone": ..., "url": ..., "format": "raw"}`), que outros serviços do mesmo tipo
também adotam. Sem essas variáveis, nada muda: o coletor faz a requisição direta.

Dois avisos que valem mais que a configuração:

- **Nem todo bloqueio é técnico.** Captcha no CNIA e no BNMP existe porque a
  consulta é feita para ser individual. Contornar isso em massa é outra
  discussão, e não é a que este projeto resolve — por isso essas fontes têm
  coletor de lista de trabalho, e não raspador.
- **Ritmo.** O padrão é 1,5 s entre requisições ao mesmo domínio
  (`COLETOR_INTERVALO`). Vale a pena aumentar, não diminuir. As fontes de
  transparência aqui são, em boa parte, projetos pequenos de sociedade civil.

## Publicando

O site serve em HTTP puro. Para expor na internet, ponha um proxy reverso na
frente resolvendo o HTTPS:

```nginx
server {
    server_name meucandidato.seudominio.com.br;
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
```

`certbot --nginx` resolve o certificado. Não há nada além disso: sem variável de
ambiente obrigatória, sem migração, sem serviço externo.
