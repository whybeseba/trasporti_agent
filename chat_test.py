"""Chat di collaudo: impersona un cliente, come farà il portale in Fase 3.
Passa dall'ORCHESTRATORE CLIENTI: il router sceglie tra gli specialisti del
registro agents_clienti.yml (costi DKV, normativa, ...).

Mostra in tempo reale che cosa fa il sistema: scelta del router, specialista
che prende in carico, chiamate al modello (con token e velocità), tool
chiamati con argomenti e risultati, contesto consumato.
Uso:  python chat_test.py"""
from urllib.parse import urlparse

import yaml

from agents.llm import config_ruolo
from agents.orchestrator_clienti import costruisci_orchestratore_cliente
from tools import tracing
from tools.db import query, salva_conversazione

traccia = tracing.attiva()

clienti = query("""SELECT id, nome_dkv AS codice_dkv,
                          COALESCE(ragione_sociale, nome_dkv) AS cliente
                   FROM clienti ORDER BY cliente""")
print(clienti.to_string(index=False))
cid = int(input("\nID del cliente da impersonare: "))
nome = clienti.set_index("id").loc[cid, "cliente"]

agente = costruisci_orchestratore_cliente(cid, nome)

with open("config/agents_clienti.yml", encoding="utf-8") as f:
    registro = yaml.safe_load(f)["agenti"]
team = ", ".join(f"{n} ({'per-cliente' if i.get('per_cliente') else 'condiviso'})"
                 for n, i in registro.items())

url_orch, mod_orch = config_ruolo("orchestratore")
url_sub, mod_sub = config_ruolo("subagente")
motori = {"motore": f"{mod_orch} @ {urlparse(url_orch).hostname}"}
if (url_orch, mod_orch) != (url_sub, mod_sub):
    motori = {"motore orchestratore": f"{mod_orch} @ {urlparse(url_orch).hostname}",
              "motore sub-agenti": f"{mod_sub} @ {urlparse(url_sub).hostname}"}

tracing.pannello_avvio("Chat di collaudo — area clienti", {
    "cliente impersonato": f"{nome} (id {cid})",
    "team di specialisti": team,
    **motori,
    "finestra di contesto": f"{traccia.max_contesto} token",
    "comandi": "'esci' per terminare",
})

storia = []
turno = 0
try:
    while True:
        domanda = input("Cliente: ").strip()
        if not domanda:
            continue
        if domanda.lower() in ("esci", "exit", "quit"):
            break
        turno += 1
        traccia.inizio_turno(turno, domanda, etichetta=f"cliente {nome}")
        storia.append({"role": "user", "content": domanda})
        try:
            risultato = agente.invoke({"messages": storia},
                                      {"callbacks": [traccia]})
        except Exception as e:
            storia.pop()          # turno fallito: non sporcare la storia
            traccia.console.print(f"[red]❌ errore durante la risposta:[/red] {e}\n")
            continue
        storia = risultato["messages"]
        risposta = storia[-1].content
        traccia.fine_turno(risposta)
        salva_conversazione(cid, domanda, risposta)
finally:
    traccia.riepilogo_sessione()
