# 2048 - Alerta de Valor de PE Divergente (WhatsApp)

Bot RPA (arquétipo **integracao-api-figueiredo** — dados e alerta via WhatsApp, ambos pela
API V2) do Grupo Figueiredo.

Verifica, para cada Pedido de Embarque (PE) da Aperam pendente de validação, se o valor total
do CTE informado pelo embarcador confere com o CTE oficial (`sgt20.gr_cte`, fonte
Protheus/TOTVS). Quando diverge, atualiza a auditoria em `cte_value_audit` e envia um alerta
via WhatsApp (`POST /v2/notificacoes/whatsapp/` da própria API V2 — a Z-API mora do outro lado,
resolvida pela API a partir do cofre dela).

## Estrutura

```
main.py                        # Entry point: init do logger, execução do fluxo
configuracoes.py               # Configuração centralizada (env vars + credenciais via API V2)
aplicacao/
├── controladores/
│   └── controlador_principal.py   # Orquestrador: busca os PEs pendentes e processa cada um
├── excecoes/
│   └── excecao_negocio.py         # ExcecaoNegocio — erro de negócio recuperável
└── servicos/
    ├── servico_compara_valores.py        # Compara o CTE do embarcador com o CTE oficial (gr_cte)
    └── servico_notifica_whatsapp.py      # Monta e envia o alerta via POST /v2/notificacoes/whatsapp/
repositorios/                  # Acesso a dados via API V2 (/v2/query/)
├── repositorio_base.py         # Executor genérico de SELECT/INSERT/UPDATE/DELETE
├── repositorio_autom_data.py    # connection: autom_data (auditoria de CTE)
└── repositorio_sgt20.py         # connection: sgt20 (CTE oficial, gr_cte)
utils/                          # Infraestrutura sobre a API V2 (cliente/JWT, logger,
                                # credenciais, arquivos) — camada mais baixa
```

Veja [CLAUDE.md](./CLAUDE.md) para as regras de arquitetura e convenções deste projeto. A
notificação de WhatsApp é hoje uma rota da própria API V2 (`POST /v2/notificacoes/whatsapp/`,
que fala com a Z-API do outro lado) — por isso `ServicoNotificaWhatsapp` chama
`ClienteApiV2.requisitar(...)` diretamente (mesmo padrão de `utils.Logger`/`utils.Arquivos` para
"qualquer outra rota da API V2"), e não `requests` contra um terceiro. Não é uma chamada de
`repositorios/` porque não é uma query em `/v2/query/`.

## Fluxo de negócio

1. Busca em `autom_data.cte_value_audit` os PEs das filiais 15/2, criados no último dia, com
   valor total informado e ainda não validados (`valor_validado is null`).
2. Para cada PE, busca o CTE oficial em `sgt20.gr_cte` pelo `documento_transporte`. Se não
   encontrar (CTE ainda não emitido/sincronizado), **pula o PE sem gravar nada** - ele continua
   com `valor_validado is null` e é tentado de novo na próxima execução.
3. Se encontrar, compara `valor_total_cte_embarcador` com `gr_cte.valor_total_frete`
   (tolerância de R$ 1,00). Se divergente, envia alerta via WhatsApp; sempre grava
   `valor_liquido_cte_figueiredo`/`valor_impostos_cte_figueiredo`/`valor_total_cte_figueiredo`
   e `numero_cte` (vindos de `gr_cte`) na auditoria, e marca `valor_validado = true`.

## Configuração

```bash
cp .env.example .env
```

| Variável | Descrição |
|---|---|
| `API_BASE_URL`/`API_USERNAME`/`API_PASSWORD` | Credenciais da **API V2** (`/v2/query/`, notificação WhatsApp, logs, credenciais) |
| `API_TIMEOUT` | Timeout (segundos) das chamadas à API V2 — inclusive `/v2/notificacoes/whatsapp/` (padrão 60) |
| `ENVIRONMENT` | `development`/`production` |

O usuário da API V2 (`API_USERNAME`) precisa ter a role **`v2_notificacoes_whatsapp`** liberada
pelo time de infraestrutura, além das roles de dados/logs já usadas — sem ela `POST
/v2/notificacoes/whatsapp/` responde `403`.

**Credencial `whatsapp_alerta_pe` na API V2** (`configuracoes.obter_credencial("whatsapp_alerta_pe")`,
lida por `ServicoNotificaWhatsapp`) — precisa ser cadastrada manualmente (`/v2/credenciais/`),
no formato:

```json
{"destino": "<telefone-ou-id-de-grupo, ex.: 120363424569399839-group>"}
```

Só o destinatário mora nessa credencial: a Z-API em si (URL/token do provedor) é resolvida do
lado da API V2, no cofre dela — o bot não guarda mais esse segredo.

## Hook de pre-commit (lint)

Este projeto tem um hook em `.githooks/pre-commit` que roda lint a cada commit local
(`ruff check` + `ruff format --check`) — **bloqueia o commit se falhar**. Ele **não** mexe na
versão: quem calcula e aplica a versão é o CI (`.github/scripts/versionar.sh`), a partir da
última tag de produção e do tipo dos commits.

Ative uma vez, logo após clonar o repositório:

```bash
git config core.hooksPath .githooks
```

Sem essa ativação, o hook não roda e nada impede um commit que quebra o lint do CI.

## Rodando localmente

```bash
uv sync
uv run python main.py
```

## Qualidade e segurança

Mesmos checks que rodam no CI (`_reusable-ci.yml`), pra rodar localmente antes do push:

```bash
uv run ruff check .
uv run ruff format .
uv run isort --check-only --diff .
uvx bandit -r . -x ./.venv -ll
uv export --no-hashes --format requirements-txt -o requirements-audit.txt && uvx pip-audit -r requirements-audit.txt
```

## Docker

```bash
docker build -t 2048-alerta-valor-pe-divergente-wpp:latest .
docker run --env-file .env 2048-alerta-valor-pe-divergente-wpp:latest
```

A imagem fixa `TZ=America/Sao_Paulo` (relevante para o filtro `CURRENT_DATE - INTERVAL '1 day'`
usado na busca dos PEs pendentes e para os timestamps de execução via `datetime.now()`).

## Kestra

Este bot roda no Kestra, orquestrador fora deste repositório. O flow de referência está em
[`kestra/bot.yml`](./kestra/bot.yml) — hoje **aplicado manualmente na UI do Kestra** (nenhum
bot do Grupo Figueiredo automatiza esse passo ainda). Build e deploy só acontecem **no merge
para a `main`** (`prd.yml`, depois do build); `release.yml` não builda nem implanta. O job
`deploy` (`_reusable-deploy.yml`) só confirma que o flow existe; a implantação automática via
API do Kestra é um `TODO(tech lead)` dentro desse workflow. O agendamento em `kestra/bot.yml`
está com o cron placeholder do scaffold (`0 * * * *`) — ajuste para a frequência real antes de
aplicar o flow.

## Acesso a dados (`permissoes.csv`)

Todo acesso a banco passa pela API V2 (`POST /v2/query/`). O inventário de tabelas/permissões
usadas está em [`permissoes.csv`](./permissoes.csv) — é o insumo do time de infraestrutura para
liberar acesso no ambiente de destino.

## Pendências manuais

- [ ] Cadastrar a credencial `whatsapp_alerta_pe` na API V2, só com `destino` (ver seção Configuração).
- [ ] Liberar a role `v2_notificacoes_whatsapp` para o `API_USERNAME` deste bot.
- [ ] Ativar o hook de pre-commit (`git config core.hooksPath .githooks`).
- [ ] Ajustar o cron real em `kestra/bot.yml` (hoje com o placeholder do scaffold).
