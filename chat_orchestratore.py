"""Chat interna del GESTORE sul motore vLLM (OVH AI Deploy).
Per la stessa chat sui modelli Claude: python chat_orchestratore_anthropic.py
Uso:  python chat_orchestratore.py"""
from agents.llm import imposta_motore

imposta_motore("vllm")          # prima di costruire agenti e orchestratori

from chat_comune import chat_gestore   # noqa: E402

chat_gestore()
