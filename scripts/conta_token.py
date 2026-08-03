"""Conta ESATTAMENTE i token dei prompt reali con l'endpoint count_tokens
dell'API Anthropic.

A cosa serve. Le chat di collaudo su vLLM contano i token col tokenizer di
Qwen3: utile per gli ordini di grandezza, ma non per fissare un prezzo ai
clienti, perché Claude tokenizza in modo diverso. Questo script prende i
prompt VERI del sistema (system prompt dell'agente + schemi dei tool + una
domanda) e li fa contare ad Anthropic, che risponde col numero esatto.

Conta senza generare nulla: count_tokens misura solo l'input, non produce
risposte e non costa token di output.

Uso:  python -m scripts.conta_token [cliente_id] [modello]
      python -m scripts.conta_token 1 claude-haiku-4-5
"""
import os
import sys

from dotenv import load_dotenv

from tools.costi import CAMBIO_EUR_USD, prezzi

load_dotenv()

DOMANDA_ESEMPIO = "Quanto ho speso di pedaggi nel 2026 e in quali nazioni?"
RISPOSTA_TIPICA_TOKEN = 220     # per stimare la parte di output nel costo


def _schema_tool(t) -> dict:
    """Tool LangChain → definizione nel formato dell'API Anthropic."""
    schema = {"type": "object", "properties": {}}
    modello = getattr(t, "args_schema", None)
    if modello is not None:
        if hasattr(modello, "model_json_schema"):      # pydantic v2
            schema = modello.model_json_schema()
        elif hasattr(modello, "schema"):               # pydantic v1
            schema = modello.schema()
    return {"name": t.name, "description": (t.description or "").strip(),
            "input_schema": schema}


def main() -> None:
    from anthropic import Anthropic

    from agents.agente_cliente import prompt_cliente
    from tools.db import query
    from tools.dkv_tools import costruisci_tools_cliente

    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise SystemExit("❌ ANTHROPIC_API_KEY mancante nel file .env")

    cid = int(sys.argv[1]) if len(sys.argv) > 1 else None
    modello = sys.argv[2] if len(sys.argv) > 2 else os.environ.get(
        "ANTHROPIC_MODEL", "claude-haiku-4-5")

    if cid is None:
        df = query("""SELECT id, COALESCE(ragione_sociale, nome_dkv) AS cliente
                      FROM clienti ORDER BY cliente LIMIT 1""")
        if df.empty:
            raise SystemExit("Nessun cliente in anagrafica: carica prima i dati DKV.")
        cid, nome = int(df.iloc[0, 0]), df.iloc[0, 1]
    else:
        df = query("""SELECT COALESCE(ragione_sociale, nome_dkv) AS cliente
                      FROM clienti WHERE id = :i""", {"i": cid})
        if df.empty:
            raise SystemExit(f"Cliente {cid} inesistente.")
        nome = df.iloc[0, 0]

    system = prompt_cliente(nome)
    tools = [_schema_tool(t) for t in costruisci_tools_cliente(cid)]

    client = Anthropic()
    print(f"Modello: {modello}   Cliente: {nome} (id {cid})\n")

    def conta(messaggi, con_tool=True) -> int:
        return client.messages.count_tokens(
            model=modello, system=system, messages=messaggi,
            **({"tools": tools} if con_tool else {})).input_tokens

    solo_prompt = conta([{"role": "user", "content": "."}])
    senza_tool = conta([{"role": "user", "content": "."}], con_tool=False)
    prima_domanda = conta([{"role": "user", "content": DOMANDA_ESEMPIO}])

    print(f"System prompt (senza tool):        {senza_tool:>7} token")
    print(f"System prompt + schemi dei tool:   {solo_prompt:>7} token   "
          f"← la parte fissa, ricaricata a ogni messaggio")
    print(f"Con la domanda di esempio:         {prima_domanda:>7} token\n")

    p = prezzi(modello)
    if p is None:
        print(f"⚠️  '{modello}' non è in LISTINO (tools/costi.py): niente costi.")
        return

    def eur(usd: float) -> float:
        return usd * CAMBIO_EUR_USD

    pieno = eur(prima_domanda * p["in"] / 1_000_000)
    cache = eur(prima_domanda * p["in"] * 0.1 / 1_000_000)
    output = eur(RISPOSTA_TIPICA_TOKEN * p["out"] / 1_000_000)

    print("Costo del solo input di UNA chiamata:")
    print(f"  a prezzo pieno (prima volta):    {pieno:.6f} €")
    print(f"  riletto dalla cache:             {cache:.6f} €   "
          f"← è quanto costa nei messaggi successivi")
    print(f"Output di una risposta tipica ({RISPOSTA_TIPICA_TOKEN} token): {output:.6f} €\n")
    print(f"La parte fissa ({solo_prompt} token) viene ricaricata a OGNI messaggio: "
          f"è esattamente\nciò che il prompt caching fa pagare un decimo. "
          f"Il resto cresce con la storia della chat.")


if __name__ == "__main__":
    main()
