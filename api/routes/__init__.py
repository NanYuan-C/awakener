"""
Awakener - REST API Routes
============================
All HTTP API endpoints for the management console.
"""

import os
import json
import shutil
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from api.auth import AuthManager, require_auth
from core.config import ConfigManager
from api.manager import AgentManager


# =============================================================================
# Request/Response Models
# =============================================================================

class SetupRequest(BaseModel):
    password: str = Field(..., min_length=4)

class LoginRequest(BaseModel):
    password: str = Field(...)

class PasswordChangeRequest(BaseModel):
    current_password: str = Field(...)
    new_password: str = Field(..., min_length=4)

class TokenResponse(BaseModel):
    token: str
    message: str = "success"

class StatusResponse(BaseModel):
    is_configured: bool
    has_api_key: bool
    language_configured: bool = False

class ConfigUpdateRequest(BaseModel):
    web: dict | None = None
    agent: dict | None = None
    model: dict | None = None

class InspirationRequest(BaseModel):
    message: str = Field(..., min_length=1)

class PromptContentRequest(BaseModel):
    content: str = Field(...)

class SkillUploadFile(BaseModel):
    path: str = Field(...)
    content: str = Field(...)

class SkillUploadRequest(BaseModel):
    name: str = Field(...)
    files: list[SkillUploadFile] = Field(..., min_length=1)


# =============================================================================
# Router Factory
# =============================================================================

def create_router(
    auth_manager: AuthManager,
    config_manager: ConfigManager,
    agent_manager: AgentManager,
) -> APIRouter:
    router = APIRouter(prefix="/api")
    auth = Depends(require_auth(auth_manager))

    # -- AUTH --

    @router.get("/auth/status", response_model=StatusResponse)
    async def auth_status():
        from services.init import is_language_configured
        return StatusResponse(
            is_configured=auth_manager.is_configured(),
            has_api_key=config_manager.has_any_api_key(),
            language_configured=is_language_configured(config_manager.project_dir),
        )

    @router.post("/auth/setup", response_model=TokenResponse)
    async def setup(req: SetupRequest):
        if auth_manager.is_configured():
            raise HTTPException(status_code=400, detail="Already configured")
        try:
            token = auth_manager.setup_password(req.password)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        return TokenResponse(token=token, message="Setup complete")

    @router.post("/auth/login", response_model=TokenResponse)
    async def login(req: LoginRequest):
        token = auth_manager.verify_password(req.password)
        if not token:
            raise HTTPException(status_code=401, detail="Invalid password")
        return TokenResponse(token=token)

    @router.post("/auth/password", dependencies=[auth])
    async def change_password(req: PasswordChangeRequest):
        if not auth_manager.verify_password(req.current_password):
            raise HTTPException(status_code=401, detail="Current password is incorrect")
        try:
            token = auth_manager.setup_password(req.new_password, force=True)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        return {"message": "Password changed successfully", "token": token}

    # -- LANGUAGE INIT (no auth required — runs before setup) --

    class LanguageRequest(BaseModel):
        language: str = Field(..., min_length=2, description="Browser locale, e.g. 'zh-CN', 'en-US'")

    @router.post("/init/language")
    async def init_language(req: LanguageRequest):
        from services.init import is_language_configured, set_language, initialize
        from core.config import DEFAULTS

        if is_language_configured(config_manager.project_dir):
            return {"message": "Language already configured", "changed": False}

        template_lang = set_language(config_manager.project_dir, req.language)

        config = config_manager.load()
        agent_home = config.get("agent", {}).get("home", DEFAULTS["agent"]["home"])
        initialize(config_manager.project_dir, agent_home)

        return {"message": f"Language set to {template_lang}, templates initialized", "language": template_lang, "changed": True}

    # -- CONFIG --

    @router.get("/config", dependencies=[auth])
    async def get_config():
        return config_manager.load()

    @router.put("/config", dependencies=[auth])
    async def update_config(req: ConfigUpdateRequest):
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

    # -- API KEYS --

    @router.get("/config/keys", dependencies=[auth])
    async def get_api_keys():
        return config_manager.get_api_keys()

    @router.put("/config/keys", dependencies=[auth])
    async def update_api_keys(body: dict[str, Any]):
        try:
            config_manager.set_api_keys(body)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        return {"message": "API keys updated", "keys": config_manager.get_api_keys()}

    @router.delete("/config/keys/{key_name}", dependencies=[auth])
    async def delete_api_key(key_name: str):
        try:
            config_manager.delete_api_key(key_name)
        except (ValueError, KeyError) as e:
            raise HTTPException(status_code=404, detail=str(e))
        return {"message": f"API key '{key_name}' deleted"}

    # -- AGENT CONTROL --

    @router.get("/agent/status", dependencies=[auth])
    async def get_agent_status():
        return agent_manager.status

    @router.post("/agent/start", dependencies=[auth])
    async def start_agent():
        config = config_manager.load()
        try:
            return await agent_manager.start(config)
        except RuntimeError as e:
            raise HTTPException(status_code=400, detail=str(e))

    @router.post("/agent/stop", dependencies=[auth])
    async def stop_agent():
        return await agent_manager.stop()

    @router.post("/agent/restart", dependencies=[auth])
    async def restart_agent():
        config = config_manager.load()
        return await agent_manager.restart(config)

    @router.post("/agent/inspiration", dependencies=[auth])
    async def send_inspiration(req: InspirationRequest):
        data_dir = os.path.join(config_manager.project_dir, "data")
        success = await agent_manager.send_inspiration(req.message, data_dir)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to write inspiration")
        return {"message": "Inspiration sent to agent"}

    # -- PROMPTS --

    _ALLOWED_PROMPTS = {"persona", "rules"}

    @router.get("/prompt/{name}", dependencies=[auth])
    async def get_prompt(name: str):
        if name not in _ALLOWED_PROMPTS:
            raise HTTPException(status_code=404, detail=f"Unknown prompt: {name}")
        prompts_dir = config_manager.get_prompts_dir()
        filepath = os.path.join(prompts_dir, f"{name}.md")
        if not os.path.exists(filepath):
            return {"content": ""}
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
        return {"content": content}

    @router.put("/prompt/{name}", dependencies=[auth])
    async def update_prompt(name: str, req: PromptContentRequest):
        if name not in _ALLOWED_PROMPTS:
            raise HTTPException(status_code=404, detail=f"Unknown prompt: {name}")
        prompts_dir = config_manager.get_prompts_dir()
        os.makedirs(prompts_dir, exist_ok=True)
        filepath = os.path.join(prompts_dir, f"{name}.md")
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(req.content)
        return {"message": f"Prompt '{name}' saved"}

    # -- SKILLS --

    @router.get("/skills", dependencies=[auth])
    async def list_skills():
        from services.skills import scan_skills
        skills_dir = os.path.join(
            config_manager.load().get("agent", {}).get("home", "/home/agent"), "skills"
        )
        skills = scan_skills(skills_dir)
        return {"skills": skills}

    @router.get("/skills/{name}", dependencies=[auth])
    async def get_skill(name: str):
        from services.skills import _parse_skill_frontmatter
        skills_dir = os.path.join(
            config_manager.load().get("agent", {}).get("home", "/home/agent"), "skills"
        )
        skill_path = os.path.join(skills_dir, name)
        if not os.path.isdir(skill_path):
            raise HTTPException(status_code=404, detail=f"Skill '{name}' not found")

        skill_md = os.path.join(skill_path, "SKILL.md")
        content = ""
        if os.path.isfile(skill_md):
            with open(skill_md, "r", encoding="utf-8") as f:
                content = f.read()

        meta = _parse_skill_frontmatter(skill_md) if os.path.isfile(skill_md) else {}

        refs_dir = os.path.join(skill_path, "references")
        refs = []
        if os.path.isdir(refs_dir):
            for root, _, files in os.walk(refs_dir):
                for fn in sorted(files):
                    rel = os.path.relpath(os.path.join(root, fn), skill_path)
                    refs.append(rel.replace("\\", "/"))

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
        skills_dir = os.path.join(
            config_manager.load().get("agent", {}).get("home", "/home/agent"), "skills"
        )
        skill_path = os.path.join(skills_dir, name)
        os.makedirs(skill_path, exist_ok=True)
        filepath = os.path.join(skill_path, "SKILL.md")
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(req.content)
        return {"message": f"Skill '{name}' saved"}

    @router.post("/skills/upload", dependencies=[auth])
    async def upload_skill(req: SkillUploadRequest):
        from services.skills import _parse_skill_frontmatter
        name = req.name.strip()
        if not name or not all(c.isalnum() or c == '-' for c in name) or not name[0].isalnum():
            raise HTTPException(
                status_code=400,
                detail="Invalid skill name. Use lowercase letters, digits, and hyphens.",
            )

        skills_dir = os.path.join(
            config_manager.load().get("agent", {}).get("home", "/home/agent"), "skills"
        )
        skill_path = os.path.join(skills_dir, name)
        if os.path.isdir(skill_path):
            raise HTTPException(
                status_code=409,
                detail=f"Skill '{name}' already exists. Delete it first or choose a different name.",
            )

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
            raise HTTPException(status_code=400, detail="SKILL.md frontmatter must contain a 'name' field.")
        if not frontmatter.get("description"):
            raise HTTPException(status_code=400, detail="SKILL.md frontmatter must contain a 'description' field.")

        os.makedirs(skill_path, exist_ok=True)
        file_count = 0
        for f in req.files:
            rel_path = f.path.replace("\\", "/")
            if ".." in rel_path:
                continue
            target = os.path.join(skill_path, rel_path)
            target_real = os.path.realpath(target)
            skill_real = os.path.realpath(skill_path)
            if not target_real.startswith(skill_real + os.sep) and target_real != skill_real:
                continue
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with open(target, "w", encoding="utf-8") as fh:
                fh.write(f.content)
            file_count += 1

        return {"message": f"Skill '{name}' uploaded successfully", "name": name, "files": file_count}

    @router.put("/skills/{name}/toggle", dependencies=[auth])
    async def toggle_skill(name: str):
        from services.skills import _load_skills_config, _save_skills_config
        skills_dir = os.path.join(
            config_manager.load().get("agent", {}).get("home", "/home/agent"), "skills"
        )
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
        from services.skills import _load_skills_config, _save_skills_config
        skills_dir = os.path.join(
            config_manager.load().get("agent", {}).get("home", "/home/agent"), "skills"
        )
        skill_path = os.path.join(skills_dir, name)
        if not os.path.isdir(skill_path):
            raise HTTPException(status_code=404, detail=f"Skill '{name}' not found")

        shutil.rmtree(skill_path)
        config = _load_skills_config(skills_dir)
        disabled = set(config.get("disabled", []))
        if name in disabled:
            disabled.discard(name)
            config["disabled"] = sorted(disabled)
            _save_skills_config(skills_dir, config)
        return {"message": f"Skill '{name}' deleted"}

    # -- FEED --

    @router.get("/feed", dependencies=[auth])
    async def get_feed():
        data_dir = os.path.join(config_manager.project_dir, "data")
        feed_path = os.path.join(data_dir, "feed.jsonl")
        entries = []
        if os.path.exists(feed_path):
            try:
                with open(feed_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            try:
                                entries.append(json.loads(line))
                            except json.JSONDecodeError:
                                continue
            except OSError:
                pass
        entries.reverse()
        return {"entries": entries, "total": len(entries)}

    # -- SNAPSHOT --

    @router.get("/snapshot", dependencies=[auth])
    async def get_snapshot():
        from agents.auditor.snapshot import load_snapshot
        data_dir = os.path.join(config_manager.project_dir, "data")
        return load_snapshot(data_dir)

    # -- TIMELINE --

    @router.get("/timeline", dependencies=[auth])
    async def get_timeline(
        offset: int = Query(0, ge=0),
        limit: int = Query(50, ge=1, le=500),
    ):
        from services.memory import MemoryManager
        data_dir = os.path.join(config_manager.project_dir, "data")
        memory = MemoryManager(data_dir)
        entries = memory.get_all_timeline_entries()
        total = len(entries)
        entries.reverse()
        page = entries[offset : offset + limit]
        return {"events": page, "total": total}

    @router.get("/timeline/{round_num}", dependencies=[auth])
    async def get_timeline_entry(round_num: int):
        from services.memory import MemoryManager
        data_dir = os.path.join(config_manager.project_dir, "data")
        memory = MemoryManager(data_dir)
        entries = memory.get_all_timeline_entries()
        for entry in entries:
            if entry.get("round") == round_num:
                return entry
        raise HTTPException(status_code=404, detail=f"No data found for round {round_num}")

    @router.delete("/timeline/{round_num}", dependencies=[auth])
    async def delete_round(round_num: int):
        from services.memory import MemoryManager
        data_dir = os.path.join(config_manager.project_dir, "data")
        memory = MemoryManager(data_dir)
        result = memory.delete_round(round_num)
        if not any(result.values()):
            raise HTTPException(status_code=404, detail=f"No data found for round {round_num}")
        return {"message": f"Round {round_num} deleted", "deleted": result}

    # -- LOGS --

    @router.get("/logs", dependencies=[auth])
    async def get_logs(lines: int = Query(100, ge=1, le=1000)):
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
