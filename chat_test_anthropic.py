"""Chat di collaudo lato CLIENTE sui modelli Claude (API Anthropic).

Identica a chat_test.py: cambia solo il motore. Il modello si sceglie nel
.env con ANTHROPIC_MODEL (default claude-haiku-4-5), oppure al volo:
  ANTHROPIC_MODEL=claude-sonnet-5 python chat_test_anthropic.py

Uso:  python chat_test_anthropic.py"""
from agents.llm import imposta_motore

imposta_motore("anthropic")     # prima di costruire agenti e orchestratori

from chat_comune import chat_cliente   # noqa: E402

chat_cliente()
