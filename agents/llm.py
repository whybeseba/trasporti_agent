"""Il motore di inferenza del progetto: DUE motori intercambiabili.

- "vllm" (default): vLLM su OVH AI Deploy, API compatibile OpenAI.
  Configurazioni in Deploy_due_modelli_vLLM_AI_Deploy.md — motore unico
  (VLLM_URL, VLLM_TOKEN, VLLM_MODEL) oppure due app distinte per ruolo
  (VLLM_URL_ORCHESTRATORE / VLLM_URL_SUBAGENTI e i rispettivi _MODEL).
- "anthropic": API Anthropic (modelli Claude) — vedi agents/llm_anthropic.py.

Come si sceglie, in ordine di precedenza:
  1. `imposta_motore("anthropic")` nel codice (lo fanno le chat _anthropic)
  2. MOTORE_AI=anthropic nel file .env
  3. altrimenti vllm

Questo è l'UNICO punto che sa quale motore gira: agenti, tool, prompt,
registri e orchestratori non cambiano di una riga passando dall'uno all'altro.

Per il tool calling l'app vLLM va avviata con:
  --enable-auto-tool-choice --tool-call-parser qwen3_coder --reasoning-parser qwen3
"""
import os

from dotenv import load_dotenv

load_dotenv()

MODELLO_DEFAULT = "Qwen/Qwen3.6-35B-A3B"
MOTORI = ("vllm", "anthropic")

_motore = os.environ.get("MOTORE_AI", "vllm").strip().lower()
if _motore not in MOTORI:
    raise SystemExit(f"❌ MOTORE_AI='{_motore}' non valido: usa {' o '.join(MOTORI)}")


def imposta_motore(nome: str) -> None:
    """Sceglie il motore a runtime. Va chiamata PRIMA di costruire agenti e
    orchestratori (il registro li costruisce all'import)."""
    global _motore
    if nome not in MOTORI:
        raise SystemExit(f"❌ motore '{nome}' sconosciuto: usa {' o '.join(MOTORI)}")
    _motore = nome


def motore() -> str:
    return _motore


def config_ruolo(ruolo: str = "subagente") -> tuple[str, str]:
    """(url, modello) del motore vLLM per un ruolo, con fallback sulla
    configurazione a motore unico. Ruoli: "subagente" o "orchestratore"."""
    suffisso = "_ORCHESTRATORE" if ruolo == "orchestratore" else "_SUBAGENTI"
    url = os.environ.get(f"VLLM_URL{suffisso}") or os.environ["VLLM_URL"]
    modello = (os.environ.get(f"VLLM_MODEL{suffisso}")
               or os.environ.get("VLLM_MODEL", MODELLO_DEFAULT))
    return url, modello


def modello_in_uso(ruolo: str = "subagente") -> str:
    """Il nome del modello che servirà quel ruolo, qualunque sia il motore.
    Serve ai riepiloghi e alla stima dei costi."""
    if _motore == "anthropic":
        from agents.llm_anthropic import config_ruolo_anthropic
        return config_ruolo_anthropic(ruolo)
    return config_ruolo(ruolo)[1]


def descrizione_motore(ruolo: str = "subagente") -> str:
    """Riga leggibile per i pannelli di avvio delle chat."""
    if _motore == "anthropic":
        from agents.llm_anthropic import caching_attivo
        cache = "caching attivo" if caching_attivo() else "senza caching"
        return f"{modello_in_uso(ruolo)} (API Anthropic, {cache})"
    from urllib.parse import urlparse
    url, modello = config_ruolo(ruolo)
    return f"{modello} (vLLM @ {urlparse(url).hostname})"


def costruisci_llm(ruolo: str = "subagente", temperature: float = 0):
    """L'LLM per un ruolo, costruito sul motore attivo."""
    if _motore == "anthropic":
        from agents.llm_anthropic import costruisci_llm_anthropic
        return costruisci_llm_anthropic(ruolo, temperature)

    from langchain_openai import ChatOpenAI
    url, modello = config_ruolo(ruolo)
    return ChatOpenAI(
        model=modello,
        base_url=url,
        api_key=os.environ["VLLM_TOKEN"],   # header Authorization: Bearer
        temperature=temperature,            # 0 = precisione, non creatività
        # Qwen3.x: spegne il "pensiero ad alta voce"
        extra_body={"chat_template_kwargs": {"enable_thinking": False}},
    )
