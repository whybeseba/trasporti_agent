"""Il modello del progetto: vLLM su OVH AI Deploy (API compatibile OpenAI).

Unico punto in cui si decide QUALE modello usare e DOVE gira: tutti gli
agenti costruiscono il loro LLM da qui. Rispetto alla guida originale
(ChatOllama in locale) cambia solo questo file: prompt, tool, fabbrica e
orchestratore restano identici.

Richiede nel file .env:
  VLLM_URL    es. https://<ID_APP>.app.gra.ai.cloud.ovh.net/v1  (con /v1!)
  VLLM_TOKEN  il token AI Deploy
  VLLM_MODEL  il nome pubblico del modello (default Qwen/Qwen3-8B)

L'app AI Deploy va avviata con i flag per il tool calling degli agenti:
  --enable-auto-tool-choice --tool-call-parser hermes --reasoning-parser qwen3
(vedi Guida_Spike_vLLM_AI_Deploy.md, Parte 5).
"""
import os

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

load_dotenv()  # legge il file .env

MODELLO = os.environ.get("VLLM_MODEL", "Qwen/Qwen3-8B")


def costruisci_llm(temperature: float = 0) -> ChatOpenAI:
    return ChatOpenAI(
        model=MODELLO,
        base_url=os.environ["VLLM_URL"],
        api_key=os.environ["VLLM_TOKEN"],   # viaggia nell'header Authorization: Bearer
        temperature=temperature,            # 0 = precisione, non creatività
        # Qwen3: spegne il "pensiero ad alta voce" (l'equivalente del
        # reasoning=False di ChatOllama; senza, ogni risposta paga i token
        # del blocco <think>)
        extra_body={"chat_template_kwargs": {"enable_thinking": False}},
    )
