"""Interroga il corpus normativo SENZA passare dal modello: mostra i passaggi
che il RAG consegnerebbe all'agente. Serve a capire se l'indice funziona e se
il corpus copre la domanda, separando i problemi di ricerca da quelli di
generazione. Mostra anche i passaggi oltre la soglia di pertinenza (che
all'agente NON arrivano): utile per tarare SOGLIA_DISTANZA in tools/rag.py.
Uso:  python -m scripts.test_normativa "come funziona il cabotaggio in Francia?"
"""
import sys

from tools.rag import SOGLIA_DISTANZA, cerca_normativa

domanda = " ".join(sys.argv[1:]) or "quanti trasporti di cabotaggio sono ammessi?"
print(f"Domanda: {domanda}   (soglia di pertinenza: {SOGLIA_DISTANZA})\n")

risultati = cerca_normativa(domanda, soglia=None)   # tutti, anche oltre soglia
if not risultati:
    raise SystemExit("Nessun risultato: il corpus è indicizzato? "
                     "(python -m scripts.indicizza_normativa)")

consegnati = 0
for i, r in enumerate(risultati, 1):
    scartato = r["distanza"] > SOGLIA_DISTANZA
    consegnati += not scartato
    marchio = "✂️  SCARTATO (oltre soglia, l'agente non lo vede)" if scartato else "✅"
    print(f"[{i}] {marchio}  distanza {r['distanza']:.3f}")
    print(f"    {r['titolo']} — {r['fonte']}, {r['data'] or 'senza data'} "
          f"(file {r['file']})")
    print("    " + r["testo"][:400].strip().replace("\n", "\n    "))
    print()

if consegnati == 0:
    print("⚠️  Tutti gli estratti sono oltre soglia: l'agente risponderà che il "
          "tema non è coperto. Se invece il primo estratto ti sembra pertinente, "
          "alza SOGLIA_DISTANZA in tools/rag.py; se il corpus non copre il tema, "
          "aggiungi il documento giusto e re-indicizza.")
