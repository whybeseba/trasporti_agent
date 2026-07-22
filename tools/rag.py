"""Collegamento a ChromaDB e ricerca nel corpus normativo (RAG).

Il corpus è CONDIVISO tra tutti i clienti: contiene solo norme e circolari
pubbliche, MAI dati di clienti. È il motivo per cui l'agente Normativa può
essere `per_cliente: false` nel registro.

Gli embedding sono calcolati in locale sulla CPU del server (modello
multilingue, adatto all'italiano): la GPU su OVH serve solo a generare le
risposte, non alla ricerca.
"""
import os

import chromadb
from chromadb.utils import embedding_functions

MODELLO_EMBEDDING = "paraphrase-multilingual-MiniLM-L12-v2"
COLLEZIONE = "normativa"

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


def cerca_normativa(domanda: str, n: int = 4) -> list[dict]:
    """I passaggi del corpus più pertinenti alla domanda, con fonte e data.
    Restituisce una lista di dict: testo, titolo, fonte, data, file, distanza
    (0 = identico, più alto = meno pertinente)."""
    ris = collezione().query(query_texts=[domanda], n_results=n)
    risultati = []
    for testo, meta, dist in zip(ris["documents"][0], ris["metadatas"][0],
                                 ris["distances"][0]):
        risultati.append({
            "testo": testo,
            "titolo": meta.get("titolo", ""),
            "fonte": meta.get("fonte", ""),
            "data": meta.get("data", ""),
            "file": meta.get("file", ""),
            "distanza": dist,
        })
    return risultati
