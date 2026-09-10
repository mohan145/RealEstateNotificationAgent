import os

from langchain_core.language_models.chat_models import BaseChatModel


def get_llm(tools: list, system_instruction: str | None = None) -> BaseChatModel:
    """Build a tool-bound LLM from LLM_PROVIDER env var (anthropic / openai / google)."""
    provider = os.environ.get("LLM_PROVIDER", "anthropic").lower()
    if provider == "anthropic":
        return _build_anthropic(tools)
    if provider == "openai":
        return _build_openai(tools)
    if provider == "google":
        return _build_google(tools)
    raise ValueError(f"Unknown LLM_PROVIDER '{provider}'. Use anthropic, openai, or google.")


def _build_anthropic(tools: list) -> BaseChatModel:
    from langchain_anthropic import ChatAnthropic
    model = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")
    return ChatAnthropic(model=model).bind_tools(tools)


def _build_openai(tools: list) -> BaseChatModel:
    from langchain_openai import ChatOpenAI
    model = os.environ.get("OPENAI_MODEL", "gpt-4o")
    return ChatOpenAI(model=model).bind_tools(tools)


def _build_google(tools: list) -> BaseChatModel:
    from langchain_google_genai import ChatGoogleGenerativeAI
    model = os.environ.get("GOOGLE_MODEL", "gemini-2.5-flash-lite")
    return ChatGoogleGenerativeAI(model=model, convert_system_message_to_human=True).bind_tools(tools)