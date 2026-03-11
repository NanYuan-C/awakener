"""
Awakener - FastAPI Application
================================
Creates and configures the FastAPI web application that serves as the
management console for the Awakener platform.
"""

import os
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
from fastapi.middleware.cors import CORSMiddleware

from api.auth import AuthManager
from core.config import ConfigManager
from api.ws.connection import WebSocketManager
from api.manager import AgentManager
from api.routes import create_router


def create_app(project_dir: str | None = None) -> FastAPI:
    """
    Application factory: create and configure the FastAPI instance.

    Args:
        project_dir: Root directory of the Awakener project.
                     If None, auto-detected from this file's location.

    Returns:
        Configured FastAPI application ready to run with uvicorn.
    """
    if project_dir is None:
        # api/app.py -> go up two levels to project root
        project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    data_dir = os.path.join(project_dir, "data")
    web_dir = os.path.join(project_dir, "web")
    templates_dir = os.path.join(web_dir, "templates")
    css_dir = os.path.join(web_dir, "css")
    js_dir = os.path.join(web_dir, "js")

    os.makedirs(data_dir, exist_ok=True)

    # -- Initialize managers --
    config_manager = ConfigManager(project_dir)
    auth_manager = AuthManager(data_dir)
    ws_manager = WebSocketManager()
    agent_manager = AgentManager(ws_manager, project_dir=project_dir)

    # -- Create FastAPI app --
    app = FastAPI(
        title="Awakener",
        description="Management console for the Awakener autonomous agent platform",
        version="2.0.0",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    # -- CORS --
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # -- Jinja2 --
    templates = Jinja2Templates(directory=templates_dir)

    # -- Store on app state --
    app.state.config_manager = config_manager
    app.state.auth_manager = auth_manager
    app.state.ws_manager = ws_manager
    app.state.agent_manager = agent_manager
    app.state.templates = templates

    # -- API routes --
    api_router = create_router(
        auth_manager=auth_manager,
        config_manager=config_manager,
        agent_manager=agent_manager,
    )
    app.include_router(api_router)

    # -- WebSocket --
    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket):
        await ws_manager.connect(websocket)
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            ws_manager.disconnect(websocket)

    # -- Static assets --
    if os.path.isdir(css_dir):
        app.mount("/css", StaticFiles(directory=css_dir), name="css")
    if os.path.isdir(js_dir):
        app.mount("/js", StaticFiles(directory=js_dir), name="js")

    # -- Page routes --
    @app.get("/")
    async def index(request: Request):
        return RedirectResponse(url="/dashboard")

    @app.get("/login")
    async def login_page(request: Request):
        return templates.TemplateResponse("login.html", {"request": request})

    @app.get("/setup")
    async def setup_page(request: Request):
        return templates.TemplateResponse("setup.html", {"request": request})

    @app.get("/dashboard")
    async def dashboard_page(request: Request):
        return templates.TemplateResponse(
            "dashboard.html", {"request": request, "page_id": "dashboard"}
        )

    @app.get("/settings")
    async def settings_page(request: Request):
        return templates.TemplateResponse(
            "settings.html", {"request": request, "page_id": "settings"}
        )

    @app.get("/prompts")
    async def prompts_page(request: Request):
        return templates.TemplateResponse(
            "prompts.html", {"request": request, "page_id": "prompts"}
        )

    @app.get("/skills")
    async def skills_page(request: Request):
        return templates.TemplateResponse(
            "skills.html", {"request": request, "page_id": "skills"}
        )

    @app.get("/feed")
    async def feed_page(request: Request):
        return templates.TemplateResponse(
            "feed.html", {"request": request, "page_id": "feed"}
        )

    @app.get("/snapshot")
    async def snapshot_page(request: Request):
        return templates.TemplateResponse(
            "snapshot.html", {"request": request, "page_id": "snapshot"}
        )

    return app
