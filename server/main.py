"""
Awakener - FastAPI Application
================================
Creates and configures the FastAPI web application that serves as the
management console for the Awakener platform.

Responsibilities:
    - Create the FastAPI app instance with CORS and metadata
    - Mount static file serving for CSS/JS assets (web/css, web/js)
    - Configure Jinja2 template rendering for HTML pages
    - Register API routes and WebSocket endpoint
    - Define page routes that render Jinja2 templates
    - Initialize all manager instances (auth, config, agent, websocket)

Architecture:
    The application uses Jinja2 template inheritance for the frontend:
    - base.html: Shared layout (collapsible sidebar + top bar + content area)
    - login.html / setup.html: Standalone auth pages (no sidebar)
    - Other pages extend base.html and fill in the content block

    Static assets (CSS, JS) are served from web/css and web/js.
    API endpoints are prefixed with /api/.
    WebSocket is available at /ws.
"""

import os
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
from fastapi.middleware.cors import CORSMiddleware

from server.auth import AuthManager
from server.config import ConfigManager
from server.websocket import WebSocketManager
from server.manager import AgentManager
from server.routes import create_router


def create_app(project_dir: str | None = None) -> FastAPI:
    """
    Application factory: create and configure the FastAPI instance.

    This factory pattern allows flexible initialization for both
    production use and testing.

    Args:
        project_dir: Root directory of the Awakener project.
                     If None, auto-detected from this file's location.

    Returns:
        Configured FastAPI application ready to run with uvicorn.
    """
    # -- Resolve directories ---------------------------------------------------
    if project_dir is None:
        project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    data_dir = os.path.join(project_dir, "data")
    web_dir = os.path.join(project_dir, "web")
    templates_dir = os.path.join(web_dir, "templates")
    css_dir = os.path.join(web_dir, "css")
    js_dir = os.path.join(web_dir, "js")

    # Ensure required directories exist
    os.makedirs(data_dir, exist_ok=True)

    # -- Initialize managers ---------------------------------------------------
    config_manager = ConfigManager(project_dir)
    auth_manager = AuthManager(data_dir)
    ws_manager = WebSocketManager()
    agent_manager = AgentManager(ws_manager, project_dir=project_dir)

    # -- Create FastAPI app ----------------------------------------------------
    app = FastAPI(
        title="Awakener",
        description="Management console for the Awakener autonomous agent platform",
        version="2.0.0",
        docs_url="/docs",
        redoc_url=None,
    )

    # -- CORS middleware -------------------------------------------------------
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # -- Jinja2 template engine ------------------------------------------------
    templates = Jinja2Templates(directory=templates_dir)

    # -- Store managers on app state -------------------------------------------
    app.state.config_manager = config_manager
    app.state.auth_manager = auth_manager
    app.state.ws_manager = ws_manager
    app.state.agent_manager = agent_manager
    app.state.templates = templates

    # -- Register API routes ---------------------------------------------------
    api_router = create_router(
        auth_manager=auth_manager,
        config_manager=config_manager,
        agent_manager=agent_manager,
    )
    app.include_router(api_router)

    # -- WebSocket endpoint ----------------------------------------------------
    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket):
        """
        WebSocket endpoint for real-time log streaming and status updates.
        Clients connect here and receive broadcast messages from the activator.
        """
        await ws_manager.connect(websocket)
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            ws_manager.disconnect(websocket)

    # -- Mount static assets ---------------------------------------------------
    if os.path.isdir(css_dir):
        app.mount("/css", StaticFiles(directory=css_dir), name="css")
    if os.path.isdir(js_dir):
        app.mount("/js", StaticFiles(directory=js_dir), name="js")

    # -- Page routes (Jinja2 template rendering) -------------------------------
    # These routes serve HTML pages. Authentication is checked client-side
    # via JavaScript (auth.js), which redirects to /login if no valid token.

    @app.get("/")
    async def index(request: Request):
        """Root route: redirect to dashboard or login based on auth state."""
        return RedirectResponse(url="/dashboard")

    @app.get("/login")
    async def login_page(request: Request):
        """Login page - standalone layout (no sidebar)."""
        return templates.TemplateResponse("login.html", {"request": request})

    @app.get("/setup")
    async def setup_page(request: Request):
        """First-time setup wizard - standalone layout (no sidebar)."""
        return templates.TemplateResponse("setup.html", {"request": request})

    @app.get("/dashboard")
    async def dashboard_page(request: Request):
        """Main dashboard - agent status, live logs, controls."""
        return templates.TemplateResponse(
            "dashboard.html", {"request": request, "page_id": "dashboard"}
        )

    @app.get("/settings")
    async def settings_page(request: Request):
        """Settings page - model, API keys, intervals, password."""
        return templates.TemplateResponse(
            "settings.html", {"request": request, "page_id": "settings"}
        )

    @app.get("/prompts")
    async def prompts_page(request: Request):
        """Global agent prompt editor."""
        return templates.TemplateResponse(
            "prompts.html", {"request": request, "page_id": "prompts"}
        )

    @app.get("/skills")
    async def skills_page(request: Request):
        """Skill management - list, view, enable/disable, create, delete."""
        return templates.TemplateResponse(
            "skills.html", {"request": request, "page_id": "skills"}
        )

    @app.get("/feed")
    async def feed_page(request: Request):
        """Activity feed - social-media-style agent activity posts."""
        return templates.TemplateResponse(
            "feed.html", {"request": request, "page_id": "feed"}
        )

    @app.get("/snapshot")
    async def snapshot_page(request: Request):
        """System snapshot view - asset inventory."""
        return templates.TemplateResponse(
            "snapshot.html", {"request": request, "page_id": "snapshot"}
        )

    return app
