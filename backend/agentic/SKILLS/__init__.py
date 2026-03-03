"""
动态 Skill 定义目录。

- 每个技能由一对文件组成：<name>.md + <name>.py
- .md 负责给大模型看的说明与参数（YAML frontmatter + Markdown 正文）
- .py 负责具体执行逻辑，需提供 async def execute(...)
"""

