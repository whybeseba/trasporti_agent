"""Carica i sub-agenti elencati nel registro YAML."""
import importlib

import yaml


def carica_agenti(percorso: str = "config/agents_config.yml") -> dict:
    with open(percorso, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    agenti = {}
    for nome, info in cfg["agenti"].items():
        modulo = importlib.import_module(info["modulo"])
        costruttore = getattr(modulo, info["funzione"])
        agenti[nome] = {"agente": costruttore(), "descrizione": info["descrizione"]}
        print(f"✅ Sub-agente caricato: {nome}")
    return agenti
