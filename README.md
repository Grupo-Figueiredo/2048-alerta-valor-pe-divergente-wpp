# 2048 - Alerta de Valor de PE Divergente (WhatsApp)

Bot RPA (arquétipo **integracao-api-figueiredo** — dados via API V2 + alerta via WhatsApp/Z-API)
do Grupo Figueiredo.

Verifica, para cada Pedido de Embarque (PE) da Aperam pendente de validação, se o valor total
do CTE informado pelo embarcador confere com o CTE oficial (`sgt20.gr_cte`, fonte
Protheus/TOTVS). Quando diverge, atualiza a auditoria em `cte_value_audit` e envia um alerta
via WhatsApp (Z-API).

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
    └── servico_notifica_whatsapp.py      # Monta e envia o alerta via Z-API (requests direto)
repositorios/                  # Acesso a dados via API V2 (/v2/query/)
├── repositorio_base.py         # Executor genérico de SELECT/INSERT/UPDATE/DELETE
├── repositorio_autom_data.py    # connection: autom_data (auditoria de CTE)
└── repositorio_sgt20.py         # connection: sgt20 (CTE oficial, gr_cte)
utils/                          # Infraestrutura sobre a API V2 (cliente/JWT, logger,
                                # credenciais, arquivos) — camada mais baixa
```

Veja [CLAUDE.md](./CLAUDE.md) para as regras de arquitetura e convenções deste projeto. A
chamada à Z-API mora em `aplicacao/servicos/` (não em `repositorios/`, reservado à API V2) —
mesmo padrão do arquétipo irmão `integracao-requests` para integrações com terceiros.

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
| `API_BASE_URL`/`API_USERNAME`/`API_PASSWORD` | Credenciais da **API V2** (`/v2/query/`) — dados + logs + credenciais |
| `API_TIMEOUT` | Timeout (segundos) das chamadas à API V2 (padrão 60) |
| `ZAPI_TIMEOUT` | Timeout (segundos) da chamada à Z-API (padrão 30) |
| `ENVIRONMENT` | `development`/`production` |

**Credencial `whatsapp_alerta_pe` na API V2** (`configuracoes.obter_credencial("whatsapp_alerta_pe")`,
lida por `ServicoNotificaWhatsapp`) — precisa ser cadastrada manualmente (`/v2/credenciais/`),
no formato:

```json
{"url": "https://api.z-api.io/instances/<id>/token/<token>/send-text", "client_token": "...", "destino": "<telefone-ou-grupo>"}
```

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

- [ ] Cadastrar a credencial `whatsapp_alerta_pe` na API V2 (ver seção Configuração).
- [ ] Ativar o hook de pre-commit (`git config core.hooksPath .githooks`).
- [ ] Ajustar o cron real em `kestra/bot.yml` (hoje com o placeholder do scaffold).
