"""Il modello del progetto: vLLM su OVH AI Deploy (API compatibile OpenAI).

Unico punto in cui si decide QUALE modello usare e DOVE gira. Supporta le due
configurazioni di Deploy_due_modelli_vLLM_AI_Deploy.md:

- MOTORE UNICO ("Quello da usare per il primo test", default): nel .env
  bastano VLLM_URL, VLLM_TOKEN e VLLM_MODEL — orchestratore e sub-agenti
  condividono lo stesso endpoint e lo stesso modello.
- DUE MOTORI (orchestratore 27B + sub-agenti 9B): aggiungi nel .env le
  variabili per-ruolo (VLLM_URL_ORCHESTRATORE / VLLM_MODEL_ORCHESTRATORE e
  VLLM_URL_SUBAGENTI / VLLM_MODEL_SUBAGENTI) e ogni ruolo va sul suo motore.
  Il token è unico (stessa label sulle due app). Nessun cambio di codice.

L'app AI Deploy va avviata con i flag per il tool calling della linea
Qwen3.5/3.6:  --enable-auto-tool-choice --tool-call-parser qwen3_coder
              --reasoning-parser qwen3
"""
import os

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

load_dotenv()  # legge il file .env

MODELLO_DEFAULT = "Qwen/Qwen3.6-35B-A3B"


def config_ruolo(ruolo: str = "subagente") -> tuple[str, str]:
    """(url, modello) per un ruolo, con fallback sulla configurazione a
    motore unico. Ruoli: "subagente" (default) o "orchestratore"."""
    suffisso = "_ORCHESTRATORE" if ruolo == "orchestratore" else "_SUBAGENTI"
    url = os.environ.get(f"VLLM_URL{suffisso}") or os.environ["VLLM_URL"]
    modello = (os.environ.get(f"VLLM_MODEL{suffisso}")
               or os.environ.get("VLLM_MODEL", MODELLO_DEFAULT))
    return url, modello


def costruisci_llm(ruolo: str = "subagente", temperature: float = 0) -> ChatOpenAI:
    """Con il motore unico i due ruoli coincidono; con due app ognuno legge
    le sue variabili .env."""
    url, modello = config_ruolo(ruolo)
    return ChatOpenAI(
        model=modello,
        base_url=url,
        api_key=os.environ["VLLM_TOKEN"],   # header Authorization: Bearer
        temperature=temperature,            # 0 = precisione, non creatività
        # Qwen3.x: spegne il "pensiero ad alta voce" (equivalente del
        # reasoning=False di ChatOllama)
        extra_body={"chat_template_kwargs": {"enable_thinking": False}},
    )
