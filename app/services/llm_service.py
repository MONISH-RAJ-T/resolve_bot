"""The only place that creates the Gemini model (via LangChain)."""
from langchain_google_genai import ChatGoogleGenerativeAI

from app.core import config


def build_model(tools):
    """Gemini at temperature 0 with the tools attached. The model only asks for tools; our code runs them."""
    if config.LLM_PROVIDER != "gemini":
        raise RuntimeError(f"Unsupported LLM_PROVIDER '{config.LLM_PROVIDER}' (only 'gemini' is implemented)")
    model = ChatGoogleGenerativeAI(
        model=config.LLM_MODEL, temperature=0, google_api_key=config.GEMINI_API_KEY or None,
        timeout=config.LLM_TIMEOUT, max_retries=1)
    return model.bind_tools(tools)
