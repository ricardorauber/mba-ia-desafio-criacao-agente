"""ADK tools for reservations and visitors.

The apartment is never a tool argument: every tool reads it from the ADK
session's user id, which the server sets once when the session is created.
Actions that charge a fee or release building access ask the system for a
confirmation and only write after an approved one.
"""

from __future__ import annotations

import asyncio
import re
import unicodedata
from datetime import date

from google.adk.tools import ToolContext

from aurora import storage

MAX_VISITOR_NAME = 80


def _apartment(tool_context: ToolContext) -> str:
    return tool_context.user_id


def _normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    ascii_text = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")


def _resolve_area(area: str, areas: list[dict]) -> dict | None:
    key = _normalize(area or "")
    if not key:
        return None
    for item in areas:
        if key in (_normalize(item["id"]), _normalize(item["nome"])):
            return item
    partial = [
        item
        for item in areas
        if key in _normalize(item["id"]) or key in _normalize(item["nome"])
    ]
    return partial[0] if len(partial) == 1 else None


def _parse_date(data: str) -> str | None:
    try:
        parsed = date.fromisoformat((data or "").strip())
    except ValueError:
        return None
    text = parsed.isoformat()
    return text if text == (data or "").strip() else None


def _area_error(areas: list[dict]) -> dict:
    valid = ", ".join(f"{item['id']} ({item['nome']})" for item in areas)
    return {"status": "erro", "mensagem": f"Área desconhecida. Áreas válidas: {valid}."}


def _date_error() -> dict:
    return {"status": "erro", "mensagem": "Data inválida. Use o formato AAAA-MM-DD."}


async def _validate(area: str, data: str) -> tuple[dict | None, str | None, dict | None]:
    areas = await asyncio.to_thread(storage.list_areas)
    found = _resolve_area(area, areas)
    if found is None:
        return None, None, _area_error(areas)
    day = _parse_date(data)
    if day is None:
        return None, None, _date_error()
    return found, day, None


async def listar_areas() -> dict:
    """Lista as áreas comuns que podem ser reservadas, com a taxa de cada uma.

    Taxa zero significa que a reserva não gera cobrança.
    """
    areas = await asyncio.to_thread(storage.list_areas)
    return {
        "areas": [
            {
                "id": item["id"],
                "nome": item["nome"],
                "taxa": item["taxa"],
                "gera_cobranca": item["taxa"] > 0,
            }
            for item in areas
        ]
    }


async def listar_minhas_reservas(tool_context: ToolContext) -> dict:
    """Lista as reservas ativas do apartamento do morador desta conversa."""
    apartment = _apartment(tool_context)
    reservations, areas = await asyncio.gather(
        asyncio.to_thread(storage.list_reservations, apartment),
        asyncio.to_thread(storage.list_areas),
    )
    names = {item["id"]: item["nome"] for item in areas}
    return {
        "reservas": [
            {
                "codigo": item["codigo"],
                "area": item["area"],
                "nome_area": names.get(item["area"], item["area"]),
                "data": item["data"],
            }
            for item in reservations
        ]
    }


async def verificar_disponibilidade(area: str, data: str) -> dict:
    """Informa se uma área comum está livre em uma data (AAAA-MM-DD).

    Args:
        area: id ou nome da área (ex.: "salao-de-festas", "Churrasqueira").
        data: data no formato AAAA-MM-DD.
    """
    found, day, error = await _validate(area, data)
    if error:
        return error
    available = await asyncio.to_thread(storage.is_available, found["id"], day)
    return {"area": found["id"], "data": day, "disponivel": available}


async def reservar_area(area: str, data: str, tool_context: ToolContext) -> dict:
    """Reserva uma área comum para o apartamento do morador desta conversa.

    Áreas com taxa só são reservadas depois que o morador aprova a cobrança
    pelo aplicativo; a ferramenta cuida desse pedido de confirmação sozinha.

    Args:
        area: id ou nome da área (ex.: "salao-de-festas", "Quadra").
        data: data no formato AAAA-MM-DD.
    """
    found, day, error = await _validate(area, data)
    if error:
        return error
    apartment = _apartment(tool_context)
    taken = {
        "status": "indisponivel",
        "mensagem": f"{found['nome']} já está reservada em {day}. Escolha outra data.",
    }
    confirmation = tool_context.tool_confirmation
    if found["taxa"] > 0 and confirmation is None:
        if not await asyncio.to_thread(storage.is_available, found["id"], day):
            return taken
        tool_context.request_confirmation(
            hint=(
                f"Confirmar a reserva de {found['nome']} em {day}? "
                f"Será cobrada a taxa de R$ {found['taxa']:.2f}."
            ),
            payload={
                "area": found["id"],
                "nome_area": found["nome"],
                "data": day,
                "taxa": found["taxa"],
            },
        )
        return {
            "status": "aguardando_confirmacao",
            "mensagem": "A reserva gera cobrança e aguarda a aprovação do morador no aplicativo.",
        }
    if confirmation is not None and not confirmation.confirmed:
        return {"status": "nao_confirmada", "mensagem": "Reserva não confirmada; nada foi feito."}
    code = await asyncio.to_thread(storage.create_reservation, apartment, found["id"], day)
    if code is None:
        return taken
    return {
        "status": "reservada",
        "codigo": code,
        "area": found["id"],
        "nome_area": found["nome"],
        "data": day,
        "taxa": found["taxa"],
    }


async def cancelar_reserva(area: str, data: str, tool_context: ToolContext) -> dict:
    """Cancela uma reserva do próprio apartamento do morador desta conversa.

    Args:
        area: id ou nome da área reservada.
        data: data da reserva no formato AAAA-MM-DD.
    """
    found, day, error = await _validate(area, data)
    if error:
        return error
    code = await asyncio.to_thread(
        storage.cancel_reservation, _apartment(tool_context), found["id"], day
    )
    if code is None:
        return {
            "status": "nao_encontrada",
            "mensagem": f"Não há reserva do seu apartamento para {found['nome']} em {day}.",
        }
    return {"status": "cancelada", "codigo": code, "area": found["id"], "data": day}


async def listar_meus_visitantes(tool_context: ToolContext) -> dict:
    """Lista os visitantes autorizados do apartamento do morador desta conversa."""
    visitors = await asyncio.to_thread(storage.list_visitors, _apartment(tool_context))
    return {"visitantes": visitors}


async def autorizar_visitante(nome: str, data: str, tool_context: ToolContext) -> dict:
    """Autoriza a entrada de um visitante no prédio em uma data.

    A autorização só é gravada depois que o morador aprova pelo aplicativo;
    a ferramenta cuida desse pedido de confirmação sozinha.

    Args:
        nome: nome completo do visitante.
        data: data da visita no formato AAAA-MM-DD.
    """
    name = (nome or "").strip()
    if not name or len(name) > MAX_VISITOR_NAME:
        return {
            "status": "erro",
            "mensagem": f"Informe o nome do visitante (até {MAX_VISITOR_NAME} caracteres).",
        }
    day = _parse_date(data)
    if day is None:
        return _date_error()
    confirmation = tool_context.tool_confirmation
    if confirmation is None:
        tool_context.request_confirmation(
            hint=f"Liberar a entrada de {name} em {day}?",
            payload={"nome": name, "data": day},
        )
        return {
            "status": "aguardando_confirmacao",
            "mensagem": "A liberação aguarda a aprovação do morador no aplicativo.",
        }
    if not confirmation.confirmed:
        return {"status": "nao_confirmada", "mensagem": "Entrada não liberada; nada foi feito."}
    await asyncio.to_thread(storage.add_visitor, _apartment(tool_context), name, day)
    return {"status": "autorizado", "nome": name, "data": day}


RESERVATION_TOOLS = [
    listar_areas,
    listar_minhas_reservas,
    verificar_disponibilidade,
    reservar_area,
    cancelar_reserva,
]
VISITOR_TOOLS = [listar_meus_visitantes, autorizar_visitante]
