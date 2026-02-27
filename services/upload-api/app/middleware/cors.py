from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI


def add_cors_middleware(app: FastAPI) -> None:
    """Attach CORS middleware allowing local frontend development."""
    origins = [
        "http://localhost:3000",
        "http://localhost:3001",
    ]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


