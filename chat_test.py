"""Chat di collaudo: impersona un cliente, come farà il portale in Fase 3.
Uso:  python chat_test.py"""
from agents.agente_cliente import costruisci_agente_cliente
from tools.db import query, salva_conversazione

clienti = query("""SELECT id, nome_dkv AS codice_dkv,
                          COALESCE(ragione_sociale, nome_dkv) AS cliente
                   FROM clienti ORDER BY cliente""")
print(clienti.to_string(index=False))
cid = int(input("\nID del cliente da impersonare: "))
nome = clienti.set_index("id").loc[cid, "cliente"]

agente = costruisci_agente_cliente(cid, nome)
storia = []
print(f"\nStai chattando come «{nome}». Scrivi 'esci' per terminare.\n")
while True:
    domanda = input("Cliente: ").strip()
    if not domanda:
        continue
    if domanda.lower() in ("esci", "exit", "quit"):
        break
    storia.append({"role": "user", "content": domanda})
    risultato = agente.invoke({"messages": storia})
    storia = risultato["messages"]
    risposta = storia[-1].content
    print(f"\nAssistente: {risposta}\n")
    salva_conversazione(cid, domanda, risposta)
