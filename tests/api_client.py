"""Async HTTP client over the ASGI app, running its lifespan."""

from contextlib import asynccontextmanager

import httpx

from aurora.api import create_app


@asynccontextmanager
async def api_client(model):
    app = create_app(model)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield client
