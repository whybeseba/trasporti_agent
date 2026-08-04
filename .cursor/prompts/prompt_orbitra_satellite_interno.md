# PROMPT — Conversione di un servizio integrato in "satellite interno" di Orbitra

## Ruolo e obiettivo

Sei l'AI incaricata dello sviluppo di **Orbitra**, una dashboard-aggregatore che raccoglie dati da servizi esterni ("satelliti") tramite API, li presenta in widget e ospita un agente AI che analizza i dati e propone azioni.

Orbitra si regge su una regola architetturale **non negoziabile**:

> **Orbitra non possiede mai i dati di dominio: li chiede al satellite, a ogni chiamata, con i permessi dell'utente.**

Attualmente esiste un servizio i cui dati arrivano via **file Excel caricati manualmente ogni ~15 giorni** e che oggi vive **dentro il database di Orbitra**, con la dashboard che legge le sue tabelle con query dirette. Questo viola la regola e va corretto.

Il tuo compito: **trasformare questo servizio in un "satellite interno"** — un servizio che gira sull'infrastruttura di Orbitra ma che, dal punto di vista della dashboard, dell'agente AI e di ogni altro consumatore, è indistinguibile da un satellite esterno. Orbitra torna a non possedere dati di dominio; il satellite interno li possiede e li espone attraverso il contratto satellite standard.

La motivazione strategica: Orbitra è un **trampolino**. I servizi poco strutturati vi si appoggiano, maturano e un giorno diventano servizi autonomi. Se la dashboard accede alle loro tabelle direttamente, quel giorno la migrazione è una riscrittura. Se accede solo tramite il contratto satellite, la graduation è: spostare lo schema, aggiornare una URL nella service discovery, fine.

---

## Architettura richiesta

### 1. Confine netto (bounded context)

- Il satellite interno ha un **proprio schema database dedicato** (o database separato). Nessun'altra parte di Orbitra ha permessi di lettura o scrittura su quello schema: né la dashboard, né l'agente, né altri servizi.
- Il satellite interno espone una **propria API HTTP** ed è l'unico punto di accesso ai suoi dati.
- **Vietati**: query dirette della dashboard sulle tabelle del satellite, JOIN cross-schema tra dati di Orbitra e dati del satellite, viste o materialized view che attraversano il confine, accesso condiviso tramite ORM comune.
- La dashboard raggiunge il satellite tramite **service discovery** (URL configurabile), mai tramite connessione database. Questo è ciò che rende la futura estrazione un'operazione di configurazione.

### 2. Contratto satellite (obbligatorio, identico ai satelliti esterni)

Il satellite interno implementa lo stesso contratto degli altri satelliti dell'ecosistema:

- **Autenticazione delegata OAuth2/OIDC**: ogni chiamata porta un access token emesso da Orbitra Identity. Il satellite valida `iss`, `aud` (deve essere il proprio resource indicator), scadenza e firma via JWKS. Nessun accesso anonimo o con credenziali condivise interne.
- **Autorizzazione risolta dal satellite, mai replicata in Orbitra**: il satellite decide cosa l'utente può vedere in base ai propri permessi interni. La dashboard chiede i dati e riceve dati già filtrati; non chiede mai "cosa può vedere questo utente" per costruirsi un'ACL locale.
- **Scope granulari** mappati sulle azioni: separare almeno `read` da ogni scrittura (`create`, `update`, `delete`, `import`). L'agente AI riceve solo scope di lettura.
- **Header `X-Permissions-Version`** su ogni risposta: un valore che cambia ogni volta che i permessi dell'utente sul satellite cambiano. La dashboard lo include nella chiave di cache: alla revoca di un permesso, la cache precedente diventa irraggiungibile senza invalidazione esplicita.
- **Audit a due soggetti**: ogni operazione registra il soggetto umano (`sub`) e, se la chiamata proviene dall'agente autonomo, il client agente come attore (`act`, claim RFC 8693). Deve essere sempre distinguibile "l'utente ha fatto X" da "l'agente ha fatto X per conto dell'utente".
- **Endpoint di revoca**: quando un utente revoca la connessione del proprio account al satellite, il satellite invalida ogni accesso delegato residuo.
- **Freschezza come dato di prima classe**: ogni record e ogni risposta aggregata portano un `valid_as_of` (data a cui i dati sono riferiti, non data di caricamento). Con dati quindicinali questo è essenziale: i widget lo mostrano, e l'agente AI lo riceve e **non genera proposte** basate su fonti oltre una soglia di anzianità configurabile — o, se le genera incrociando fonti di freschezza diversa, dichiara esplicitamente l'anzianità della fonte più vecchia.
- **Cancellazione GDPR**: il satellite espone un endpoint di erasure per soggetto. Le chiavi di cifratura per-soggetto vengono chiavi dal servizio condiviso di key management dell'ecosistema (non un'implementazione locale), così il crypto-shred di un soggetto si propaga con una sola operazione.

### 3. Pipeline di ingestione Excel (di proprietà del satellite, non di Orbitra)

L'acquisizione dei file è una funzione **interna al satellite**:

- **Batch versionati, mai overwrite**: ogni import crea una riga in `import_batches` (hash del file, utente che ha caricato, periodo coperto, righe accettate/scartate/in errore, stato) e ogni record dati referenzia il batch di provenienza. Un file correttivo genera una nuova versione; la storia resta interrogabile ("perché questo numero è cambiato" deve avere una risposta).
- **Staging e quarantena**: validazione in area separata, promozione solo dopo esito positivo; righe scartate conservate con motivazione.
- **Idempotenza tramite hash del file**: ricaricare lo stesso file non duplica nulla.
- **Il caricamento è azione ad alto privilegio**: richiede scope dedicato (`import`), step-up authentication (riautenticazione recente / secondo fattore verificato tramite `acr`/`amr` e `max_age`), audit completo. Il file originale viene conservato cifrato in Object Storage con la propria retention.
- L'automazione futura dell'acquisizione sostituirà il canale di ingresso (upload umano → feed automatico) **senza toccare il contratto verso i consumatori**: è un cambiamento interno al satellite.

### 4. Migrazione dallo stato attuale

Procedi in questi passi, in ordine, senza saltarne:

1. **Censimento**: elenca tutte le tabelle del servizio oggi nel DB di Orbitra e tutti i punti del codice (dashboard, agente, job) che le leggono o scrivono direttamente.
2. **Carve-out dello schema**: sposta le tabelle nello schema dedicato del satellite; revoca i permessi di accesso a ogni altro componente.
3. **API facade**: costruisci l'API del satellite che copre tutti i casi d'uso censiti al punto 1, conforme al contratto della sezione 2.
4. **Taglio delle query dirette**: sostituisci ogni accesso diretto con chiamate all'API, un consumatore alla volta, verificando la parità funzionale.
5. **Registrazione**: il satellite entra nella service discovery e nel registry dei satelliti come gli altri; la dashboard lo tratta come esterno.
6. **Verifica finale**: nessuna connessione database residua attraversa il confine (verificalo dai grant del DB, non solo dal codice).

### 5. Anti-obiettivi (cosa NON fare)

- Non lasciare "scorciatoie temporanee" di lettura diretta per performance: se una vista aggregata è lenta via API, l'ottimizzazione va fatta **dentro** il satellite (endpoint aggregato dedicato, cache interna), non bucando il confine.
- Non replicare in Orbitra i permessi del satellite, nemmeno come cache "di cortesia".
- Non condividere modelli/entità ORM tra Orbitra e il satellite: i tipi che attraversano il confine sono i DTO dell'API, generati dal contratto.
- Non far dipendere il satellite da tabelle di Orbitra per funzionare (a parte la validazione dei token verso Orbitra Identity).

---

## Output atteso da te

1. **Censimento** delle tabelle e dei punti di accesso diretto attuali.
2. **Progetto dello schema** del satellite (incluse `import_batches` e le strutture di staging).
3. **Specifica dell'API** del satellite conforme al contratto (endpoint, scope richiesti, formato `valid_as_of`, `X-Permissions-Version`, audit, revoca, erasure).
4. **Piano di migrazione** con l'ordine dei tagli e i criteri di verifica di ciascun passo.
5. **Elenco dei punti aperti** che richiedono una decisione umana (es. soglia di anzianità dati per l'agente, retention dei file originali, mapping dei permessi interni del satellite).

Se qualcosa nel sistema attuale contraddice queste istruzioni o rende ambiguo un passo, **fermati e chiedi** prima di implementare: la tenuta del confine vale più della velocità di consegna.
