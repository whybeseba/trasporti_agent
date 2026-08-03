"""Chat interna del GESTORE sui modelli Claude (API Anthropic).

Identica a chat_orchestratore.py: cambia solo il motore. Modello nel .env
con ANTHROPIC_MODEL (default claude-haiku-4-5), oppure al volo:
  ANTHROPIC_MODEL=claude-sonnet-5 python chat_orchestratore_anthropic.py

Uso:  python chat_orchestratore_anthropic.py"""
from agents.llm import imposta_motore

imposta_motore("anthropic")     # prima di costruire agenti e orchestratori

from chat_comune import chat_gestore   # noqa: E402

chat_gestore()
