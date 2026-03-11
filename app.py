#!/usr/bin/env python3
"""
Awakener - Entry Point
========================
One-command startup for the Awakener autonomous agent platform.

Usage:
    python app.py              # Start with default settings
    python app.py --port 9000  # Start on custom port
"""

import os
import sys
import argparse
import uvicorn
from dotenv import load_dotenv


def main():
    """Parse arguments, load config, and start the web server."""

    parser = argparse.ArgumentParser(
        description="Awakener - Autonomous Agent Platform",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Visit https://github.com/NanYuan-C/awakener for documentation.",
    )
    parser.add_argument(
        "--port", type=int, default=None,
        help="Port number for the web console (overrides config.yaml)",
    )
    parser.add_argument(
        "--host", type=str, default=None,
        help="Host binding address (overrides config.yaml)",
    )
    args = parser.parse_args()

    # -- Resolve project directory --
    project_dir = os.path.dirname(os.path.abspath(__file__))

    # -- Ensure config.yaml exists --
    config_path = os.path.join(project_dir, "config.yaml")
    config_example = os.path.join(project_dir, "config.yaml.example")
    if not os.path.exists(config_path) and os.path.exists(config_example):
        import shutil
        shutil.copy2(config_example, config_path)
        print("[INIT] Created config.yaml from template")

    # -- Load .env --
    env_path = os.path.join(project_dir, ".env")
    if os.path.exists(env_path):
        load_dotenv(env_path)

    # -- Load config --
    from core.config import ConfigManager, DEFAULTS
    config_manager = ConfigManager(project_dir)
    config = config_manager.load()

    host = args.host or config["web"].get("host", DEFAULTS["web"]["host"])
    port = args.port or config["web"].get("port", DEFAULTS["web"]["port"])

    # -- Initialize prompts and agent home from templates --
    # Only run if language is already configured (set by browser on first visit).
    # On first run, templates are NOT copied until the browser sends its language.
    from services.init import is_language_configured, initialize
    agent_home = config["agent"].get("home", DEFAULTS["agent"]["home"])
    if is_language_configured(project_dir):
        initialize(project_dir, agent_home)

    # -- Startup banner --
    print()
    print("  ╔══════════════════════════════════════════════╗")
    print("  ║           AWAKENER v2.0                      ║")
    print("  ║   Autonomous Agent Management Console        ║")
    print("  ╚══════════════════════════════════════════════╝")
    print()
    print(f"  Console : http://{host}:{port}")
    print(f"  Project : https://github.com/NanYuan-C/awakener")
    print()

    # -- Start web server --
    uvicorn.run(
        "api.app:create_app",
        factory=True,
        host=host,
        port=port,
        reload=False,
        log_level="info",
    )


if __name__ == "__main__":
    main()
