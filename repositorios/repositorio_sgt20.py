"""Repositório da connection `sgt20` (Postgres): CTE oficial (fonte Protheus/TOTVS)."""

from typing import Any

from configuracoes import Configuracoes
from repositorios.repositorio_base import RepositorioBase


class RepositorioSgt20(RepositorioBase):
    """Repositório da connection `sgt20`."""

    def __init__(self, configuracoes: Configuracoes):
        self.configuracoes = configuracoes
        self.connection_name = "sgt20"

    def __str__(self) -> str:
        return "RepositorioSgt20 - conexão sgt20"

    def obter_cte_por_documento(self, documento_transporte: str) -> list[dict[str, Any]]:
        """CTE oficial (`gr_cte`) do documento de transporte - fonte de verdade do valor/número do CTE.

        Filtra `ativo`/`deletado`/`id_rejeicao_cte` pra excluir CTE cancelado, recusado ou inativo, e
        pega o mais recente (`order by id desc`) quando houver mais de um pro mesmo documento.
        """
        sql = f"""
            SELECT
                numero_documento,
                valor_frete,
                valor_imposto,
                valor_total_frete
            FROM
                gr_cte
            WHERE
                documento_transporte = '{self._escapar(documento_transporte)}'
                AND ativo = true
                AND deletado IS false
                AND id_rejeicao_cte = 100
            ORDER BY
                id DESC
        """  # nosec B608
        return self._executar_consulta(sql)
