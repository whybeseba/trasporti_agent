"""Verifica il collegamento al motore vLLM su OVH AI Deploy.
Controlla in ordine: variabili nel .env → endpoint raggiungibile e token
valido (/v1/models) → nome del modello coerente → una risposta vera.
Uso:  python -m scripts.test_vllm   (dalla cartella principale, .venv attivo)"""
import os
import sys

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

url = os.environ.get("VLLM_URL", "")
token = os.environ.get("VLLM_TOKEN", "")
modello = os.environ.get("VLLM_MODEL", "Qwen/Qwen3-8B")

if not url or not token or "<" in url or "<" in token:
    sys.exit("❌ VLLM_URL e/o VLLM_TOKEN mancanti o non compilati nel file .env")
if not url.rstrip("/").endswith("/v1"):
    sys.exit(f"❌ VLLM_URL deve terminare con /v1 — trovato: {url}")

client = OpenAI(base_url=url, api_key=token)

print(f"Endpoint: {url}")
try:
    disponibili = [m.id for m in client.models.list().data]
except Exception as e:
    sys.exit(f"❌ /v1/models non risponde (app spenta? token errato?): {e}")
print(f"✅ Endpoint raggiungibile. Modelli serviti: {disponibili}")

if modello not in disponibili:
    sys.exit(f"❌ VLLM_MODEL='{modello}' non è tra i modelli serviti {disponibili}: "
             "controlla --served-model-name nell'app AI Deploy o correggi il .env")

try:
    r = client.chat.completions.create(
        model=modello,
        messages=[{"role": "user", "content": "Presentati in una frase."}],
        max_tokens=100,
        extra_body={"chat_template_kwargs": {"enable_thinking": False}},
    )
except Exception as e:
    sys.exit(f"❌ La chat completion è fallita: {e}")

print(f"✅ Risposta del modello: {r.choices[0].message.content.strip()}")
print("\n🎉 Motore vLLM su OVH operativo: gli agenti possono partire.")
