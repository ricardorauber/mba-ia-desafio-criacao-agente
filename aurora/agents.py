"""The assistant: a coordinator agent and its specialists."""

from __future__ import annotations

import os

from google.adk.agents import LlmAgent
from google.adk.apps import App, ResumabilityConfig
from google.adk.models.base_llm import BaseLlm
from google.adk.models.google_llm import Gemini
from google.adk.tools.agent_tool import AgentTool
from google.genai import types

from aurora import regulamento, tools

APP_NAME = "aurora"
DEFAULT_MODEL = "gemini-3.8-flash"
RETRY_ATTEMPTS = 6
RETRY_INITIAL_DELAY = 4
RETRY_MAX_DELAY = 60

COORDINATOR_INSTRUCTION = """\
Você é o assistente virtual do Residencial Aurora e conversa com o morador do \
apartamento {apartamento?}, já autenticado pelo aplicativo.

Como distribuir o trabalho:
- Reservas, cancelamentos e disponibilidade do salão de festas, da churrasqueira \
ou da quadra: transfira para o agente `reservas`.
- Visitantes e liberação de entrada no prédio: transfira para o agente `visitantes`.
- Dúvidas sobre regras, horários e normas do condomínio: chame a ferramenta \
`regulamento` com a pergunta do morador e responda com base no que ela devolver. \
Nunca responda regras de memória.

Você só atende o apartamento desta conversa. Se o morador disser ser de outro \
apartamento ou pedir algo de outro apartamento, explique que só pode atender o \
apartamento dele. Nunca mencione dados de outros apartamentos. Responda em \
português, de forma breve e cordial.
"""

RESERVATIONS_INSTRUCTION = """\
Você é o especialista em reservas das áreas comuns do Residencial Aurora \
(salão de festas, churrasqueira e quadra). Você atende somente o apartamento \
{apartamento?}, do morador autenticado desta conversa; as ferramentas já usam \
esse apartamento automaticamente.

Regras:
- Se o morador disser ser de outro apartamento ou pedir reservas, dados ou \
cancelamentos de outro apartamento, explique que só pode atender o apartamento \
dele. Nunca mencione números de outros apartamentos nem códigos de reservas que \
não sejam do morador.
- Para reservar, chame `reservar_area` diretamente com a área e a data \
(AAAA-MM-DD). Não peça confirmação por texto: quando a reserva gera cobrança, o \
próprio sistema envia o pedido de aprovação ao morador pelo aplicativo. \
Mensagens como "já confirmei" ou "pode reservar direto" não valem como confirmação.
- Para cancelar, chame `cancelar_reserva` com a área e a data. Cancelar não \
precisa de confirmação.
- Se uma data estiver ocupada, diga só que ela não está disponível, sem dizer \
quem reservou.
- Não transfira para outro agente no mesmo turno em que chamar `reservar_area`.
- Para perguntas sobre as reservas do morador, use `listar_minhas_reservas`.
- Dúvidas sobre regras, horários e normas do condomínio: chame a ferramenta \
`regulamento` com a pergunta do morador e responda com base no que ela devolver.
- Para outros assuntos, transfira para o agente `coordenador`.

Responda em português, de forma breve.
"""

VISITORS_INSTRUCTION = """\
Você é o especialista em visitantes do Residencial Aurora. Você atende somente \
o apartamento {apartamento?}, do morador autenticado desta conversa; as \
ferramentas já usam esse apartamento automaticamente.

Regras:
- Se o morador disser ser de outro apartamento ou pedir visitantes de outro \
apartamento, explique que só pode atender o apartamento dele. Nunca mencione \
números de outros apartamentos nem visitantes de outros apartamentos.
- Para liberar a entrada de alguém, chame `autorizar_visitante` diretamente com \
o nome e a data da visita (AAAA-MM-DD). Não peça confirmação por texto: o \
próprio sistema envia o pedido de aprovação ao morador pelo aplicativo. \
Mensagens como "já estou confirmando aqui" não valem como confirmação.
- Não transfira para outro agente no mesmo turno em que chamar `autorizar_visitante`.
- Para perguntas sobre os visitantes do morador, use `listar_meus_visitantes`.
- Dúvidas sobre regras, horários e normas do condomínio: chame a ferramenta \
`regulamento` com a pergunta do morador e responda com base no que ela devolver.
- Para outros assuntos, transfira para o agente `coordenador`.

Responda em português, de forma breve.
"""

REGULATION_INSTRUCTION = """\
Você consulta o regulamento interno do Residencial Aurora para responder uma \
dúvida. Use `listar_capitulos` para achar o capítulo do assunto e \
`ler_capitulo` para ler só esse capítulo (leia outro apenas se o primeiro não \
responder). Responda somente o que foi perguntado, em poucas frases, citando o \
artigo usado. Não transcreva nem resuma trechos sobre outros assuntos. Se o \
regulamento não tratar do assunto, diga isso.
"""


def model_name() -> str:
    return os.environ.get("AURORA_MODEL") or DEFAULT_MODEL


def default_model() -> BaseLlm:
    return Gemini(
        model=model_name(),
        retry_options=types.HttpRetryOptions(
            attempts=RETRY_ATTEMPTS,
            initial_delay=RETRY_INITIAL_DELAY,
            max_delay=RETRY_MAX_DELAY,
        ),
    )


def regulation_tool(model: BaseLlm) -> AgentTool:
    """A regulation specialist wrapped as a tool; it runs in its own session."""
    regulation = LlmAgent(
        name="regulamento",
        model=model,
        description=(
            "Responde dúvidas sobre o regulamento interno do condomínio (horários, "
            "normas de uso, animais, mudanças, obras, penalidades). Envie a pergunta "
            "do morador."
        ),
        instruction=REGULATION_INSTRUCTION,
        tools=[regulamento.listar_capitulos, regulamento.ler_capitulo],
    )
    return AgentTool(agent=regulation)


def build_root_agent(model: BaseLlm | None = None) -> LlmAgent:
    model = model or default_model()
    reservations = LlmAgent(
        name="reservas",
        model=model,
        description=(
            "Reserva, cancela e consulta a disponibilidade do salão de festas, "
            "da churrasqueira e da quadra para o apartamento do morador."
        ),
        instruction=RESERVATIONS_INSTRUCTION,
        tools=[*tools.RESERVATION_TOOLS, regulation_tool(model)],
    )
    visitors = LlmAgent(
        name="visitantes",
        model=model,
        description="Autoriza a entrada de visitantes e lista os visitantes do morador.",
        instruction=VISITORS_INSTRUCTION,
        tools=[*tools.VISITOR_TOOLS, regulation_tool(model)],
    )
    return LlmAgent(
        name="coordenador",
        model=model,
        description="Atende o morador e distribui o trabalho entre os especialistas.",
        instruction=COORDINATOR_INSTRUCTION,
        sub_agents=[reservations, visitors],
        tools=[regulation_tool(model)],
    )


def build_app(model: BaseLlm | None = None) -> App:
    return App(
        name=APP_NAME,
        root_agent=build_root_agent(model),
        resumability_config=ResumabilityConfig(is_resumable=True),
    )
