import asyncio

from aurora import storage
from tests.api_client import api_client
from tests.fakes import ScriptedLlm, call, say


def _salon(apartment, day):
    return [
        r for r in storage.list_reservations(apartment)
        if r["area"] == "salao-de-festas" and r["data"] == day
    ]


async def _session(client, apartment="101"):
    return (await client.post("/sessoes", json={"apartamento": apartment})).json()["session_id"]


async def _request(client, model, session_id, tool="reservar_area", transfer=True, **args):
    agent = "reservas" if tool == "reservar_area" else "visitantes"
    if transfer:
        model.script(call("transfer_to_agent", agent_name=agent))
    model.script(call(tool, **args))
    response = await client.post(f"/sessoes/{session_id}/mensagens", json={"texto": "pedido"})
    assert response.status_code == 200
    [pending] = response.json()["confirmacoes_pendentes"]
    return pending["id"]


async def _answer(client, session_id, confirmation_id, confirmed):
    return await client.post(
        f"/sessoes/{session_id}/confirmacoes",
        json={"id": confirmation_id, "confirmado": confirmed},
    )


async def test_reject_then_approve_then_resend():
    model = ScriptedLlm()
    async with api_client(model) as client:
        session_id = await _session(client)
        first = await _request(client, model, session_id, area="salao-de-festas", data="2030-04-20")
        model.script(say("Tudo bem, não reservei."))
        response = await _answer(client, session_id, first, False)
        assert response.status_code == 200
        assert response.json()["confirmacoes_pendentes"] == []
        assert _salon("101", "2030-04-20") == []

        second = await _request(
            client, model, session_id, transfer=False, area="salao-de-festas", data="2030-04-20"
        )
        assert second != first
        model.script(say("Reserva feita."))
        response = await _answer(client, session_id, second, True)
        assert response.status_code == 200
        assert response.json() == {"resposta": "Reserva feita.", "confirmacoes_pendentes": []}
        assert len(_salon("101", "2030-04-20")) == 1

        response = await _answer(client, session_id, second, True)
        assert response.status_code == 409
        assert response.json()["detail"]
        assert len(_salon("101", "2030-04-20")) == 1


async def test_unknown_id_is_409():
    async with api_client(ScriptedLlm()) as client:
        session_id = await _session(client)
        before = storage.list_reservations("101")
        response = await _answer(client, session_id, "id-inexistente", True)
        assert response.status_code == 409
        assert storage.list_reservations("101") == before
        response = await _answer(client, "sessao-inexistente", "id-inexistente", True)
        assert response.status_code == 404


async def test_id_from_another_session_is_409():
    model = ScriptedLlm()
    async with api_client(model) as client:
        session_a = await _session(client)
        session_b = await _session(client)
        confirmation_id = await _request(
            client, model, session_a, area="salao-de-festas", data="2030-04-27"
        )
        response = await _answer(client, session_b, confirmation_id, True)
        assert response.status_code == 409
        assert _salon("101", "2030-04-27") == []


async def test_approval_after_restart():
    model = ScriptedLlm()
    async with api_client(model) as client:
        session_id = await _session(client)
        confirmation_id = await _request(
            client, model, session_id, area="churrasqueira", data="2030-06-01"
        )
    async with api_client(model) as client:
        response = await _answer(client, session_id, confirmation_id, True)
        assert response.status_code == 200
    reservations = [r for r in storage.list_reservations("101") if r["area"] == "churrasqueira"]
    assert [r["data"] for r in reservations] == ["2030-06-01"]


async def test_concurrent_approvals_only_one_wins():
    model = ScriptedLlm()
    async with api_client(model) as client:
        session_101 = await _session(client, "101")
        session_201 = await _session(client, "201")
        id_101 = await _request(client, model, session_101, area="salao-de-festas", data="2030-05-11")
        id_201 = await _request(client, model, session_201, area="salao-de-festas", data="2030-05-11")
        responses = await asyncio.gather(
            _answer(client, session_101, id_101, True),
            _answer(client, session_201, id_201, True),
        )
        assert [r.status_code for r in responses] == [200, 200]
        assert len(_salon("101", "2030-05-11")) + len(_salon("201", "2030-05-11")) == 1


async def test_visitor_written_only_after_approval():
    model = ScriptedLlm()
    async with api_client(model) as client:
        session_id = await _session(client)
        confirmation_id = await _request(
            client, model, session_id, tool="autorizar_visitante", nome="Joana Ribeiro", data="2030-04-21"
        )
        assert storage.list_visitors("101") == []
        response = await _answer(client, session_id, confirmation_id, True)
        assert response.status_code == 200
        assert storage.list_visitors("101") == [{"nome": "Joana Ribeiro", "data": "2030-04-21"}]
