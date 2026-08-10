"""Manipulação de arquivos no storage do Grupo Figueiredo via API V2.

Substitui o antigo `manage_files_adapter`. Todas as rotas trabalham com dois
parâmetros: `local_storage` (qual armazenamento — o `storage_name` de antes) e
`file_path` (caminho **relativo** dentro dele).

- `enviar`  → `POST   /v2/arquivos/`      (multipart)
- `baixar`  → `GET    /v2/arquivos/view/` (binário)
- `listar`  → `GET    /v2/arquivos/`
- `remover` → `DELETE /v2/arquivos/`
"""

from pathlib import Path
from typing import Any

from utils.cliente_api_v2 import ClienteApiV2, ErroApiV2


class Arquivos:
    """Arquivos no storage remoto, via API V2.

    `armazenamento_padrao` evita repetir o `local_storage` em toda chamada; vem
    de `Configuracoes.ARMAZENAMENTO_PADRAO` e pode ser sobrescrito por chamada.
    """

    def __init__(self, configuracoes: Any) -> None:
        self._cliente = ClienteApiV2.instancia(configuracoes)
        self._armazenamento_padrao = getattr(configuracoes, "ARMAZENAMENTO_PADRAO", "local")

    def enviar(
        self, caminho_local: str | Path, caminho_remoto: str, armazenamento: str | None = None
    ) -> dict[str, Any]:
        """Sobe `caminho_local` para `caminho_remoto` dentro do armazenamento.

        O conteúdo é lido em **bytes** antes de enviar, e não passado como
        arquivo aberto: um `401` faz o cliente renovar o token e repetir a
        requisição, e um handle já consumido subiria vazio na segunda tentativa.
        """
        origem = Path(caminho_local)
        if not origem.is_file():
            raise ErroApiV2(f"Arquivo local inexistente para upload: {origem}")

        resposta = self._cliente.requisitar(
            "POST",
            "/v2/arquivos/",
            dados={"local_storage": self._armazenamento(armazenamento), "file_path": caminho_remoto},
            arquivos={"arquivo": (origem.name, origem.read_bytes())},
        )
        if resposta.status_code != 201:
            raise ErroApiV2(
                f"Falha ao enviar {origem.name} para {caminho_remoto} (HTTP {resposta.status_code}): "
                f"{resposta.text[:200]}"
            )
        return self._json(resposta)

    def baixar(self, caminho_remoto: str, caminho_local: str | Path, armazenamento: str | None = None) -> Path:
        """Baixa `caminho_remoto` para `caminho_local`. Devolve o caminho gravado."""
        resposta = self._cliente.requisitar(
            "GET",
            "/v2/arquivos/view/",
            parametros={
                "local_storage": self._armazenamento(armazenamento),
                "file_path": caminho_remoto,
                "download": "true",
            },
        )
        if resposta.status_code != 200:
            raise ErroApiV2(f"Falha ao baixar {caminho_remoto} (HTTP {resposta.status_code}): {resposta.text[:200]}")

        destino = Path(caminho_local)
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(resposta.content)
        return destino

    def listar(self, diretorio: str = "", armazenamento: str | None = None) -> dict[str, Any]:
        """Lista arquivos e pastas de `diretorio` (vazio = raiz do armazenamento)."""
        resposta = self._cliente.requisitar(
            "GET",
            "/v2/arquivos/",
            parametros={"local_storage": self._armazenamento(armazenamento), "file_path": diretorio},
        )
        if resposta.status_code != 200:
            raise ErroApiV2(f"Falha ao listar {diretorio!r} (HTTP {resposta.status_code}): {resposta.text[:200]}")
        return self._json(resposta)

    def remover(self, caminho_remoto: str, armazenamento: str | None = None) -> dict[str, Any]:
        """Apaga `caminho_remoto` no armazenamento.

        Escrita destrutiva: pela Regra Zero do `CLAUDE.md`, só chame com
        aprovação explícita — não há lixeira do outro lado.
        """
        resposta = self._cliente.requisitar(
            "DELETE",
            "/v2/arquivos/",
            parametros={"local_storage": self._armazenamento(armazenamento), "file_path": caminho_remoto},
        )
        if resposta.status_code != 200:
            raise ErroApiV2(f"Falha ao remover {caminho_remoto} (HTTP {resposta.status_code}): {resposta.text[:200]}")
        return self._json(resposta)

    # --- auxiliares -------------------------------------------------------

    def _armazenamento(self, informado: str | None) -> str:
        return informado or self._armazenamento_padrao

    @staticmethod
    def _json(resposta: Any) -> dict[str, Any]:
        try:
            return resposta.json()
        except ValueError:
            return {}
