"""Comparação entre o frete calculado pelo bot e o valor informado pelo embarcador."""

from decimal import Decimal

TOLERANCIA_REAIS = Decimal("1.00")


class ServicoComparaValores:
    """Decide se o frete calculado confere com o valor do CTE do embarcador (tolerância de R$ 1,00)."""

    def comparar_valores(
        self, valor_frete_total_calculado: Decimal | float, valor_total_cte_embarcador: Decimal | float
    ) -> bool:
        """Compara o frete total calculado com o valor total do CTE do embarcador.

        Os dois lados passam por `Decimal(str(...))` - a API V2 devolve numéricos
        como `float` (JSON), e `float - float` perde precisão em centavos.
        """
        valor_frete_total_calculado = Decimal(str(valor_frete_total_calculado))
        valor_total_cte_embarcador = Decimal(str(valor_total_cte_embarcador))
        return abs(valor_frete_total_calculado - valor_total_cte_embarcador) <= TOLERANCIA_REAIS
