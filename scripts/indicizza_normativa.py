"""Indicizza norme e circolari in ChromaDB per l'agente Normativa.

Legge i documenti da dati/normativa/ (.pdf, .txt, .md), li spezza in blocchi,
arricchisce ogni blocco con titolo/fonte/data presi da dati/normativa/fonti.yml
e ricostruisce DA ZERO la collezione: ogni esecuzione è una re-indicizzazione
completa (il corpus è piccolo, la semplicità vale più dell'incrementale).

Uso:  python -m scripts.indicizza_normativa   (dalla cartella principale)
Guida completa: Guida_Indicizzazione_Normativa.md"""
from pathlib import Path

import yaml

CARTELLA = Path("dati/normativa")
MANIFEST = CARTELLA / "fonti.yml"
ESTENSIONI = {".pdf", ".txt", ".md"}
LOTTO = 64          # blocchi inviati a ChromaDB per volta


def estrai_testo(percorso: Path) -> str:
    if percorso.suffix.lower() == ".pdf":
        from pypdf import PdfReader
        return "\n\n".join(pagina.extract_text() or ""
                           for pagina in PdfReader(str(percorso)).pages)
    return percorso.read_text(encoding="utf-8", errors="replace")


def spezza(testo: str, max_car: int = 1200, coda: int = 150) -> list[str]:
    """Divide il testo in blocchi di ~max_car caratteri seguendo i paragrafi;
    ogni blocco riparte con la coda del precedente, così un articolo tagliato
    a metà resta comprensibile."""
    paragrafi = [p.strip() for p in testo.replace("\r", "").split("\n\n")
                 if p.strip()]
    unita = []
    for p in paragrafi:
        while len(p) > max_car:        # paragrafo-monstre (tabelle, PDF senza a capo)
            unita.append(p[:max_car])
            p = p[max_car - coda:]
        unita.append(p)
    blocchi, corrente = [], ""
    for u in unita:
        if corrente and len(corrente) + len(u) + 2 > max_car:
            blocchi.append(corrente)
            corrente = corrente[-coda:] + "\n\n" + u
        else:
            corrente = f"{corrente}\n\n{u}" if corrente else u
    if corrente:
        blocchi.append(corrente)
    return blocchi


def main() -> None:
    import os

    import chromadb

    from tools.rag import COLLEZIONE, collezione

    manifest = {}
    if MANIFEST.exists():
        with open(MANIFEST, encoding="utf-8") as f:
            manifest = (yaml.safe_load(f) or {}).get("documenti") or {}

    files = sorted(p for p in CARTELLA.iterdir()
                   if p.suffix.lower() in ESTENSIONI) if CARTELLA.exists() else []
    if not files:
        raise SystemExit(f"Nessun documento (.pdf/.txt/.md) in {CARTELLA}/ — "
                         "vedi Guida_Indicizzazione_Normativa.md")

    # ricostruzione da zero: via la collezione vecchia, se c'è
    client = chromadb.HttpClient(
        host=os.environ.get("CHROMA_HOST", "localhost"),
        port=int(os.environ.get("CHROMA_PORT", "8001")))
    try:
        client.delete_collection(COLLEZIONE)
    except Exception:
        pass
    col = collezione()

    totale = 0
    for percorso in files:
        info = manifest.get(percorso.name, {})
        titolo = info.get("titolo", percorso.stem)
        fonte = info.get("fonte", percorso.name)
        data = str(info.get("data", ""))
        if percorso.name not in manifest:
            print(f"⚠️  {percorso.name}: non elencato in {MANIFEST} — "
                  "userò il nome del file come titolo/fonte e nessuna data")

        testo = estrai_testo(percorso)
        if len(testo.strip()) < 200:
            print(f"⚠️  {percorso.name}: quasi nessun testo estratto "
                  "(PDF scansionato? serve l'OCR) — SALTATO")
            continue

        blocchi = spezza(testo)
        for inizio in range(0, len(blocchi), LOTTO):
            fetta = blocchi[inizio:inizio + LOTTO]
            col.add(
                ids=[f"{percorso.name}::{inizio + i}" for i in range(len(fetta))],
                documents=fetta,
                metadatas=[{"titolo": titolo, "fonte": fonte, "data": data,
                            "file": percorso.name}] * len(fetta),
            )
        totale += len(blocchi)
        print(f"✅ {percorso.name}: {len(blocchi)} blocchi — «{titolo}» ({data or 'senza data'})")

    print(f"\n✅ Corpus indicizzato: {len(files)} documenti, {totale} blocchi "
          f"nella collezione '{COLLEZIONE}'")
    print("Prova subito:  python -m scripts.test_normativa \"quanti trasporti di cabotaggio sono ammessi?\"")


if __name__ == "__main__":
    main()
