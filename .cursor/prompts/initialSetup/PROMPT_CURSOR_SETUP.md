# Prompt per Cursor — verifica e preparazione dell'ambiente sul server

**Come usarlo:** apri Cursor collegato al server Ubuntu via Remote-SSH, apri la
cartella del progetto `trasporti_agent`, poi copia tutto il blocco qui sotto e
incollalo nella chat AI di Cursor (modalità agent). Prima di lanciarlo:
attiva la **Privacy Mode** nelle impostazioni di Cursor (nel progetto c'è già
il file `.cursorignore` che esclude `.env` e `dati/`).

---

```
Sei collegato via SSH a un server Ubuntu con Docker già installato. Nella
cartella corrente c'è il progetto `trasporti_agent`: il motore delle Fasi 1-2
di un portale clienti DKV (Python + LangChain/LangGraph, PostgreSQL e n8n in
Docker). L'inferenza AI NON gira su questo server: gli agenti chiamano un
motore vLLM remoto su OVH AI Deploy (endpoint HTTPS + token, letti dal file
.env). Il tuo compito è SOLO verificare e preparare l'ambiente: non modificare
il codice del progetto, non refactorare nulla.

Esegui in ordine questi controlli e sistemazioni. Per ogni punto: se è già a
posto segnalo ✅, se lo correggi segnalo 🔧 con il comando usato, se non puoi
correggerlo (serve una mia decisione o un valore che ho solo io) segnalo ❌ e
fermati a chiedermelo.

1. DOCKER
   - `docker --version` e `docker compose version` rispondono entrambi.
   - L'utente corrente può usare docker senza sudo (`docker ps` non dà errore
     di permessi; se lo dà: `sudo usermod -aG docker $USER` e avvisami che
     devo riaprire la sessione).

2. STRUTTURA DEL PROGETTO
   - Esistono: `agents/`, `tools/`, `scripts/`, `config/prompts/`,
     `dati/excel_dkv/`, `logs/`. Crea con `mkdir -p` solo quelle mancanti
     (probabilmente `logs/`).
   - Esistono i file: `docker-compose.yml`, `requirements.txt`, `.env.example`,
     `.cursorignore`, `server.py`, `chat_test.py`, `chat_orchestratore.py`.

3. FILE .env (⚠️ non stamparne MAI il contenuto: contiene password e token)
   - Se `.env` non esiste: `cp .env.example .env`, poi fermati e chiedimi di
     compilare a mano POSTGRES_PASSWORD, DATABASE_URL, VLLM_URL, VLLM_TOKEN.
   - Se esiste: verifica solo che definisca le variabili POSTGRES_PASSWORD,
     DATABASE_URL, VLLM_URL, VLLM_TOKEN (controlla i NOMI, ad esempio con
     `grep -c '^NOME_VARIABILE=' .env`, senza mostrare i valori) e che nessuna
     contenga ancora i segnaposto `<...>` o il testo di esempio
     "ScegliUnaPasswordLungaECasuale".
   - Se voglio provare anche i modelli Claude: deve esserci ANTHROPIC_API_KEY
     compilata (senza `<...>`). Se manca, segnalamelo senza bloccare il resto:
     serve solo alle chat *_anthropic.py.
   - Verifica che VLLM_URL termini con `/v1` (puoi controllare con
     `grep -c '^VLLM_URL=.*\/v1\s*$' .env`).
   - Permessi: `chmod 600 .env`.

4. PYTHON
   - `python3 --version` è 3.11 o superiore.
   - I pacchetti di sistema `python3-venv` e `python3-pip` sono installati;
     se mancano: `sudo apt update && sudo apt install -y python3-venv python3-pip`.

5. AMBIENTE VIRTUALE E DIPENDENZE
   - Se `.venv/` non esiste: `python3 -m venv .venv`.
   - `source .venv/bin/activate` e poi:
     `pip install --upgrade pip && pip install -r requirements.txt`.
   - `pip check` non segnala conflitti.
   - Verifica gli import chiave:
     `python -c "import langchain, langgraph, langchain_openai, langchain_anthropic, anthropic, pandas, sqlalchemy, psycopg2, yaml, fastapi, openpyxl, chromadb, sentence_transformers, pypdf, rich; print('import ok')"`
     (nota: sentence-transformers è pesante, l'installazione può richiedere minuti)

6. CONTAINER DOCKER
   - `docker compose up -d` (scarica le immagini alla prima esecuzione).
   - `docker compose ps`: i container `n8n`, `postgres`, `chromadb`, `adminer`
     e `open-webui` sono tutti in stato "running" (non "restarting"). Se uno
     non parte, mostrami le ultime 30 righe dei suoi log
     (`docker compose logs --tail 30 <nome>`).
   - Nessun container espone porte su 0.0.0.0: nell'output di `docker ps` le
     porte pubblicate devono essere tutte su 127.0.0.1.

7. DATABASE
   - `docker exec postgres pg_isready -U trasporti` risponde
     "accepting connections".
   - Con la venv attiva, crea/verifica le tabelle:
     `python -c "from tools.db import crea_tabelle, query; crea_tabelle(); print(query('SELECT COUNT(*) AS clienti FROM clienti').to_string(index=False))"`
     (deve stampare un numero, anche 0: vuol dire che connessione, credenziali
     e schema funzionano).

8. MOTORE vLLM SU OVH (il collaudo più importante)
   - Con la venv attiva: `python -m scripts.test_vllm`
   - Deve stampare l'elenco dei modelli serviti e una risposta del modello.
   - Se fallisce, NON tentare workaround: riporta l'errore esatto. Le cause
     tipiche sono: app AI Deploy spenta (si riaccende con `ovhai app start`,
     ma chiedimelo prima), token errato, VLLM_URL senza /v1, o VLLM_MODEL
     diverso dal --served-model-name dell'app.

9. RETE E SICUREZZA (solo report, non cambiare nulla)
   - Riporta l'output di `sudo ufw status` (o segnala se ufw non è attivo).
   - Conferma che `.gitignore` contiene `.env` e che
     `git status --porcelain` non mostra `.env` né file in `dati/` tra i file
     tracciabili.

10. REPORT FINALE
    - Chiudi con una checklist ✅/🔧/❌ dei 9 punti sopra e l'elenco esatto dei
      comandi che ho ancora da fare io a mano (es. compilare il .env, riaprire
      la sessione per il gruppo docker, caricare gli Excel in dati/excel_dkv/).

Cose da NON fare in nessun caso: stampare o inviare valori di .env; installare
driver GPU, CUDA o Ollama (l'inferenza è remota); aprire porte su 0.0.0.0 o
toccare il firewall; committare o pushare su git; modificare i file Python o
YAML del progetto.
```

---

**Dopo il report di Cursor**, i passi che restano tuoi (non automatizzabili):

1. Compilare `.env` con la password Postgres e con URL + token dell'app AI
   Deploy (l'URL con `/v1` finale).
2. Verificare che l'app su OVH sia avviata **con i flag del tool calling**
   (`--enable-auto-tool-choice --tool-call-parser qwen3_coder --reasoning-parser qwen3`
   — comandi completi in `Deploy_due_modelli_vLLM_AI_Deploy.md`): senza,
   gli agenti non chiamano i tool.
3. Copiare gli export DKV in `dati/excel_dkv/` e adattare
   `config/dkv_mapping.yml` ai nomi reali delle colonne.
4. `python -m scripts.carica_dkv`, poi il collaudo con `chat_test.py`:
   le 5 domande funzionali **e i 3 tentativi di evasione** del §2.8.
5. Copiare le norme/circolari in `dati/normativa/`, compilare `fonti.yml` e
   lanciare `python -m scripts.indicizza_normativa`
   (guida completa: `Guida_Indicizzazione_Normativa.md`).
6. Primo accesso a n8n (`http://localhost:5678` via port-forward) e creazione
   dell'account proprietario.
