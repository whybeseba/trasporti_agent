# Deploy dei modelli su AI Deploy — due configurazioni

> Questo documento contiene **due opzioni**: (1) due modelli distinti su due app — orchestratore grande + sotto-agenti 9B; (2) un solo modello `35B-A3B` per tutti i ruoli su una sola app (in fondo). Scegli in base a budget e qualità richiesta.

## Configurazione 1 — Due modelli (orchestratore + sotto-agenti)

> **Perché due app e non una.** Un processo vLLM serve **un solo modello**: non esiste `--model A --model B`. Per avere l'orchestratore (modello grande) e i sotto-agenti (9B) come modelli distinti servono **due app AI Deploy separate**, una per modello, ciascuna su una `l40s-1-gpu`. È anche la scelta più pulita: si spengono e si scalano in modo indipendente, e nel codice l'orchestratore punta a un `VLLM_URL`, i sotto-agenti all'altro.
>
> **Prerequisito.** I due modelli FP8 vanno **pre-caricati** nei rispettivi container Object Storage (AI Deploy non fa write-back: vedi guida spike, Parte 2). Qui si assume: `vllm-model-27b` (con `Qwen3.6-27B-FP8`) e `vllm-model-9b` (con `Qwen3.5-9B-FP8`), più un container scrivibile `vllm-workspace`. Adatta i nomi ai tuoi.

---

## App 1 — Orchestratore (Qwen3.6-27B-FP8)

```bash
ovhai app run \
  --name vllm-orchestratore \
  --flavor l40s-1-gpu \
  --gpu 1 \
  --default-http-port 8000 \
  --label ai_deploy_token=spike-vllm \
  --env HOME=/workspace \
  --env USER=vllm \
  --env LOGNAME=vllm \
  --env OUTLINES_CACHE_DIR=/workspace/.outlines \
  --env TORCHINDUCTOR_CACHE_DIR=/workspace/inductor \
  --volume vllm-model-27b@GRA/:/hub:ro \
  --volume vllm-workspace@GRA/:/workspace:rw \
  vllm/vllm-openai:v0.26.0 \
  -- bash -c "python3 -m vllm.entrypoints.openai.api_server --model /hub --served-model-name Qwen/Qwen3.6-27B --max-model-len 32768 --enable-auto-tool-choice --tool-call-parser qwen3_coder --reasoning-parser qwen3"
```

## App 2 — Sotto-agenti (Qwen3.5-9B-FP8)

```bash
ovhai app run \
  --name vllm-subagenti \
  --flavor l40s-1-gpu \
  --gpu 1 \
  --default-http-port 8000 \
  --label ai_deploy_token=spike-vllm \
  --env HOME=/workspace \
  --env USER=vllm \
  --env LOGNAME=vllm \
  --env OUTLINES_CACHE_DIR=/workspace/.outlines \
  --env TORCHINDUCTOR_CACHE_DIR=/workspace/inductor \
  --volume vllm-model-9b@GRA/:/hub:ro \
  --volume vllm-workspace@GRA/:/workspace:rw \
  vllm/vllm-openai:v0.26.0 \
  -- bash -c "python3 -m vllm.entrypoints.openai.api_server --model /hub --served-model-name Qwen/Qwen3.5-9B --max-model-len 32768 --enable-auto-tool-choice --tool-call-parser qwen3_coder --reasoning-parser qwen3"
```

---

## Spiegazione dei flag (valida per entrambi)

| Flag | Cosa fa |
|---|---|
| `--flavor l40s-1-gpu --gpu 1` | Una GPU NVIDIA L40S (48 GB VRAM). Regge il 27B-FP8 (~27 GB) con margine per il KV cache; il 9B-FP8 (~14 GB) ci sta larghissimo. |
| `--default-http-port 8000` | La porta su cui vLLM ascolta dentro il container; AI Deploy la espone via HTTPS. |
| `--label ai_deploy_token=spike-vllm` | Stessa etichetta sulle due app → **un solo token** vale per entrambe. |
| `--env HOME/USER/LOGNAME` | Necessari: AI Deploy gira come utente non-root UID 42420, assente da `/etc/passwd`; senza queste PyTorch crasha all'import (`KeyError: getpwuid()`). |
| `--env OUTLINES_CACHE_DIR / TORCHINDUCTOR_CACHE_DIR` | Indirizzano le cache di compilazione sotto `/workspace`, l'unico percorso scrivibile. |
| `--volume vllm-model-*@GRA/:/hub:ro` | I pesi del modello **pre-caricati**, montati in **sola lettura**. Ogni app monta il proprio modello. |
| `--volume vllm-workspace@GRA/:/workspace:rw` | Container scrivibile per le cache runtime: senza un `rw` su `/workspace` l'app crasha con `PermissionError`. È scratch usa-e-getta (nessun write-back). |
| `vllm/vllm-openai:v0.26.0` | Immagine vLLM con **tag fissato** (mai `:latest`). La v0.26.0 copre la linea Qwen3.5/3.6. |
| `--model /hub` | Punta ai file locali del modello. **Adatta il percorso** al punto in cui sta `config.json` nel bucket (`ovhai bucket object list … \| grep config.json`). |
| `--served-model-name Qwen/…` | Nome "pubblico" pulito nell'API: senza, vLLM chiamerebbe il modello `/hub`. È il nome che userai nel client. |
| `--max-model-len 32768` | Finestra di contesto. Alzata da 16384 per evitare il 400 "context length exceeded" nelle sessioni con storia lunga o tool verbosi. |
| `--enable-auto-tool-choice --tool-call-parser qwen3_coder` | Abilita il tool calling; per la linea 3.5/3.6 il parser è `qwen3_coder` (non più `hermes`). |
| `--reasoning-parser qwen3` | Separa il "pensiero" dalla risposta. Resta `qwen3` anche per la 3.5/3.6. |

---

## Collegare gli agenti (nel codice)

Due endpoint distinti nel `.env`, uno per ruolo:

```
VLLM_URL_ORCHESTRATORE=https://<ID_APP_ORCH>.app.gra.ai.cloud.ovh.net/v1
VLLM_URL_SUBAGENTI=https://<ID_APP_SUB>.app.gra.ai.cloud.ovh.net/v1
VLLM_TOKEN=<token unico, stessa label>
```

Nel `ChatOpenAI`: l'orchestratore usa `model="Qwen/Qwen3.6-27B"` + `VLLM_URL_ORCHESTRATORE`; i sotto-agenti `model="Qwen/Qwen3.5-9B"` + `VLLM_URL_SUBAGENTI`.

---

# Variante — un solo modello per tutto (Qwen3.6-35B-A3B-FP8)

Un unico modello capace serve **sia l'orchestratore che i sotto-agenti**: una sola app, una sola L40S, un solo endpoint. È il pattern della Fase 2 (lì era `qwen3:30b` per tutti i ruoli), ora su vLLM. Metà del costo orario rispetto alle due app sopra.

**Prerequisito:** pre-carica `Qwen/Qwen3.6-35B-A3B-FP8` nel container `vllm-model-35b` (o come lo chiami tu).

```bash
ovhai app run \
  --name vllm-motore \
  --flavor l40s-1-gpu \
  --gpu 1 \
  --default-http-port 8000 \
  --label ai_deploy_token=spike-vllm \
  --env HOME=/workspace \
  --env USER=vllm \
  --env LOGNAME=vllm \
  --env OUTLINES_CACHE_DIR=/workspace/.outlines \
  --env TORCHINDUCTOR_CACHE_DIR=/workspace/inductor \
  --volume vllm-model-35b@GRA/:/hub:ro \
  --volume vllm-workspace@GRA/:/workspace:rw \
  vllm/vllm-openai:v0.26.0 \
  -- bash -c "python3 -m vllm.entrypoints.openai.api_server --model /hub --served-model-name Qwen/Qwen3.6-35B-A3B --max-model-len 32768 --enable-auto-tool-choice --tool-call-parser qwen3_coder --reasoning-parser qwen3"
```

**Cosa cambia rispetto alle due app:**
- Un solo `--volume` modello (`vllm-model-35b`), un solo `--served-model-name` (`Qwen/Qwen3.6-35B-A3B`).
- Nel codice **un solo endpoint**: orchestratore e sotto-agenti usano lo stesso `VLLM_URL` e lo stesso `model="Qwen/Qwen3.6-35B-A3B"`. Nessuna distinzione di URL per ruolo.

> ⚠️ **VRAM più stretta che con il 27B.** Il 35B-A3B-FP8 pesa ~35 GB: su una L40S da 48 GB restano ~13 GB per KV cache e cattura dei CUDA graph. Regolare va bene per contesto e concorrenza moderati, ma è più al limite del 27B (~27 GB). Se al caricamento vedi `CUDA out of memory`: abbassa `--max-model-len` (es. 16384) oppure aggiungi `--gpu-memory-utilization 0.95`. È MoE (3B attivi per token), quindi in compenso è **veloce** in inferenza nonostante i 35B totali.

---

## Note operative

- **Validare la v0.26.0**: nuovo tag = ricollaudo. Se un flag non è riconosciuto, guarda lì (`ovhai app logs <ID> --follow`).
- **Spegnere a fine giornata**: `ovhai app stop <ID>` per entrambe; `ovhai app delete <ID>` a spike concluso. Due L40S accese costano il doppio.
- **Alternativa a una sola GPU**: se ti basta *un* modello per tutto (orchestratore + sotto-agenti), servi solo il `35B-A3B` o il `9B` in un'app sola — una L40S, metà costo.


## Quello da usare per il primo test

```bash
ovhai app run \
  --name vllm-motore \
  --flavor l40s-1-gpu \
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
  vllm/vllm-openai:v0.26.0 \
  -- bash -c "python3 -m vllm.entrypoints.openai.api_server --model /hub/qwen3.6-35b-a3b-fp8 --served-model-name Qwen/Qwen3.6-35B-A3B --max-model-len 32768 --enable-auto-tool-choice --tool-call-parser qwen3_coder --reasoning-parser qwen3"
```