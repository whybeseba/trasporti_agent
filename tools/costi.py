"""Stima di quanto costerebbe il sistema sull'API Anthropic.

Serve a decidere il prezzo da fare ai clienti: le chat di collaudo contano i
token realmente consumati da orchestratore e specialisti, e qui quei numeri
diventano euro.

⚠️ DUE APPROSSIMAZIONI DA TENERE A MENTE
1. I token li conta il tokenizer di Qwen3 (il modello su vLLM), non quello di
   Claude: sullo stesso testo i due contano in modo diverso. La stima è un
   ordine di grandezza, non un preventivo. Per il numero esatto si usa
   l'endpoint `count_tokens` dell'API Anthropic sui prompt reali.
2. Il prezzo dipende molto dal *prompt caching* (vedi sotto): la forbice tra
   i due scenari è larga, ed è lì che si gioca il margine.

📖 PROMPT CACHING — perché conta tantissimo qui. In chat la storia viene
rimandata intera al modello a ogni messaggio: senza cache paghi ogni volta
tutto il passato a prezzo pieno. Con il caching la parte già vista costa un
decimo (le riletture) e la scrittura in cache costa 1,25 volte. In una
conversazione che cresce, la quasi totalità dell'input è "già vista": è la
differenza tra un servizio sostenibile e uno che non sta in piedi.

Listino Anthropic in $ per milione di token, giugno 2026 (verificare prima di
fissare i prezzi ai clienti: i listini cambiano).
"""

# modello → (input $/Mtok, output $/Mtok)
LISTINO = {
    "Claude Opus 5":    (5.00, 25.00),
    "Claude Sonnet 5":  (3.00, 15.00),
    "Claude Haiku 4.5": (1.00, 5.00),
}

MOLTIPLICATORE_LETTURA_CACHE = 0.1     # token riletti dalla cache
MOLTIPLICATORE_SCRITTURA_CACHE = 1.25  # token scritti in cache (TTL 5 minuti)

# Quota di input che in una chat con storia rimandata risulta già in cache.
# 0.8 è prudente: in conversazioni lunghe si sale, sulla prima domanda è 0.
QUOTA_CACHE_TIPICA = 0.8

CAMBIO_EUR_USD = 0.92   # aggiornalo quando serve precisione sui preventivi


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


def stima(tok_in: int, tok_out: int) -> list[dict]:
    """Per ogni modello del listino: costo senza caching e con caching tipico,
    in dollari e in euro."""
    righe = []
    for nome, (p_in, p_out) in LISTINO.items():
        senza = costo(tok_in, tok_out, p_in, p_out, quota_cache=0.0)
        con = costo(tok_in, tok_out, p_in, p_out, quota_cache=QUOTA_CACHE_TIPICA)
        righe.append({
            "modello": nome,
            "usd_senza_cache": senza,
            "usd_con_cache": con,
            "eur_senza_cache": senza * CAMBIO_EUR_USD,
            "eur_con_cache": con * CAMBIO_EUR_USD,
        })
    return righe
