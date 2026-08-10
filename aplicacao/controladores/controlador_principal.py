from datetime import datetime

from aplicacao.excecoes import ExcecaoNegocio
from configuracoes import Configuracoes
from utils import STATUS_RESSALVA, STATUS_SUCESSO, Logger


def main(
    logger: Logger,
    configuracoes: Configuracoes,
):
    itens_processados = 0

    try:
        # TODO: Implementar a lógica aqui
        pass
    except ExcecaoNegocio as e:
        logger.atualizar_execucao(
            status=STATUS_RESSALVA,
            mensagem=f"Processo finalizado com exceção - {e!s}",
            fim=datetime.now(),
            itens_processados=itens_processados,
        )
        return

    logger.atualizar_execucao(
        status=STATUS_SUCESSO,
        mensagem="Processo finalizado com sucesso",
        fim=datetime.now(),
        itens_processados=itens_processados,
    )
