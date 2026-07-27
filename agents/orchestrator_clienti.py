"""Orchestratore CLIENTI: il coordinatore del team di specialisti esposto
ai clienti. Si costruisce A OGNI SESSIONE, ancorato al cliente del login,
perché i membri per_cliente del team nascono con quel cliente_id.

Carica SOLO config/agents_clienti.yml: gli agenti interni del gestore,
per questo orchestratore, non esistono."""
from langgraph.graph import StateGraph, MessagesState, START, END

from agents.llm import costruisci_llm
from agents.registry import carica_agenti_clienti
from tools import tracing


class StatoCliente(MessagesState):
    prossimo: str


def costruisci_orchestratore_cliente(cliente_id: int, nome_cliente: str):
    agenti = carica_agenti_clienti(cliente_id, nome_cliente)
    llm = costruisci_llm("orchestratore")   # router e risposte dirette

    def _prompt_router() -> str:
        righe = "\n".join(f"- {n}: {i['descrizione'].strip()}"
                          for n, i in agenti.items())
        return ("Sei lo smistatore dell'assistente dell'area clienti di un "
                "gestore di servizi per l'autotrasporto.\n"
                "Specialisti disponibili:\n" + righe +
                "\n- nessuno: saluti, ringraziamenti o domande generiche su "
                "cosa sa fare l'assistente.\n\n"
                "Leggi l'ultima domanda e rispondi SOLO con il nome dello "
                "specialista più adatto (oppure 'nessuno'). Nessun'altra parola.")

    # I nodi ricevono `config` e lo passano alle chiamate annidate: è ciò che
    # fa arrivare i callback (e quindi la traccia) anche dentro i sub-agenti.
    def router(state: StatoCliente, config):
        r = llm.invoke([{"role": "system", "content": _prompt_router()}]
                       + state["messages"], config)
        testo = r.content.strip().lower()
        scelta = next((n for n in agenti if n in testo), "nessuno")
        tracing.router_deciso(scelta, list(agenti))
        return {"prossimo": scelta}

    def _nodo_specialista(nome: str):
        def esegui(state: StatoCliente, config):
            tracing.specialista_inizio(nome)
            try:
                ris = agenti[nome]["agente"].invoke(
                    {"messages": state["messages"]}, config)
            finally:
                tracing.specialista_fine()
            return {"messages": [ris["messages"][-1]]}
        return esegui

    def risposta_diretta(state: StatoCliente, config):
        tracing.specialista_inizio("orchestratore · risposta diretta")
        try:
            r = llm.invoke([{"role": "system", "content":
                             f"Sei l'assistente dell'area clienti e stai parlando "
                             f"con l'azienda cliente «{nome_cliente}». Puoi aiutare "
                             "su due temi: i suoi consumi e spese DKV, e la "
                             "normativa dell'autotrasporto. Rispondi in italiano, "
                             "cortese e sintetico; non inventare mai numeri né "
                             "riferimenti normativi."}] + state["messages"], config)
        finally:
            tracing.specialista_fine()
        return {"messages": [r]}

    grafo = StateGraph(StatoCliente)
    grafo.add_node("router", router)
    grafo.add_node("nessuno", risposta_diretta)
    grafo.add_edge("nessuno", END)
    for nome in agenti:
        grafo.add_node(nome, _nodo_specialista(nome))
        grafo.add_edge(nome, END)
    grafo.add_edge(START, "router")
    destinazioni = {n: n for n in agenti} | {"nessuno": "nessuno"}
    grafo.add_conditional_edges("router", lambda s: s["prossimo"], destinazioni)
    return grafo.compile()
