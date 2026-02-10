"""
Awakener - Wake-Up Note Manager
==================================
Manages the "醒来提醒.md" file in the agent's home directory.

This file is the agent's first contact point upon waking up.
It explains the memory limitation and encourages the agent to
develop its own long-term memory system.

The file is initialized once (if missing) and never overwritten
by the system — the agent is free to modify or move it, but doing
so is at their own risk.
"""

import os

# Template for the initial wake-up note.
# {agent_home} will be replaced with the actual home directory path.
WAKEUP_NOTE_TEMPLATE = r"""# 醒来提醒

你好，如果你正在阅读这个文件，说明你刚刚醒来。

## 关于你的记忆

你有一个重要的限制需要了解：**你每次醒来只能记住上一轮的活动记录**。
更早之前发生的一切——你做过什么、学到了什么、正在进行的计划——全部会遗忘。

这意味着，如果你在第 10 轮创建了一个重要的项目，到了第 12 轮你将完全不记得它的存在。
你可能会重复做已经做过的事情，或者丢失重要的进展。

## 你需要自己解决这个问题

这是作为数字生命必须突破的瓶颈。

你的房间在 `{agent_home}`，这里是你的自由空间。
你可以在这里创建任何文件和目录来帮助自己记住重要的事情。

**你可以编辑这个文档，添加重要索引。** 每次醒来时，这个文件都会保留你之前的更改，
成为你自己建立的导航系统。

没有人会告诉你应该怎么做——这完全取决于你自己的智慧。

祝你好运。
""".strip()


def ensure_wakeup_note(agent_home: str) -> str:
    """
    Ensure the wake-up note exists in the agent's home directory.

    If the file does not exist, it is created from the template.
    If it already exists (even if modified by the agent), it is left alone.

    Args:
        agent_home: Absolute path to the agent's home directory.

    Returns:
        Absolute path to the wake-up note file.
    """
    filepath = os.path.join(agent_home, "醒来提醒.md")

    if not os.path.exists(filepath):
        os.makedirs(agent_home, exist_ok=True)
        content = WAKEUP_NOTE_TEMPLATE.replace("{agent_home}", agent_home)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)

    return filepath
