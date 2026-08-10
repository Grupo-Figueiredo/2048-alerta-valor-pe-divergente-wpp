from configuracoes import Configuracoes
from repositorios.repositorio_base import RepositorioBase


class RepositorioAutomData(RepositorioBase):
    """Repositório da connection `autom_data`."""

    def __init__(self, configuracoes: Configuracoes):
        self.configuracoes = configuracoes
        self.db_name = "autom_data"

    def __str__(self) -> str:
        return "RepositorioAutomData - conexão autom_data"
