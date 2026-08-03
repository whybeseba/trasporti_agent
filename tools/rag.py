"""Collegamento a ChromaDB e ricerca nel corpus normativo (RAG).

Il corpus è CONDIVISO tra tutti i clienti: contiene solo norme e circolari
pubbliche, MAI dati di clienti. È il motivo per cui l'agente Normativa può
essere `per_cliente: false` nel registro.

Gli embedding sono calcolati in locale sulla CPU del server (modello
multilingue, adatto all'italiano): la GPU su OVH serve solo a generare le
risposte, non alla ricerca.

La ricerca usata dall'agente è MULTI-QUERY (`cerca_normativa_multi`): il
motore riformula la domanda del cliente in più varianti col lessico
tecnico-giuridico del corpus, ogni variante interroga il database, e le
classifiche si fondono con la Reciprocal Rank Fusion — un passaggio trovato
da più riformulazioni è un segnale forte di pertinenza. Il linguaggio di chi
chiede ("quante ore può guidare il mio autista?") e quello delle norme
("periodo di guida giornaliero") spesso non si somigliano: le riformulazioni
servono a colmare esattamente quel divario.
"""
import os
import re

import chromadb
from chromadb.utils import embedding_functions

MODELLO_EMBEDDING = "paraphrase-multilingual-MiniLM-L12-v2"
COLLEZIONE = "normativa"

# Distanza coseno oltre la quale un estratto è considerato non pertinente e
# NON viene consegnato all'agente: passaggi fuori tema in mano al modello
# sono l'innesco classico delle risposte inventate. Tarala con
# scripts/test_normativa.py (che mostra anche gli estratti scartati).
SOGLIA_DISTANZA = 0.7

N_RIFORMULAZIONI = 3      # varianti generate oltre alla domanda originale
N_PER_INTERROGAZIONE = 6  # risultati chiesti a Chroma per ogni interrogazione
_K_RRF = 60               # costante standard della Reciprocal Rank Fusion

_collezione = None


def collezione():
    """Client + collection ChromaDB, creati pigramente e riusati."""
    global _collezione
    if _collezione is None:
        client = chromadb.HttpClient(
            host=os.environ.get("CHROMA_HOST", "localhost"),
            port=int(os.environ.get("CHROMA_PORT", "8001")),
        )
        ef = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name=MODELLO_EMBEDDING)
        _collezione = client.get_or_create_collection(
            COLLEZIONE, embedding_function=ef,
            metadata={"hnsw:space": "cosine"})
    return _collezione


def cerca_normativa(domanda: str, n: int = 4,
                    soglia: float | None = SOGLIA_DISTANZA) -> list[dict]:
    """Ricerca a interrogazione SINGOLA (per debug e confronti; l'agente usa
    cerca_normativa_multi). Restituisce una lista di dict: testo, titolo,
    fonte, data, file, distanza (0 = identico, più alto = meno pertinente).
    Con soglia=None restituisce anche i passaggi oltre soglia."""
    ris = collezione().query(query_texts=[domanda], n_results=n)
    risultati = []
    for testo, meta, dist in zip(ris["documents"][0], ris["metadatas"][0],
                                 ris["distances"][0]):
        if soglia is not None and dist > soglia:
            continue
        risultati.append({
            "testo": testo,
            "titolo": meta.get("titolo", ""),
            "fonte": meta.get("fonte", ""),
            "data": meta.get("data", ""),
            "file": meta.get("file", ""),
            "distanza": dist,
        })
    return risultati


def _estrai_righe(testo: str, quante: int, originale: str) -> list[str]:
    """Ripulisce l'output del modello: una riformulazione per riga, via
    numeri/elenchi, niente doppioni né copie della domanda originale."""
    righe: list[str] = []
    viste = {originale.strip().lower()}
    for riga in testo.splitlines():
        r = re.sub(r"^[\s\-•*\d.)\]]+", "", riga).strip()
        if len(r) < 8 or r.endswith(":"):        # preamboli tipo "Ecco le..."
            continue
        chiave = r.lower()
        if chiave in viste:
            continue
        viste.add(chiave)
        righe.append(r)
    return righe[:quante]


def genera_riformulazioni(domanda: str, quante: int = N_RIFORMULAZIONI,
                          config=None) -> list[str]:
    """Chiede al motore `quante` riformulazioni della domanda, orientate al
    lessico del corpus. Se il motore non è raggiungibile restituisce una
    lista vuota e la ricerca prosegue con la sola domanda originale."""
    from agents.llm import costruisci_llm   # import pigro: rag resta usabile senza .env del motore

    messaggi = [
        {"role": "system", "content":
         "Riformuli domande per la ricerca in un corpus di norme e circolari "
         "dell'autotrasporto (regolamenti UE, circolari ministeriali, testi "
         "giuridici in italiano)."},
        {"role": "user", "content":
         f"Scrivi {quante} riformulazioni diverse della domanda, usando "
         "sinonimi e il lessico tecnico-giuridico della materia (es. "
         "«periodo di guida giornaliero» invece di «ore di guida al "
         "giorno»). Una per riga, senza numeri, elenchi o altro testo.\n\n"
         f"Domanda: {domanda}"},
    ]
    try:
        from tools.messaggi import testo_contenuto
        r = costruisci_llm("subagente").invoke(messaggi, config)
        # con i modelli che ragionano `content` è un elenco di blocchi
        return _estrai_righe(testo_contenuto(r.content), quante, domanda)
    except Exception:
        return []


def cerca_normativa_multi(domanda: str, n: int = 5,
                          soglia: float | None = SOGLIA_DISTANZA,
                          domande_extra: list[str] | None = None,
                          config=None) -> list[dict]:
    """Ricerca MULTI-QUERY: domanda originale + riformulazioni, un'unica
    chiamata batch a Chroma, fusione delle classifiche con RRF, filtro di
    soglia sulla distanza migliore, primi n risultati.

    domande_extra: riformulazioni già pronte (le genera il chiamante, come
    fa scripts/test_normativa per mostrarle); None = generarle qui.
    Ogni risultato riporta anche `interrogazioni`: da quante delle varianti
    è stato trovato — più è alto, più il passaggio è solido."""
    if domande_extra is None:
        domande_extra = genera_riformulazioni(domanda, config=config)
    domande = [domanda] + [d for d in domande_extra if d]

    ris = collezione().query(query_texts=domande,
                             n_results=N_PER_INTERROGAZIONE)

    fusi: dict[str, dict] = {}
    for ids, testi, mete, distanze in zip(ris["ids"], ris["documents"],
                                          ris["metadatas"], ris["distances"]):
        for rango, (i, testo, meta, dist) in enumerate(
                zip(ids, testi, mete, distanze)):
            e = fusi.setdefault(i, {
                "testo": testo,
                "titolo": meta.get("titolo", ""),
                "fonte": meta.get("fonte", ""),
                "data": meta.get("data", ""),
                "file": meta.get("file", ""),
                "distanza": dist,
                "interrogazioni": 0,
                "_rrf": 0.0,
            })
            e["_rrf"] += 1.0 / (_K_RRF + rango + 1)
            e["interrogazioni"] += 1
            e["distanza"] = min(e["distanza"], dist)

    candidati = [e for e in fusi.values()
                 if soglia is None or e["distanza"] <= soglia]
    candidati.sort(key=lambda e: (-e["_rrf"], e["distanza"]))
    for e in candidati:
        del e["_rrf"]
    return candidati[:n]
