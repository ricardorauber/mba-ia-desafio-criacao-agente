"""Runs conversation turns over persisted ADK sessions."""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from typing import Iterable

from google.adk.events import Event
from google.adk.runners import Runner
from google.adk.sessions import BaseSessionService, Session
from google.genai import errors as genai_errors
from google.genai import types

from aurora import storage
from aurora.agents import APP_NAME

CONFIRMATION_CALL = "adk_request_confirmation"
TURN_FAILED = (
    "Desculpe, não consegui concluir o seu pedido agora. Pode repetir, por favor?"
)
ANSWER_REGISTERED = (
    "Sua resposta foi registrada, mas não consegui concluir o atendimento agora. "
    "Confira o resultado nas suas reservas ou visitantes."
)

logger = logging.getLogger(__name__)


class SessionNotFound(Exception):
    """The session id does not exist."""


class ModelUnavailable(Exception):
    """The model provider failed even after retries."""


class ConfirmationNotPending(Exception):
    """The confirmation id is not pending in this session."""


def pending_confirmations(session: Session) -> list[dict]:
    """Confirmation requests of the session that no user answer has closed yet."""
    requested: dict[str, dict] = {}
    answered: set[str] = set()
    for event in session.events:
        system_calls = set(event.long_running_tool_ids or ())
        for call in event.get_function_calls():
            if (
                call.name == CONFIRMATION_CALL
                and call.id in system_calls
                and event.author != "user"
            ):
                requested[call.id] = call.args or {}
        if event.author == "user":
            for response in event.get_function_responses():
                if response.name == CONFIRMATION_CALL and response.id:
                    answered.add(response.id)
    pending = []
    for call_id, args in requested.items():
        if call_id in answered:
            continue
        original = args.get("originalFunctionCall") or {}
        confirmation = args.get("toolConfirmation") or {}
        pending.append(
            {
                "id": call_id,
                "acao": original.get("name", ""),
                "detalhes": confirmation.get("payload") or {},
            }
        )
    return pending


def _describe_outcome(result: dict) -> str | None:
    status = result.get("status")
    if status == "reservada":
        return (
            f"Reserva confirmada: {result.get('nome_area', result.get('area'))} em "
            f"{result.get('data')} (código {result.get('codigo')})."
        )
    if status == "autorizado":
        return f"Entrada de {result.get('nome')} liberada para {result.get('data')}."
    if status in ("indisponivel", "nao_confirmada", "erro"):
        return result.get("mensagem")
    return None


def confirmation_outcome(session: Session, confirmation_id: str) -> str:
    """Describes what the confirmed tool recorded after the resident's answer."""
    original_id = None
    answered = False
    outcome = None
    for event in session.events:
        for call in event.get_function_calls():
            if call.id == confirmation_id:
                original_id = ((call.args or {}).get("originalFunctionCall") or {}).get("id")
        for response in event.get_function_responses():
            if event.author == "user" and response.id == confirmation_id:
                answered = True
            elif answered and original_id and response.id == original_id:
                outcome = _describe_outcome(response.response or {})
    return outcome or ANSWER_REGISTERED


def reply_text(events: Iterable[Event]) -> str:
    """Joins the visible text the agents produced in a turn."""
    texts = []
    for event in events:
        if event.author == "user" or event.partial or not event.content:
            continue
        for part in event.content.parts or []:
            if part.text and not part.thought:
                texts.append(part.text.strip())
    return "\n\n".join(text for text in texts if text)


class Conversation:
    def __init__(self, runner: Runner, session_service: BaseSessionService):
        self.runner = runner
        self.sessions = session_service
        self._locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    async def create_session(self, apartamento: str) -> str:
        session = await self.sessions.create_session(
            app_name=APP_NAME,
            user_id=apartamento,
            state={"apartamento": apartamento},
        )
        await asyncio.to_thread(storage.save_session, session.id, apartamento)
        return session.id

    async def get_session(self, session_id: str) -> Session:
        apartamento = await asyncio.to_thread(storage.session_apartment, session_id)
        session = None
        if apartamento is not None:
            session = await self.sessions.get_session(
                app_name=APP_NAME, user_id=apartamento, session_id=session_id
            )
        if session is None:
            raise SessionNotFound(session_id)
        return session

    async def events(self, session_id: str) -> list[dict]:
        session = await self.get_session(session_id)
        return [event.model_dump(mode="json", exclude_none=True) for event in session.events]

    async def send_text(self, session_id: str, texto: str) -> dict:
        message = types.Content(role="user", parts=[types.Part(text=texto)])
        async with self._locks[session_id]:
            session = await self.get_session(session_id)
            return await self._run_turn(session, message)

    async def answer_confirmation(
        self, session_id: str, confirmation_id: str, confirmado: bool
    ) -> dict:
        """Delivers the resident's answer to the agent that asked for it."""
        message = types.Content(
            role="user",
            parts=[
                types.Part(
                    function_response=types.FunctionResponse(
                        id=confirmation_id,
                        name=CONFIRMATION_CALL,
                        response={"confirmed": confirmado},
                    )
                )
            ],
        )
        async with self._locks[session_id]:
            session = await self.get_session(session_id)
            pending_ids = {item["id"] for item in pending_confirmations(session)}
            if confirmation_id not in pending_ids:
                raise ConfirmationNotPending(confirmation_id)
            return await self._run_turn(session, message, confirmation_id)

    async def _run_turn(
        self,
        session: Session,
        message: types.Content,
        confirmation_id: str | None = None,
    ) -> dict:
        produced: list[Event] = []
        try:
            async for event in self.runner.run_async(
                user_id=session.user_id, session_id=session.id, new_message=message
            ):
                produced.append(event)
            text = None
        except Exception as error:
            if confirmation_id is None and isinstance(error, genai_errors.APIError):
                raise ModelUnavailable(str(error)) from error
            logger.exception("turn failed in session %s", session.id)
            text = TURN_FAILED
        updated = await self.get_session(session.id)
        if text is not None and confirmation_id is not None:
            text = confirmation_outcome(updated, confirmation_id)
        return {
            "resposta": reply_text(produced) if text is None else text,
            "confirmacoes_pendentes": pending_confirmations(updated),
        }
