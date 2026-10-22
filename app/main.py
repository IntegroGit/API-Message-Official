"""Ponto de entrada do FastAPI e definição das rotas.

Estrutura inicial; implementação pendente.
"""
import asyncio
from fastapi import FastAPI
from app.webhook import router
from contextlib import asynccontextmanager, suppress
from app.worker import session_closure_loop

@asynccontextmanager
async def lifespan(app):

    task = asyncio.create_task(session_closure_loop())

    try:
        yield
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task

app = FastAPI(lifespan=lifespan)
app.include_router(router)

@app.get("/status")
async def root():
    return {"status":"OK"}

