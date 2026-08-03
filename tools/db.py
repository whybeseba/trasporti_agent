"""Connessione a PostgreSQL e funzioni condivise."""
import os

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv()  # legge il file .env
engine = create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)


def query(sql: str, params: dict | None = None) -> pd.DataFrame:
    """Esegue una SELECT e restituisce una tabella pandas."""
    return pd.read_sql_query(text(sql), engine, params=params or {})


def esegui(sql: str, params: dict | None = None) -> None:
    """Esegue un comando che modifica i dati (INSERT, DELETE, ...)."""
    with engine.begin() as con:
        con.execute(text(sql), params or {})


def crea_tabelle() -> None:
    ddl = """
    CREATE TABLE IF NOT EXISTS clienti (
        id              SERIAL PRIMARY KEY,
        nome_dkv        TEXT UNIQUE NOT NULL,
        ragione_sociale TEXT,
        email           TEXT,
        attivo          BOOLEAN DEFAULT TRUE,
        -- profilo dell'azienda, raccolto in chat una domanda alla volta:
        -- NULL = non ancora saputo (diverso da "no")
        conto_terzi                   BOOLEAN,
        internazionale                BOOLEAN,
        trasporto_attivita_principale BOOLEAN,
        massa_massima_t               NUMERIC
    );
    CREATE TABLE IF NOT EXISTS dkv_mensile (
        cliente_id          INTEGER REFERENCES clienti(id),
        periodo             TEXT NOT NULL,
        nazione             TEXT,
        litri               NUMERIC,
        importo_carburante  NUMERIC,
        importo_pedaggi     NUMERIC
    );
    CREATE INDEX IF NOT EXISTS idx_dkv_cliente ON dkv_mensile (cliente_id, periodo);
    CREATE TABLE IF NOT EXISTS log_conversazioni (
        id          SERIAL PRIMARY KEY,
        cliente_id  INTEGER,
        canale      TEXT,
        creato      TIMESTAMPTZ DEFAULT now(),
        domanda     TEXT,
        risposta    TEXT
    );
    """
    with engine.begin() as con:
        con.execute(text(ddl))
    migra()


# Colonne del profilo cliente: nome → tipo SQL. Sono anche l'elenco delle
# uniche colonne che i tool del profilo possono scrivere.
COLONNE_PROFILO = {
    "conto_terzi": "BOOLEAN",
    "internazionale": "BOOLEAN",
    "trasporto_attivita_principale": "BOOLEAN",
    "massa_massima_t": "NUMERIC",
}


def migra() -> None:
    """Porta un database già esistente allo schema corrente.

    `crea_tabelle` usa CREATE TABLE IF NOT EXISTS, che su una tabella già
    creata non aggiunge nulla: le colonne nuove vanno aggiunte qui.
    Idempotente — si può rilanciare quante volte si vuole.
    Uso manuale:  python -m scripts.migra_db"""
    with engine.begin() as con:
        for nome, tipo in COLONNE_PROFILO.items():
            # nomi e tipi vengono da questa costante, mai da input esterno
            con.execute(text(
                f"ALTER TABLE clienti ADD COLUMN IF NOT EXISTS {nome} {tipo}"))


def salva_conversazione(cliente_id: int, domanda: str, risposta: str,
                        canale: str = "chat") -> None:
    esegui("""INSERT INTO log_conversazioni (cliente_id, canale, domanda, risposta)
              VALUES (:cid, :canale, :d, :r)""",
           {"cid": cliente_id, "canale": canale, "d": domanda, "r": risposta})
