# CLAUDE.md — Bot RPA (arquétipo integracao-api-figueiredo) — Grupo Figueiredo

> Regras para agentes de IA trabalhando neste bot RPA. Arquétipo **integracao-api-figueiredo**:
> bot só de dados, sem portal externo nem desktop — lê/escreve exclusivamente via
> API V2 (`/v2/query/`). Para acesso direto a outro banco via SQLAlchemy, veja o
> arquétipo irmão **integracao-sqlalchemy**; para chamar API de terceiros, veja
> **integracao-requests**.
> Comunicação com o usuário sempre em **PT-BR**.

## ⛔ Regra Zero — Proteção de dados e efeitos colaterais

**Nunca execute, sem aprovação explícita do usuário**, nada que crie, altere ou apague dado real:
`INSERT`/`UPDATE`/`DELETE`/`UPSERT` em SQL ou API, requisições `POST`/`PUT`/`PATCH`/`DELETE`,
upload/overwrite/delete de arquivos (`utils.Arquivos`), interação com aplicações desktop, ou
rodar `main.py`/`controlador_principal.main()` (dispara chamadas reais). Escrever/editar código Python
é sempre permitido — **executar** é que precisa de aprovação.

Testes **nunca** podem fazer escrita real: todo `POST`/`PUT`/`DELETE`/SQL de escrita e toda
interação com sistemas externos devem ser mockados nos testes.

## 📚 Documentação e permissões — OBRIGATÓRIO

**O `README.md` é a documentação oficial deste projeto e precisa estar sempre atualizado.**
Qualquer modificação — fluxo, camada, serviço, repositório, dependência, variável de
ambiente, comando, tabela ou endpoint — só está concluída depois de o `README.md` refletir
o novo estado, na **mesma** alteração. Nunca deixe a doc para depois nem crie documentação
paralela (`PLANO_*.md`, `NOTAS.md`, arquivos avulsos): o que precisa ser sabido entra no
`README.md`.

**Mantenha o `permissoes.csv` (raiz do projeto) com todas as tabelas que o bot acessa**, no
formato exato abaixo — uma linha por par tabela × permissão:

```csv
banco,schema,tabela,permissao
autom_data,public,execucoes,read
autom_data,public,execucoes,write
```

| coluna | conteúdo |
|---|---|
| `banco` | connection/base acessada (ex.: `autom_data`, `sgt20`, `protheus`) |
| `schema` | schema dentro do banco (`public`, `dbo`, ...); `-` quando não se aplica |
| `tabela` | nome da tabela ou view |
| `permissao` | `read`, `write`, `update`, `delete` — uma linha por permissão |

Toda query criada, alterada ou removida (via API V2 ou conexão direta) exige atualizar o
`permissoes.csv` na mesma alteração. Esse arquivo é o insumo do time de infraestrutura para
liberar acesso: tabela fora do CSV = bot sem permissão no ambiente de destino.

## 🌿 Fluxo de branches — OBRIGATÓRIO

O repositório nasce com `main` (produção), `dev` (integração) e a `release/*` **efêmera**
(criada sob demanda a cada ciclo de homologação, sem PR — é só um `checkout` a partir da
`dev`) — e com os Environments `release` e `prd` no GitHub. **Nunca commite direto em `dev`,
`release/*` ou `main`, e a `dev` nunca abre PR direto para a `main`** — a única ponte
é a `release/*` (ou, em emergência, a `fix/hotfix-*`).

Toda modificação sai de uma branch nova criada **a partir da `dev`**, nomeada com o mesmo
tipo do Conventional Commit (`feat/`, `fix/`, `refactor/`, `perf/`, `docs/`, `test/`,
`chore/`, `build/`, `ci/`), e volta para a `dev` por **Pull Request**:

```bash
git checkout dev && git pull
git checkout -b feat/descricao-curta
# ... commits ...
git push -u origin feat/descricao-curta   # e abra o PR para `dev`
```

A promoção é sempre para frente, sem pular etapa:

```
feat/* · fix/* · chore/* · docs/* …  ──PR──►  dev  ──(checkout)──►  release/*  ──PR──►  main
```

Uma `release/*` só é aceita se nascer da `dev` — uma automação apaga na hora qualquer
`release/*` criada de outro lugar. Antes do merge de `release/*`/`fix/hotfix-*` para a
`main`, outra automação garante que a versão em `pyproject.toml` avançou pelo tipo dos
commits — não é preciso lembrar de fazer isso na mão.

Única exceção: hotfix de produção sai de `fix/hotfix-*` a partir da `main`, com back-merge
automático em `dev` logo após o merge (a `release/*` não recebe back-merge — ela é efêmera e
some antes do próximo ciclo).

## Arquitetura

```
main.py                      # Entry point: init do logger, execução do fluxo
configuracoes.py             # Configuração centralizada (env vars + credenciais via API V2)
aplicacao/
├── controladores/            # Um controlador por fluxo (pode haver mais de um)
│   └── controlador_principal.py  # Orquestrador: único ponto que coordena serviços e repositórios
├── excecoes/                 # ExcecaoNegocio (erros de regra de negócio, recuperáveis)
└── servicos/                 # Lógica de negócio
repositorios/                 # Acesso a dados via API V2 (/v2/query/) — um arquivo por connection
├── repositorio_base.py        # Base de acesso via API V2 (/v2/query/, JWT transparente)
└── repositorio_autom_data.py  # connection: autom_data
utils/                        # Infraestrutura sobre a API V2 — camada mais baixa
├── cliente_api_v2.py          # HTTP + JWT (login/refresh transparentes) — usado por todos
├── logger.py                  # Logger: execução e registros (/v2/logs/)
├── credenciais.py             # Credenciais de sistemas externos (/v2/credenciais/)
└── arquivos.py                # Upload/download/listagem/remoção (/v2/arquivos/)
```

Direção de dependência (estrita, sem ciclos): `main.py → controladores → servicos → repositorios → utils`.

- Nenhuma chamada HTTP fora de `repositorios/`.
- `utils/` é a camada mais baixa: `aplicacao/` e `repositorios/` dependem dela, nunca o
  contrário. Não importe `aplicacao`/`repositorios` de dentro de `utils/`.
- `configuracoes.py` é a única fonte de configuração — nunca hardcode URL/credenciais.
- Novas exceções de negócio herdam de `ExcecaoNegocio`; falhas de infraestrutura seguem como `Exception`.
- Não crie novas camadas (DTOs, mappers, interfaces) sem aprovação explícita.

## Convenções de código

- **Idioma:** nomes em **português** para arquivos/classes/funções/variáveis. Mantenha em inglês
  apenas o que é **contrato externo** (chaves de payload da API, kwargs de bibliotecas de terceiros).
- **ruff:** `line-length = 120`, `select = ["E","F","W","I","N","UP","B","SIM"]`,
  `ignore = ["E501","N818"]`, `quote-style = "double"`. Rode `uv run ruff check .` e
  `uv run ruff format .` após toda modificação, antes de finalizar.
- **Tipagem:** type hints obrigatórios em toda assinatura de função (`str | None`, `list[dict]`, etc.).
- **Funções:** no máximo ~50 linhas, no máximo 3 níveis de aninhamento. Sem números mágicos —
  use `Configuracoes` ou constantes nomeadas.
- Desktop: espere elementos de UI ficarem prontos explicitamente (nunca `time.sleep` como espera principal).
- Planilhas/arquivos: valide existência/formato antes de processar; nunca sobrescreva o arquivo de origem.

## Logging

- Logger: `utils.Logger` (`utils/logger.py`), sobre `POST /v2/logs/`. Ciclo:
  `logger.iniciar_execucao()` → `logger.atualizar_execucao(status=...)`.
- **Status de execução** (constantes em `utils`, nunca o número solto): `STATUS_SUCESSO` (4) ·
  `STATUS_ERRO_SISTEMA` (3, exceção não tratada) · `STATUS_RESSALVA` (2, regra de negócio) ·
  `STATUS_CANCELADO` (5).
- **Chamadas:** `logger.registrar(tipo="info|warning|error", tarefa="...", mensagem="...", traceback=...)`.
  **Nunca use `print()`**. Sempre inclua `traceback=traceback.format_exc()` em logs de erro.
- `tipo="error"`/`"critical"` **encerra a execução sozinho** do lado da API (status 3, `end_date` e
  `final_id_error`) — não é preciso chamar `atualizar_execucao` depois de logar um erro fatal.
- Falha ao registrar log **nunca derruba o bot**: vira aviso no `stderr`. `registrar` é chamado de
  dentro do `except`, e estourar ali esconderia o erro real por trás de um erro de rede.
- **Nunca logue dado sensível**: senha, token, API key, CPF completo (mascare `cpf[:3]***`).

### Logs de progresso (obrigatório)

O log precisa deixar claro **onde o bot está** a cada momento — quem acompanha a execução tem
que responder "em que etapa/item ele está?" só olhando o log:

- Marque início e fim de cada etapa macro: `"Iniciando processamento..."` → `"Processamento concluído"`.
- Use `tarefa` como a "âncora" da etapa atual (`"processar_item"`, `"finalizar"`).
- Inclua progresso e identificador do item ao iterar lotes: `f"Processando {i}/{total} (DT={documento})"`.
- Logue quantidades ao obter dados: `f"{len(itens)} itens encontrados"`.
- Logue sucesso/skip/erro por item, com o motivo (`"DT=... ignorada: sem data"`).
- Erro não fatal (1 item) → `tipo="error"` com `traceback`, e **segue** para o próximo — não
  derrube o lote inteiro por causa de um item.

## Acesso a dados pela API V2 (leitura × escrita)

Toda interação com banco passa pela **API V2** (`POST /v2/query/`) — **nunca** conexão direta.
A autenticação JWT é transparente (login/refresh automáticos, centralizados em
`utils/cliente_api_v2.py`); os repositórios só montam o SQL.

- **Leitura (SELECT):** `_executar_consulta(sql)` → `POST /v2/query/` → devolve as linhas como
  `list[dict]` (converte `columns`+`rows`).
- **Escrita (INSERT/UPDATE/DELETE):** `_executar_escrita(sql)` → mesmo `/v2/query/` → devolve o
  `rowcount`. **Um comando por chamada** (a API rejeita múltiplos comandos).
- **SQL seguro:** sempre escape com `_escapar()` e force `int()` em inteiros antes de interpolar —
  nunca concatene entrada crua na query. `_escapar()` só vale para **literais de texto**: não use
  para nome de tabela/coluna nem para o corpo de um `LIKE` (escape `%`/`_` à parte).
- **Dialeto:** `_escapar()` depende do banco por trás da connection. O padrão é `postgres` (a barra
  invertida é literal, basta duplicar a aspa). Numa connection **MySQL**, declare
  `dialeto = DIALETO_MYSQL` no repositório — lá a barra invertida também escapa e, sem duplicá-la,
  um valor terminado em `\` escapa da string (injeção). Dialeto não declarado → erro, nunca um
  escape silenciosamente errado.
- `db` = a `connection_name` do repositório (ex.: `autom_data`). Cada connection tem seu próprio
  arquivo em `repositorios/`, herdando de `RepositorioBase`. Não misture connections no mesmo arquivo.
- Erros da API → `ErroApiV2`: `400` (SQL inválido/múltiplos comandos), `401` (credenciais recusadas
  mesmo após renovar o token), `403` (sem permissão), `404` (banco inexistente).
- **Resultado truncado:** se a API sinalizar `truncated`, `_executar_consulta()` levanta `ErroApiV2`
  em vez de devolver um lote parcial. Refine o `WHERE` ou pagine — nunca processe meio lote calado.
- **Fonte de verdade sobre a API e os bancos: SEMPRE o MCP `api-figueiredo`** (configurado em
  `.mcp.json`; servidor HTTP protegido por HTTP Basic). Antes de escrever qualquer query, endpoint ou
  payload, **consulte o MCP** — nunca deduza nome de tabela/coluna/rota nem confie na memória:
  - Catálogo de endpoints da API: `list_endpoints`, `search_endpoints`, `get_endpoint_detail`.
  - Estrutura/dicionário dos bancos: `list_databases`, `describe_table`, `list_data_dictionary`,
    `search_data_dictionary`.
- **Schema/docs (fallback se o MCP estiver fora):** o schema OpenAPI do v2 é `GET /v2/schema`
  (`?format=yaml` ou `?format=json`) — **exige o JWT** (`Authorization: Bearer`), não abre no
  navegador anônimo. Para navegar com login já injetado use `/v2/docs` (referência Scalar) e o
  dicionário de dados em `/v2/docs/bancos` (HTML) ou `GET /v2/schema/bancos` (JSON). O v1
  `http://api.grupofigueiredo.com.br/api/schema` NÃO descreve as rotas /v2.
- Credenciais: `API_BASE_URL`/`API_USERNAME`/`API_PASSWORD` no `.env` (atribuídas no registro do
  SGT20). Segredos de conexões diretas/terceiros seguem via `configuracoes.obter_credencial(...)`.
  Nunca logue o dict retornado (contém senha/API key).

## Camada `utils/` — logs, credenciais e arquivos pela API V2

Este bot **não usa adaptador externo**. As três coisas que antes vinham de pacotes privados
são rotas da API V2, consumidas por classes locais. Nunca reimplemente nenhuma delas com
`requests` direto: o `ClienteApiV2` já resolve login, refresh de JWT e retry no `401`.

| Precisa de… | Use | Não use |
|---|---|---|
| registrar log/execução | `utils.Logger` (já injetado como `logger`) | `print()`, `logging` |
| senha/token de sistema externo | `configuracoes.obter_credencial("<sistema>")` | `os.getenv`, valor no `.env` |
| subir/baixar arquivo | `utils.Arquivos(configuracoes)` | `open()` + `requests.post` |
| qualquer outra rota da API V2 | `ClienteApiV2.instancia(configuracoes).requisitar(...)` | `requests` direto |

```python
from utils import Arquivos

# Credencial de sistema externo — resolvida pela API V2, nunca do .env.
credenciais = configuracoes.obter_credencial("sistema_parceiro")

# Arquivos: o armazenamento padrão vem de `Configuracoes.ARMAZENAMENTO_PADRAO`.
arquivos = Arquivos(configuracoes)
arquivos.enviar(caminho_local="relatorio.pdf", caminho_remoto=f"RPA/{configuracoes.ID_BOT}/relatorio.pdf")
arquivos.baixar("RPA/190/entrada.csv", "entrada.csv")
```

- `utils/` é a **camada mais baixa**: não importe `aplicacao/` nem `repositorios/` de dentro
  dela. Os cinco módulos são idênticos em todos os arquétipos — se precisar corrigir algo
  neles, o ajuste vale para todos (o SDK tem guarda de igualdade).
- `Credenciais.obter` **levanta** `CredencialNaoEncontrada` no `404` em vez de devolver um
  dicionário vazio: um dict vazio faria o bot tentar autenticar sem senha e falhar num ponto
  distante da causa real.
- `Arquivos.remover` é escrita destrutiva sem lixeira do outro lado — vale a Regra Zero.
- Toda credencial devolvida é segredo: **nunca** logue o dicionário inteiro.

## Tratamento de erros

- `ExcecaoNegocio` = erro de negócio recuperável → `logger.atualizar_execucao(status=STATUS_RESSALVA)`, bot não crasha.
- `Exception` genérica = erro de infraestrutura → propaga, `main.py` loga `STATUS_ERRO_SISTEMA` e crasha.
- Nunca engula exceção silenciosamente (`except Exception: pass`). Preserve o traceback (`raise ... from e`).

## Testes

- **Não crie testes proativamente** — só quando o usuário pedir explicitamente.
- O CI (`_reusable-ci.yml`) já roda automaticamente a cada Pull Request/push, em todas as
  etapas (`feat`→`dev`, `dev`→`release/*`, `release/*`/`fix/hotfix-*`→`main`): `isort
  --check-only`, SAST Python (`bandit`), segredo exposto (`gitleaks`), CVE de dependência
  (`pip-audit`) e Trivy em modo filesystem. Nenhum desses checks precisa ser criado por você
  — só não quebre o que já roda. Este projeto não usa `pytest`.
- Quando pedidos: `pytest`, mocks para toda dependência externa (API, filesystem, `utils.Arquivos`,
  UI desktop). Nunca chamada HTTP real, nunca aplicação desktop real, nunca escrita real.

## Dependências

- Gerenciador: **`uv`** (nunca `pip`/`poetry`). Adicionar dependência: `uv add <pacote>`.
- **Sem adaptadores internos.** Logs, credenciais e arquivos passaram a ser rotas da API V2,
  consumidas por `utils/` (`Logger`, `Credenciais`, `Arquivos`) — o bot não depende mais de
  `logger_adapter`/`secrets_adapter`/`manage_files_adapter`, nem de repositório privado nenhum.
  A única credencial que ele precisa é a da própria API V2, atribuída no registro do SGT20.
- Python fixado em **3.12** (`.python-version`).

## Versionamento e CI/CD

- A versão em `pyproject.toml` segue o significado clássico de semver
  (`major.minor.patch`) e **nunca é editada manualmente nem a cada commit local** — o hook
  de pre-commit (`.githooks/pre-commit`) só faz lint. Quem calcula e aplica a versão é o
  script `.github/scripts/versionar.sh`, chamado a cada push em `release/**` (dentro do job
  `versionar` de `release.yml`, antes do build) e em `fix/hotfix-**`
  (`automacao-versiona-fix-hotfix.yml`), e também quando uma label muda num PR aberto de
  `release/*`/`fix/hotfix-*` para a `main` (`automacao-versiona-por-label.yml`).
- **Como o script decide o nível do bump:**
  1. Se o PR desta branch para a `main` já existir e tiver uma label `version:major`,
     `version:minor` ou `version:patch`, usa essa sobrescrita direto.
  2. Sem label: varre as mensagens de commit desde a última tag de produção (`vX.Y.Z`) e
     pega o maior nível presente — `!` depois do tipo ou `BREAKING CHANGE` no corpo →
     **major**; `feat:` (sem quebra) → **minor**; qualquer outro tipo (`fix`, `chore`,
     `refactor`, `docs`, ...) → **patch**.
  3. A versão base do incremento é sempre a última tag de produção — nunca o valor atual do
     `pyproject.toml` na branch, que pode estar desatualizado. Um bump de major zera minor e
     patch; um bump de minor zera patch — comportamento clássico de semver, sem limite
     artificial de dígito.
  4. Usa `secrets.GH_TOKEN` (PAT do Admin) para o push e para o `gh` CLI consultar a label
     do PR.
- **Tag de homologação em `release/*` (`vX.Y.Z-hml`):** a cada push numa `release/*`,
  `versionar.sh` cria (ou move) uma tag `vX.Y.Z-hml` apontando pro commit mais novo -
  marca o build de homologação, sem sufixo nenhum no `pyproject.toml` (que grava direto a
  versão final `X.Y.Z`: é número de pacote Python, PEP 440, não aceita sufixo tipo
  `-hml` - `uv`/`hatchling` recusam o arquivo). Se a mesma `release/*` receber mais um push
  (ex.: correção depois de feedback de homologação), a versão já estabelecida é reaproveitada
  (lida da própria tag `-hml` alcançável a partir do commit atual) em vez de recalculada - só
  a tag se move. A tag final `vX.Y.Z` (sem sufixo) nasce sem nenhuma automação nova: é a
  mesma que `_reusable-build.yml` já cria hoje, depois do build que só acontece no merge para
  a `main` - que só é possível depois de aprovação de code owner. `fix/hotfix-*` nunca ganha
  tag `-hml` (vai direto pra versão final, é urgência).
- O push do bump usa um PAT de verdade (`GH_TOKEN`, não o `GITHUB_TOKEN` padrão), o que
  dispara o próprio `release.yml` de novo — `versionar.sh` detecta se o commit mais recente
  já é um bump seu e não faz nada, pra não entrar em loop de incremento.
- Uma `release/*` só é aceita se nascer da `dev` — `automacao-valida-origem-release.yml`
  apaga na hora qualquer `release/*` criada de outro lugar (checa se os commits exclusivos
  desde a `dev` são só do `versionamento-bot`).
- **Um workflow por branch principal**, em `.github/workflows/`: `dev.yml`, `release.yml`
  e `prd.yml`. **A validação (`ruff check` + `ruff format --check` + isort + bandit +
  gitleaks + pip-audit + Trivy fs) roda em Pull Request e em push, nas três branches** —
  inclusive em `release/*`. **O build da imagem e o deploy no Kestra só acontecem no merge
  para a `main`** (`github.event_name == 'push'` em `prd.yml`), seja vindo de `release/*` ou
  de `fix/hotfix-*`. `release.yml` **não** builda nem implanta — só valida e versiona
  (se preciso). A `dev` também não constrói imagem — é linha de integração.
- A implementação é única e vive nos reutilizáveis `_reusable-ci.yml` (validação, chamado
  por `dev.yml`/`release.yml`/`prd.yml`), `_reusable-build.yml` (build + Trivy de imagem +
  push) e `_reusable-deploy.yml` (deploy) — esses dois últimos só são chamados por
  `prd.yml`. Mexeu na pipeline? Mexa no reutilizável, não copie o passo para os arquivos de
  branch.
- No build/push de imagem, o CI **lê** a versão do `pyproject.toml` para taguear a imagem —
  não a incrementa nesse passo. A imagem de produção sai como `:latest` e `:X.Y.Z`.
- Antes do push da imagem, o CI roda uma varredura de vulnerabilidades (Trivy) — falhas
  `CRITICAL`/`HIGH` com correção disponível bloqueiam o pipeline antes de chegar à registry.
- **A tag `v<versão>` e a release do GitHub nascem em `_reusable-build.yml`, depois do push
  da imagem** — nunca antes: uma versão cuja imagem falhou no build, no Trivy ou no push não
  pode ser marcada como publicada. Essa tag não é decorativa: é dela que `versionar.sh` parte
  para calcular o próximo incremento e é a partir dela que ele varre os commits. Sem esse
  passo, todo ciclo recalcularia a versão sobre o histórico inteiro, a partir de uma base
  errada.
- **Deploy no Kestra é scaffold, não automação real:** `_reusable-deploy.yml` roda depois do
  build (só em `prd.yml`), usa o Environment `prd` já provisionado pelo `create`, mas só
  confirma que `kestra/bot.yml` existe — a implantação de verdade ainda é manual, na UI do
  Kestra (nenhum bot do Grupo Figueiredo automatiza esse passo hoje). O ponto de extensão
  está marcado com `TODO(tech lead)` dentro do workflow.

## Commits

Conventional Commits, descrição em PT-BR, imperativo, máx. 72 caracteres, sem ponto final:
`feat|fix|refactor|perf|docs|test|chore|build|ci(escopo): descrição`.

## Checklist antes de finalizar

- [ ] Trabalho feito em branch própria a partir da `dev` (nunca commit direto)
- [ ] `README.md` atualizado com o que mudou nesta alteração
- [ ] `permissoes.csv` atualizado com toda tabela/permissão acessada
- [ ] Regra Zero respeitada — nenhuma ação de escrita/execução sem aprovação
- [ ] Direção de dependência respeitada, sem imports circulares
- [ ] Idempotência preservada (seguro rodar de novo)
- [ ] Só `logger.registrar()` — nenhum `print()`
- [ ] Nenhum segredo/CPF/token exposto em log
- [ ] Segredo de sistema externo vindo de `configuracoes.obter_credencial()` — nunca do `.env`
- [ ] Type hints em toda assinatura nova/alterada
- [ ] Timeouts explícitos em toda chamada HTTP
- [ ] Entradas de SQL escapadas
- [ ] `uv run ruff check .` e `uv run ruff format .` executados, sem violação
- [ ] `configuracoes.py` usado para toda configuração (nada hardcoded)
