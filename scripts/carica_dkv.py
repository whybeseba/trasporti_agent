"""Carica gli export DKV (aggregati mensili) in PostgreSQL.
Uso:  python -m scripts.carica_dkv   (dalla cartella principale)"""
import glob

import pandas as pd
import yaml
from sqlalchemy import text

from tools.db import engine, crea_tabelle

CONFIG = "config/dkv_mapping.yml"
CARTELLA_EXCEL = "dati/excel_dkv"

with open(CONFIG, encoding="utf-8") as f:
    cfg = yaml.safe_load(f)
mappa = cfg["colonne"]

# 1) Legge tutti i file Excel della cartella
frames = []
for percorso in sorted(glob.glob(f"{CARTELLA_EXCEL}/*.xlsx")):
    df = pd.read_excel(percorso, sheet_name=cfg.get("foglio", 0))
    df = df.rename(columns={v: k for k, v in mappa.items()})
    mancanti = [c for c in mappa if c not in df.columns]
    if mancanti:
        print(f"⚠️  {percorso}: colonne non trovate {mancanti} — controlla dkv_mapping.yml")
    frames.append(df[[c for c in mappa if c in df.columns]])
    print(f"Letto {percorso}: {len(df)} righe")

if not frames:
    raise SystemExit("Nessun file .xlsx trovato in dati/excel_dkv/")
dati = pd.concat(frames, ignore_index=True)

# 2) Pulizia
# periodo → testo "AAAA-MM" (es. 2026-03), qualunque sia il formato di partenza
dati["periodo"] = (pd.to_datetime(dati["periodo"], dayfirst=True, errors="coerce")
                     .dt.strftime("%Y-%m"))
dati["cliente"] = dati["cliente"].astype(str).str.strip()
dati["nazione"] = dati["nazione"].astype(str).str.strip().str.upper()

for col in ["litri", "importo_carburante", "importo_pedaggi"]:
    if dati[col].dtype == object:
        # Gestisce il formato italiano "1.234,56" → 1234.56
        dati[col] = (dati[col].astype(str)
                     .str.replace(".", "", regex=False)
                     .str.replace(",", ".", regex=False))
    dati[col] = pd.to_numeric(dati[col], errors="coerce").fillna(0)

dati = dati.drop_duplicates()

# 3) Anagrafica clienti (crea i nuovi, recupera gli id) e caricamento
crea_tabelle()
with engine.begin() as con:
    for nome in sorted(dati["cliente"].dropna().unique()):
        con.execute(text("""INSERT INTO clienti (nome_dkv) VALUES (:n)
                            ON CONFLICT (nome_dkv) DO NOTHING"""), {"n": nome})
    ids = dict(con.execute(text("SELECT nome_dkv, id FROM clienti")).fetchall())
    con.execute(text("DELETE FROM dkv_mensile"))   # ricaricamento completo: semplice e sicuro

dati["cliente_id"] = dati["cliente"].map(ids)
dati = dati.drop(columns=["cliente"])
dati.to_sql("dkv_mensile", engine, if_exists="append", index=False)

print(f"\n✅ Caricate {len(dati)} righe per {len(ids)} clienti")
print(dati.groupby(dati["periodo"].str[:4])[
      ["litri", "importo_carburante", "importo_pedaggi"]].sum().round(2).to_string())
