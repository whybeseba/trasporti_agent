"""Interroga il corpus normativo SENZA passare dall'agente: mostra il
percorso completo della ricerca multi-query — le riformulazioni generate
dal motore, la classifica fusa (RRF) e quali passaggi supererebbero la
soglia di pertinenza. Serve a capire se un problema è di ricerca (corpus,
soglia, riformulazioni) o di generazione (l'agente).
Uso:  python -m scripts.test_normativa "come funziona il cabotaggio in Francia?"
"""
import sys

from tools.rag import (SOGLIA_DISTANZA, cerca_normativa_multi,
                       genera_riformulazioni)

domanda = " ".join(sys.argv[1:]) or "quanti trasporti di cabotaggio sono ammessi?"
print(f"Domanda: {domanda}   (soglia di pertinenza: {SOGLIA_DISTANZA})\n")

riformulazioni = genera_riformulazioni(domanda)
if riformulazioni:
    print("Riformulazioni generate dal motore:")
    for r in riformulazioni:
        print(f"  · {r}")
else:
    print("⚠️  Nessuna riformulazione (motore vLLM spento o .env incompleto): "
          "interrogo solo con la domanda originale")
print()

interrogazioni = 1 + len(riformulazioni)
risultati = cerca_normativa_multi(domanda, n=8, soglia=None,
                                  domande_extra=riformulazioni)
if not risultati:
    raise SystemExit("Nessun risultato: il corpus è indicizzato? "
                     "(python -m scripts.indicizza_normativa)")

consegnati = 0
for i, r in enumerate(risultati, 1):
    scartato = r["distanza"] > SOGLIA_DISTANZA
    consegnati += not scartato
    marchio = "✂️  SCARTATO (oltre soglia, l'agente non lo vede)" if scartato else "✅"
    print(f"[{i}] {marchio}  distanza {r['distanza']:.3f} · "
          f"trovato da {r['interrogazioni']}/{interrogazioni} interrogazioni")
    print(f"    {r['titolo']} — {r['fonte']}, {r['data'] or 'senza data'} "
          f"(file {r['file']})")
    print("    " + r["testo"][:400].strip().replace("\n", "\n    "))
    print()

if consegnati == 0:
    print("⚠️  Tutti gli estratti sono oltre soglia: l'agente risponderà che il "
          "tema non è coperto. Se invece il primo estratto ti sembra pertinente, "
          "alza SOGLIA_DISTANZA in tools/rag.py; se il corpus non copre il tema, "
          "aggiungi il documento giusto e re-indicizza.")
else:
    print(f"All'agente arriverebbero i migliori {min(consegnati, 5)} "
          f"passaggi entro soglia (ordinati per consenso tra le interrogazioni).")
