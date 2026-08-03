"""Il ciclo delle chat di collaudo, condiviso dai due motori.

chat_test.py / chat_orchestratore.py (vLLM su OVH) e le loro varianti
_anthropic.py scelgono il motore e poi chiamano una di queste due funzioni:
il comportamento della chat è identico, cambia solo chi risponde.

Gli import dei moduli che costruiscono agenti sono volutamente DENTRO le
funzioni: il registro costruisce i sub-agenti al momento dell'import, quindi
il motore va scelto prima."""
import yaml

from agents.llm import descrizione_motore
from tools import tracing


def _riga_motori() -> dict[str, str]:
    """Un motore solo se i due ruoli coincidono, due righe se differiscono."""
    orch = descrizione_motore("orchestratore")
    sub = descrizione_motore("subagente")
    if orch == sub:
        return {"motore": orch}
    return {"motore orchestratore": orch, "motore sub-agenti": sub}


def _ciclo(traccia, agente, etichetta: str, invito: str, salva) -> None:
    storia = []
    turno = 0
    try:
        while True:
            domanda = input(f"{invito}: ").strip()
            if not domanda:
                continue
            if domanda.lower() in ("esci", "exit", "quit"):
                break
            turno += 1
            traccia.inizio_turno(turno, domanda, etichetta=etichetta)
            storia.append({"role": "user", "content": domanda})
            try:
                risultato = agente.invoke({"messages": storia},
                                          {"callbacks": [traccia]})
            except Exception as e:
                storia.pop()      # turno fallito: non sporcare la storia
                traccia.console.print(f"[red]❌ errore durante la risposta:[/red] {e}\n")
                continue
            storia = risultato["messages"]
            risposta = storia[-1].content
            traccia.fine_turno(risposta)
            salva(domanda, risposta)
    finally:
        traccia.riepilogo_sessione()


def chat_cliente() -> None:
    """Impersona un cliente, come farà il portale in Fase 3: passa
    dall'orchestratore clienti, che smista tra gli specialisti."""
    from agents.orchestrator_clienti import costruisci_orchestratore_cliente
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
    team = ", ".join(
        f"{n} ({'per-cliente' if i.get('per_cliente') else 'condiviso'})"
        for n, i in registro.items())

    tracing.pannello_avvio("Chat di collaudo — area clienti", {
        "cliente impersonato": f"{nome} (id {cid})",
        "team di specialisti": team,
        **_riga_motori(),
        "finestra di contesto": f"{traccia.max_contesto} token",
        "comandi": "'esci' per terminare",
    })

    _ciclo(traccia, agente, etichetta=f"cliente {nome}", invito="Cliente",
           salva=lambda d, r: salva_conversazione(cid, d, r))


def chat_gestore() -> None:
    """La chat interna del gestore: passa dall'orchestratore interno."""
    from agents.orchestrator import AGENTI, costruisci_orchestratore
    from tools.db import salva_conversazione

    traccia = tracing.attiva()
    orchestratore = costruisci_orchestratore()

    tracing.pannello_avvio("Chat interna — vista gestore", {
        "sub-agenti interni": ", ".join(AGENTI),
        **_riga_motori(),
        "finestra di contesto": f"{traccia.max_contesto} token",
        "comandi": "'esci' per terminare",
    })

    _ciclo(traccia, orchestratore, etichetta="gestore", invito="Gestore",
           salva=lambda d, r: salva_conversazione(0, d, r, canale="gestore"))
