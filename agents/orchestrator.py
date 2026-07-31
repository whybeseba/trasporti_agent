"""Orchestratore INTERNO (gestore): coordina i sub-agenti del registro
config/agents_config.yml. La meccanica del grafo (router che scompone la
domanda, sub-agenti in parallelo, composizione) è condivisa col lato
clienti: agents/team_graph.py."""
from agents.llm import costruisci_llm
from agents.registry import carica_agenti
from agents.team_graph import costruisci_grafo_team

AGENTI = carica_agenti()


def costruisci_orchestratore():
    return costruisci_grafo_team(
        AGENTI,
        costruisci_llm("orchestratore"),
        intro_router=("Sei l'orchestratore del sistema interno di un gestore "
                      "di servizi per aziende di trasporto."),
        prompt_diretta=("Sei l'assistente interno del gestore. Rispondi in "
                        "italiano."),
    )
