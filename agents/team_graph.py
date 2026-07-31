"""Il grafo comune dei due orchestratori (clienti e gestore).

Il router non sceglie più UN solo specialista: SCOMPONE la domanda in
incarichi — uno per ogni specialista competente, ciascuno con la propria
sotto-domanda — e il grafo li esegue IN PARALLELO (Send API di LangGraph:
due chiamate simultanee sono esattamente il carico su cui vLLM rende).
Con un solo incarico il flusso resta identico a prima; con più incarichi
un passaggio finale compone le risposte in una sola, senza aggiungere nulla.

Stesso meccanismo per i due team, registri rigorosamente separati: chi
costruisce il grafo decide quali agenti esistono."""
import json
import operator
import re
from typing import Annotated

from langchain_core.messages import AIMessage
from langgraph.graph import StateGraph, MessagesState, START, END
from langgraph.types import Send

from tools import tracing


class StatoTeam(MessagesState):
    incarichi: list                              # [{"specialista", "domanda"}]
    risposte: Annotated[list, operator.add]      # [(specialista, testo)] dai rami


def _prompt_router(agenti: dict, intro: str) -> str:
    righe = "\n".join(f"- {n}: {i['descrizione'].strip()}" for n, i in agenti.items())
    return (
        intro + "\nSpecialisti disponibili:\n" + righe + "\n\n"
        "L'ultima domanda può riguardare UNO specialista, PIÙ specialisti "
        "insieme, o nessuno.\n"
        "Rispondi SOLO con un array JSON, nessun altro testo. Formato:\n"
        '[{"specialista": "<nome>", "domanda": "<sotto-domanda per lui>"}]\n'
        "Regole:\n"
        "- un elemento per OGNI specialista necessario a coprire tutta la domanda\n"
        "- ogni sotto-domanda deve essere autosufficiente e contenere SOLO la "
        "parte di competenza di quello specialista\n"
        "- array vuoto [] per saluti o domande generiche a cui rispondere "
        "direttamente")


def _leggi_incarichi(testo: str, nomi) -> list | None:
    """Estrae gli incarichi dal JSON del router. None = risposta illeggibile
    (il chiamante ripiega sul vecchio comportamento a specialista singolo)."""
    m = re.search(r"\[.*\]", testo, re.S)
    if not m:
        return None
    try:
        dati = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
    if not isinstance(dati, list):
        return None
    incarichi, visti = [], set()
    for el in dati:
        if not isinstance(el, dict):
            continue
        nome = str(el.get("specialista", "")).strip()
        if nome in nomi and nome not in visti:
            visti.add(nome)
            incarichi.append({"specialista": nome,
                              "domanda": str(el.get("domanda") or "").strip()})
    return incarichi


def costruisci_grafo_team(agenti: dict, llm, intro_router: str,
                          prompt_diretta: str):
    """agenti: registro già caricato {nome: {agente, descrizione}}.
    intro_router / prompt_diretta: la voce del team (clienti o gestore)."""
    prompt_router = _prompt_router(agenti, intro_router)

    # I nodi ricevono `config` e lo passano alle chiamate annidate: è ciò che
    # fa arrivare i callback (la traccia) anche dentro i sub-agenti.
    def router(state: StatoTeam, config):
        r = llm.invoke([{"role": "system", "content": prompt_router}]
                       + state["messages"], config)
        incarichi = _leggi_incarichi(r.content, set(agenti))
        if incarichi is None:      # niente JSON: ripiego a specialista singolo
            testo = r.content.strip().lower()
            nome = next((n for n in agenti if n in testo), None)
            incarichi = [{"specialista": nome, "domanda": ""}] if nome else []
        tracing.router_deciso(incarichi, list(agenti))
        return {"incarichi": incarichi}

    def smista(state: StatoTeam):
        if not state["incarichi"]:
            return "nessuno"
        return [Send(i["specialista"],
                     {"messages": state["messages"], "domanda": i["domanda"]})
                for i in state["incarichi"]]

    def _nodo_specialista(nome: str):
        def esegui(state, config):
            # allo specialista arriva la storia con l'ultima domanda
            # SOSTITUITA dalla sua sotto-domanda: contesto intero, compito suo
            messaggi = list(state["messages"])
            if state.get("domanda"):
                messaggi = messaggi[:-1] + [{"role": "user",
                                             "content": state["domanda"]}]
            tracing.specialista_inizio(nome)
            try:
                ris = agenti[nome]["agente"].invoke({"messages": messaggi}, config)
            finally:
                tracing.specialista_fine()
            return {"risposte": [(nome, ris["messages"][-1].content)]}
        return esegui

    def componi(state: StatoTeam, config):
        ordine = {i["specialista"]: k for k, i in enumerate(state["incarichi"])}
        risposte = sorted(state["risposte"], key=lambda r: ordine.get(r[0], 99))
        if len(risposte) == 1:     # un solo specialista: la sua risposta È la risposta
            return {"messages": [AIMessage(content=risposte[0][1])]}

        parti = "\n\n".join(f"[{n}]\n{r}" for n, r in risposte)
        domanda = state["messages"][-1].content
        tracing.specialista_inizio("orchestratore · composizione")
        try:
            r = llm.invoke([
                {"role": "system", "content":
                 "Hai smistato la domanda ai tuoi specialisti; qui sotto le "
                 "loro risposte, col nome tra parentesi quadre. Componi "
                 "UN'unica risposta in italiano: usa SOLO le informazioni "
                 "delle risposte, senza aggiungere nulla di tuo; conserva le "
                 "citazioni delle fonti e le note o disclaimer presenti; "
                 "ordina per argomento, chiaro e sintetico."},
                {"role": "user", "content":
                 f"Domanda: {domanda}\n\nRisposte degli specialisti:\n\n{parti}"},
            ], config)
        finally:
            tracing.specialista_fine()
        return {"messages": [r]}

    def risposta_diretta(state: StatoTeam, config):
        tracing.specialista_inizio("orchestratore · risposta diretta")
        try:
            r = llm.invoke([{"role": "system", "content": prompt_diretta}]
                           + state["messages"], config)
        finally:
            tracing.specialista_fine()
        return {"messages": [r]}

    grafo = StateGraph(StatoTeam)
    grafo.add_node("router", router)
    grafo.add_node("componi", componi)
    grafo.add_node("nessuno", risposta_diretta)
    for nome in agenti:
        grafo.add_node(nome, _nodo_specialista(nome))
        grafo.add_edge(nome, "componi")
    grafo.add_edge(START, "router")
    grafo.add_conditional_edges("router", smista)
    grafo.add_edge("componi", END)
    grafo.add_edge("nessuno", END)
    return grafo.compile()
