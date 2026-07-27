"""Orchestratore INTERNO (gestore): sceglie il sub-agente dal registro."""
from langgraph.graph import StateGraph, MessagesState, START, END

from agents.llm import costruisci_llm
from agents.registry import carica_agenti

AGENTI = carica_agenti()
llm = costruisci_llm("orchestratore")


class Stato(MessagesState):
    prossimo: str


def _prompt_router() -> str:
    righe = "\n".join(f"- {n}: {i['descrizione'].strip()}" for n, i in AGENTI.items())
    return ("Sei l'orchestratore del sistema interno di un gestore di servizi "
            "per aziende di trasporto.\nSub-agenti disponibili:\n" + righe +
            "\n- nessuno: la domanda è generica, si può rispondere direttamente.\n\n"
            "Leggi l'ultima domanda e rispondi SOLO con il nome del sub-agente "
            "più adatto (oppure 'nessuno'). Nessun'altra parola.")


def router(state: Stato):
    r = llm.invoke([{"role": "system", "content": _prompt_router()}] + state["messages"])
    testo = r.content.strip().lower()
    for nome in AGENTI:
        if nome in testo:
            return {"prossimo": nome}
    return {"prossimo": "nessuno"}


def _nodo_sub_agente(nome: str):
    def esegui(state: Stato):
        ris = AGENTI[nome]["agente"].invoke({"messages": state["messages"]})
        return {"messages": [ris["messages"][-1]]}
    return esegui


def risposta_diretta(state: Stato):
    r = llm.invoke([{"role": "system", "content":
                     "Sei l'assistente interno del gestore. Rispondi in italiano."}]
                   + state["messages"])
    return {"messages": [r]}


def costruisci_orchestratore():
    grafo = StateGraph(Stato)
    grafo.add_node("router", router)
    grafo.add_node("nessuno", risposta_diretta)
    grafo.add_edge("nessuno", END)
    for nome in AGENTI:
        grafo.add_node(nome, _nodo_sub_agente(nome))
        grafo.add_edge(nome, END)
    grafo.add_edge(START, "router")
    destinazioni = {n: n for n in AGENTI} | {"nessuno": "nessuno"}
    grafo.add_conditional_edges("router", lambda s: s["prossimo"], destinazioni)
    return grafo.compile()
