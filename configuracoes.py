import os
import socket
from typing import Any

from utils.credenciais import Credenciais


class Configuracoes:
    """Configuração centralizada do bot (variáveis de ambiente + constantes)."""

    def __init__(self) -> None:
        # Criado sob demanda em `obter_credencial`: um bot que não usa sistema
        # externo nenhum não precisa nem autenticar na API V2 por causa disto.
        self._credenciais: Credenciais | None = None

    # API V2 — acesso a dados (`/v2/query/`), logs, credenciais e arquivos.
    API_BASE_URL: str | None = os.getenv("API_BASE_URL")
    API_USERNAME: str | None = os.getenv("API_USERNAME")
    API_PASSWORD: str | None = os.getenv("API_PASSWORD")
    # Timeout (s) de toda chamada HTTP à API V2 — usado por `utils.ClienteApiV2`.
    API_TIMEOUT: int = int(os.getenv("API_TIMEOUT", "60"))

    # Identificação do bot (contrato com o logger).
    NOME_SERVICO: str = "alerta-valor-pe-divergente-wpp"
    ID_BOT: str = "2048"
    GRUPO_BOT: str = "APERAM"
    VERSAO: str = "0.0.1"

    AMBIENTE: str = os.getenv("ENVIRONMENT", "development")
    HOST: str = socket.gethostname()

    # Armazenamento padrão usado por `utils.Arquivos` (o `storage_name` de antes).
    ARMAZENAMENTO_PADRAO: str = os.getenv("ARMAZENAMENTO_PADRAO", "local")

    def obter_credencial(self, sistema: str) -> dict[str, Any]:
        """Credencial de um sistema externo, resolvida pela API V2.

        Substitui o `get_secret(vault="apifig", system=...)` do `secrets_adapter`:
        o vault agora é resolvido do lado da API, e o bot só precisa das próprias
        credenciais da API V2. Nunca logue o dicionário devolvido.
        """
        if self._credenciais is None:
            self._credenciais = Credenciais(self)
        return self._credenciais.obter(sistema)


if __name__ == "__main__":
    configuracoes = Configuracoes()
    print(configuracoes.API_BASE_URL)
