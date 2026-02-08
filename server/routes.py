"""
Awakener - REST API Routes
============================
All HTTP API endpoints for the management console.

Route groups:
    /api/auth/*      - Authentication (status, setup, login, password change)
    /api/config      - Configuration management (read / update config.yaml)
    /api/config/keys - API key management (list / add / update / delete)
    /api/agent/*     - Agent lifecycle control (start / stop / restart / status / inspiration)
    /api/prompts/*   - Persona prompt management (list / read / write / delete)
    /api/timeline    - Timeline data access (one entry per round)
    /api/memory/*    - Agent notebook entries (JSONL per-round notes)
    /api/logs        - Activator run logs (per-day files)

All routes except /api/auth/* require a valid JWT token.
See auth.py for authentication details.
"""

import os
import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from server.auth import AuthManager, require_auth
from server.config import ConfigManager
from server.manager import AgentManager


# =============================================================================
# Request/Response Models (Pydantic)
# =============================================================================

class SetupRequest(BaseModel):
    """First-time setup: set admin password."""
    password: str = Field(..., min_length=4, description="Admin password (min 4 chars)")

class LoginRequest(BaseModel):
    """Login with admin password."""
    password: str = Field(..., description="Admin password")

class PasswordChangeRequest(BaseModel):
    """Change the admin password."""
    current_password: str = Field(..., description="Current admin password")
    new_password: str = Field(..., min_length=4, description="New admin password")

class TokenResponse(BaseModel):
    """JWT token returned after successful auth."""
    token: str
    message: str = "success"

class StatusResponse(BaseModel):
    """Authentication/setup status check."""
    is_configured: bool = Field(description="Whether initial setup is complete")
    has_api_key: bool = Field(description="Whether at least one API key is set")

class ConfigUpdateRequest(BaseModel):
    """
    Partial configuration update.
    Any combination of top-level config sections can be provided.
    """
    web: dict | None = None
    agent: dict | None = None
    model: dict | None = None

class InspirationRequest(BaseModel):
    """Send an inspiration message to the agent."""
    message: str = Field(..., min_length=1, description="Inspiration text for the agent")

class PromptContentRequest(BaseModel):
    """Create or update a persona prompt."""
    content: str = Field(..., description="Prompt content in Markdown")


# =============================================================================
# Router Factory
# =============================================================================

def create_router(
    auth_manager: AuthManager,
    config_manager: ConfigManager,
    agent_manager: AgentManager,
) -> APIRouter:
    """
    Create and configure the API router with all endpoints.

    This factory pattern allows dependency injection of manager instances,
    making the routes testable and decoupled from global state.

    Args:
        auth_manager:   Handles password verification and JWT tokens.
        config_manager: Reads/writes configuration files.
        agent_manager:  Controls the activator process lifecycle.

    Returns:
        Configured APIRouter with all endpoints registered.
    """
    router = APIRouter(prefix="/api")

    # Shorthand for the auth dependency
    auth = Depends(require_auth(auth_manager))

    # =========================================================================
    # AUTH ROUTES - No authentication required
    # =========================================================================

    @router.get("/auth/status", response_model=StatusResponse)
    async def auth_status():
        """
        Check if the system has been set up (password configured).
        Used by the frontend to decide whether to show setup or login page.
        """
        return StatusResponse(
            is_configured=auth_manager.is_configured(),
            has_api_key=config_manager.has_any_api_key(),
        )

    @router.post("/auth/setup", response_model=TokenResponse)
    async def setup(req: SetupRequest):
        """
        First-time setup: set admin password.
        Returns a JWT token for immediate access.
        """
        if auth_manager.is_configured():
            raise HTTPException(status_code=400, detail="Already configured")

        try:
            token = auth_manager.setup_password(req.password)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

        return TokenResponse(token=token, message="Setup complete")

    @router.post("/auth/login", response_model=TokenResponse)
    async def login(req: LoginRequest):
        """
        Login with admin password. Returns a JWT token on success.
        """
        token = auth_manager.verify_password(req.password)
        if not token:
            raise HTTPException(status_code=401, detail="Invalid password")
        return TokenResponse(token=token)

    @router.post("/auth/password", dependencies=[auth])
    async def change_password(req: PasswordChangeRequest):
        """
        Change the admin password. Requires current password for verification.
        Returns a new JWT token after successful password change.
        """
        # Verify current password
        if not auth_manager.verify_password(req.current_password):
            raise HTTPException(status_code=401, detail="Current password is incorrect")

        try:
            token = auth_manager.setup_password(req.new_password, force=True)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

        return {"message": "Password changed successfully", "token": token}

    # =========================================================================
    # CONFIG ROUTES - Requires authentication
    # =========================================================================

    @router.get("/config", dependencies=[auth])
    async def get_config():
        """
        Get the current configuration (from config.yaml).
        API keys are NOT included here - use /api/config/keys instead.
        """
        return config_manager.load()

    @router.put("/config", dependencies=[auth])
    async def update_config(req: ConfigUpdateRequest):
        """
        Update configuration settings. Accepts partial updates.
        Changes are written to config.yaml immediately.

        Supports updating: web, agent, and model sections.
        """
        updates = {}
        if req.web is not None:
            updates["web"] = req.web
        if req.agent is not None:
            updates["agent"] = req.agent
        if req.model is not None:
            updates["model"] = req.model

        if not updates:
            raise HTTPException(status_code=400, detail="No updates provided")

        return config_manager.update(updates)

    # =========================================================================
    # API KEY ROUTES - Requires authentication
    # =========================================================================

    @router.get("/config/keys", dependencies=[auth])
    async def get_api_keys():
        """
        Get configured API keys (masked for security).
        Only shows first 6 and last 4 characters of each key.
        """
        return config_manager.get_api_keys()

    @router.put("/config/keys", dependencies=[auth])
    async def update_api_keys(body: dict[str, Any]):
        """
        Update one or more API keys. Keys are stored in the .env file.
        Accepts a flat dict of {KEY_NAME: value} pairs.
        """
        try:
            config_manager.set_api_keys(body)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        return {"message": "API keys updated", "keys": config_manager.get_api_keys()}

    @router.delete("/config/keys/{key_name}", dependencies=[auth])
    async def delete_api_key(key_name: str):
        """
        Delete a single API key from the .env file.

        Args:
            key_name: The environment variable name to remove (e.g., DEEPSEEK_API_KEY).
        """
        try:
            config_manager.delete_api_key(key_name)
        except (ValueError, KeyError) as e:
            raise HTTPException(status_code=404, detail=str(e))
        return {"message": f"API key '{key_name}' deleted"}

    # =========================================================================
    # AGENT CONTROL ROUTES - Requires authentication
    # =========================================================================

    @router.get("/agent/status", dependencies=[auth])
    async def get_agent_status():
        """Get the current agent status (state, round, uptime, etc.)."""
        return agent_manager.status

    @router.post("/agent/start", dependencies=[auth])
    async def start_agent():
        """
        Start the agent activator.
        The activator will begin its activation loop in a background thread.
        """
        config = config_manager.load()
        try:
            return await agent_manager.start(config)
        except RuntimeError as e:
            raise HTTPException(status_code=400, detail=str(e))

    @router.post("/agent/stop", dependencies=[auth])
    async def stop_agent():
        """
        Stop the agent activator gracefully.
        The current activation round will be completed before stopping.
        """
        return await agent_manager.stop()

    @router.post("/agent/restart", dependencies=[auth])
    async def restart_agent():
        """
        Restart the agent activator with the latest configuration.
        Equivalent to stop + start.
        """
        config = config_manager.load()
        return await agent_manager.restart(config)

    @router.post("/agent/inspiration", dependencies=[auth])
    async def send_inspiration(req: InspirationRequest):
        """
        Send an inspiration to the agent.
        The agent will see it as a "spark of inspiration" at the start
        of its next activation round. It's a one-way hint, not a conversation.
        """
        data_dir = os.path.join(config_manager.project_dir, "data")
        success = await agent_manager.send_inspiration(req.message, data_dir)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to write inspiration")
        return {"message": "Inspiration sent to agent"}

    # =========================================================================
    # PROMPT MANAGEMENT ROUTES - Requires authentication
    # =========================================================================

    @router.get("/prompts", dependencies=[auth])
    async def list_prompts():
        """
        List all available persona prompts from the prompts/ directory.
        Returns name, filename, preview text, and active status.
        """
        config = config_manager.load()
        active = config.get("agent", {}).get("persona", "default")
        personas = config_manager.list_personas()

        for p in personas:
            p["active"] = (p["name"] == active or p["name"] == active + ".md")

        return {"prompts": personas, "active": active}

    @router.get("/prompts/{name:path}", dependencies=[auth])
    async def get_prompt(name: str):
        """
        Get the content of a specific persona prompt file.
        The name parameter can include the .md extension or not.
        """
        prompts_dir = config_manager.get_prompts_dir()

        # Support both "default" and "default.md"
        if not name.endswith(".md"):
            filename = name + ".md"
        else:
            filename = name
            name = name[:-3]

        filepath = os.path.join(prompts_dir, filename)

        if not os.path.exists(filepath):
            raise HTTPException(status_code=404, detail=f"Persona '{name}' not found")

        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()

        return {"name": name, "content": content}

    @router.put("/prompts/{name:path}", dependencies=[auth])
    async def update_prompt(name: str, req: PromptContentRequest):
        """
        Create or update a persona prompt file.
        If the file doesn't exist, it will be created.
        The name parameter can include the .md extension or not.
        """
        prompts_dir = config_manager.get_prompts_dir()

        if not name.endswith(".md"):
            filename = name + ".md"
        else:
            filename = name

        filepath = os.path.join(prompts_dir, filename)
        os.makedirs(prompts_dir, exist_ok=True)

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(req.content)

        return {"message": f"Persona '{name}' saved"}

    @router.delete("/prompts/{name:path}", dependencies=[auth])
    async def delete_prompt(name: str):
        """
        Delete a persona prompt file.
        The 'default' persona cannot be deleted.
        """
        # Strip .md extension for name comparison
        clean_name = name[:-3] if name.endswith(".md") else name

        if clean_name == "default":
            raise HTTPException(status_code=400, detail="Cannot delete the default persona")

        prompts_dir = config_manager.get_prompts_dir()
        filename = clean_name + ".md"
        filepath = os.path.join(prompts_dir, filename)

        if not os.path.exists(filepath):
            raise HTTPException(status_code=404, detail=f"Persona '{clean_name}' not found")

        os.remove(filepath)

        # If the deleted persona was active, switch to default
        config = config_manager.load()
        if config.get("agent", {}).get("persona") == clean_name:
            config_manager.update({"agent": {"persona": "default"}})

        return {"message": f"Persona '{clean_name}' deleted"}

    # =========================================================================
    # TIMELINE ROUTE - Requires authentication
    # =========================================================================

    @router.get("/timeline", dependencies=[auth])
    async def get_timeline(
        offset: int = Query(0, ge=0, description="Offset for pagination"),
        limit: int = Query(50, ge=1, le=500, description="Max entries to return"),
    ):
        """
        Get timeline entries from timeline.jsonl.
        Each entry is one activation round's summary (round, timestamp,
        tools_used, duration, summary).
        Returns events in reverse chronological order (newest first).
        """
        from activator.memory import MemoryManager

        data_dir = os.path.join(config_manager.project_dir, "data")
        memory = MemoryManager(data_dir)
        entries = memory.get_all_timeline_entries()

        total = len(entries)

        # Return newest first, with pagination
        entries.reverse()
        page = entries[offset : offset + limit]

        return {"events": page, "total": total}

    # =========================================================================
    # MEMORY ROUTES - Requires authentication
    # =========================================================================

    @router.get("/memory/notebook", dependencies=[auth])
    async def get_memory_notebook(
        offset: int = Query(0, ge=0, description="Offset for pagination"),
        limit: int = Query(50, ge=1, le=500, description="Max entries to return"),
    ):
        """
        Get the agent's notebook entries (per-round notes from notebook.jsonl).
        Returns entries in reverse order (newest first) with pagination.
        """
        from activator.memory import MemoryManager

        data_dir = os.path.join(config_manager.project_dir, "data")
        memory = MemoryManager(data_dir)
        entries = memory.get_all_notebook_entries()

        total = len(entries)
        # Reverse for newest-first display
        entries.reverse()
        page = entries[offset : offset + limit]

        return {"entries": page, "total": total}

    @router.get("/memory/recent", dependencies=[auth])
    async def get_recent_notes(
        count: int = Query(10, ge=1, le=50, description="Number of recent notes"),
    ):
        """
        Get the most recent notebook entries.
        Returns notes in chronological order (oldest first within the window).
        """
        from activator.memory import MemoryManager

        data_dir = os.path.join(config_manager.project_dir, "data")
        memory = MemoryManager(data_dir)
        notes = memory.get_recent_notes(count=count)

        return {"notes": notes}

    # =========================================================================
    # LOG ROUTE - Requires authentication
    # =========================================================================

    @router.get("/logs", dependencies=[auth])
    async def get_logs(lines: int = Query(100, ge=1, le=1000)):
        """
        Get the most recent lines from the activator log.

        Args:
            lines: Number of lines to return (default 100, max 1000).
        """
        log_dir = os.path.join(config_manager.project_dir, "data", "logs")

        if not os.path.isdir(log_dir):
            return {"lines": [], "total": 0}

        log_files = sorted(
            [f for f in os.listdir(log_dir) if f.endswith(".log")],
            reverse=True,
        )
        if not log_files:
            return {"lines": [], "total": 0}

        log_path = os.path.join(log_dir, log_files[0])
        try:
            with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                all_lines = f.readlines()
            return {
                "lines": [l.rstrip() for l in all_lines[-lines:]],
                "total": len(all_lines),
                "file": log_files[0],
            }
        except OSError:
            return {"lines": [], "total": 0}

    return router
