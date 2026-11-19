"""Report provider configuration without sending evidence or exposing credentials."""

import os

from paperrule.providers import CodexCLIProvider, OpenAIAPIProvider


def provider_diagnostics() -> dict:
    name = os.environ.get("PAPERRULE_PROVIDER", "manual").casefold()
    factories = {
        "openai": OpenAIAPIProvider, "openai_api": OpenAIAPIProvider,
        "codex": CodexCLIProvider, "codex_cli": CodexCLIProvider,
    }
    factory = factories.get(name)
    configured = bool(factory and factory().configured)
    return {
        "name": name,
        "configured": configured,
        "connection": "not_checked",
        "message": (
            "已检测到配置；尚未验证登录、网络连接或模型回复。"
            if configured else
            "当前为人工编辑模式，未连接可用的 AI 服务。"
            if name == "manual" else
            "未检测到可用配置，请按照安装指南配置 AI 服务后重试。"
        ),
    }
