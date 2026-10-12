"""Compatibility bridge for RAGAS 0.4.x and LangChain 1.x.

RAGAS imports two retired VertexAI classes even when evaluation uses Gemini via
the Google provider. They are only used in RAGAS for ``isinstance`` checks.
LangChain 1.x no longer exposes them from ``langchain_community``, so supply
placeholder types before importing RAGAS. Remove this module when upstream
RAGAS stops importing the retired paths.
"""
import sys
import types


def prepare_ragas_imports() -> None:
    try:
        from langchain_community.chat_models.vertexai import ChatVertexAI  # noqa: F401
        from langchain_community.llms import VertexAI  # noqa: F401
    except ModuleNotFoundError:
        vertex_module_name = "langchain_community.chat_models.vertexai"
        vertex_module = types.ModuleType(vertex_module_name)
        vertex_module.ChatVertexAI = type("ChatVertexAI", (), {})
        sys.modules.setdefault(vertex_module_name, vertex_module)

        import langchain_community.llms as community_llms

        if not hasattr(community_llms, "VertexAI"):
            community_llms.VertexAI = type("VertexAI", (), {})
