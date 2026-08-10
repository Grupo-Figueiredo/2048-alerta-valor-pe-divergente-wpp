"""Monta e envia a mensagem de alerta de PE com valor divergente via WhatsApp (Z-API).

Diferente dos `repositorios/` (que falam com a API V2), este serviço fala com um
sistema **externo** ao Grupo Figueiredo (Z-API) — por isso a chamada HTTP mora
aqui, em `aplicacao/servicos/`, e não em `repositorios/`.
"""

from decimal import Decimal
from typing import Any

import requests

from configuracoes import Configuracoes

_SISTEMA_CREDENCIAL = "whatsapp_alerta_pe"


class ErroNotificacaoWhatsapp(Exception):
    """Falha de infraestrutura ao notificar via WhatsApp (Z-API)."""


class ServicoNotificaWhatsapp:
    """Formata a mensagem de alerta e envia via Z-API.

    Credenciais (`url`, `client_token`, `destino`) vêm da API V2
    (`configuracoes.obter_credencial("whatsapp_alerta_pe")`) — nunca hardcoded
    no código nem lidas do `.env`.
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
        """Envia o alerta de divergência para o grupo de WhatsApp configurado.

        Retorna `True` se a Z-API confirmou o envio (HTTP 200).
        """
        credenciais: dict[str, Any] = self._configuracoes.obter_credencial(_SISTEMA_CREDENCIAL)
        url = credenciais.get("url")
        client_token = credenciais.get("client_token")
        destino = credenciais.get("destino")
        if not url or not client_token or not destino:
            raise ErroNotificacaoWhatsapp(
                f"Credencial incompleta para o sistema {_SISTEMA_CREDENCIAL!r} — esperado url/client_token/destino."
            )

        mensagem = (
            f"🤖 *ALERTA AUTOMÁTICO - VALOR PE DIVERGENTE* 🤖\n\n"
            f"📄 *PE:* {documento_transporte}\n\n"
            f"💰 *Frete Total:* {self.formatar_brl(valor_frete_total_calculado)}\n"
            f"🧾 *Valor Total CTE Embarcador:* {self.formatar_brl(valor_total_cte_embarcador)}\n\n"
            f"⚠️ *Divergência identificada automaticamente pelo robô de monitoramento.*"
        )

        resposta = requests.post(
            url,
            json={"phone": destino, "message": mensagem},
            headers={"client-token": client_token, "Content-Type": "application/json"},
            timeout=self._configuracoes.ZAPI_TIMEOUT,
        )
        return resposta.status_code == 200
