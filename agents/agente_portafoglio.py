"""Agente interno del gestore: vede tutto il portafoglio clienti."""
from datetime import date
from pathlib import Path

from langchain.agents import create_agent

from agents.llm import costruisci_llm
from tools.portafoglio_tools import TOOLS_PORTAFOGLIO


def costruisci_agente_portafoglio():
    prompt = Path("config/prompts/agente_portafoglio.txt").read_text(encoding="utf-8")
    prompt = prompt.replace("{data_oggi}", date.today().isoformat())
    return create_agent(costruisci_llm(), tools=TOOLS_PORTAFOGLIO,
                        system_prompt=prompt)
