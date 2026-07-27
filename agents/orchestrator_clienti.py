"""Orchestratore CLIENTI: il coordinatore del team di specialisti esposto
ai clienti. Si costruisce A OGNI SESSIONE, ancorato al cliente del login,
perché i membri per_cliente del team nascono con quel cliente_id.

Carica SOLO config/agents_clienti.yml: gli agenti interni del gestore,
per questo orchestratore, non esistono."""
from langgraph.graph import StateGraph, MessagesState, START, END

from agents.llm import costruisci_llm
from agents.registry import carica_agenti_clienti


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

    def router(state: StatoCliente):
        r = llm.invoke([{"role": "system", "content": _prompt_router()}]
                       + state["messages"])
        testo = r.content.strip().lower()
        for nome in agenti:
            if nome in testo:
                return {"prossimo": nome}
        return {"prossimo": "nessuno"}

    def _nodo_specialista(nome: str):
        def esegui(state: StatoCliente):
            ris = agenti[nome]["agente"].invoke({"messages": state["messages"]})
            return {"messages": [ris["messages"][-1]]}
        return esegui

    def risposta_diretta(state: StatoCliente):
        r = llm.invoke([{"role": "system", "content":
                         f"Sei l'assistente dell'area clienti e stai parlando "
                         f"con l'azienda cliente «{nome_cliente}». Puoi aiutare "
                         "su due temi: i suoi consumi e spese DKV, e la "
                         "normativa dell'autotrasporto. Rispondi in italiano, "
                         "cortese e sintetico; non inventare mai numeri né "
                         "riferimenti normativi."}] + state["messages"])
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
