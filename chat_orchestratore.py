"""Chat interna del gestore (passa dall'orchestratore).
Uso:  python chat_orchestratore.py"""
from agents.orchestrator import costruisci_orchestratore
from tools.db import salva_conversazione

orchestratore = costruisci_orchestratore()
storia = []
print("Assistente gestore pronto. Scrivi 'esci' per terminare.\n")
while True:
    domanda = input("Gestore: ").strip()
    if not domanda:
        continue
    if domanda.lower() in ("esci", "exit", "quit"):
        break
    storia.append({"role": "user", "content": domanda})
    risultato = orchestratore.invoke({"messages": storia})
    storia = risultato["messages"]
    risposta = storia[-1].content
    print(f"\nAssistente: {risposta}\n")
    salva_conversazione(0, domanda, risposta, canale="gestore")   # 0 = interno
