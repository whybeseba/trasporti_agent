"""Stima e calcolo dei costi sull'API Anthropic.

Serve a decidere il prezzo da fare ai clienti. Due usi:

1. STIMA (motore vLLM): i token li conta il tokenizer di Qwen3, non quello di
   Claude, quindi il risultato è un ordine di grandezza. Per il numero esatto
   c'è `scripts/conta_token.py`, che misura i prompt reali con l'endpoint
   count_tokens di Anthropic.
2. CALCOLO ESATTO (motore Anthropic): l'API riporta nella risposta i token
   effettivamente fatturati, cache inclusa — lì il costo è esatto.

📖 PROMPT CACHING — perché conta tantissimo qui. In chat la storia viene
rimandata intera al modello a ogni messaggio: senza cache paghi ogni volta
tutto il passato a prezzo pieno. Con il caching la parte già vista costa un
decimo (le riletture) e la scrittura in cache costa 1,25 volte. In una
conversazione che cresce è la differenza tra un servizio sostenibile e uno
che non sta in piedi.

Listino Anthropic in $ per milione di token, giugno 2026 (verificare prima di
fissare i prezzi ai clienti: i listini cambiano).
"""

LISTINO = {
    "claude-opus-5":    {"nome": "Claude Opus 5",    "in": 5.00, "out": 25.00},
    "claude-sonnet-5":  {"nome": "Claude Sonnet 5",  "in": 3.00, "out": 15.00},
    "claude-haiku-4-5": {"nome": "Claude Haiku 4.5", "in": 1.00, "out": 5.00},
}

MOLTIPLICATORE_LETTURA_CACHE = 0.1     # token riletti dalla cache
MOLTIPLICATORE_SCRITTURA_CACHE = 1.25  # token scritti in cache (TTL 5 minuti)

# Quota di input che in una chat con storia rimandata risulta già in cache.
# Usata SOLO nelle stime: col motore Anthropic la quota vera si legge dai dati.
QUOTA_CACHE_TIPICA = 0.8

CAMBIO_EUR_USD = 0.92   # aggiornalo quando serve precisione sui preventivi


def prezzi(modello: str) -> dict | None:
    """Voce di listino per un id modello ('claude-haiku-4-5'), None se ignoto."""
    return LISTINO.get((modello or "").strip())


def costo(tok_in: int, tok_out: int, prezzo_in: float, prezzo_out: float,
          quota_cache: float = 0.0) -> float:
    """Costo in dollari di tok_in token di input e tok_out di output.

    quota_cache = 0  → caching NON attivo: tutto l'input a prezzo pieno.
    quota_cache > 0  → caching attivo: quella frazione dell'input è riletta
                       dalla cache (un decimo del prezzo) e il resto viene
                       scritto in cache (1,25 volte il prezzo)."""
    if quota_cache <= 0:
        input_usd = tok_in * prezzo_in / 1_000_000
    else:
        letti = tok_in * quota_cache
        scritti = tok_in - letti
        input_usd = (letti * prezzo_in * MOLTIPLICATORE_LETTURA_CACHE
                     + scritti * prezzo_in * MOLTIPLICATORE_SCRITTURA_CACHE) / 1_000_000
    return input_usd + tok_out * prezzo_out / 1_000_000


def costo_esatto(modello: str, tok_in_pieno: int, tok_out: int,
                 cache_lette: int = 0, cache_scritte: int = 0) -> float | None:
    """Costo in dollari dai token REALI riportati dall'API Anthropic.
    tok_in_pieno = input non servito dalla cache. None se il modello non è
    in listino (aggiungilo a LISTINO)."""
    p = prezzi(modello)
    if p is None:
        return None
    return (tok_in_pieno * p["in"]
            + cache_lette * p["in"] * MOLTIPLICATORE_LETTURA_CACHE
            + cache_scritte * p["in"] * MOLTIPLICATORE_SCRITTURA_CACHE
            + tok_out * p["out"]) / 1_000_000


def stima(tok_in: int, tok_out: int) -> list[dict]:
    """Per ogni modello del listino: costo senza caching e con caching tipico,
    in dollari e in euro."""
    righe = []
    for info in LISTINO.values():
        senza = costo(tok_in, tok_out, info["in"], info["out"], quota_cache=0.0)
        con = costo(tok_in, tok_out, info["in"], info["out"],
                    quota_cache=QUOTA_CACHE_TIPICA)
        righe.append({
            "modello": info["nome"],
            "usd_senza_cache": senza,
            "usd_con_cache": con,
            "eur_senza_cache": senza * CAMBIO_EUR_USD,
            "eur_con_cache": con * CAMBIO_EUR_USD,
        })
    return righe
