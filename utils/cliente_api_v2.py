"""Cliente HTTP centralizado da API V2 — autenticação JWT e transporte.

Toda a comunicação com a API passa por aqui: dados (`/v2/query/`), logs
(`/v2/logs/`), credenciais (`/v2/credenciais/`) e arquivos (`/v2/arquivos/`).
O cliente autentica com `API_USERNAME`/`API_PASSWORD` em `POST /v2/auth/token/`,
guarda o par `access`/`refresh`, renova o `access` automaticamente (por
expiração ou ao receber `401`) via `POST /v2/auth/token/refresh/` e, quando o
`refresh` não vale mais, faz um novo login.

A autenticação é transparente para o resto da aplicação: os repositórios só
chamam `executar_query(db, sql)` e as classes de `utils/` só chamam
`requisitar(...)`. **Nunca** loga token nem senha.

Este módulo mora em `utils/` (e não em `repositorios/`) porque é infraestrutura
compartilhada: `repositorios/` depende dele, não o contrário.
"""

import base64
import binascii
import json
import time
from functools import partial
from typing import Any, ClassVar

import requests

# Renova o access esta quantidade de segundos ANTES do exp (margem de segurança).
_MARGEM_EXPIRACAO_SEGUNDOS = 30


class ErroApiV2(Exception):
    """Falha de infraestrutura ao falar com a API V2 (rede, autenticação, HTTP != 2xx)."""


class ClienteApiV2:
    """Cliente autenticado da API V2, com token compartilhado por processo.

    Use `ClienteApiV2.instancia(configuracoes)` — há uma instância por
    `(base_url, username)`, de modo que o token seja reaproveitado por todos os
    repositórios do processo.
    """

    _instancias: ClassVar[dict[tuple[str, str], "ClienteApiV2"]] = {}

    def __init__(self, base_url: str, username: str, password: str, timeout: int = 60) -> None:
        self._base_url = (base_url or "").rstrip("/")
        self._username = username
        self._password = password
        self._timeout = timeout
        self._access: str | None = None
        self._refresh: str | None = None

    @classmethod
    def instancia(cls, configuracoes: Any) -> "ClienteApiV2":
        base_url = (getattr(configuracoes, "API_BASE_URL", None) or "").rstrip("/")
        username = getattr(configuracoes, "API_USERNAME", None) or ""
        chave = (base_url, username)
        if chave not in cls._instancias:
            cls._instancias[chave] = cls(
                base_url=base_url,
                username=username,
                password=getattr(configuracoes, "API_PASSWORD", None) or "",
                timeout=getattr(configuracoes, "API_TIMEOUT", 60),
            )
        return cls._instancias[chave]

    def executar_query(self, db: str, sql: str) -> dict[str, Any]:
        """`POST /v2/query/` com `{db, sql}` → `{columns, rows, rowcount, truncated}`."""
        resposta = self._requisicao_autenticada("POST", "/v2/query/", corpo={"db": db, "sql": sql})
        if resposta.status_code == 200:
            return self._json(resposta)
        raise ErroApiV2(self._mensagem_erro_query(resposta, db))

    def requisitar(
        self,
        metodo: str,
        caminho: str,
        *,
        corpo: dict[str, Any] | None = None,
        parametros: dict[str, Any] | None = None,
        arquivos: dict[str, Any] | None = None,
        dados: dict[str, Any] | None = None,
    ) -> requests.Response:
        """Requisição autenticada arbitrária à API V2. Devolve a `Response` crua.

        Usado pelas classes de `utils/` (logs, credenciais, arquivos), que
        precisam de verbos e formatos que o `executar_query` não cobre —
        inclusive `multipart` (`arquivos`/`dados`) e resposta binária.

        Não interpreta o status: quem chama decide o que é erro no seu contexto
        (um `404` em credencial é "não existe"; num upload é falha). Só falha de
        transporte vira `ErroApiV2` aqui.
        """
        return self._requisicao_autenticada(
            metodo, caminho, corpo=corpo, parametros=parametros, arquivos=arquivos, dados=dados
        )

    # --- autenticação -----------------------------------------------------

    def _requisicao_autenticada(
        self,
        metodo: str,
        caminho: str,
        *,
        corpo: dict[str, Any] | None = None,
        parametros: dict[str, Any] | None = None,
        arquivos: dict[str, Any] | None = None,
        dados: dict[str, Any] | None = None,
    ) -> requests.Response:
        if not self._token_valido():
            self._garantir_token()
        enviar = partial(
            self._requisitar, metodo, caminho, corpo=corpo, parametros=parametros, arquivos=arquivos, dados=dados
        )
        resposta = enviar(bearer=self._access)
        if resposta.status_code == 401:
            # Access recusado: renova (refresh → senão login) e tenta de novo 1x.
            self._renovar()
            resposta = enviar(bearer=self._access)
        return resposta

    def _garantir_token(self) -> None:
        if self._refresh:
            self._renovar()
        else:
            self._login()

    def _login(self) -> None:
        # `API_BASE_URL` ausente já falha em `_requisitar`, ponto único de rede.
        resposta = self._post("/v2/auth/token/", {"username": self._username, "password": self._password})
        if resposta.status_code != 200:
            raise ErroApiV2(f"Falha ao autenticar na API V2 (HTTP {resposta.status_code}).")
        dados = self._json(resposta)
        self._access = dados.get("access")
        self._refresh = dados.get("refresh")
        if not self._access:
            raise ErroApiV2("Login na API V2 não retornou o token de acesso (`access`).")

    def _renovar(self) -> None:
        """Renova o `access` via `refresh`; se o `refresh` não valer, faz novo login."""
        if not self._refresh:
            self._login()
            return
        resposta = self._post("/v2/auth/token/refresh/", {"refresh": self._refresh})
        if resposta.status_code == 200:
            novo = self._json(resposta).get("access")
            if novo:
                self._access = novo
                return
        # Refresh inválido/expirado → login completo com usuário e senha.
        self._login()

    def _token_valido(self) -> bool:
        if not self._access:
            return False
        exp = self._exp_do_jwt(self._access)
        if exp is None:
            return True  # sem exp legível: confia e deixa o 401 tratar
        return time.time() < (exp - _MARGEM_EXPIRACAO_SEGUNDOS)

    @staticmethod
    def _exp_do_jwt(token: str) -> float | None:
        """Lê o claim `exp` do JWT (sem verificar assinatura)."""
        try:
            payload_b64 = token.split(".")[1]
            padding = "=" * (-len(payload_b64) % 4)
            payload = json.loads(base64.urlsafe_b64decode(payload_b64 + padding))
            exp = payload.get("exp")
            return float(exp) if exp is not None else None
        except (IndexError, ValueError, binascii.Error, json.JSONDecodeError):
            return None

    # --- HTTP base --------------------------------------------------------

    def _post(self, caminho: str, corpo: dict[str, Any], bearer: str | None = None) -> requests.Response:
        return self._requisitar("POST", caminho, corpo=corpo, bearer=bearer)

    def _requisitar(
        self,
        metodo: str,
        caminho: str,
        *,
        corpo: dict[str, Any] | None = None,
        parametros: dict[str, Any] | None = None,
        arquivos: dict[str, Any] | None = None,
        dados: dict[str, Any] | None = None,
        bearer: str | None = None,
    ) -> requests.Response:
        """Ponto único que fala com a rede — todo o resto do cliente passa por aqui.

        `arquivos` (multipart) deve conter **bytes**, nunca um arquivo aberto: um
        `401` faz a requisição ser repetida depois de renovar o token, e um
        handle já lido subiria vazio na segunda tentativa. Ver `utils/arquivos.py`.
        """
        if not self._base_url:
            raise ErroApiV2("API_BASE_URL não definida — configure o acesso à API V2.")
        cabecalhos = {"Authorization": f"Bearer {bearer}"} if bearer else None
        try:
            return requests.request(
                metodo,
                f"{self._base_url}{caminho}",
                # `json` e `files` são mutuamente exclusivos: com multipart, os
                # campos de texto vão em `data`, não serializados como JSON.
                json=corpo if arquivos is None else None,
                data=dados,
                files=arquivos,
                params=parametros,
                headers=cabecalhos,
                timeout=self._timeout,
            )
        except requests.RequestException as e:
            raise ErroApiV2(f"Não foi possível contatar a API V2 em {self._base_url}{caminho}: {e}") from e

    @staticmethod
    def _json(resposta: requests.Response) -> dict[str, Any]:
        try:
            return resposta.json()
        except ValueError:
            return {}

    @staticmethod
    def _mensagem_erro_query(resposta: requests.Response, db: str) -> str:
        detalhes = {
            400: "SQL inválido ou mais de um comando",
            # 401 aqui já é o *segundo* 401: o cliente renovou o token e repetiu.
            401: "credenciais recusadas mesmo após renovar o token — confira API_USERNAME/API_PASSWORD",
            403: "usuário sem permissão para executar o comando",
            404: f"banco '{db}' inexistente",
        }
        detalhe = detalhes.get(resposta.status_code, "erro inesperado")
        return f"Falha na consulta à API V2 (HTTP {resposta.status_code}: {detalhe})."
