"""Agente per-cliente: modello vLLM su OVH + prompt personalizzato + tool ancorati."""
from datetime import date
from pathlib import Path

from langchain.agents import create_agent

from agents.llm import costruisci_llm
from tools.dkv_tools import costruisci_tools_cliente


def costruisci_agente_cliente(cliente_id: int, nome_cliente: str):
    prompt = Path("config/prompts/agente_cliente.txt").read_text(encoding="utf-8")
    prompt = (prompt.replace("{data_oggi}", date.today().isoformat())
                    .replace("{nome_cliente}", nome_cliente))
    return create_agent(costruisci_llm(),
                        tools=costruisci_tools_cliente(cliente_id),
                        system_prompt=prompt)
