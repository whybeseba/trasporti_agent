"""Orchestratore CLIENTI: il coordinatore del team di specialisti esposto
ai clienti. Si costruisce A OGNI SESSIONE, ancorato al cliente del login,
perché i membri per_cliente del team nascono con quel cliente_id.

Carica SOLO config/agents_clienti.yml: gli agenti interni del gestore,
per questo orchestratore, non esistono. La meccanica del grafo (router che
scompone la domanda, specialisti in parallelo, composizione) è condivisa
col lato gestore: agents/team_graph.py."""
from agents.llm import costruisci_llm
from agents.registry import carica_agenti_clienti
from agents.team_graph import costruisci_grafo_team


def costruisci_orchestratore_cliente(cliente_id: int, nome_cliente: str):
    agenti = carica_agenti_clienti(cliente_id, nome_cliente)
    return costruisci_grafo_team(
        agenti,
        costruisci_llm("orchestratore"),
        intro_router=("Sei lo smistatore dell'assistente dell'area clienti "
                      "di un gestore di servizi per l'autotrasporto."),
        prompt_diretta=(f"Sei l'assistente dell'area clienti e stai parlando "
                        f"con l'azienda cliente «{nome_cliente}». Puoi "
                        "aiutare su due temi: i suoi consumi e spese DKV, e "
                        "la normativa dell'autotrasporto. Rispondi in "
                        "italiano, cortese e sintetico; non inventare mai "
                        "numeri né riferimenti normativi."),
    )
