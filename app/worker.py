"""Processamento da fila de eventos e mídias pendentes.

Estrutura inicial; implementação pendente.
"""

import asyncio, logging
from starlette.concurrency import run_in_threadpool
from datetime import datetime, timezone
from app.database import get_connection, get_sessions_without_report
from app.grouping import close_inactive_sessions
from app.report import generate_session_report, ReportNotReadyError
from app.recovery import (recover_audio_downloads, 
                          recover_image_downloads, 
                          recover_stale_audio_downloads, 
                          recover_stale_image_downloads,
                          recover_stale_transcriptions,
                          recover_transcriptions,
                          recover_stale_interpretations,
                          recover_interpretations)

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
            
            await run_in_threadpool(recover_stale_image_downloads)
        
        except Exception:
            
            logger.exception("Falha na recuperação das reservas de imagem")
            
        
        try:
                    
            await run_in_threadpool(recover_stale_audio_downloads)
                
        except Exception:
                    
            logger.exception("Falha na recuperação das reservas de audio")
            
            
        try:

            await run_in_threadpool(recover_stale_transcriptions)
            
        except Exception:
            
            logger.exception("Falha na recuperação das reservas de transcrição")
            
        
        try:
            
            await run_in_threadpool(recover_stale_interpretations)
            
        except Exception:
            
            logger.exception("Falha na recuperação das reservas de interpretação")
            

        try:

            await run_in_threadpool(recover_image_downloads)

        except Exception:

            logger.exception("Falhas na recuperação dos downloads das imagens")


        try:

            await run_in_threadpool(recover_audio_downloads)

        except Exception:

            logger.exception("Falhas na recuperação dos downloads dos áudios")

        
        try:
                    
            await run_in_threadpool(recover_transcriptions)
                
        except Exception:
                    
            logger.exception("Falha na recuperação da transcricão do áudio")
            
        
        try:
            
            await run_in_threadpool(recover_interpretations)
        
        except Exception:
            
            logger.exception("Falha na recuperação da interpretação")
        
        
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

