# trasporti_agent — Motore DKV (Fasi 1-2, variante vLLM su OVH AI Deploy)

Implementazione delle Fasi 1 e 2 di `Guida_Fase_1_e_2_v3.md` (architettura in
`Architettura_v3_Portale_Clienti_DKV.md`), con **una** differenza rispetto alla
guida: l'inferenza non gira su Ollama in locale ma sul **motore vLLM già
validato su OVH AI Deploy** (vedi `Guida_Spike_vLLM_AI_Deploy.md`).

## Cosa cambia rispetto alla guida originale

| Punto della guida | Originale (Ollama) | Questa repo (vLLM su OVH) |
|---|---|---|
| `docker-compose.yml` | ollama + n8n + postgres | n8n + postgres + **ChromaDB** (RAG normativa) + Adminer + **Open WebUI** (chat di collaudo verso OVH); niente container ollama |
| 1.5 Scaricare i modelli | `ollama pull qwen3:…` | Non serve: il modello è già pre-caricato nel bucket e servito da AI Deploy |
| `requirements.txt` | `langchain-ollama` | `langchain-openai` (l'API di vLLM è compatibile OpenAI) |
| Costruzione dell'LLM | `ChatOllama(...)` in ogni agente | **`agents/llm.py`**: unico punto con `ChatOpenAI(base_url=..., api_key=VLLM_TOKEN)`, con distinzione di ruolo orchestratore/sub-agenti; gli agenti lo importano |
| `.env` | password Postgres | \+ `VLLM_URL`, `VLLM_TOKEN`, `VLLM_MODEL` (e opzionali per-ruolo `VLLM_URL_ORCHESTRATORE`/`VLLM_URL_SUBAGENTI`...) |
| Tutto il resto | — | **Identico**: tool, fabbrica per-cliente, prompt, registro, orchestratore, API |

**Oltre la guida originale**, questa repo anticipa due pezzi previsti dalle
fasi successive dell'architettura (v3, §2 e Fase 6): il **team di agenti dei
clienti** con il suo orchestratore (`agents/orchestrator_clienti.py` +
registro `config/agents_clienti.yml`, con la distinzione `per_cliente`) e il
secondo membro del team, l'**agente Normativa** (RAG su ChromaDB — setup del
corpus in `Guida_Indicizzazione_Normativa.md`). `chat_test.py` e `server.py`
passano già dall'orchestratore clienti, come farà il portale in Fase 3.

## Prerequisito: il motore su AI Deploy acceso, con i flag per il tool calling

I comandi `ovhai` aggiornati sono in **`Deploy_due_modelli_vLLM_AI_Deploy.md`**,
che prevede due configurazioni:

- **Motore unico** (sezione "Quello da usare per il primo test", la
  configurazione attuale): `Qwen/Qwen3.6-35B-A3B` FP8 su una L40S — un solo
  endpoint per orchestratore e sub-agenti. Nel `.env` bastano `VLLM_URL`,
  `VLLM_TOKEN` e `VLLM_MODEL=Qwen/Qwen3.6-35B-A3B`.
- **Due motori** (orchestratore `Qwen3.6-27B` + sub-agenti `Qwen3.5-9B`, due
  app): aggiungi nel `.env` le variabili per-ruolo
  (`VLLM_URL_ORCHESTRATORE`/`VLLM_MODEL_ORCHESTRATORE` e
  `VLLM_URL_SUBAGENTI`/`VLLM_MODEL_SUBAGENTI`) — il codice le usa da solo,
  nessuna modifica necessaria.

In entrambi i casi l'app va lanciata con i flag del tool calling della linea
Qwen3.5/3.6: `--enable-auto-tool-choice --tool-call-parser qwen3_coder
--reasoning-parser qwen3` (immagine `vllm/vllm-openai:v0.26.0`). Ricorda
`ovhai app stop` a fine giornata: la GPU si paga a tempo di esecuzione.

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

# 6) Corpus normativo (agente Normativa): PDF in dati/normativa/,
#    manifest fonti.yml, poi (guida completa: Guida_Indicizzazione_Normativa.md)
python -m scripts.indicizza_normativa
python -m scripts.test_normativa "come funziona il cabotaggio?"

# 7) Collaudo agenti
python chat_test.py            # impersona un cliente: il router smista tra
                               # costi DKV e normativa (+ collaudo §2.8)
python chat_orchestratore.py   # vista gestore ("quali clienti sono in calo?")

# 8) API di sviluppo
uvicorn server:app --host 127.0.0.1 --port 8080
curl -X POST http://localhost:8080/dev/chat/1 \
     -H "Content-Type: application/json" \
     -d '{"domanda": "Quanto ho speso nel 2025?"}'
```

Interfacce web (solo da localhost, via port-forward di Cursor o tunnel SSH):
n8n su `http://localhost:5678`, Open WebUI su `http://localhost:3000`,
Adminer su `http://localhost:8081`.

## Leggere i log delle chat di collaudo

`chat_test.py` e `chat_orchestratore.py` mostrano in tempo reale cosa succede
dentro il sistema (`tools/tracing.py`, un callback handler LangChain + `rich`):

- 🧭 **la scelta del router**: quale specialista prende in carico la domanda,
  o se risponde direttamente l'orchestratore;
- 🤖 **chi sta lavorando** in ogni momento — orchestratore o un sub-agente;
- 🧠 **ogni chiamata al modello** mentre è in corso ("sta pensando…"), poi
  con durata, modello effettivamente usato, token in ingresso e generati,
  velocità in token/s e percentuale di contesto occupato;
- 🔧 **ogni tool chiamato**, con gli argomenti scelti dal modello, la durata
  e l'inizio del risultato: è il modo per verificare che l'agente stia
  leggendo i numeri veri invece di inventarli;
- ❌ **gli errori** di modello e tool, senza far cadere la chat;
- un **riepilogo per turno** e uno **di sessione** (turni, chiamate, tool più
  usati, token totali, picco di contesto).

La percentuale di contesto si basa su `VLLM_MAX_MODEL_LEN` nel `.env`, che
deve corrispondere al `--max-model-len` con cui hai avviato l'app AI Deploy.
In produzione la traccia resta spenta: le annotazioni negli orchestratori
sono no-op finché nessuno la attiva, quindi `server.py` non cambia.

## Struttura

```
agents/            llm.py (client vLLM/OVH) · agente_cliente · agente_normativa ·
                   agente_portafoglio · registry · orchestrator (gestore) ·
                   orchestrator_clienti (per-sessione)
tools/             db.py · dkv_tools.py (per-cliente, fabbrica) · rag.py (ChromaDB) ·
                   portafoglio_tools.py (interni) · tracing.py (log delle chat)
scripts/           esplora_excel · carica_dkv · test_vllm · indicizza_normativa ·
                   test_normativa
config/            dkv_mapping.yml · regole_servizi.yml · agents_config.yml (interno) ·
                   agents_clienti.yml (team clienti) · prompts/
dati/excel_dkv/    gli export DKV (mai su git)
dati/normativa/    il corpus di norme/circolari + fonti.yml (mai su git)
chat_test.py       collaudo cliente via orchestratore (funzionale + sicurezza §2.8)
chat_orchestratore.py  chat interna del gestore
server.py          API di sviluppo (127.0.0.1, da eliminare in Fase 3)
```

## Sicurezza — i punti fermi

- L'isolamento multi-tenant è **nel codice** (fabbrica + closure in
  `tools/dkv_tools.py`): nessun tool ha un parametro "cliente".
- **Due registri di agenti, mai mescolati**: l'orchestratore dei clienti
  carica solo `agents_clienti.yml` e non conosce gli agenti interni del
  gestore (`agents_config.yml`).
- Il **corpus normativo è condiviso** tra tutti i clienti: dentro solo
  documenti pubblici, mai dati di clienti (vedi guida indicizzazione).
- Il **collaudo di sicurezza** del §2.8 va ripetuto su ogni motore nuovo —
  quindi anche su questo vLLM remoto, anche se i tool non sono cambiati.
- `.env` (token OVH e password) non si committa mai; `.cursorignore` tiene
  `.env` e `dati/` fuori dai servizi AI dell'editor (attiva anche la Privacy
  Mode di Cursor).
- Tutte le porte locali ascoltano su `127.0.0.1`; l'unica cosa remota è
  l'endpoint HTTPS di AI Deploy, protetto dal token.
