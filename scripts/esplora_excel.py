"""Mostra fogli, colonne e prime righe di un file Excel.
Uso:  python -m scripts.esplora_excel dati/excel_dkv/nomefile.xlsx"""
import sys

import pandas as pd

percorso = sys.argv[1]
fogli = pd.read_excel(percorso, sheet_name=None)

for nome, df in fogli.items():
    print(f"\n=== FOGLIO: {nome} ===")
    print(f"Righe: {len(df)} — Colonne: {len(df.columns)}\n")
    print("Colonne trovate:")
    for c in df.columns:
        print(f"  - {c}")
    print("\nPrime 5 righe:")
    print(df.head().to_string())
