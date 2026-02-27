from prometheus_client import CollectorRegistry, generate_latest
from starlette.responses import PlainTextResponse
from starlette.requests import Request


registry = CollectorRegistry()


async def metrics_endpoint(_request: Request) -> PlainTextResponse:
    payload = generate_latest()
    return PlainTextResponse(
        content=payload.decode("utf-8"),
        media_type="text/plain; version=0.0.4",
    )


