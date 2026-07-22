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
        attivo          BOOLEAN DEFAULT TRUE
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


def salva_conversazione(cliente_id: int, domanda: str, risposta: str,
                        canale: str = "chat") -> None:
    esegui("""INSERT INTO log_conversazioni (cliente_id, canale, domanda, risposta)
              VALUES (:cid, :canale, :d, :r)""",
           {"cid": cliente_id, "canale": canale, "d": domanda, "r": risposta})
