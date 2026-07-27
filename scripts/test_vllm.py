"""Verifica il collegamento ai motori vLLM su OVH AI Deploy.

Controlla i due RUOLI del sistema (orchestratore e sub-agenti): con il
motore unico coincidono e il test è uno solo; con le due app di
Deploy_due_modelli_vLLM_AI_Deploy.md vengono collaudate entrambe.
Per ogni endpoint: raggiungibilità e token (/v1/models), coerenza del nome
del modello, una risposta vera.
Uso:  python -m scripts.test_vllm   (dalla cartella principale, .venv attivo)"""
import os
import sys

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

token = os.environ.get("VLLM_TOKEN", "")
if not token or "<" in token:
    sys.exit("❌ VLLM_TOKEN mancante o non compilato nel file .env")


def config_ruolo(suffisso: str) -> tuple[str, str]:
    url = os.environ.get(f"VLLM_URL{suffisso}") or os.environ.get("VLLM_URL", "")
    modello = (os.environ.get(f"VLLM_MODEL{suffisso}")
               or os.environ.get("VLLM_MODEL", ""))
    return url, modello


ruoli = {"orchestratore": config_ruolo("_ORCHESTRATORE"),
         "sub-agenti": config_ruolo("_SUBAGENTI")}

if ruoli["orchestratore"] == ruoli["sub-agenti"]:
    print("Configurazione a MOTORE UNICO: orchestratore e sub-agenti "
          "condividono endpoint e modello.\n")

errori = False
testati: dict[tuple[str, str], bool] = {}
for ruolo, (url, modello) in ruoli.items():
    if not url or "<" in url:
        print(f"❌ [{ruolo}] VLLM_URL mancante o non compilato nel .env")
        errori = True
        continue
    if not url.rstrip("/").endswith("/v1"):
        print(f"❌ [{ruolo}] l'URL deve terminare con /v1 — trovato: {url}")
        errori = True
        continue
    chiave = (url, modello)
    if chiave in testati:
        print(f"✅ [{ruolo}] stesso motore già collaudato ({modello})")
        continue

    print(f"[{ruolo}] endpoint: {url}")
    client = OpenAI(base_url=url, api_key=token)
    try:
        disponibili = [m.id for m in client.models.list().data]
    except Exception as e:
        print(f"❌ [{ruolo}] /v1/models non risponde (app spenta? token errato?): {e}")
        errori = True
        continue
    print(f"✅ [{ruolo}] endpoint raggiungibile. Modelli serviti: {disponibili}")

    if modello not in disponibili:
        print(f"❌ [{ruolo}] il modello '{modello}' del .env non è tra quelli "
              f"serviti {disponibili}: controlla --served-model-name dell'app")
        errori = True
        continue

    try:
        r = client.chat.completions.create(
            model=modello,
            messages=[{"role": "user", "content": "Presentati in una frase."}],
            max_tokens=100,
            extra_body={"chat_template_kwargs": {"enable_thinking": False}},
        )
    except Exception as e:
        print(f"❌ [{ruolo}] la chat completion è fallita: {e}")
        errori = True
        continue
    print(f"✅ [{ruolo}] risposta: {r.choices[0].message.content.strip()}\n")
    testati[chiave] = True

if errori:
    sys.exit(1)
print("🎉 Motori vLLM su OVH operativi: gli agenti possono partire.")
