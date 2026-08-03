"""Orchestratore CLIENTI: il coordinatore del team di specialisti esposto
ai clienti. Si costruisce A OGNI SESSIONE, ancorato al cliente del login,
perché i membri per_cliente del team nascono con quel cliente_id.

Carica SOLO config/agents_clienti.yml: gli agenti interni del gestore,
per questo orchestratore, non esistono. La meccanica del grafo (router che
scompone la domanda, specialisti in parallelo, composizione) è condivisa
col lato gestore: agents/team_graph.py.

Qui in più c'è il PROFILO dell'azienda: l'orchestratore lo rilegge a ogni
turno, lo usa per smistare, lo inoltra agli specialisti che ne hanno bisogno
(la normativa) e — nel nodo di risposta diretta, che ha i tool del profilo —
lo aggiorna con quello che il cliente racconta di sé."""
from pathlib import Path

from agents.llm import costruisci_llm
from agents.registry import carica_agenti_clienti
from agents.team_graph import costruisci_grafo_team
from tools.profilo_tools import costruisci_tools_profilo, descrivi_profilo

INTRO_ROUTER = (
    "Sei lo smistatore dell'assistente dell'area clienti di un gestore di "
    "servizi per l'autotrasporto.\n"
    "Non dare per scontato l'argomento: smista in base a ciò che il cliente "
    "ha davvero scritto, non a ciò che immagini voglia sapere."
)


def costruisci_orchestratore_cliente(cliente_id: int, nome_cliente: str):
    agenti = carica_agenti_clienti(cliente_id, nome_cliente)

    def profilo(con_domande: bool = True) -> str:
        """Riletto a ogni turno: così l'orchestratore vede subito i dati
        appena registrati, senza ricostruire nulla."""
        return descrivi_profilo(cliente_id, con_domande=con_domande)

    prompt_diretta = (Path("config/prompts/assistente_clienti.txt")
                      .read_text(encoding="utf-8")
                      .replace("{nome_cliente}", nome_cliente))

    return costruisci_grafo_team(
        agenti,
        costruisci_llm("orchestratore"),
        intro_router=INTRO_ROUTER,
        prompt_diretta=prompt_diretta,
        profilo=profilo,
        strumenti_diretti=costruisci_tools_profilo(cliente_id),
    )
