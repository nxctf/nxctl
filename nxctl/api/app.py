"""FastAPI application factory for NXCTL."""

from fastapi import FastAPI

from nxctl.api.routes.challenges import router as challenges_router
from nxctl.api.routes.health import router as health_router
from nxctl.api.routes.lifecycle import router as lifecycle_router
from nxctl.api.routes.root import router as root_router
from nxctl.api.routes.status import router as status_router


def create_app() -> FastAPI:
    app = FastAPI(
        title="NXCTL API",
        description="API for NXCTL challenge orchestration",
    )
    app.include_router(root_router)
    app.include_router(challenges_router)
    app.include_router(status_router)
    app.include_router(health_router)
    app.include_router(lifecycle_router)
    return app


app = create_app()
