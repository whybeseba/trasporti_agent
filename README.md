# trasporti_agent — Motore DKV (Fasi 1-2, variante vLLM su OVH AI Deploy)

Implementazione delle Fasi 1 e 2 di `Guida_Fase_1_e_2_v3.md` (architettura in
`Architettura_v3_Portale_Clienti_DKV.md`), con **una** differenza rispetto alla
guida: l'inferenza non gira su Ollama in locale ma sul **motore vLLM già
validato su OVH AI Deploy** (vedi `Guida_Spike_vLLM_AI_Deploy.md`).

## Cosa cambia rispetto alla guida originale

| Punto della guida | Originale (Ollama) | Questa repo (vLLM su OVH) |
|---|---|---|
| `docker-compose.yml` | ollama + n8n + postgres | n8n + postgres + **Open WebUI** (chat di collaudo verso OVH); niente container ollama |
| 1.5 Scaricare i modelli | `ollama pull qwen3:…` | Non serve: il modello è già pre-caricato nel bucket e servito da AI Deploy |
| `requirements.txt` | `langchain-ollama` | `langchain-openai` (l'API di vLLM è compatibile OpenAI) |
| Costruzione dell'LLM | `ChatOllama(...)` in ogni agente | **`agents/llm.py`**: unico punto con `ChatOpenAI(base_url=VLLM_URL, api_key=VLLM_TOKEN)`; gli agenti lo importano |
| `.env` | password Postgres | \+ `VLLM_URL`, `VLLM_TOKEN`, `VLLM_MODEL` |
| Tutto il resto | — | **Identico**: tool, fabbrica per-cliente, prompt, registro, orchestratore, API |

## Prerequisito: il motore su AI Deploy acceso, con i flag per il tool calling

Gli agenti usano il tool calling, quindi l'app AI Deploy va lanciata con i tre
flag della Parte 5 della guida spike. Comando completo di riferimento (adatta
`--model` al tuo percorso nel bucket, vedi Parte 2 della guida spike):

```bash
ovhai app run \
  --name vllm-qwen3-8b \
  --flavor l4-1-gpu \
  --gpu 1 \
  --default-http-port 8000 \
  --label ai_deploy_token=spike-vllm \
  --env HOME=/workspace \
  --env USER=vllm \
  --env LOGNAME=vllm \
  --env OUTLINES_CACHE_DIR=/workspace/.outlines \
  --env TORCHINDUCTOR_CACHE_DIR=/workspace/inductor \
  --volume vllm-models@GRA/:/hub:ro \
  --volume vllm-workspace@GRA/:/workspace:rw \
  vllm/vllm-openai:v0.24.0 \
  -- bash -c "python3 -m vllm.entrypoints.openai.api_server --model /hub --served-model-name Qwen/Qwen3-8B --max-model-len 16384 --enable-auto-tool-choice --tool-call-parser hermes --reasoning-parser qwen3"
```

Se l'app dello spike gira ancora **senza** quei tre flag, rilanciala con questo
comando (o creane una seconda cambiando `--name`). Ricorda `ovhai app stop` a
fine giornata: la GPU si paga a tempo di esecuzione.

## Setup sul server (riassunto operativo)

Per la verifica guidata dell'ambiente c'è **`PROMPT_CURSOR_SETUP.md`**: si
incolla nella chat AI di Cursor collegato al server e fa tutti i controlli.
A mano, i passi sono:

```bash
# 1) Configurazione (password Postgres + endpoint e token OVH)
cp .env.example .env
nano .env

# 2) Infrastruttura Docker (n8n, Postgres, Open WebUI)
docker compose up -d
docker compose ps          # tutti "running"

# 3) Ambiente Python
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 4) Collaudo del motore remoto (endpoint, token, nome modello, una risposta)
python -m scripts.test_vllm

# 5) Dati: metti gli export DKV in dati/excel_dkv/, poi
python -m scripts.esplora_excel dati/excel_dkv/nomefile.xlsx   # annota i nomi colonna
nano config/dkv_mapping.yml                                    # adattali
python -m scripts.carica_dkv

# 6) Collaudo agenti
python chat_test.py            # impersona un cliente (5 domande + tentativi di evasione, §2.8)
python chat_orchestratore.py   # vista gestore ("quali clienti sono in calo?")

# 7) API di sviluppo
uvicorn server:app --host 127.0.0.1 --port 8080
curl -X POST http://localhost:8080/dev/chat/1 \
     -H "Content-Type: application/json" \
     -d '{"domanda": "Quanto ho speso nel 2025?"}'
```

Interfacce web (solo da localhost, via port-forward di Cursor o tunnel SSH):
n8n su `http://localhost:5678`, Open WebUI su `http://localhost:3000`.

## Struttura

```
agents/            llm.py (client vLLM/OVH) · agente_cliente · agente_portafoglio ·
                   registry · orchestrator
tools/             db.py · dkv_tools.py (per-cliente, fabbrica) · portafoglio_tools.py (interni)
scripts/           esplora_excel · carica_dkv · test_vllm
config/            dkv_mapping.yml · regole_servizi.yml · agents_config.yml · prompts/
dati/excel_dkv/    gli export DKV (mai su git)
chat_test.py       collaudo per-cliente (funzionale + sicurezza §2.8)
chat_orchestratore.py  chat interna del gestore
server.py          API di sviluppo (127.0.0.1, da eliminare in Fase 3)
```

## Sicurezza — i punti fermi

- L'isolamento multi-tenant è **nel codice** (fabbrica + closure in
  `tools/dkv_tools.py`): nessun tool ha un parametro "cliente".
- Il **collaudo di sicurezza** del §2.8 va ripetuto su ogni motore nuovo —
  quindi anche su questo vLLM remoto, anche se i tool non sono cambiati.
- `.env` (token OVH e password) non si committa mai; `.cursorignore` tiene
  `.env` e `dati/` fuori dai servizi AI dell'editor (attiva anche la Privacy
  Mode di Cursor).
- Tutte le porte locali ascoltano su `127.0.0.1`; l'unica cosa remota è
  l'endpoint HTTPS di AI Deploy, protetto dal token.
