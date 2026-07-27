"""Chat interna del gestore (passa dall'orchestratore interno).

Mostra in tempo reale che cosa fa il sistema: scelta del router, sub-agente
che prende in carico, chiamate al modello (con token e velocità), tool
chiamati con argomenti e risultati, contesto consumato.
Uso:  python chat_orchestratore.py"""
from urllib.parse import urlparse

from agents.llm import config_ruolo
from tools import tracing

traccia = tracing.attiva()

# importato dopo tracing.attiva(): il registro carica i sub-agenti all'import
from agents.orchestrator import AGENTI, costruisci_orchestratore  # noqa: E402
from tools.db import salva_conversazione  # noqa: E402

orchestratore = costruisci_orchestratore()

url_orch, mod_orch = config_ruolo("orchestratore")
url_sub, mod_sub = config_ruolo("subagente")
motori = {"motore": f"{mod_orch} @ {urlparse(url_orch).hostname}"}
if (url_orch, mod_orch) != (url_sub, mod_sub):
    motori = {"motore orchestratore": f"{mod_orch} @ {urlparse(url_orch).hostname}",
              "motore sub-agenti": f"{mod_sub} @ {urlparse(url_sub).hostname}"}

tracing.pannello_avvio("Chat interna — vista gestore", {
    "sub-agenti interni": ", ".join(AGENTI),
    **motori,
    "finestra di contesto": f"{traccia.max_contesto} token",
    "comandi": "'esci' per terminare",
})

storia = []
turno = 0
try:
    while True:
        domanda = input("Gestore: ").strip()
        if not domanda:
            continue
        if domanda.lower() in ("esci", "exit", "quit"):
            break
        turno += 1
        traccia.inizio_turno(turno, domanda, etichetta="gestore")
        storia.append({"role": "user", "content": domanda})
        try:
            risultato = orchestratore.invoke({"messages": storia},
                                             {"callbacks": [traccia]})
        except Exception as e:
            storia.pop()          # turno fallito: non sporcare la storia
            traccia.console.print(f"[red]❌ errore durante la risposta:[/red] {e}\n")
            continue
        storia = risultato["messages"]
        risposta = storia[-1].content
        traccia.fine_turno(risposta)
        salva_conversazione(0, domanda, risposta, canale="gestore")   # 0 = interno
finally:
    traccia.riepilogo_sessione()
