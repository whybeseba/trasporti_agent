"""Carica gli export DKV in PostgreSQL.

L'export DKV è in formato "wide": colonne anagrafiche a inizio riga e i mesi
nelle colonne successive ("JAN 2026", "FEB 2026", ...), con le stesse metriche
ripetute sotto ogni mese. Questo script lo trasforma in righe
cliente × mese × nazione e le carica nel database.

Uso:  python -m scripts.carica_dkv   (dalla cartella principale)"""
import glob

import pandas as pd
import yaml

CONFIG = "config/dkv_mapping.yml"
CARTELLA_EXCEL = "dati/excel_dkv"
METRICHE_DB = ["litri", "importo_carburante", "importo_pedaggi"]

# Abbreviazioni inglesi e italiane: DKV usa "JAN 2026", ma se un export
# arrivasse con i mesi in italiano ("GEN 2026") funziona lo stesso.
MESI = {"JAN": "01", "GEN": "01", "FEB": "02", "MAR": "03", "APR": "04",
        "MAY": "05", "MAG": "05", "JUN": "06", "GIU": "06", "JUL": "07",
        "LUG": "07", "AUG": "08", "AGO": "08", "SEP": "09", "SET": "09",
        "OCT": "10", "OTT": "10", "NOV": "11", "DEC": "12", "DIC": "12"}


def _periodo(etichetta) -> str | None:
    """'JAN 2026' → '2026-01'; None se la cella non è un'etichetta di mese."""
    parti = str(etichetta).strip().upper().split()
    if len(parti) == 2 and parti[0][:3] in MESI and parti[1].isdigit():
        return f"{parti[1]}-{MESI[parti[0][:3]]}"
    return None


def _codice(valore) -> str:
    """Codice cliente come testo pulito (11461.0 → '11461')."""
    s = str(valore).strip()
    return s[:-2] if s.endswith(".0") else s


def leggi_export(percorso: str, cfg: dict) -> pd.DataFrame:
    """Legge un export wide e restituisce righe cliente × mese × nazione."""
    grezzo = pd.read_excel(percorso, sheet_name=cfg.get("foglio", 0), header=None)
    periodi = grezzo.iloc[cfg["riga_periodi"] - 1]
    intestazioni = grezzo.iloc[cfg["riga_intestazioni"] - 1].astype(str).str.strip()
    dati = grezzo.iloc[cfg["riga_intestazioni"]:].reset_index(drop=True)

    pos_fisse = {}
    for campo, nome in cfg["colonne_fisse"].items():
        trovate = [i for i, h in enumerate(intestazioni) if h == str(nome).strip()]
        if not trovate:
            raise SystemExit(f"❌ {percorso}: colonna '{nome}' non trovata nella riga "
                             f"{cfg['riga_intestazioni']} — controlla {CONFIG}")
        pos_fisse[campo] = trovate[0]

    metriche = {str(k).strip(): v for k, v in cfg["metriche"].items()}
    per_mese: dict[str, dict[str, int]] = {}
    non_mappate = set()
    for i, nome in enumerate(intestazioni):
        periodo = _periodo(periodi.iloc[i])
        if periodo is None:
            continue                    # colonna anagrafica o etichetta varia
        if nome not in metriche:
            non_mappate.add(nome)
            continue
        campo = metriche[nome]
        if campo != "ignora":
            per_mese.setdefault(periodo, {})[campo] = i

    if non_mappate:
        print(f"⚠️  {percorso}: metriche mensili non mappate {sorted(non_mappate)} — "
              f"aggiungile a 'metriche' in {CONFIG} (eventualmente come 'ignora')")
    if not per_mese:
        raise SystemExit(f"❌ {percorso}: nessuna colonna mensile riconosciuta — "
                         f"controlla riga_periodi e 'metriche' in {CONFIG}")

    blocchi = []
    for periodo, campi in sorted(per_mese.items()):
        blocco = pd.DataFrame({
            "cliente_codice": dati.iloc[:, pos_fisse["cliente_codice"]],
            "cliente_nome": dati.iloc[:, pos_fisse["cliente_nome"]],
            "nazione": dati.iloc[:, pos_fisse["nazione"]],
            "periodo": periodo,
        })
        for campo, i in campi.items():
            blocco[campo] = pd.to_numeric(dati.iloc[:, i], errors="coerce")
        blocchi.append(blocco)
    return pd.concat(blocchi, ignore_index=True)


def pulisci(dati: pd.DataFrame) -> pd.DataFrame:
    dati = dati.dropna(subset=["cliente_codice"]).copy()   # righe vuote in coda
    dati["cliente_codice"] = dati["cliente_codice"].map(_codice)
    dati["cliente_nome"] = dati["cliente_nome"].astype(str).str.strip()
    dati["nazione"] = dati["nazione"].astype(str).str.strip().str.upper()

    presenti = [c for c in METRICHE_DB if c in dati.columns]
    for campo in METRICHE_DB:
        if campo not in dati.columns:
            print(f"⚠️  '{campo}' non è mappato in nessuna colonna dell'export: "
                  f"nel database resterà a 0")
            dati[campo] = 0.0

    # un mese senza alcun valore = nessuna attività: la riga non serve
    dati = dati.dropna(subset=presenti, how="all")
    dati[METRICHE_DB] = dati[METRICHE_DB].fillna(0)
    return dati.drop_duplicates()


def main() -> None:
    from sqlalchemy import text

    from tools.db import engine, crea_tabelle

    with open(CONFIG, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    frames = []
    for percorso in sorted(glob.glob(f"{CARTELLA_EXCEL}/*.xlsx")):
        df = leggi_export(percorso, cfg)
        frames.append(df)
        print(f"Letto {percorso}: {df['cliente_codice'].nunique()} clienti, "
              f"{df['periodo'].nunique()} mesi")
    if not frames:
        raise SystemExit("Nessun file .xlsx trovato in dati/excel_dkv/")

    dati = pulisci(pd.concat(frames, ignore_index=True))

    # Anagrafica: il codice DKV è la chiave (nome_dkv), la ragione sociale
    # è solo descrittiva. Mai usare il nome come chiave: due clienti con lo
    # stesso nome finirebbero fusi in uno — e uno vedrebbe i dati dell'altro.
    crea_tabelle()
    anagrafica = (dati[["cliente_codice", "cliente_nome"]]
                  .drop_duplicates("cliente_codice"))
    with engine.begin() as con:
        for _, r in anagrafica.iterrows():
            con.execute(text("""
                INSERT INTO clienti (nome_dkv, ragione_sociale) VALUES (:c, :n)
                ON CONFLICT (nome_dkv)
                DO UPDATE SET ragione_sociale = EXCLUDED.ragione_sociale
            """), {"c": r["cliente_codice"], "n": r["cliente_nome"]})
        ids = dict(con.execute(text("SELECT nome_dkv, id FROM clienti")).fetchall())
        con.execute(text("DELETE FROM dkv_mensile"))   # ricaricamento completo

    dati["cliente_id"] = dati["cliente_codice"].map(ids)
    dati = dati[["cliente_id", "periodo", "nazione"] + METRICHE_DB]
    dati.to_sql("dkv_mensile", engine, if_exists="append", index=False)

    print(f"\n✅ Caricate {len(dati)} righe per {len(ids)} clienti")
    print(dati.groupby(dati["periodo"].str[:4])[METRICHE_DB].sum().round(2).to_string())


if __name__ == "__main__":
    main()
