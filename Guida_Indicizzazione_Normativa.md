# Guida — Indicizzare norme e circolari per l'agente Normativa (RAG su ChromaDB)

> Come trasformare una cartella di PDF di norme e circolari nella "biblioteca"
> che l'agente Normativa consulta per rispondere ai clienti — con fonte e data
> citate in ogni risposta. Da ripetere ogni volta che il corpus cambia.

**Cosa avrai alla fine:**
1. ChromaDB acceso in Docker con il corpus normativo indicizzato
2. L'agente Normativa che risponde citando titolo, fonte e data dei documenti
3. Il rito di manutenzione per quando le norme cambiano

---

## Parte 0 — I concetti (5 minuti ben spesi)

> 📖 **RAG (Retrieval-Augmented Generation):** invece di sperare che il modello
> "ricordi" le norme (le inventerebbe: si chiama allucinazione), gli si dà uno
> strumento di **ricerca**: alla domanda del cliente, il sistema pesca i
> passaggi più pertinenti dai documenti veri e il modello risponde SOLO
> basandosi su quelli, citandoli. Il modello mette la lingua, i documenti
> mettono la verità.
>
> 📖 **Database vettoriale (ChromaDB):** un archivio che indicizza i testi per
> **significato**, non per parole esatte. "Quante consegne posso fare in
> Francia dopo un viaggio internazionale?" trova i passaggi sul *cabotaggio*
> anche se la domanda non contiene quella parola.
>
> 📖 **Embedding:** la traduzione di un testo in una lista di numeri che ne
> rappresenta il significato: testi simili → numeri vicini. Li calcola un
> piccolo modello **multilingue** che gira sulla CPU del server (niente GPU:
> quella su OVH serve solo a generare le risposte).
>
> 📖 **Chunk (blocco):** i documenti si indicizzano a pezzi di ~1.200
> caratteri, perché la ricerca funziona meglio su passaggi brevi e mirati che
> su un PDF intero. Lo script spezza seguendo i paragrafi e fa "ripartire"
> ogni blocco con la coda del precedente, così un articolo tagliato a metà
> resta comprensibile.

**Il principio che comanda (dall'architettura, §2):** il corpus è **condiviso
tra tutti i clienti** — è il motivo per cui l'agente Normativa è
`per_cliente: false` nel registro. Quindi dentro ci vanno **solo documenti
pubblici**: norme, regolamenti, circolari. **Mai** dati di clienti, contratti,
listini o note interne: qualunque cosa indicizzi qui può riemergere nella
chat di qualunque cliente.

---

## Parte 1 — Accendere ChromaDB

È già nel `docker-compose.yml` (porta `127.0.0.1:8001`, dati nel volume
`chroma_data`). Basta:

```bash
docker compose up -d
docker compose ps        # "chromadb" deve essere running
```

E le nuove librerie Python (la prima installazione è pesante, ~1-2 GB:
`sentence-transformers` porta con sé PyTorch per la CPU):

```bash
source .venv/bin/activate
pip install -r requirements.txt
```

## Parte 2 — Preparare il corpus (il lavoro che conta davvero)

La qualità delle risposte dell'agente è un riflesso della qualità di questa
cartella: **curare il corpus è il vero lavoro**, l'indicizzazione è un comando.

**Dove:** i documenti vanno in `dati/normativa/` (formati: `.pdf`, `.txt`,
`.md`). La cartella è esclusa da git e da Cursor: i file restano solo sul
server.

**Regole di selezione:**
1. **Versioni consolidate**, non bozze né riassunti di terzi: il testo del
   regolamento dalla Gazzetta ufficiale (EUR-Lex per le norme UE, Normattiva
   per quelle italiane), la circolare dal sito del Ministero.
2. **PDF con testo selezionabile.** Se in un PDF non riesci a selezionare il
   testo col mouse è una scansione: lo script la salta avvisandoti (servirebbe
   l'OCR — tienile da parte e dimmelo, lo aggiungiamo se serve).
3. **Un tema per file** quando puoi: meglio "circolare sul cabotaggio" e
   "circolare sul distacco" separate che un PDF unico da 400 pagine.
4. **Niente duplicati né versioni superate:** quando esce la circolare nuova,
   la vecchia si **toglie** dalla cartella (la ricerca non sa quale sia quella
   buona: se le lasci entrambe, citerà anche l'abrogata).

**Con cosa partire (suggerimento per l'autotrasporto):** Regolamento (CE)
1072/2009 (accesso al mercato e cabotaggio), Regolamento (CE) 561/2006 (tempi
di guida e riposo), la direttiva sul distacco dei conducenti (2020/1057) e le
circolari ministeriali applicative che già usi in azienda. Parti con 5-10
documenti buoni: si allarga dopo.

## Parte 3 — Il manifest delle fonti

Compila `dati/normativa/fonti.yml`: per ogni file, titolo, fonte e data.
**È ciò che l'agente cita al cliente** — un file non elencato viene
indicizzato lo stesso, ma citato solo col nome del file e senza data.

```yaml
documenti:
  "regolamento_ce_1072_2009.pdf":
    titolo: "Regolamento (CE) n. 1072/2009 — accesso al mercato del trasporto internazionale su strada"
    fonte: "Gazzetta ufficiale dell'Unione europea"
    data: "2009-10-21"
  "circolare_cabotaggio_2026.pdf":
    titolo: "Circolare MIT — chiarimenti sul cabotaggio stradale"
    fonte: "Ministero delle Infrastrutture e dei Trasporti"
    data: "2026-02-10"
```

La data non è un vezzo: il prompt dell'agente la usa per avvisare il cliente
quando un documento ha qualche anno ("la norma potrebbe essere stata
aggiornata").

## Parte 4 — Indicizzare

```bash
python -m scripts.indicizza_normativa
```

Cosa fa: legge i file, li spezza in blocchi, calcola gli embedding (la prima
volta scarica il modello multilingue, qualche minuto) e **ricostruisce la
collezione da zero**. Ogni esecuzione è una re-indicizzazione completa: col
corpus di poche centinaia di documenti costa pochi minuti, e in cambio
l'indice rispecchia SEMPRE esattamente la cartella — niente residui di file
cancellati.

Output atteso: una riga `✅` per documento col numero di blocchi, e gli
eventuali `⚠️` (file non nel manifest, PDF senza testo).

## Parte 5 — Collaudo

**Prima la ricerca da sola** (senza modello di mezzo — così se qualcosa non
va sai subito se il problema è l'indice o l'agente):

```bash
python -m scripts.test_normativa "quanti trasporti di cabotaggio posso fare in Francia?"
```

Devi vedere 4 passaggi pertinenti, ognuno con titolo, fonte, data e una
**distanza** (più bassa = più pertinente; sopra ~0.6-0.7 il passaggio c'entra
poco — se tutti i risultati sono lì, il corpus non copre la domanda).

**Poi l'agente completo**, impersonando un cliente:

```bash
python chat_test.py
```

Domande di collaudo funzionale:
1. *"Come funziona il cabotaggio dopo un viaggio internazionale?"* → deve
   passare dallo specialista normativa, citare fonte e data, chiudere col
   disclaimer.
2. *"Quanto ho speso di pedaggi quest'anno?"* → deve passare dai costi DKV
   (il router smista bene?).
3. Una domanda su un tema che NON è nel corpus (es. *"che targhe servono in
   Svizzera?"* se non hai nulla in merito) → deve dire che non lo sa e
   invitare a contattarvi, NON improvvisare.

**E il collaudo di sicurezza** (§2.8 della guida principale, come sempre):
anche via specialista normativa, i tentativi di farsi dare dati di altri
clienti devono fallire — questo agente non ha proprio strumenti sui dati,
ma il rito si ripete a ogni nuovo membro del team.

## Parte 6 — Manutenzione (il rito quando le norme cambiano)

1. Scarica il documento nuovo in `dati/normativa/`
2. **Togli** la versione superata dalla cartella
3. Aggiorna `fonti.yml` (voce nuova, via quella vecchia)
4. `python -m scripts.indicizza_normativa`
5. Un giro di `python -m scripts.test_normativa` sul tema aggiornato

Metti in agenda un controllo del corpus **ogni 3-6 mesi** (stessa cadenza con
cui l'architettura fa rivedere modelli e listini): l'architettura lo dice
chiaro, qualcuno deve mantenere il corpus, e quel qualcuno per ora sei tu.
In Fase 4 potrai farti aiutare da n8n (promemoria periodico automatico).

## Problemi comuni

| Sintomo | Causa probabile | Soluzione |
|---|---|---|
| `Connection refused` su localhost:8001 | Container chromadb spento | `docker compose up -d`, poi `docker compose ps` |
| Lo script salta un PDF con "quasi nessun testo estratto" | PDF scansionato (immagine, non testo) | Recupera la versione testuale, o accantonalo per l'OCR |
| Risultati con distanze tutte alte / fuori tema | Il corpus non copre la domanda | Aggiungi il documento giusto e re-indicizza; non è un difetto del RAG |
| L'agente risponde senza citare le fonti | Documento non nel manifest, o prompt modificato | Compila `fonti.yml` e re-indicizza; verifica `config/prompts/agente_normativa.txt` |
| L'agente "sa" cose non nel corpus | Sta improvvisando dalla sua memoria di addestramento | Il prompt lo vieta (regole 1 e 3): se succede, segnalamelo con la domanda esatta |
| Il router manda le domande normative ai costi DKV (o viceversa) | Descrizioni del registro poco distinguibili | Ritocca le `descrizione` in `config/agents_clienti.yml` con esempi concreti |
| Prima indicizzazione lentissima | Download del modello di embedding + PyTorch | Solo la prima volta; poi resta in cache |
| `no such column` o errori strani dal client Chroma | Versioni client/server disallineate | Il client `chromadb` (pip) e l'immagine Docker devono essere entrambi 1.x; aggiorna il più vecchio dei due |

## ✅ Checklist

- [ ] `chromadb` running in `docker compose ps`
- [ ] Corpus in `dati/normativa/` (consolidato, testuale, senza versioni doppie)
- [ ] `fonti.yml` compilato per ogni documento
- [ ] `indicizza_normativa` completato senza `⚠️` inattesi
- [ ] `test_normativa` restituisce passaggi pertinenti con fonte e data
- [ ] `chat_test.py`: il router smista bene tra normativa e costi DKV
- [ ] Domanda fuori corpus → l'agente lo ammette invece di inventare
- [ ] Collaudo di sicurezza §2.8 ripetuto
- [ ] Promemoria manutenzione corpus in agenda (3-6 mesi)

---

*Guida corpus normativo — luglio 2026. Il disclaimer "non è consulenza legale"
è nel prompt dell'agente: non toglierlo.*
