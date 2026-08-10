import traceback
from datetime import datetime

from aplicacao.controladores import controlador_principal
from configuracoes import Configuracoes
from utils import STATUS_ERRO_SISTEMA, Logger


def run():
    configuracoes = Configuracoes()

    logger = Logger(configuracoes)
    try:
        logger.iniciar_execucao()
        controlador_principal.main(
            logger=logger,
            configuracoes=configuracoes,
        )
    except Exception as erro:
        logger.registrar(
            tipo="error",
            tarefa=traceback.extract_tb(erro.__traceback__)[-1][2],
            mensagem=str(erro),
            traceback=traceback.format_exc(),
        )
        logger.atualizar_execucao(
            status=STATUS_ERRO_SISTEMA,
            mensagem=f"Erro de sistema não tratado - {erro!s}",
            fim=datetime.now(),
        )
        raise erro


if __name__ == "__main__":
    run()
