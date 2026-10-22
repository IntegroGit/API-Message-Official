"""Processamento da fila de eventos e mídias pendentes.

Estrutura inicial; implementação pendente.
"""

import asyncio, logging
from starlette.concurrency import run_in_threadpool
from datetime import datetime, timezone
from app.database import get_connection, get_sessions_without_report
from app.grouping import close_inactive_sessions
from app.report import generate_session_report, ReportNotReadyError

logger = logging.getLogger("uvicorn.error")

def run_session_closure():

    with get_connection() as conn:
        closed_session_ids = close_inactive_sessions(conn, datetime.now(timezone.utc))


    return closed_session_ids

async def session_closure_loop():

    while True:

        try:

            await run_in_threadpool(run_session_closure)

        except Exception:

            logger.exception("Erro no fechamento das sessões")

        try:

            await run_in_threadpool(run_pending_reports)

        except Exception:

            logger.exception("Falha na busca ou no processamento do relatório")

        await asyncio.sleep(60)

def run_pending_reports():

    ids = get_sessions_without_report()

    for id in ids:

        try:

            generate_session_report(id)

        except ReportNotReadyError:
            continue

        except Exception:

            logger.exception(f"Falha ao gerar o relatório da sessão: {id}")