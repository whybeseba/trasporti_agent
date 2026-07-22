"""Carica i sub-agenti dai registri YAML.

Due registri, due funzioni, mai mescolati:
- carica_agenti          → config/agents_config.yml  (team INTERNO del gestore)
- carica_agenti_clienti  → config/agents_clienti.yml (team esposto ai CLIENTI)
"""
import importlib

import yaml

# Gli agenti condivisi (per_cliente: false) non dipendono dalla sessione:
# costruiti una volta e riusati, qualunque sia il cliente collegato.
_cache_condivisi: dict = {}


def _costruttore(info: dict):
    modulo = importlib.import_module(info["modulo"])
    return getattr(modulo, info["funzione"])


def carica_agenti(percorso: str = "config/agents_config.yml") -> dict:
    with open(percorso, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    agenti = {}
    for nome, info in cfg["agenti"].items():
        agenti[nome] = {"agente": _costruttore(info)(),
                        "descrizione": info["descrizione"]}
        print(f"✅ Sub-agente caricato: {nome}")
    return agenti


def carica_agenti_clienti(cliente_id: int, nome_cliente: str,
                          percorso: str = "config/agents_clienti.yml") -> dict:
    """Il team di specialisti per UNA sessione cliente: gli agenti ancorati
    (per_cliente: true) nascono qui con il cliente_id del login, quelli
    condivisi arrivano dalla cache."""
    with open(percorso, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    agenti = {}
    for nome, info in cfg["agenti"].items():
        if info.get("per_cliente"):
            agente = _costruttore(info)(cliente_id, nome_cliente)
        else:
            if nome not in _cache_condivisi:
                _cache_condivisi[nome] = _costruttore(info)()
                print(f"✅ Agente condiviso caricato: {nome}")
            agente = _cache_condivisi[nome]
        agenti[nome] = {"agente": agente, "descrizione": info["descrizione"]}
    return agenti
