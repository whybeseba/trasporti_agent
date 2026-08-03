"""Agente per-cliente: modello (vLLM o Anthropic) + prompt personalizzato +
tool ancorati al cliente della sessione."""
from datetime import date
from pathlib import Path

from langchain.agents import create_agent

from agents.llm import costruisci_llm
from tools.dkv_tools import costruisci_tools_cliente


def prompt_cliente(nome_cliente: str) -> str:
    """Il system prompt dell'agente, con nome cliente e data sostituiti.
    Esposto perché lo usa anche scripts/conta_token.py per misurarlo."""
    prompt = Path("config/prompts/agente_cliente.txt").read_text(encoding="utf-8")
    return (prompt.replace("{data_oggi}", date.today().isoformat())
                  .replace("{nome_cliente}", nome_cliente))


def costruisci_agente_cliente(cliente_id: int, nome_cliente: str):
    return create_agent(costruisci_llm(),
                        tools=costruisci_tools_cliente(cliente_id),
                        system_prompt=prompt_cliente(nome_cliente))
