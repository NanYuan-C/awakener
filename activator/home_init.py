"""
Awakener - Agent Home Initializer
====================================
Syncs the agent's home directory from home_template/ on startup.

Rules:
  - Directories in template -> create in agent_home if missing
  - Files in template       -> copy to agent_home if missing
  - Existing files/dirs     -> never touched

To add a new file or directory to the agent home, simply place it
in home_template/. No code changes needed — the next restart will
create it in the agent's home directory.
"""

import os
import shutil


def init_agent_home(agent_home: str, project_dir: str) -> None:
    """
    Ensure agent_home mirrors the structure of home_template/.

    Args:
        agent_home:  Absolute path to the agent's home directory.
        project_dir: Awakener project root (contains home_template/).
    """
    template_dir = os.path.join(project_dir, "home_template")
    if not os.path.isdir(template_dir):
        return

    os.makedirs(agent_home, exist_ok=True)

    for root, dirs, files in os.walk(template_dir):
        # Relative path from template root
        rel_root = os.path.relpath(root, template_dir)
        target_root = os.path.join(agent_home, rel_root) if rel_root != "." else agent_home

        # Create missing directories
        for d in dirs:
            target_dir = os.path.join(target_root, d)
            if not os.path.exists(target_dir):
                os.makedirs(target_dir, exist_ok=True)
                print(f"[INIT] Created dir:  {target_dir}")

        # Copy missing files (skip .gitkeep placeholders)
        for f in files:
            if f == ".gitkeep":
                continue
            target_file = os.path.join(target_root, f)
            if not os.path.exists(target_file):
                shutil.copy2(os.path.join(root, f), target_file)
                print(f"[INIT] Created file: {target_file}")
