from typing import Any

from utils.cliente_api_v2 import ClienteApiV2, ErroApiV2

# Dialetos com regra de escape conhecida (ver `_escapar`).
DIALETO_POSTGRES = "postgres"
DIALETO_MYSQL = "mysql"


class RepositorioBase:
    """Executor de SQL (leitura e escrita) via API V2 (`POST /v2/query/`).

    As classes filhas definem `self.configuracoes` e `self.connection_name`
    (o `db` da API V2, ex.: "autom_data"). A autenticação JWT é transparente e
    centralizada no `ClienteApiV2` — os repositórios só montam o SQL.

    `dialeto` decide a regra de escape de `_escapar()` e **precisa** bater com o
    banco real por trás da connection — o escape correto em um dialeto é uma
    brecha de injeção no outro.
    """

    configuracoes: Any
    connection_name: str
    dialeto: str = DIALETO_POSTGRES

    @property
    def _cliente(self) -> ClienteApiV2:
        return ClienteApiV2.instancia(self.configuracoes)

    def _executar_consulta(self, sql: str) -> list[dict[str, Any]]:
        """Executa um SELECT via `/v2/query/` e devolve as linhas como dicts."""
        resultado = self._cliente.executar_query(self.connection_name, sql)
        if resultado.get("truncated"):
            raise ErroApiV2(
                f"A API V2 truncou o resultado da consulta em '{self.connection_name}' "
                f"({len(resultado.get('rows') or [])} linhas devolvidas). Processar um lote "
                "parcial silenciosamente causaria perda de dados — refine o WHERE ou pagine a consulta."
            )
        return self._linhas_como_dicts(resultado)

    def _executar_escrita(self, sql: str) -> int:
        """Executa um INSERT/UPDATE/DELETE (comando único) via `/v2/query/`.

        Retorna o `rowcount` informado pela API.
        """
        resultado = self._cliente.executar_query(self.connection_name, sql)
        return int(resultado.get("rowcount") or 0)

    @staticmethod
    def _linhas_como_dicts(resultado: dict[str, Any]) -> list[dict[str, Any]]:
        """Valida as `rows` da API V2 - já vêm como `list[dict]` (chave = nome da coluna).

        DIVERGE DO TEMPLATE DO SDK (`sdk-expfig`) DE PROPÓSITO: a versão gerada faz
        `dict(zip(columns, linha))`, o que pressupõe `rows` como lista de listas.
        A API V2 real devolve `rows` como lista de **dicts** — `zip` nesse caso itera
        as chaves do dict (que batem com `columns`, na mesma ordem), produzindo
        `{coluna: coluna}` em vez de `{coluna: valor}`, corrompendo todo `SELECT`
        silenciosamente (confirmado direto contra a API V2 real). Reporte isso pra
        quem mantém o `sdk-expfig` — este arquivo é guardado/idêntico nos 7
        arquétipos, então o bug afeta todo bot gerado por ele.

        Confere que cada linha tem exatamente as chaves declaradas em `columns`;
        se divergir, falha alto em vez de processar dado incompleto silenciosamente.
        """
        colunas = set(resultado.get("columns") or [])
        linhas = resultado.get("rows") or []
        for linha in linhas:
            if set(linha.keys()) != colunas:
                raise ErroApiV2(
                    f"Linha da API V2 com colunas divergentes do esperado: "
                    f"esperado {sorted(colunas)}, recebido {sorted(linha.keys())}."
                )
        return linhas

    @classmethod
    def _escapar(cls, valor: str) -> str:
        """Escapa um literal de texto para interpolar em SQL, conforme o `dialeto`.

        A API V2 não aceita parâmetros vinculados (bind), então o escape é a
        única defesa — e ele **depende do dialeto**:

        - **Postgres** (`standard_conforming_strings=on`, o padrão): a barra
          invertida é caractere literal; basta duplicar a aspa simples.
        - **MySQL**: a barra invertida também escapa. Sem duplicá-la, um valor
          terminado em `\\` engole a aspa de fechamento e escapa da string —
          injeção. Por isso a barra vem primeiro, depois a aspa.

        Só cobre **literais de texto**. Nunca use para nome de tabela/coluna nem
        para montar o corpo de um `LIKE` sem escapar `%`/`_`; inteiros vão por
        `int()`, não por aqui.
        """
        if "\x00" in valor:
            raise ValueError("Valor contém byte nulo, inválido em literais SQL.")
        if cls.dialeto == DIALETO_POSTGRES:
            return valor.replace("'", "''")
        if cls.dialeto == DIALETO_MYSQL:
            return valor.replace("\\", "\\\\").replace("'", "''")
        raise ValueError(
            f"Dialeto {cls.dialeto!r} sem regra de escape conhecida em {cls.__name__}. "
            f"Defina `dialeto` como {DIALETO_POSTGRES!r} ou {DIALETO_MYSQL!r}."
        )
