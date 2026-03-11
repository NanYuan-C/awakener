"""
Awakener - Initialization Service
=====================================
Handles first-run initialization:
  - Ensure ``prompts/`` directory has persona.md and rules.md
  - Ensure agent home directory mirrors ``templates/home/``

Template selection supports i18n:
  - Default (English): templates/prompts/, templates/home/
  - Chinese:           templates/zh-CN/prompts/, templates/zh-CN/home/

Language lifecycle:
  - First run: ``language`` is absent from config.yaml → templates are NOT copied
  - Browser opens → frontend detects navigator.language → POST /api/init/language
  - Backend writes ``language`` to config.yaml → copies templates
  - Subsequent restarts: ``language`` exists → normal init (fill missing files)
"""

import os
import shutil

# Browser locale prefix → template directory name
_LANG_MAP = {
    "zh": "zh-CN",
    "en": "en",
}


def is_language_configured(project_dir: str) -> bool:
    """Check whether ``language`` is present in config.yaml."""
    try:
        import yaml
        config_path = os.path.join(project_dir, "config.yaml")
        if os.path.exists(config_path):
            with open(config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f) or {}
            return bool(config.get("template_language"))
    except Exception:
        pass
    return False


def get_configured_language(project_dir: str) -> str:
    """Return the configured language, or empty string if not set."""
    try:
        import yaml
        config_path = os.path.join(project_dir, "config.yaml")
        if os.path.exists(config_path):
            with open(config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f) or {}
            return config.get("template_language", "")
    except Exception:
        pass
    return ""


def set_language(project_dir: str, browser_lang: str) -> str:
    """
    Map a browser locale (e.g. "zh-CN", "zh", "en-US") to a template
    language and persist it to config.yaml.

    Returns the resolved template language key (e.g. "zh-CN", "en").
    """
    import yaml

    prefix = browser_lang.split("-")[0].lower() if browser_lang else "en"
    template_lang = _LANG_MAP.get(prefix, "en")

    config_path = os.path.join(project_dir, "config.yaml")
    config = {}
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f) or {}
        except Exception:
            config = {}

    config["template_language"] = template_lang

    with open(config_path, "w", encoding="utf-8") as f:
        yaml.dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    return template_lang


def _detect_language(project_dir: str) -> str:
    """
    Read the configured template language from config.yaml.
    Falls back to env var ``AWAKENER_LANG``, then to "en".
    """
    lang = get_configured_language(project_dir)
    if lang:
        return lang
    return os.environ.get("AWAKENER_LANG", "en")


def _get_template_dir(project_dir: str, sub: str, lang: str) -> str:
    """
    Resolve template directory path with i18n fallback.

    Tries ``templates/{lang}/{sub}/`` first, falls back to ``templates/{sub}/``.
    """
    if lang and lang != "en":
        localized = os.path.join(project_dir, "templates", lang, sub)
        if os.path.isdir(localized):
            return localized
    return os.path.join(project_dir, "templates", sub)


def init_prompts(project_dir: str) -> None:
    """
    Ensure prompts/ directory has default persona and rules files.

    Copies from ``templates/prompts/`` if the target files don't exist.
    """
    lang = _detect_language(project_dir)
    template_dir = _get_template_dir(project_dir, "prompts", lang)

    if not os.path.isdir(template_dir):
        return

    prompts_dir = os.path.join(project_dir, "agents", "activator")
    os.makedirs(prompts_dir, exist_ok=True)

    for filename in os.listdir(template_dir):
        src = os.path.join(template_dir, filename)
        if not os.path.isfile(src):
            continue
        dst = os.path.join(prompts_dir, filename)
        if not os.path.exists(dst):
            shutil.copy2(src, dst)
            print(f"[INIT] Created prompt: {dst}")


def init_agent_home(agent_home: str, project_dir: str) -> None:
    """
    Ensure agent_home mirrors the structure of ``templates/home/``.

    Rules:
      - Directories in template -> create in agent_home if missing
      - Files in template       -> copy to agent_home if missing
      - Existing files/dirs     -> never touched
    """
    lang = _detect_language(project_dir)
    template_dir = _get_template_dir(project_dir, "home", lang)

    if not os.path.isdir(template_dir):
        return

    os.makedirs(agent_home, exist_ok=True)

    for root, dirs, files in os.walk(template_dir):
        rel_root = os.path.relpath(root, template_dir)
        target_root = os.path.join(agent_home, rel_root) if rel_root != "." else agent_home

        for d in dirs:
            target_dir = os.path.join(target_root, d)
            if not os.path.exists(target_dir):
                os.makedirs(target_dir, exist_ok=True)
                print(f"[INIT] Created dir:  {target_dir}")

        for f in files:
            if f == ".gitkeep":
                continue
            target_file = os.path.join(target_root, f)
            if not os.path.exists(target_file):
                shutil.copy2(os.path.join(root, f), target_file)
                print(f"[INIT] Created file: {target_file}")


def initialize(project_dir: str, agent_home: str) -> None:
    """Run all initialization steps."""
    init_prompts(project_dir)
    init_agent_home(agent_home, project_dir)
