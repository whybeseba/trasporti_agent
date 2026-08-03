"""API di SVILUPPO del motore. ⚠️ Non esporre su internet: qui il cliente
viene indicato nell'indirizzo solo per collaudo; nel portale (Fase 3)
arriverà dal login, e questo endpoint di sviluppo verrà eliminato."""
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from agents.orchestrator_clienti import costruisci_orchestratore_cliente
from tools.db import query, salva_conversazione
from tools.messaggi import testo_messaggio

app = FastAPI(title="Motore DKV — API di sviluppo")
_cache_agenti = {}


class Domanda(BaseModel):
    domanda: str


@app.post("/dev/chat/{cliente_id}")
def chat_cliente(cliente_id: int, d: Domanda):
    if cliente_id not in _cache_agenti:
        df = query("""SELECT COALESCE(ragione_sociale, nome_dkv)
                      FROM clienti WHERE id = :i""", {"i": cliente_id})
        if df.empty:
            raise HTTPException(404, "Cliente inesistente")
        _cache_agenti[cliente_id] = costruisci_orchestratore_cliente(
            cliente_id, df.iloc[0, 0])
    ris = _cache_agenti[cliente_id].invoke(
        {"messages": [{"role": "user", "content": d.domanda}]})
    risposta = testo_messaggio(ris["messages"][-1])
    salva_conversazione(cliente_id, d.domanda, risposta, canale="api-dev")
    return {"risposta": risposta}
