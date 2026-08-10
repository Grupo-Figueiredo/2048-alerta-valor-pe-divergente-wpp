"""Orquestrador principal do bot: único ponto que combina repositórios e serviços.

Fluxo, por PE pendente de validação (`autom_data.cte_value_audit`):

1. Busca o CTE oficial correspondente em `sgt20.gr_cte` pelo `documento_transporte`.
2. Se não encontrar, **pula o PE sem gravar nada** - `valor_validado` continua
   `NULL`, então `obter_pes_para_verificar()` tenta esse mesmo PE de novo na
   próxima execução (o CTE pode ainda não ter sido emitido/sincronizado).
3. Se encontrar, compara `valor_total_cte_embarcador` com `gr_cte.valor_total_frete`
   (tolerância de R$ 1,00): se divergir, envia alerta via WhatsApp; sempre grava
   os valores e o número do CTE oficial na auditoria.

Erros de negócio (`ExcecaoNegocio`) interrompem o lote e marcam a execução como
"finalizada com ressalva"; erro de item individual (infraestrutura, ex.: API sem
permissão para aquele PE) só pula aquele PE e segue para o próximo, sem derrubar
o lote.
"""

import traceback
from datetime import datetime

from aplicacao.excecoes import ExcecaoNegocio
from aplicacao.servicos import ServicoComparaValores, ServicoNotificaWhatsapp
from configuracoes import Configuracoes
from repositorios import RepositorioAutomData, RepositorioSgt20
from utils import STATUS_RESSALVA, STATUS_SUCESSO, Logger

TASK_INICIAR = "iniciar_processamento"
TASK_PROCESSAR_PE = "processar_pe"
TASK_FINALIZAR = "finalizar_processamento"


def main(logger: Logger, configuracoes: Configuracoes) -> None:
    """Busca os PEs pendentes de validação e processa cada um (ver docstring do módulo)."""
    itens_processados = 0

    repositorio_autom_data = RepositorioAutomData(configuracoes)
    repositorio_sgt20 = RepositorioSgt20(configuracoes)
    servico_compara_valores = ServicoComparaValores()
    servico_notifica_whatsapp = ServicoNotificaWhatsapp(configuracoes)

    def _processar_pe(pe: dict) -> None:
        """Busca o CTE oficial do PE em `gr_cte`, compara e grava (ou pula, se não encontrado)."""
        documento_transporte = pe["documento_transporte"]
        cte = repositorio_sgt20.obter_cte_por_documento(documento_transporte=documento_transporte)
        if not cte:
            mensagem = "Documento não encontrado em gr_cte - será tentado novamente na próxima execução."
            logger.registrar(
                tipo="warning", tarefa=TASK_PROCESSAR_PE, mensagem=f"DT={documento_transporte}: {mensagem}"
            )
            return

        dados_cte = cte[0]
        valores_conferem = servico_compara_valores.comparar_valores(
            valor_frete_total_calculado=dados_cte["valor_total_frete"],
            valor_total_cte_embarcador=pe["valor_total_cte_embarcador"],
        )
        if valores_conferem:
            mensagem = "Valores conferem."
        else:
            mensagem = "Valores divergentes! Alerta enviado via WPP."
            servico_notifica_whatsapp.notificar_whatsapp(
                documento_transporte=documento_transporte,
                valor_frete_total_calculado=dados_cte["valor_total_frete"],
                valor_total_cte_embarcador=pe["valor_total_cte_embarcador"],
            )
        repositorio_autom_data.atualizar_auditoria_cte(
            id_registro=pe["id"],
            valor_liquido_figueiredo=dados_cte["valor_frete"],
            valor_impostos_figueiredo=dados_cte["valor_imposto"],
            valor_total_figueiredo=dados_cte["valor_total_frete"],
            numero_cte=dados_cte["numero_documento"],
            extras=mensagem,
        )
        logger.registrar(tipo="info", tarefa=TASK_PROCESSAR_PE, mensagem=f"DT={documento_transporte}: {mensagem}")

    try:
        logger.registrar(tipo="info", tarefa=TASK_INICIAR, mensagem="Iniciando verificação de PEs com valor divergente")
        pes_para_verificar = repositorio_autom_data.obter_pes_para_verificar()
        if not pes_para_verificar:
            logger.atualizar_execucao(
                status=STATUS_SUCESSO,
                mensagem="Nenhum PE para verificação",
                fim=datetime.now(),
                itens_processados=itens_processados,
            )
            return

        total = len(pes_para_verificar)
        logger.registrar(tipo="info", tarefa=TASK_INICIAR, mensagem=f"{total} PE(s) encontrados para verificação")

        for indice, pe in enumerate(pes_para_verificar, start=1):
            logger.registrar(
                tipo="info",
                tarefa=TASK_PROCESSAR_PE,
                mensagem=f"Processando {indice}/{total} (DT={pe['documento_transporte']})",
            )
            try:
                _processar_pe(pe)
            except ExcecaoNegocio:
                raise
            except Exception as erro:
                # Erro de infraestrutura em 1 PE (ex.: API fora do ar, sem permissão) não
                # derruba o lote inteiro - loga e segue para o próximo.
                logger.registrar(
                    tipo="error",
                    tarefa=TASK_PROCESSAR_PE,
                    mensagem=f"DT={pe['documento_transporte']}: falha ao processar - {erro!s}",
                    traceback=traceback.format_exc(),
                )
            itens_processados += 1

    except ExcecaoNegocio as e:
        logger.atualizar_execucao(
            status=STATUS_RESSALVA,
            mensagem=f"Processo finalizado com exceção - {e!s}",
            fim=datetime.now(),
            itens_processados=itens_processados,
        )
        return

    logger.registrar(tipo="info", tarefa=TASK_FINALIZAR, mensagem="Processamento concluído")
    logger.atualizar_execucao(
        status=STATUS_SUCESSO,
        mensagem="Processo finalizado com sucesso",
        fim=datetime.now(),
        itens_processados=itens_processados,
    )
