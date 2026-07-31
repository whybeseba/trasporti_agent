"""Agente Normativa (condiviso): norme e circolari dell'autotrasporto via RAG.

Nessun dato di clienti: il suo unico strumento legge il corpus normativo
pubblico su ChromaDB. Per questo nel registro è `per_cliente: false` e la
stessa istanza serve tutte le sessioni."""
from datetime import date
from pathlib import Path

from langchain.agents import create_agent
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from agents.llm import costruisci_llm
from tools.rag import cerca_normativa_multi as _cerca


def costruisci_agente_normativa():

    # `config` è iniettato da LangChain (il modello non lo vede): serve a far
    # comparire nella traccia anche la chiamata che genera le riformulazioni.
    @tool
    def cerca_normativa(domanda: str, config: RunnableConfig) -> str:
        """Cerca nei testi ufficiali di norme e circolari dell'autotrasporto
        (cabotaggio, distacco dei conducenti, tempi di guida e riposo,
        documenti di trasporto...) i passaggi più pertinenti alla domanda.
        Riformula da solo la domanda in più varianti e interroga il corpus
        con tutte, restituendo i passaggi migliori con titolo, fonte e data."""
        risultati = _cerca(domanda, config=config)
        if not risultati:
            return ("Nessun passaggio pertinente trovato nel corpus normativo. "
                    "NON rispondere a memoria: se anche una seconda ricerca "
                    "riformulata non trova nulla, di' al cliente che il tema "
                    "non è coperto dai documenti disponibili.")
        blocchi = [f"[{i}] {r['titolo']} ({r['fonte']}, {r['data'] or 'senza data'}):\n"
                   f"{r['testo']}"
                   for i, r in enumerate(risultati, 1)]
        blocchi.append("(Rispondi usando SOLO gli estratti sopra, citandone "
                       "titolo e data. Se non bastano, dillo al cliente.)")
        return "\n\n".join(blocchi)

    prompt = Path("config/prompts/agente_normativa.txt").read_text(encoding="utf-8")
    prompt = prompt.replace("{data_oggi}", date.today().isoformat())
    return create_agent(costruisci_llm(), tools=[cerca_normativa],
                        system_prompt=prompt)
