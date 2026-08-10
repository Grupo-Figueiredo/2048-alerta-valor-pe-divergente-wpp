# {{Nome do bot}}

Bot RPA (arquétipo **integracao-api-figueiredo** — só dados, via API V2) do Grupo Figueiredo.

## Estrutura

```
main.py                      # Entry point: init do logger, execução do fluxo
configuracoes.py             # Configuração centralizada (env vars + credenciais via API V2)
aplicacao/
├── controladores/            # Um controlador por fluxo (pode haver mais de um)
│   └── controlador_principal.py  # Orquestrador do processo
├── excecoes/                 # Exceções de negócio (ExcecaoNegocio)
└── servicos/                 # Lógica de negócio
repositorios/                 # Acesso a dados via API V2 (/v2/query/)
├── repositorio_base.py
└── repositorio_autom_data.py
```

Veja [CLAUDE.md](./CLAUDE.md) para as regras de arquitetura e convenções deste projeto.

## Configuração

1. O `.env` já é gerado com as credenciais da **API V2** (registro no SGT20) — é a única
   credencial que o bot precisa.

   ```bash
   cp .env.example .env
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

Sem essa ativação, o hook não roda e nada impede um commit que quebra o lint do CI. A versão
não depende dele: quem versiona é o CI, a partir da última tag de produção.

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
docker build --secret id=github_token,env=GITHUB_TOKEN -t <id>-<nome>:latest .
docker run --env-file .env <id>-<nome>:latest
utils/                        # Infraestrutura sobre a API V2 (cliente/JWT, logger,
                              # credenciais, arquivos) — camada mais baixa
```

## Kestra

Este bot roda no Kestra, orquestrador fora deste repositório. O flow de referência está em
[`kestra/bot.yml`](./kestra/bot.yml) — hoje **aplicado manualmente na UI do Kestra** (nenhum
bot do Grupo Figueiredo automatiza esse passo ainda). Build e deploy só acontecem **no merge
para a `main`** (`prd.yml`, depois do build); `release.yml` não builda nem implanta. O job
`deploy` (`_reusable-deploy.yml`) só confirma que o flow existe; a implantação automática via
API do Kestra é um `TODO(tech lead)` dentro desse workflow.
