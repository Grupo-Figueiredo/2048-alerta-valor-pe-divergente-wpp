"""Registro de execução e de logs do bot via API V2 (`/v2/logs/`).

Substitui o antigo `logger_adapter`: as rotas `/v2/logs/` foram feitas com esse
contrato em mente (a própria API documenta o `id` devolvido pelo início da
execução como "o mesmo `id_exec` que o adaptador guardava").

Duas tabelas por trás, uma linha em cada nível:

- `logs.process` — **a execução** (uma por rodada do bot): criada por
  `iniciar_execucao()` e encerrada por `atualizar_execucao(status=...)`.
- `logs.logs` — **os registros** dentro dela: cada `registrar(...)`.

Status da execução (coluna `status`): `1` executando · `2` finalizado com
ressalva (regra de negócio) · `3` erro de sistema · `4` sucesso · `5` cancelado.

Um `registrar()` com tipo `error`/`critical` **encerra a execução sozinho** do
lado da API (`status=3`, `final_id_error` e `end_date`) — não é preciso chamar
`atualizar_execucao` depois de logar um erro fatal.

Os três métodos também ecoam a mesma linha no console (`stdout`, `flush=True`)
antes de falar com a API — ver `_ecoar`.
"""

import sys
from datetime import datetime
from typing import Any

from utils.cliente_api_v2 import ClienteApiV2, ErroApiV2

# Tipos aceitos em `type_log`. `error`/`critical` encerram a execução na API.
TIPOS_LOG = ("debug", "info", "warning", "error", "critical")

# Status de execução (`logs.process.status`), na semântica usada pelos bots.
STATUS_EXECUTANDO = 1
STATUS_RESSALVA = 2
STATUS_ERRO_SISTEMA = 3
STATUS_SUCESSO = 4
STATUS_CANCELADO = 5

_NOME_STATUS = {
    STATUS_EXECUTANDO: "EXECUTANDO",
    STATUS_RESSALVA: "RESSALVA",
    STATUS_ERRO_SISTEMA: "ERRO_SISTEMA",
    STATUS_SUCESSO: "SUCESSO",
    STATUS_CANCELADO: "CANCELADO",
}


class Logger:
    """Logger do bot: abre a execução, registra os passos e a encerra.

    Recebe o objeto de configuração inteiro (não campos soltos) porque todos os
    dados de identificação — `ID_BOT`, `NOME_SERVICO`, `GRUPO_BOT`, `AMBIENTE`,
    `HOST` — já moram lá, cravados no `create` do SDK.
    """

    def __init__(self, configuracoes: Any) -> None:
        self._configuracoes = configuracoes
        self._cliente = ClienteApiV2.instancia(configuracoes)
        self._id_execucao: int | None = None

    @property
    def id_execucao(self) -> int | None:
        """`id` da execução aberta (o `logs.process.id`), ou `None` antes de iniciar."""
        return self._id_execucao

    def iniciar_execucao(self, **campos: Any) -> int:
        """`POST /v2/logs/execucoes/` — abre a execução e guarda o `id`.

        `status`, `message`, `processed_items` e `start_date` são preenchidos
        pela API; passe `campos` só para sobrescrevê-los.

        Falha aqui **propaga**: sem execução aberta o bot roda cego, e é melhor
        parar no início do que descobrir isso no fim.
        """
        corpo = {
            "bot_id": self._configuracoes.ID_BOT,
            "environment": self._configuracoes.AMBIENTE,
            "runner": self._configuracoes.HOST,
            **campos,
        }
        self._ecoar(f"INICIO bot_id={corpo['bot_id']} environment={corpo['environment']} runner={corpo['runner']}")
        resposta = self._cliente.requisitar("POST", "/v2/logs/execucoes/", corpo=corpo)
        if resposta.status_code != 201:
            raise ErroApiV2(f"Falha ao iniciar a execução do bot (HTTP {resposta.status_code}): {resposta.text[:200]}")

        identificador = self._json(resposta).get("id")
        if identificador is None:
            # Sem `id` não há como amarrar registro nenhum à execução: os logs
            # seguintes virariam avulsos, silenciosamente órfãos.
            raise ErroApiV2("A API aceitou a execução mas não devolveu o `id` — impossível vincular os logs a ela.")
        self._id_execucao = int(identificador)
        return self._id_execucao

    def registrar(
        self,
        tipo: str,
        tarefa: str,
        mensagem: str,
        traceback: str | None = None,
        **campos: Any,
    ) -> dict[str, Any]:
        """Registra um log da execução (ou avulso, se ela ainda não foi aberta).

        `mensagem` é cortada em 250 caracteres pela API; o `traceback` vai
        inteiro. `bot_id`/`environment`/`runner` são herdados da execução.

        **Nunca levanta exceção.** Este método é chamado de dentro de blocos
        `except` — falhar aqui mascararia o erro real do bot com um erro de
        rede. Uma falha de log vira aviso no `stderr` e a execução segue.
        """
        if tipo not in TIPOS_LOG:
            raise ValueError(f"type_log inválido: {tipo!r}. Use um de {TIPOS_LOG}.")

        self._ecoar(f"{tipo.upper()} [{tarefa}] {mensagem}")
        if traceback:
            print(traceback, flush=True)

        corpo: dict[str, Any] = {
            "type_log": tipo,
            "task_name": tarefa,
            "message": mensagem,
            "group_name": self._configuracoes.GRUPO_BOT,
            **campos,
        }
        if traceback:
            corpo["traceback"] = traceback

        if self._id_execucao is not None:
            caminho = f"/v2/logs/execucoes/{self._id_execucao}/registros/"
        else:
            # Sem execução aberta: log avulso, que exige a identificação completa
            # (não há execução de onde herdá-la).
            caminho = "/v2/logs/registros/"
            corpo.setdefault("bot_id", self._configuracoes.ID_BOT)
            corpo.setdefault("environment", self._configuracoes.AMBIENTE)
            corpo.setdefault("runner", self._configuracoes.HOST)

        try:
            resposta = self._cliente.requisitar("POST", caminho, corpo=corpo)
        except ErroApiV2 as erro:
            return self._avisar_falha(f"não foi possível registrar o log: {erro}")
        if resposta.status_code != 201:
            return self._avisar_falha(f"log recusado pela API (HTTP {resposta.status_code}): {resposta.text[:200]}")

        # Num log `error`/`critical` a resposta traz a execução já encerrada pela
        # API (`status=3`, `final_id_error`, `end_date`) na chave `execucao`; nos
        # demais tipos ela vem `null`.
        return self._json(resposta)

    def atualizar_execucao(
        self,
        status: int | None = None,
        mensagem: str | None = None,
        fim: datetime | None = None,
        itens_processados: int | None = None,
        **campos: Any,
    ) -> dict[str, Any]:
        """`PATCH /v2/logs/execucoes/{id}/` — atualização parcial da execução.

        Campo ausente não altera nada do outro lado. Encerrar é mandar `status`
        (4 sucesso · 2 ressalva · 5 cancelado) junto de `fim`.

        Como `registrar`, **não levanta**: costuma ser chamado no `finally`/
        `except`, onde estourar esconderia a falha original.
        """
        if self._id_execucao is None:
            return self._avisar_falha("execução não iniciada — nada a atualizar.")

        detalhes = " ".join(
            parte
            for parte in (
                f"status={_NOME_STATUS.get(status, status)}" if status is not None else None,
                f"mensagem={mensagem!r}" if mensagem is not None else None,
                f"itens_processados={itens_processados}" if itens_processados is not None else None,
            )
            if parte
        )
        self._ecoar(f"FIM {detalhes}" if detalhes else "FIM (atualização parcial)")

        corpo: dict[str, Any] = dict(campos)
        if status is not None:
            corpo["status"] = status
        if mensagem is not None:
            corpo["message"] = mensagem
        if fim is not None:
            corpo["end_date"] = fim.isoformat()
        if itens_processados is not None:
            corpo["processed_items"] = itens_processados

        try:
            resposta = self._cliente.requisitar("PATCH", f"/v2/logs/execucoes/{self._id_execucao}/", corpo=corpo)
        except ErroApiV2 as erro:
            return self._avisar_falha(f"não foi possível atualizar a execução: {erro}")
        if resposta.status_code != 200:
            return self._avisar_falha(
                f"atualização da execução recusada (HTTP {resposta.status_code}): {resposta.text[:200]}"
            )
        return self._json(resposta)

    # --- auxiliares -------------------------------------------------------

    @staticmethod
    def _ecoar(linha: str) -> None:
        """Espelha a mesma linha do log no `stdout`, além do `POST`/`PATCH` à API V2.

        Sem isso a task do bot no Kestra aparecia vazia — nada era impresso, então
        não dava pra saber em que etapa o bot estava. `flush=True` e chamado antes
        da requisição de propósito: se o bot morrer no meio da chamada de rede (API
        fora do ar, credencial errada), a linha já foi pro console mesmo sem
        chegar na API — o buffer padrão do stdout só é descartado nesse cenário se
        não for esvaziado explicitamente.
        """
        print(linha, flush=True)

    @staticmethod
    def _avisar_falha(motivo: str) -> dict[str, Any]:
        """Falha de logging vai para o `stderr` e não interrompe o bot.

        `stderr` e não `logger.log()` de propósito: o canal de log é justamente
        o que acabou de falhar.
        """
        print(f"[logger] {motivo}", file=sys.stderr)
        return {}

    @staticmethod
    def _json(resposta: Any) -> dict[str, Any]:
        try:
            return resposta.json()
        except ValueError:
            return {}
