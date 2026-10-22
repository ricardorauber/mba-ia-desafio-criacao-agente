"""HTTP API of the Residencial Aurora assistant."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from google.adk.models.base_llm import BaseLlm
from google.adk.runners import Runner
from google.adk.sessions.sqlite_session_service import SqliteSessionService
from pydantic import BaseModel

from aurora import config, storage
from aurora.agents import build_app
from aurora.conversation import (
    ConfirmationNotPending,
    Conversation,
    ModelUnavailable,
    SessionNotFound,
)


class NovaSessao(BaseModel):
    apartamento: str


class NovaMensagem(BaseModel):
    texto: str


class RespostaConfirmacao(BaseModel):
    id: str
    confirmado: bool


class Pendencia(BaseModel):
    id: str
    acao: str
    detalhes: dict


class RespostaTurno(BaseModel):
    resposta: str
    confirmacoes_pendentes: list[Pendencia]


def create_app(model: BaseLlm | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        session_service = SqliteSessionService(db_path=str(config.sessions_db_path()))
        runner = Runner(app=build_app(model), session_service=session_service)
        app.state.conversation = Conversation(runner, session_service)
        try:
            yield
        finally:
            await runner.close()

    app = FastAPI(title="Assistente do Residencial Aurora", lifespan=lifespan)

    @app.exception_handler(SessionNotFound)
    async def session_not_found(request: Request, exc: SessionNotFound):
        return JSONResponse(status_code=404, content={"detail": "Sessão não encontrada."})

    @app.exception_handler(ModelUnavailable)
    async def model_unavailable(request: Request, exc: ModelUnavailable):
        return JSONResponse(
            status_code=503,
            content={"detail": "O assistente está indisponível no momento. Tente novamente."},
        )

    @app.exception_handler(ConfirmationNotPending)
    async def confirmation_not_pending(request: Request, exc: ConfirmationNotPending):
        return JSONResponse(
            status_code=409,
            content={"detail": "Não existe confirmação pendente com esse id nesta sessão."},
        )

    def conversation(request: Request) -> Conversation:
        return request.app.state.conversation

    @app.post("/sessoes", status_code=201)
    async def criar_sessao(body: NovaSessao, request: Request) -> dict:
        if not await asyncio.to_thread(storage.apartment_exists, body.apartamento):
            raise HTTPException(status_code=422, detail="Apartamento inexistente.")
        session_id = await conversation(request).create_session(body.apartamento)
        return {"session_id": session_id}

    @app.post("/sessoes/{session_id}/mensagens", response_model=RespostaTurno)
    async def enviar_mensagem(session_id: str, body: NovaMensagem, request: Request) -> dict:
        return await conversation(request).send_text(session_id, body.texto)

    @app.post("/sessoes/{session_id}/confirmacoes", response_model=RespostaTurno)
    async def responder_confirmacao(
        session_id: str, body: RespostaConfirmacao, request: Request
    ) -> dict:
        return await conversation(request).answer_confirmation(
            session_id, body.id, body.confirmado
        )

    @app.get("/sessoes/{session_id}/eventos")
    async def listar_eventos(session_id: str, request: Request) -> list[dict]:
        return await conversation(request).events(session_id)

    return app
