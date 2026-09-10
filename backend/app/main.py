"""FastAPI application entrypoint.

Wires configuration, logging, and the API routers. When a pre-built frontend
bundle is present (``app/static/index.html`` — produced for single-container
deployments such as Hugging Face Spaces), the same app also serves the SPA, so
the whole product runs from one origin. In the docker-compose setup nginx serves
the frontend instead and this static mount is simply absent.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.routes import auth, dataset, evaluation, health, incidents
from app.core.config import settings
from app.core.logger import configure_logging, get_logger

configure_logging()
logger = get_logger(__name__)

# Directory a single-container build drops the compiled frontend into.
_STATIC_DIR = Path(__file__).resolve().parent / "static"


class _SPAStaticFiles(StaticFiles):
    """StaticFiles that falls back to index.html for client-side routes."""

    async def get_response(self, path: str, scope):  # type: ignore[override]
        response = await super().get_response(path, scope)
        if response.status_code == 404:
            # Unknown path -> let the SPA router handle it.
            return await super().get_response("index.html", scope)
        return response


def create_app() -> FastAPI:
    """Application factory: build and configure the FastAPI instance."""
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        debug=settings.debug,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router, prefix=settings.api_prefix)
    app.include_router(auth.router, prefix=settings.api_prefix)
    app.include_router(incidents.router, prefix=settings.api_prefix)
    app.include_router(dataset.router, prefix=settings.api_prefix)
    app.include_router(evaluation.router, prefix=settings.api_prefix)

    # Serve the SPA last (mounted at "/"), so it only catches paths the API
    # routers above didn't. Absent in the compose setup (nginx serves it there).
    if (_STATIC_DIR / "index.html").is_file():
        app.mount("/", _SPAStaticFiles(directory=_STATIC_DIR, html=True), name="spa")
        logger.info("Serving frontend SPA from %s", _STATIC_DIR)

    logger.info("%s started (api_prefix=%s)", settings.app_name, settings.api_prefix)
    return app


app = create_app()
