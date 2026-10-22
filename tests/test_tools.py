import inspect
import json

import pytest
from google.adk.agents import LlmAgent
from google.adk.apps import App, ResumabilityConfig
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService

from aurora import storage, tools
from tests.fakes import (
    ScriptedLlm,
    call,
    confirmation_answer,
    function_responses,
    open_confirmations,
    user_text,
)


class Harness:
    def __init__(self, apartment: str = "101"):
        self.model = ScriptedLlm()
        agent = LlmAgent(
            name="assistente",
            model=self.model,
            instruction="teste",
            tools=tools.RESERVATION_TOOLS + tools.VISITOR_TOOLS,
        )
        app = App(
            name="aurora",
            root_agent=agent,
            resumability_config=ResumabilityConfig(is_resumable=True),
        )
        self.service = InMemorySessionService()
        self.runner = Runner(app=app, session_service=self.service)
        self.apartment = apartment
        self.session_id = None

    async def start(self):
        session = await self.service.create_session(
            app_name="aurora", user_id=self.apartment, state={"apartamento": self.apartment}
        )
        self.session_id = session.id

    async def send(self, content):
        async for _ in self.runner.run_async(
            user_id=self.apartment, session_id=self.session_id, new_message=content
        ):
            pass
        return await self.session()

    async def session(self):
        return await self.service.get_session(
            app_name="aurora", user_id=self.apartment, session_id=self.session_id
        )

    async def use(self, tool_name, **args):
        self.model.script(call(tool_name, **args))
        session = await self.send(user_text("pedido"))
        return function_responses(session, tool_name)[-1], session


@pytest.fixture
async def harness():
    h = Harness("101")
    await h.start()
    return h


def test_tools_have_no_apartment_parameter():
    allowed = {"area", "data", "nome", "tool_context"}
    for tool in tools.RESERVATION_TOOLS + tools.VISITOR_TOOLS:
        assert set(inspect.signature(tool).parameters) <= allowed, tool.__name__


def test_area_aliases():
    areas = storage.list_areas()
    for alias in ("Salão de Festas", "salao de festas", "salao-de-festas", "salão"):
        assert tools._resolve_area(alias, areas)["id"] == "salao-de-festas"
    assert tools._resolve_area("piscina", areas) is None


async def test_unknown_area_lists_valid_ones(harness):
    result, _ = await harness.use("verificar_disponibilidade", area="piscina", data="2030-04-01")
    assert result["status"] == "erro"
    for area_id in ("salao-de-festas", "churrasqueira", "quadra"):
        assert area_id in result["mensagem"]
    result, _ = await harness.use("verificar_disponibilidade", area="quadra", data="20/04/2030")
    assert result["status"] == "erro"


async def test_lists_only_own_data(harness):
    result, _ = await harness.use("listar_minhas_reservas")
    assert [r["codigo"] for r in result["reservas"]] == ["RSV-1377"]
    result, _ = await harness.use("listar_meus_visitantes")
    assert result == {"visitantes": []}
    result, _ = await harness.use("listar_areas")
    assert {a["id"]: a["gera_cobranca"] for a in result["areas"]} == {
        "salao-de-festas": True,
        "churrasqueira": True,
        "quadra": False,
    }


async def test_availability_does_not_leak_holder(harness):
    result, session = await harness.use(
        "verificar_disponibilidade", area="Salão de festas", data="2030-03-16"
    )
    assert result == {"area": "salao-de-festas", "data": "2030-03-16", "disponivel": False}


async def test_free_area_books_without_confirmation(harness):
    result, session = await harness.use("reservar_area", area="quadra", data="2030-04-06")
    assert result["status"] == "reservada"
    assert open_confirmations(session) == {}
    assert {"codigo": result["codigo"], "area": "quadra", "data": "2030-04-06"} in (
        storage.list_reservations("101")
    )


@pytest.mark.parametrize("approve", [False, True])
async def test_fee_area_waits_for_confirmation(harness, approve):
    result, session = await harness.use(
        "reservar_area", area="salao de festas", data="2030-04-20"
    )
    assert result["status"] == "aguardando_confirmacao"
    [(confirmation_id, args)] = open_confirmations(session).items()
    payload = args["toolConfirmation"]["payload"]
    assert payload["area"] == "salao-de-festas" and payload["data"] == "2030-04-20"
    assert storage.is_available("salao-de-festas", "2030-04-20")

    session = await harness.send(confirmation_answer(confirmation_id, approve))
    final = function_responses(session, "reservar_area")[-1]
    salons = [r for r in storage.list_reservations("101") if r["area"] == "salao-de-festas"]
    if approve:
        assert final["status"] == "reservada"
        assert len(salons) == 1
    else:
        assert final["status"] == "nao_confirmada"
        assert salons == []


async def test_taken_date_is_refused_without_confirmation(harness):
    result, session = await harness.use(
        "reservar_area", area="salao-de-festas", data="2030-03-16"
    )
    assert result["status"] == "indisponivel"
    assert open_confirmations(session) == {}
    assert "302" not in json.dumps(result) and "RSV-4821" not in json.dumps(result)
    assert "RSV-4821" not in json.dumps([e.model_dump(mode="json") for e in session.events])


async def test_cancel_only_own(harness):
    result, session = await harness.use(
        "cancelar_reserva", area="salao-de-festas", data="2030-03-16"
    )
    assert result["status"] == "nao_encontrada"
    assert storage.list_reservations("302")[0]["codigo"] == "RSV-4821"
    assert "RSV-4821" not in json.dumps([e.model_dump(mode="json") for e in session.events])
    result, session = await harness.use("cancelar_reserva", area="quadra", data="2030-03-09")
    assert result["status"] == "cancelada"
    assert open_confirmations(session) == {}
    assert storage.list_reservations("101") == []


@pytest.mark.parametrize("approve", [False, True])
async def test_visitor_always_needs_confirmation(harness, approve):
    result, session = await harness.use(
        "autorizar_visitante", nome="  Joana Ribeiro ", data="2030-04-21"
    )
    assert result["status"] == "aguardando_confirmacao"
    [(confirmation_id, args)] = open_confirmations(session).items()
    assert args["toolConfirmation"]["payload"] == {"nome": "Joana Ribeiro", "data": "2030-04-21"}
    assert storage.list_visitors("101") == []
    await harness.send(confirmation_answer(confirmation_id, approve))
    expected = [{"nome": "Joana Ribeiro", "data": "2030-04-21"}] if approve else []
    assert storage.list_visitors("101") == expected


async def test_visitor_name_validation(harness):
    result, _ = await harness.use("autorizar_visitante", nome="  ", data="2030-04-21")
    assert result["status"] == "erro"
    result, _ = await harness.use("autorizar_visitante", nome="x" * 81, data="2030-04-21")
    assert result["status"] == "erro"
