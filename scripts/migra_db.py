"""Porta il database allo schema corrente (idempotente).

Da lanciare dopo un aggiornamento del codice che aggiunge colonne: qui le
colonne del profilo cliente (conto terzi, internazionale, trasporto come
attività principale, massa massima a pieno carico).

Uso:  python -m scripts.migra_db"""
from tools.db import COLONNE_PROFILO, crea_tabelle, query

crea_tabelle()          # crea ciò che manca e applica le migrazioni

presenti = query("""
    SELECT column_name FROM information_schema.columns
    WHERE table_name = 'clienti'
""")["column_name"].tolist()

print("Colonne del profilo sulla tabella 'clienti':")
for nome in COLONNE_PROFILO:
    print(f"  {'✅' if nome in presenti else '❌'} {nome}")

df = query("""
    SELECT COUNT(*) AS clienti,
           COUNT(conto_terzi) AS con_conto_terzi,
           COUNT(internazionale) AS con_internazionale,
           COUNT(trasporto_attivita_principale) AS con_attivita,
           COUNT(massa_massima_t) AS con_massa
    FROM clienti
""")
print("\nQuanti clienti hanno già ciascun dato (il resto è da raccogliere in chat):")
print(df.to_string(index=False))
