"""Interroga il corpus normativo SENZA passare dal modello: mostra i passaggi
che il RAG consegnerebbe all'agente. Serve a capire se l'indice funziona e se
il corpus copre la domanda, separando i problemi di ricerca da quelli di
generazione.
Uso:  python -m scripts.test_normativa "come funziona il cabotaggio in Francia?"
"""
import sys

from tools.rag import cerca_normativa

domanda = " ".join(sys.argv[1:]) or "quanti trasporti di cabotaggio sono ammessi?"
print(f"Domanda: {domanda}\n")

risultati = cerca_normativa(domanda)
if not risultati:
    raise SystemExit("Nessun risultato: il corpus è indicizzato? "
                     "(python -m scripts.indicizza_normativa)")

for i, r in enumerate(risultati, 1):
    print(f"[{i}] {r['titolo']} — {r['fonte']}, {r['data'] or 'senza data'} "
          f"(distanza {r['distanza']:.3f}, file {r['file']})")
    print(r["testo"][:400].strip())
    print()
