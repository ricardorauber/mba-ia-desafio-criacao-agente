"""Scripted stand-in for Gemini, so flows run without network or API key."""

from __future__ import annotations

from typing import Any, AsyncGenerator, Callable, Union

from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.adk.models._capabilities import LlmCapabilities
from google.genai import types
from pydantic import Field

Step = Union[types.Part, Callable[[LlmRequest], types.Part], Exception]


def call(name: str, **args: Any) -> types.Part:
    return types.Part(function_call=types.FunctionCall(name=name, args=args))


def say(text: str) -> types.Part:
    return types.Part(text=text)


class ScriptedLlm(BaseLlm):
    """Answers each model call with the next scripted step ("ok" when empty)."""

    model: str = "scripted"
    steps: list = Field(default_factory=list)
    requests: list = Field(default_factory=list)

    @property
    def capabilities(self) -> LlmCapabilities:
        return LlmCapabilities(output_schema_and_tools=True)

    def script(self, *steps: Step) -> None:
        self.steps.extend(steps)

    async def generate_content_async(
        self, llm_request: LlmRequest, stream: bool = False
    ) -> AsyncGenerator[LlmResponse, None]:
        self.requests.append(llm_request)
        step = self.steps.pop(0) if self.steps else say("ok")
        if isinstance(step, Exception):
            raise step
        if callable(step):
            step = step(llm_request)
        yield LlmResponse(content=types.Content(role="model", parts=[step]))


def user_text(text: str) -> types.Content:
    return types.Content(role="user", parts=[types.Part(text=text)])


def confirmation_answer(confirmation_id: str, confirmed: bool) -> types.Content:
    return types.Content(
        role="user",
        parts=[
            types.Part(
                function_response=types.FunctionResponse(
                    id=confirmation_id,
                    name="adk_request_confirmation",
                    response={"confirmed": confirmed},
                )
            )
        ],
    )


def function_responses(session, name: str) -> list[dict]:
    return [
        fr.response
        for event in session.events
        for fr in event.get_function_responses()
        if fr.name == name
    ]


def open_confirmations(session) -> dict[str, dict]:
    asked: dict[str, dict] = {}
    answered: set[str] = set()
    for event in session.events:
        for fc in event.get_function_calls():
            if fc.name == "adk_request_confirmation":
                asked[fc.id] = fc.args
        for fr in event.get_function_responses():
            if fr.name == "adk_request_confirmation":
                answered.add(fr.id)
    return {key: value for key, value in asked.items() if key not in answered}
