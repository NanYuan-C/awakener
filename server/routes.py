"""
Awakener - REST API Routes
============================
All HTTP API endpoints for the management console.

Route groups:
    /api/auth/*      - Authentication (status, setup, login, password change)
    /api/config      - Configuration management (read / update config.yaml)
    /api/config/keys - API key management (list / add / update / delete)
    /api/agent/*     - Agent lifecycle control (start / stop / restart / status / inspiration)
    /api/prompt      - Single global prompt management (read / update default.md)
    /api/skills/*    - Skill management (list / get / add / toggle / delete)
    /api/timeline    - Timeline data access (one entry per round)
    /api/logs        - Activator run logs (per-day files)

All routes except /api/auth/* require a valid JWT token.
See auth.py for authentication details.
"""

import os
import json
import shutil
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
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

class SkillUploadFile(BaseModel):
    """A single file within a skill upload."""
    path: str = Field(..., description="Relative path within the skill directory")
    content: str = Field(..., description="File content (text)")

class SkillUploadRequest(BaseModel):
    """Upload a complete skill directory."""
    name: str = Field(..., description="Skill directory name")
    files: list[SkillUploadFile] = Field(..., min_length=1)


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
    # PROMPT ROUTE - Single global prompt (default.md)
    # =========================================================================

    @router.get("/prompt", dependencies=[auth])
    async def get_prompt():
        """
        Get the content of the global agent prompt (prompts/default.md).
        There is only one prompt file — no switching or listing.
        """
        prompts_dir = config_manager.get_prompts_dir()
        filepath = os.path.join(prompts_dir, "default.md")

        if not os.path.exists(filepath):
            return {"content": ""}

        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()

        return {"content": content}

    @router.put("/prompt", dependencies=[auth])
    async def update_prompt(req: PromptContentRequest):
        """
        Update the global agent prompt (prompts/default.md).
        """
        prompts_dir = config_manager.get_prompts_dir()
        os.makedirs(prompts_dir, exist_ok=True)
        filepath = os.path.join(prompts_dir, "default.md")

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(req.content)

        return {"message": "Prompt saved"}

    # =========================================================================
    # SKILL MANAGEMENT ROUTES - Requires authentication
    # =========================================================================

    @router.get("/skills", dependencies=[auth])
    async def list_skills():
        """
        List all installed skills from data/skills/ directory.
        Each skill has a SKILL.md with YAML frontmatter metadata.
        Returns name, title, description, tags, enabled status.
        """
        from activator.tools import scan_skills

        skills_dir = os.path.join(config_manager.project_dir, "data", "skills")
        skills = scan_skills(skills_dir)
        return {"skills": skills}

    @router.get("/skills/{name}", dependencies=[auth])
    async def get_skill(name: str):
        """
        Get full details for a single skill including SKILL.md content,
        list of reference files, and list of scripts.
        """
        from activator.tools import _parse_skill_frontmatter

        skills_dir = os.path.join(config_manager.project_dir, "data", "skills")
        skill_path = os.path.join(skills_dir, name)

        if not os.path.isdir(skill_path):
            raise HTTPException(status_code=404, detail=f"Skill '{name}' not found")

        skill_md = os.path.join(skill_path, "SKILL.md")
        content = ""
        if os.path.isfile(skill_md):
            with open(skill_md, "r", encoding="utf-8") as f:
                content = f.read()

        meta = _parse_skill_frontmatter(skill_md) if os.path.isfile(skill_md) else {}

        # List reference files
        refs_dir = os.path.join(skill_path, "references")
        refs = []
        if os.path.isdir(refs_dir):
            for root, _, files in os.walk(refs_dir):
                for fn in sorted(files):
                    rel = os.path.relpath(os.path.join(root, fn), skill_path)
                    refs.append(rel.replace("\\", "/"))

        # List scripts
        scripts_dir = os.path.join(skill_path, "scripts")
        scripts = []
        if os.path.isdir(scripts_dir):
            for fn in sorted(os.listdir(scripts_dir)):
                fp = os.path.join(scripts_dir, fn)
                if os.path.isfile(fp):
                    scripts.append(fn)

        return {
            "name": name,
            "title": meta.get("name", name),
            "description": meta.get("description", ""),
            "version": str(meta.get("version", "")),
            "tags": meta.get("tags", []),
            "content": content,
            "references": refs,
            "scripts": scripts,
        }

    @router.put("/skills/{name}", dependencies=[auth])
    async def update_skill(name: str, req: PromptContentRequest):
        """
        Update a skill's SKILL.md content.
        If the skill directory doesn't exist, it is created.
        """
        skills_dir = os.path.join(config_manager.project_dir, "data", "skills")
        skill_path = os.path.join(skills_dir, name)
        os.makedirs(skill_path, exist_ok=True)

        filepath = os.path.join(skill_path, "SKILL.md")
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(req.content)

        return {"message": f"Skill '{name}' saved"}

    @router.post("/skills/upload", dependencies=[auth])
    async def upload_skill(req: SkillUploadRequest):
        """
        Upload a complete skill directory (multiple files).

        Validates:
        - Name uses valid characters (lowercase, digits, hyphens)
        - No skill with the same name already exists
        - A SKILL.md file is included
        - SKILL.md frontmatter contains 'name' and 'description'

        All files are written to data/skills/<name>/.
        """
        from activator.tools import _parse_skill_frontmatter

        name = req.name.strip()

        # Validate name format
        if not name or not all(
            c.isalnum() or c == '-' for c in name
        ) or not name[0].isalnum():
            raise HTTPException(
                status_code=400,
                detail="Invalid skill name. Use lowercase letters, digits, and hyphens.",
            )

        skills_dir = os.path.join(config_manager.project_dir, "data", "skills")
        skill_path = os.path.join(skills_dir, name)

        # Check for duplicate
        if os.path.isdir(skill_path):
            raise HTTPException(
                status_code=409,
                detail=f"Skill '{name}' already exists. Delete it first or choose a different name.",
            )

        # Check SKILL.md is present
        skill_md_file = None
        for f in req.files:
            normalized = f.path.replace("\\", "/")
            if normalized == "SKILL.md" or normalized.endswith("/SKILL.md"):
                skill_md_file = f
                break

        if not skill_md_file:
            raise HTTPException(
                status_code=400,
                detail="SKILL.md file is required but not found in the upload.",
            )

        # Validate frontmatter has name and description
        content = skill_md_file.content
        if not content.startswith("---"):
            raise HTTPException(
                status_code=400,
                detail="SKILL.md must start with YAML frontmatter (--- delimiter).",
            )

        end = content.find("---", 3)
        if end == -1:
            raise HTTPException(
                status_code=400,
                detail="SKILL.md frontmatter is not properly closed (missing closing ---).",
            )

        import yaml
        try:
            frontmatter = yaml.safe_load(content[3:end].strip()) or {}
        except yaml.YAMLError:
            raise HTTPException(
                status_code=400,
                detail="SKILL.md frontmatter contains invalid YAML.",
            )

        if not frontmatter.get("name"):
            raise HTTPException(
                status_code=400,
                detail="SKILL.md frontmatter must contain a 'name' field.",
            )

        if not frontmatter.get("description"):
            raise HTTPException(
                status_code=400,
                detail="SKILL.md frontmatter must contain a 'description' field.",
            )

        # Write all files
        os.makedirs(skill_path, exist_ok=True)
        file_count = 0

        for f in req.files:
            # Normalize path separators and prevent traversal
            rel_path = f.path.replace("\\", "/")
            if ".." in rel_path:
                continue

            target = os.path.join(skill_path, rel_path)
            target_real = os.path.realpath(target)
            skill_real = os.path.realpath(skill_path)

            if not target_real.startswith(skill_real + os.sep) and target_real != skill_real:
                continue  # Skip files that would escape the skill directory

            os.makedirs(os.path.dirname(target), exist_ok=True)
            with open(target, "w", encoding="utf-8") as fh:
                fh.write(f.content)
            file_count += 1

        return {
            "message": f"Skill '{name}' uploaded successfully",
            "name": name,
            "files": file_count,
        }

    @router.put("/skills/{name}/toggle", dependencies=[auth])
    async def toggle_skill(name: str):
        """
        Toggle the enabled/disabled state of a skill.
        Disabled skills are not injected into the agent's prompt and
        their tools are hidden.
        """
        from activator.tools import _load_skills_config, _save_skills_config

        skills_dir = os.path.join(config_manager.project_dir, "data", "skills")
        skill_path = os.path.join(skills_dir, name)

        if not os.path.isdir(skill_path):
            raise HTTPException(status_code=404, detail=f"Skill '{name}' not found")

        config = _load_skills_config(skills_dir)
        disabled = set(config.get("disabled", []))

        if name in disabled:
            disabled.discard(name)
            enabled = True
        else:
            disabled.add(name)
            enabled = False

        config["disabled"] = sorted(disabled)
        _save_skills_config(skills_dir, config)

        return {"name": name, "enabled": enabled}

    @router.delete("/skills/{name}", dependencies=[auth])
    async def delete_skill(name: str):
        """
        Delete a skill and all its files.
        This permanently removes the skill directory.
        """
        skills_dir = os.path.join(config_manager.project_dir, "data", "skills")
        skill_path = os.path.join(skills_dir, name)

        if not os.path.isdir(skill_path):
            raise HTTPException(status_code=404, detail=f"Skill '{name}' not found")

        shutil.rmtree(skill_path)

        # Remove from disabled list if present
        from activator.tools import _load_skills_config, _save_skills_config
        config = _load_skills_config(skills_dir)
        disabled = set(config.get("disabled", []))
        if name in disabled:
            disabled.discard(name)
            config["disabled"] = sorted(disabled)
            _save_skills_config(skills_dir, config)

        return {"message": f"Skill '{name}' deleted"}

    # =========================================================================
    # SNAPSHOT ROUTE - Requires authentication
    # =========================================================================

    @router.get("/snapshot", dependencies=[auth])
    async def get_snapshot():
        """
        Get the current system snapshot (asset inventory).
        Returns the content of data/snapshot.yaml as a JSON object.
        """
        from activator.snapshot import load_snapshot

        data_dir = os.path.join(config_manager.project_dir, "data")
        return load_snapshot(data_dir)

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

    @router.delete("/timeline/{round_num}", dependencies=[auth])
    async def delete_round(round_num: int):
        """
        Cascade-delete all data for a given round.
        Removes the timeline entry and log section
        for the specified round number.
        """
        from activator.memory import MemoryManager

        data_dir = os.path.join(config_manager.project_dir, "data")
        memory = MemoryManager(data_dir)
        result = memory.delete_round(round_num)

        if not any(result.values()):
            raise HTTPException(status_code=404, detail=f"No data found for round {round_num}")

        return {
            "message": f"Round {round_num} deleted",
            "deleted": result,
        }

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
