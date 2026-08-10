"""Repositório da connection `autom_data` (Postgres): auditoria de CTE."""

from decimal import Decimal
from typing import Any

from configuracoes import Configuracoes
from repositorios.repositorio_base import RepositorioBase


class RepositorioAutomData(RepositorioBase):
    """Repositório da connection `autom_data`."""

    def __init__(self, configuracoes: Configuracoes):
        self.configuracoes = configuracoes
        self.connection_name = "autom_data"

    def __str__(self) -> str:
        return "RepositorioAutomData - conexão autom_data"

    def obter_pes_para_verificar(self) -> list[dict[str, Any]]:
        """PEs das filiais 15/2, criados no último dia, com valor informado e ainda não validados."""
        sql = """
            SELECT
                id,
                documento_transporte,
                valor_liquido_cte_embarcador,
                valor_impostos_cte_embarcador,
                valor_total_cte_embarcador
            FROM
                cte_value_audit
            WHERE
                lg_filial in (15, 2)
            AND
                data_criacao >= CURRENT_DATE - INTERVAL '1 day'
            AND
                valor_total_cte_embarcador is not NULL
            AND
                valor_total_cte_embarcador <> 0
            AND valor_validado is null
        """
        return self._executar_consulta(sql)

    def atualizar_auditoria_cte(
        self,
        id_registro: int,
        valor_liquido_figueiredo: Decimal | float,
        valor_impostos_figueiredo: Decimal | float,
        valor_total_figueiredo: Decimal | float,
        numero_cte: str,
        extras: str,
    ) -> int:
        """Marca o PE como validado e grava os valores/número do CTE oficial (`sgt20.gr_cte`).

        Só é chamado quando o documento **foi** encontrado em `gr_cte` - quando não é
        encontrado, o chamador pula o PE sem gravar nada (fica `valor_validado is
        null`, pra ser tentado de novo na próxima execução).

        Os três valores passam por `Decimal(str(...))` - a API V2 devolve numéricos
        como `float` (JSON), e interpolar `float` direto no SQL arrisca ruído de
        ponto flutuante no literal (ex.: `7834.430000000001`).
        """
        valor_liquido_figueiredo = Decimal(str(valor_liquido_figueiredo))
        valor_impostos_figueiredo = Decimal(str(valor_impostos_figueiredo))
        valor_total_figueiredo = Decimal(str(valor_total_figueiredo))
        sql = f"""
            UPDATE cte_value_audit
            SET
                valor_validado = true,
                valor_liquido_cte_figueiredo = {valor_liquido_figueiredo},
                valor_impostos_cte_figueiredo = {valor_impostos_figueiredo},
                valor_total_cte_figueiredo = {valor_total_figueiredo},
                numero_cte = '{self._escapar(str(numero_cte))}',
                extras = '{self._escapar(extras)}'
            WHERE id = {int(id_registro)}
        """
        return self._executar_escrita(sql)
