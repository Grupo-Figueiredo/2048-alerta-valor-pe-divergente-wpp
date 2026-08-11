"""Monta e envia a mensagem de alerta de PE com valor divergente via WhatsApp.

Usa `POST /v2/notificacoes/whatsapp/`, rota própria da API V2 (a Z-API mora do
outro lado, resolvida pela API a partir do cofre dela) — não é mais uma
integração direta com terceiro. Por isso a chamada usa
`ClienteApiV2.requisitar` (mesmo padrão de `utils.Logger`/`utils.Arquivos` para
"qualquer outra rota da API V2" descrito no `CLAUDE.md`), e não `requests`
direto contra a Z-API.
"""

from decimal import Decimal
from typing import Any

from configuracoes import Configuracoes
from utils.cliente_api_v2 import ClienteApiV2, ErroApiV2

_SISTEMA_CREDENCIAL = "whatsapp_alerta_pe"
_TIPO_DESTINATARIO_TELEFONE = "telefone"


class ErroNotificacaoWhatsapp(Exception):
    """Falha de infraestrutura ao notificar via WhatsApp (API V2)."""


class ServicoNotificaWhatsapp:
    """Formata a mensagem de alerta e envia via `POST /v2/notificacoes/whatsapp/`.

    O destinatário (telefone ou id de grupo, ex.: `<id>-group`) vem da
    credencial `whatsapp_alerta_pe` na API V2
    (`configuracoes.obter_credencial("whatsapp_alerta_pe")`) — nunca hardcoded
    no código nem lido do `.env`.
    """

    def __init__(self, configuracoes: Configuracoes):
        self._configuracoes = configuracoes

    @staticmethod
    def formatar_brl(valor: Decimal | float | str) -> str:
        """Formata número para padrão monetário brasileiro. Ex: `999999.99` -> `"R$ 999.999,99"`."""
        valor = Decimal(str(valor))
        return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    def notificar_whatsapp(
        self,
        documento_transporte: str,
        valor_frete_total_calculado: Decimal,
        valor_total_cte_embarcador: Decimal,
    ) -> bool:
        """Envia o alerta de divergência para o destinatário configurado.

        Retorna `True` se a API V2 aceitou o envio (HTTP 200). Um `200` cobre o
        resultado por destinatário — como só há um destinatário configurado,
        aceitar o HTTP já basta; falha de infraestrutura vira `ErroNotificacaoWhatsapp`.
        """
        credenciais: dict[str, Any] = self._configuracoes.obter_credencial(_SISTEMA_CREDENCIAL)
        destino = credenciais.get("destino")
        if not destino:
            raise ErroNotificacaoWhatsapp(
                f"Credencial incompleta para o sistema {_SISTEMA_CREDENCIAL!r} — esperado 'destino'."
            )

        mensagem = (
            f"🤖 *ALERTA AUTOMÁTICO - VALOR PE DIVERGENTE* 🤖\n\n"
            f"📄 *PE:* {documento_transporte}\n\n"
            f"💰 *Frete Total:* {self.formatar_brl(valor_frete_total_calculado)}\n"
            f"🧾 *Valor Total CTE Embarcador:* {self.formatar_brl(valor_total_cte_embarcador)}\n\n"
            f"⚠️ *Divergência identificada automaticamente pelo robô de monitoramento.*"
        )

        cliente = ClienteApiV2.instancia(self._configuracoes)
        try:
            resposta = cliente.requisitar(
                "POST",
                "/v2/notificacoes/whatsapp/",
                dados={
                    "destinatarios": [destino],
                    "mensagem": mensagem,
                    "tipo_destinatario": _TIPO_DESTINATARIO_TELEFONE,
                },
            )
        except ErroApiV2 as erro:
            raise ErroNotificacaoWhatsapp(f"Não foi possível contatar a rota de notificação: {erro}") from erro

        if resposta.status_code != 200:
            raise ErroNotificacaoWhatsapp(
                f"Falha ao enviar alerta via WhatsApp (HTTP {resposta.status_code}): {resposta.text[:200]}"
            )
        return True
