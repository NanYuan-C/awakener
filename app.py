#!/usr/bin/env python3
"""
Awakener - Entry Point
========================
One-command startup for the Awakener autonomous agent platform.

Usage:
    python app.py              # Start with default settings
    python app.py --port 9000  # Start on custom port

This script:
    1. Loads configuration from config.yaml
    2. Loads environment variables from .env (API keys)
    3. Creates the FastAPI web application
    4. Starts the uvicorn server

After starting, open the printed URL in a browser to access
the management console.
"""

import os
import sys
import argparse
import uvicorn
from dotenv import load_dotenv


def main():
    """Parse arguments, load config, and start the web server."""

    # -- Parse command-line arguments ------------------------------------------
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

    # -- Resolve project directory ---------------------------------------------
    project_dir = os.path.dirname(os.path.abspath(__file__))

    # -- Ensure configuration files exist --------------------------------------
    # If config.yaml or prompts/default.md are missing, create them from examples.
    # This prevents overwriting user customization on updates while ensuring
    # new installations work out of the box.
    config_path = os.path.join(project_dir, "config.yaml")
    config_example = os.path.join(project_dir, "config.yaml.example")
    if not os.path.exists(config_path) and os.path.exists(config_example):
        import shutil
        shutil.copy2(config_example, config_path)
        print(f"[INIT] Created config.yaml from template")

    prompt_path = os.path.join(project_dir, "prompts", "default.md")
    prompt_example = os.path.join(project_dir, "prompts", "default.md.example")
    if not os.path.exists(prompt_path) and os.path.exists(prompt_example):
        import shutil
        shutil.copy2(prompt_example, prompt_path)
        print(f"[INIT] Created prompts/default.md from template")

    # -- Load environment variables from .env ----------------------------------
    env_path = os.path.join(project_dir, ".env")
    if os.path.exists(env_path):
        load_dotenv(env_path)

    # -- Load configuration to get web server settings -------------------------
    from server.config import ConfigManager, DEFAULTS
    config_manager = ConfigManager(project_dir)
    config = config_manager.load()

    # Command-line args override config file
    host = args.host or config["web"].get("host", DEFAULTS["web"]["host"])
    port = args.port or config["web"].get("port", DEFAULTS["web"]["port"])

    # -- Print startup banner --------------------------------------------------
    print()
    print("  ╔══════════════════════════════════════════════╗")
    print("  ║           AWAKENER v2.0                      ║")
    print("  ║   Autonomous Agent Management Console        ║")
    print("  ╚══════════════════════════════════════════════╝")
    print()
    print(f"  Console : http://{host}:{port}")
    print(f"  Project : https://github.com/NanYuan-C/awakener")
    print()

    # -- Start the web server --------------------------------------------------
    uvicorn.run(
        "server.main:create_app",
        factory=True,
        host=host,
        port=port,
        reload=False,
        log_level="info",
    )


if __name__ == "__main__":
    main()
