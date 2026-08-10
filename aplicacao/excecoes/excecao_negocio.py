class ExcecaoNegocio(Exception):
    """Exceção base para erros de regra de negócio (recuperáveis, não derrubam o bot)."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)
