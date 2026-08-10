"""Utilitários de infraestrutura do bot, todos sobre a API V2.

Camada mais baixa do projeto: não conhece `aplicacao/` nem `repositorios/` —
os dois é que dependem dela. Substitui os antigos adaptadores externos
(`logger_adapter`, `secrets_adapter`, `manage_files_adapter`), que agora são só
rotas da API V2.

| antes (adaptador)                        | agora                          |
|------------------------------------------|--------------------------------|
| `LoggerAdapter(...)`                      | `Logger(configuracoes)`        |
| `.start_exec()`                           | `.iniciar_execucao()`          |
| `.log(type_log=, task_name=, message=)`   | `.registrar(tipo, tarefa, mensagem)` |
| `.update_exec(status=, end_date=)`        | `.atualizar_execucao(status=, fim=)` |
| `.id_exec`                                | `.id_execucao`                 |
| `SecretAdapter().get_secret(vault, system)` | `Credenciais(cfg).obter(sistema)` |
| `ManageFilesAdapter().upload_file(...)`   | `Arquivos(cfg).enviar(...)`    |
"""

from utils.arquivos import Arquivos
from utils.cliente_api_v2 import ClienteApiV2, ErroApiV2
from utils.credenciais import Credenciais, CredencialNaoEncontrada
from utils.logger import (
    STATUS_CANCELADO,
    STATUS_ERRO_SISTEMA,
    STATUS_EXECUTANDO,
    STATUS_RESSALVA,
    STATUS_SUCESSO,
    Logger,
)

__all__ = [
    "STATUS_CANCELADO",
    "STATUS_ERRO_SISTEMA",
    "STATUS_EXECUTANDO",
    "STATUS_RESSALVA",
    "STATUS_SUCESSO",
    "Arquivos",
    "ClienteApiV2",
    "CredencialNaoEncontrada",
    "Credenciais",
    "ErroApiV2",
    "Logger",
]
