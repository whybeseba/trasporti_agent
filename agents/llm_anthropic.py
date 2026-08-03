"""Motore di inferenza alternativo: API Anthropic (modelli Claude).

Serve a collaudare il sistema su Claude senza toccare nulla del lavoro fatto
su vLLM/OVH: agenti, tool, prompt, registri e orchestratori restano identici,
cambia solo l'oggetto LLM che ricevono. Lo scambio tra i due motori si fa con
`agents.llm.imposta_motore("anthropic")` o con MOTORE_AI nel .env.

Configurazione (.env):
  ANTHROPIC_API_KEY        la chiave (obbligatoria)
  ANTHROPIC_MODEL          modello per tutti i ruoli (default: claude-haiku-4-5)
  ANTHROPIC_MODEL_ORCHESTRATORE / _SUBAGENTI   opzionali, per ruolo
  ANTHROPIC_MAX_TOKENS     tetto ai token generati per risposta (default 16000)
  ANTHROPIC_CACHING        true/false: prompt caching (default true, vedi sotto)

📖 PROMPT CACHING — in questa architettura la storia della chat viene
rimandata intera al modello a ogni messaggio, quindi senza cache si ripaga
ogni volta tutto il passato. Con il caching attivo la parte già vista costa
un decimo. Qui usiamo il caching automatico (l'API mette il punto di cache
sull'ultimo blocco riutilizzabile). Nei riepiloghi delle chat vedrai quanti
token sono stati riletti dalla cache: è la conferma che sta funzionando.
Se la tua versione dell'SDK non accettasse il parametro, metti
ANTHROPIC_CACHING=false nel .env e riprova.
"""
import os

from dotenv import load_dotenv

load_dotenv()

MODELLO_DEFAULT = "claude-haiku-4-5"

# Modelli che NON accettano più i parametri di campionamento: passare
# temperature (o top_p/top_k) restituisce un errore 400. Elenco da estendere
# man mano che escono modelli nuovi; i modelli più vecchi accettano ancora
# temperature e per loro la impostiamo a 0 (precisione, non creatività).
SENZA_TEMPERATURE = {
    "claude-opus-5", "claude-sonnet-5", "claude-fable-5", "claude-mythos-5",
    "claude-opus-4-8", "claude-opus-4-7",
}

_VERI = {"1", "true", "yes", "si", "sì"}


def caching_attivo() -> bool:
    return os.environ.get("ANTHROPIC_CACHING", "true").strip().lower() in _VERI


def config_ruolo_anthropic(ruolo: str = "subagente") -> str:
    """Il modello Claude da usare per un ruolo (orchestratore o subagente).
    Con un solo modello configurato i due ruoli coincidono."""
    suffisso = "_ORCHESTRATORE" if ruolo == "orchestratore" else "_SUBAGENTI"
    return (os.environ.get(f"ANTHROPIC_MODEL{suffisso}")
            or os.environ.get("ANTHROPIC_MODEL", MODELLO_DEFAULT)).strip()


def costruisci_llm_anthropic(ruolo: str = "subagente", temperature: float = 0):
    from langchain_anthropic import ChatAnthropic   # import pigro

    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise SystemExit("❌ ANTHROPIC_API_KEY mancante nel file .env")

    modello = config_ruolo_anthropic(ruolo)
    parametri = {
        "model": modello,
        "max_tokens": int(os.environ.get("ANTHROPIC_MAX_TOKENS", "16000")),
    }
    if modello not in SENZA_TEMPERATURE:
        parametri["temperature"] = temperature
    if caching_attivo():
        # caching automatico: l'API mette il punto di cache sull'ultimo
        # blocco riutilizzabile (system prompt + tool + storia già vista)
        parametri["model_kwargs"] = {"cache_control": {"type": "ephemeral"}}
    return ChatAnthropic(**parametri)
