"""Chat di collaudo lato CLIENTE sul motore vLLM (OVH AI Deploy).
Per la stessa chat sui modelli Claude: python chat_test_anthropic.py
Uso:  python chat_test.py"""
from agents.llm import imposta_motore

imposta_motore("vllm")          # prima di costruire agenti e orchestratori

from chat_comune import chat_cliente   # noqa: E402

chat_cliente()
