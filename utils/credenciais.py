"""Consulta de credenciais de sistemas externos via API V2 (`/v2/credenciais/`).

Substitui o antigo `secrets_adapter`: em vez de falar com o vault direto, o bot
pede a credencial à API, que resolve o vault do outro lado. O bot passa a
precisar de **um** par de credenciais (o da própria API V2, gerado no registro
do SGT20) em vez de dois.

Nunca logue o dicionário devolvido: ele contém senha/token em texto claro.
"""

from typing import Any

from utils.cliente_api_v2 import ClienteApiV2, ErroApiV2


class CredencialNaoEncontrada(ErroApiV2):
    """O sistema pedido não tem credencial cadastrada (HTTP 404).

    Subclasse de `ErroApiV2` para quem só quer tratar "falhou o acesso à API"
    continuar pegando os dois casos com um `except` só.
    """


class Credenciais:
    """Credenciais de sistemas externos, resolvidas pela API V2."""

    def __init__(self, configuracoes: Any) -> None:
        self._cliente = ClienteApiV2.instancia(configuracoes)

    def obter(self, sistema: str) -> dict[str, Any]:
        """`GET /v2/credenciais/?sistema=<sistema>` → dicionário da credencial.

        `sistema` é o mesmo identificador que era passado ao `secrets_adapter`
        (o `system=` de então). Levanta `CredencialNaoEncontrada` no `404` e
        `ErroApiV2` em qualquer outra falha — nunca devolve um dicionário vazio
        se passando por sucesso, o que faria o bot tentar logar sem senha e
        falhar num ponto distante da causa.
        """
        resposta = self._cliente.requisitar("GET", "/v2/credenciais/", parametros={"sistema": sistema})

        if resposta.status_code == 200:
            return self._json(resposta)
        if resposta.status_code == 404:
            raise CredencialNaoEncontrada(f"Nenhuma credencial cadastrada para o sistema {sistema!r}.")
        if resposta.status_code == 403:
            raise ErroApiV2(
                f"Sem permissão para ler a credencial de {sistema!r} — confira o role do usuário da API V2."
            )
        raise ErroApiV2(f"Falha ao consultar a credencial de {sistema!r} (HTTP {resposta.status_code}).")

    @staticmethod
    def _json(resposta: Any) -> dict[str, Any]:
        try:
            return resposta.json()
        except ValueError as erro:
            raise ErroApiV2(f"Resposta de credencial não é um JSON válido: {erro}") from erro
