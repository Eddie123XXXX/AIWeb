"""
意图路由：根据用户输入判断目标领域，用于记忆检索的 domain 过滤。

6 大通用领域：
- general_chat: 通用客观知识问答、闲聊，不检索记忆
- user_preferences: AI 助手的回复格式、语气偏好、用户个人身份设定
- professional_and_academic: 职业与学术
- lifestyle_and_interests: 兴趣爱好、文学电影、饮食、旅游与娱乐
- social_and_relationships: 家人、朋友、同事、宠物及人际关系
- tasks_and_schedules: 待办事项、行程规划、备忘录与购物清单
"""
import json
import logging
import os

from openai import AsyncOpenAI

logger = logging.getLogger("memory")

# 6 大通用领域
MEMORY_DOMAINS = [
    "general_chat",
    "user_preferences",
    "professional_and_academic",
    "lifestyle_and_interests",
    "social_and_relationships",
    "tasks_and_schedules",
]

NON_GENERAL_DOMAINS = [d for d in MEMORY_DOMAINS if d != "general_chat"]

ROUTER_PROMPT = """你是一个高精度的意图分类路由器，服务于一个通用的 AI 助手平台。请分析用户的最新输入，判断为了完美回答这个问题，我们需要从向量数据库中提取该用户的哪个生活领域的历史记忆。

【可选领域列表】
- user_preferences: 涉及 AI 助手的回复格式、语气偏好、用户个人身份的基础设定。
- professional_and_academic: 涉及用户的工作内容、代码开发、学术研究、职业规划与项目细节。
- lifestyle_and_interests: 涉及用户的兴趣爱好、文学电影、饮食习惯、旅游与娱乐。
- social_and_relationships: 涉及用户的家人、朋友、同事、宠物及人际关系处理。
- tasks_and_schedules: 涉及用户的待办事项、行程规划、备忘录与购物清单。
- general_chat: 通用客观知识问答、临时翻译、闲聊，无需调取用户的专属历史记忆。

【用户输入】
{user_input}

【输出要求】
请严格输出 JSON 格式，包含一个 "target_domains" 数组。最多选取 2 个最相关的领域。如果完全不需要调用用户的历史记忆，必须输出 ["general_chat"]。
示例：{{"target_domains": ["professional_and_academic"]}}"""


def _get_router_client() -> AsyncOpenAI:
    """路由模型客户端（优先 DeepSeek，与打分模型一致）。"""
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if api_key:
        base_url = os.getenv("DEEPSEEK_API_BASE", "https://api.deepseek.com/v1")
        return AsyncOpenAI(api_key=api_key, base_url=base_url)
    api_key = os.getenv("QWEN_API_KEY")
    if api_key:
        base_url = os.getenv(
            "QWEN_API_BASE",
            "https://dashscope.aliyuncs.com/compatible-mode/v1",
        )
        return AsyncOpenAI(api_key=api_key, base_url=base_url)
    raise RuntimeError("DEEPSEEK_API_KEY 或 QWEN_API_KEY 未配置，无法执行意图路由")


async def get_intent_domains(user_input: str) -> list[str]:
    """
    调用轻量级模型进行意图路由，返回目标领域列表。

    - 若为纯闲聊，返回 ["general_chat"]，调用方不检索记忆
    - 否则返回非 general 的领域列表，用于 Milvus domain 过滤
    """
    if not user_input or not user_input.strip():
        return ["general_chat"]

    model = os.getenv("MEMORY_ROUTER_MODEL", "deepseek-chat")  # 可用小模型提速
    try:
        client = _get_router_client()
        resp = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "user", "content": ROUTER_PROMPT.format(user_input=user_input[:1000])}
            ],
            temperature=0.1,
            max_tokens=128,
        )
        raw = resp.choices[0].message.content or "{}"
        data = json.loads(raw)
        domains = data.get("target_domains", ["general_chat"])
        if not isinstance(domains, list):
            domains = ["general_chat"]
        # 校验领域名
        valid = [d for d in domains if d in MEMORY_DOMAINS]
        if not valid:
            valid = ["general_chat"]
        logger.info("[Memory] 意图路由 get_intent_domains | domains=%s", valid)
        return valid
    except Exception as e:
        logger.warning("[Memory] 意图路由失败，降级为 general_chat: %s", e)
        return ["general_chat"]
