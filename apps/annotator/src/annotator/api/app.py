from annotator.workspace import WorkspaceManager
from fastapi import FastAPI

# Global singleton
_workspace_manager = WorkspaceManager()

def get_workspace() -> WorkspaceManager:
    return _workspace_manager

def create_app() -> FastAPI:
    app = FastAPI(title="Annotator API")

    from .routes import broadcaster, router  # noqa: PLC0415

    # Subscribe the broadcaster to the workspace manager
    _workspace_manager.subscribe(broadcaster.broadcast_sync)

    app.include_router(router)
    return app
