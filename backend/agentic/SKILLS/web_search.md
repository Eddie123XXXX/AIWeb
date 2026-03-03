---
name: web_search
parameters:
  type: object
  properties:
    query:
      type: string
      description: "需要搜索的关键词或完整问题"
  required: ["query"]
---

# Web Search Tool

这是一个网页搜索引擎技能。当你当前的记忆或 RAG 知识库中没有足够的信息时，或者用户询问最新的实时信息时，请调用此技能。

## 使用建议

- 请提取用户查询中最核心的关键词传入 `query`。
- 如果是专有名词，请尽量保持原语言搜索。

