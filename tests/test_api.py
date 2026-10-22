from google.genai import errors as genai_errors

from tests.api_client import api_client
from tests.fakes import ScriptedLlm, call, say


async def _session(client, apartment="101"):
    response = await client.post("/sessoes", json={"apartamento": apartment})
    assert response.status_code == 201
    return response.json()["session_id"]


async def test_create_session():
    async with api_client(ScriptedLlm()) as client:
        session_id = await _session(client)
        assert isinstance(session_id, str) and session_id
        response = await client.post("/sessoes", json={"apartamento": "999"})
        assert response.status_code == 422


async def test_message_returns_contract_shape():
    model = ScriptedLlm()
    model.script(say("Olá! Como posso ajudar?"))
    async with api_client(model) as client:
        session_id = await _session(client)
        response = await client.post(f"/sessoes/{session_id}/mensagens", json={"texto": "Oi"})
        assert response.status_code == 200
        assert response.json() == {"resposta": "Olá! Como posso ajudar?", "confirmacoes_pendentes": []}


async def test_fee_reservation_lists_pending_confirmation():
    model = ScriptedLlm()
    model.script(
        call("transfer_to_agent", agent_name="reservas"),
        call("reservar_area", area="salao-de-festas", data="2030-04-20"),
    )
    async with api_client(model) as client:
        session_id = await _session(client)
        response = await client.post(
            f"/sessoes/{session_id}/mensagens",
            json={"texto": "Reserve o salão de festas para 2030-04-20"},
        )
        assert response.status_code == 200
        [pending] = response.json()["confirmacoes_pendentes"]
        assert pending["acao"] == "reservar_area"
        assert pending["detalhes"]["area"] == "salao-de-festas"
        assert pending["detalhes"]["data"] == "2030-04-20"
        assert pending["id"]


async def test_unknown_session_is_404():
    async with api_client(ScriptedLlm()) as client:
        assert (await client.get("/sessoes/sessao-inexistente/eventos")).status_code == 404
        response = await client.post("/sessoes/sessao-inexistente/mensagens", json={"texto": "oi"})
        assert response.status_code == 404


async def test_session_survives_restart():
    model = ScriptedLlm()
    model.script(say("Primeira resposta."))
    async with api_client(model) as client:
        session_id = await _session(client)
        await client.post(f"/sessoes/{session_id}/mensagens", json={"texto": "Oi"})
        before = (await client.get(f"/sessoes/{session_id}/eventos")).json()
    assert len(before) >= 2

    model.script(say("Segunda resposta."))
    async with api_client(model) as client:
        after_restart = (await client.get(f"/sessoes/{session_id}/eventos")).json()
        assert after_restart == before
        response = await client.post(f"/sessoes/{session_id}/mensagens", json={"texto": "De novo"})
        assert response.status_code == 200
        assert response.json()["resposta"] == "Segunda resposta."
        later = (await client.get(f"/sessoes/{session_id}/eventos")).json()
        assert len(later) > len(before)


async def test_provider_error_is_503():
    model = ScriptedLlm()
    model.script(genai_errors.ServerError(503, {"error": {"message": "overloaded"}}))
    async with api_client(model) as client:
        session_id = await _session(client)
        response = await client.post(f"/sessoes/{session_id}/mensagens", json={"texto": "Oi"})
        assert response.status_code == 503
        assert response.json()["detail"]
