"""Osservabilità in tempo reale delle chat di collaudo.

Mostra a terminale che cosa succede davvero dentro il sistema: la scelta del
router, quale specialista prende in carico la domanda, quando un agente sta
"pensando" (cioè sta aspettando il modello su OVH), quali tool vengono
chiamati con quali argomenti e cosa restituiscono, quanti token entrano ed
escono e quanta finestra di contesto stai consumando.

Si aggancia a LangChain/LangGraph come callback handler: gli eventi di
modello e tool arrivano da soli, senza sporcare il codice degli agenti. Gli
orchestratori aggiungono solo tre annotazioni (chi ha scelto il router, quale
specialista entra ed esce) tramite le funzioni in fondo al modulo, che sono
NO-OP quando la traccia non è attiva — quindi in produzione (server.py) non
cambia nulla.

Usato da chat_test.py e chat_orchestratore.py.
"""
import os
import threading
import time
from collections import Counter, defaultdict

try:
    from rich.console import Console
    from rich.markup import escape
    from rich.panel import Panel
    from rich.table import Table
except ImportError:  # pragma: no cover
    raise SystemExit("Manca la libreria 'rich': pip install -r requirements.txt")

from tools.costi import (CAMBIO_EUR_USD, QUOTA_CACHE_TIPICA, costo_esatto,
                         prezzi, stima)

from langchain_core.callbacks import BaseCallbackHandler

# Finestra di contesto del motore: è il --max-model-len con cui hai avviato
# l'app AI Deploy. Serve solo a calcolare la percentuale di contesto usata.
MAX_CONTESTO = int(os.environ.get("VLLM_MAX_MODEL_LEN", "32768"))


# ── formattazione ────────────────────────────────────────────────────────

def _num(n: int) -> str:
    """1204 → '1.204' (separatore italiano)."""
    return f"{n:,}".replace(",", ".")


def _plurale(n: int, singolare: str, plurale: str) -> str:
    return f"{n} {singolare if n == 1 else plurale}"


def _taglia(testo: str, massimo: int = 220) -> str:
    """Testo su una riga sola, accorciato: i risultati dei tool possono
    essere tabelle lunghe e qui interessa il colpo d'occhio."""
    piatto = " ".join(str(testo).split())
    return piatto if len(piatto) <= massimo else piatto[:massimo] + "…"


def _colore_contesto(frazione: float) -> str:
    return "green" if frazione < 0.5 else ("yellow" if frazione < 0.8 else "red")


def _estrai_token(risposta) -> tuple[int, int, int, int]:
    """(input, output, riletti da cache, scritti in cache) dalla risposta.

    Col motore Anthropic questi sono i token ESATTI che l'API fattura: la
    risposta li riporta, cache inclusa. Col motore vLLM le due voci di cache
    restano a 0. `input_tokens` di LangChain comprende già i token di cache,
    quindi il resto si ricava per differenza."""
    try:
        for generazioni in risposta.generations:
            for g in generazioni:
                uso = getattr(getattr(g, "message", None), "usage_metadata", None)
                if uso:
                    dettagli = uso.get("input_token_details") or {}
                    return (int(uso.get("input_tokens", 0)),
                            int(uso.get("output_tokens", 0)),
                            int(dettagli.get("cache_read", 0)),
                            int(dettagli.get("cache_creation", 0)))
    except Exception:
        pass
    uso = (getattr(risposta, "llm_output", None) or {}).get("token_usage") or {}
    return (int(uso.get("prompt_tokens", 0)),
            int(uso.get("completion_tokens", 0)), 0, 0)


class _Attesa:
    """Lo spinner «sta pensando…». Su un terminale vero è animato; se l'output
    è rediretto su file si limita a non disturbare.

    ⚠️ Deve essere a prova di concorrenza: da quando il router scompone la
    domanda, più specialisti girano IN PARALLELO e le loro chiamate al modello
    aprono e chiudono l'attesa da thread diversi. Senza lock due thread
    possono lasciare acceso un display di rich che nessuno spegne più: lo
    spinner resta appeso per sempre e, finché è attivo, si mangia ciò che
    scrivi al prompt. Perciò: un solo spinner, un conteggio delle attese
    aperte, un lock, e la possibilità di spegnere tutto d'autorità."""

    def __init__(self, console: Console):
        self.console = console
        self._stato = None
        self._aperte = 0
        self._ultima = ""
        self._lock = threading.RLock()

    def _testo(self) -> str:
        if self._aperte > 1:
            return (f"[dim]{self._aperte} chiamate al modello in "
                    f"parallelo…[/dim]")
        return self._ultima

    def avvia(self, testo: str) -> None:
        with self._lock:
            self._aperte += 1
            self._ultima = testo
            if not self.console.is_terminal:
                return
            if self._stato is not None:          # già acceso: aggiorna e basta
                try:
                    self._stato.update(self._testo())
                except Exception:
                    pass
                return
            nuovo = None
            try:
                nuovo = self.console.status(self._testo(), spinner="dots")
                nuovo.start()
                self._stato = nuovo
            except Exception:
                # non lasciare mai un display orfano acceso
                if nuovo is not None:
                    try:
                        nuovo.stop()
                    except Exception:
                        pass

    def ferma(self) -> None:
        """Chiude UNA attesa; lo spinner si spegne solo quando finiscono tutte."""
        with self._lock:
            self._aperte = max(0, self._aperte - 1)
            if self._aperte == 0:
                self._spegni()
            elif self._stato is not None:
                try:
                    self._stato.update(self._testo())
                except Exception:
                    pass

    def spegni_tutto(self) -> None:
        """Rete di sicurezza: prima di leggere da tastiera e a fine turno,
        così un'attesa rimasta appesa non blocca comunque il prompt."""
        with self._lock:
            self._aperte = 0
            self._spegni()

    def _spegni(self) -> None:
        if self._stato is not None:
            try:
                self._stato.stop()
            except Exception:
                pass
            self._stato = None


# ── il tracciatore ───────────────────────────────────────────────────────

class Traccia(BaseCallbackHandler):
    """Callback handler: intercetta modello e tool e li racconta a terminale."""

    def __init__(self, console: Console | None = None,
                 max_contesto: int = MAX_CONTESTO):
        self.console = console or Console()
        self.max_contesto = max_contesto
        self.attore = "orchestratore"
        self._attesa = _Attesa(self.console)
        self._in_corso: dict = {}          # run_id → dati della chiamata

        self._reset_turno()
        self.turni = 0
        self.sessione_in = self.sessione_out = 0
        self.sessione_llm = self.sessione_tool = 0
        self.sessione_durata = 0.0
        self.picco_contesto = 0
        self.tool_usati: Counter = Counter()
        # chi consuma i token: orchestratore, router, ogni specialista
        self.per_attore: dict[str, dict] = defaultdict(
            lambda: {"in": 0, "out": 0, "chiamate": 0})
        # token di cache (solo motore Anthropic) e costo esatto in dollari
        self.cache_lette = self.cache_scritte = 0
        self.costo_usd = 0.0
        self.costo_calcolabile = False   # True appena un modello è in listino
        self.modelli_visti: Counter = Counter()

    def _reset_turno(self) -> None:
        self.turno_in = self.turno_out = 0
        self.turno_llm = self.turno_tool = 0
        self.turno_contesto = 0
        self._t0_turno = time.perf_counter()

    def _stampa(self, testo: str, una_riga: bool = False) -> None:
        # Non tocca lo spinner: rich stampa sopra l'area animata, e con le
        # chiamate in parallelo l'attesa la chiude solo chi l'ha aperta
        # (on_llm_end / on_llm_error), altrimenti il conteggio si sfalsa.
        # una_riga: il risultato di un tool può essere una tabella lunga —
        # qui serve il colpo d'occhio, non il contenuto integrale.
        self.console.print(testo, no_wrap=una_riga,
                           overflow="ellipsis" if una_riga else None)

    def pausa(self) -> None:
        """Spegne qualunque attesa animata. Va chiamata prima di leggere da
        tastiera: un display rimasto acceso renderebbe invisibile ciò che
        l'utente scrive."""
        self._attesa.spegni_tutto()

    # ── eventi del modello ───────────────────────────────────────────────

    def on_chat_model_start(self, serialized, messages, **kwargs):
        n_messaggi = len(messages[0]) if messages else 0
        self._inizio_llm(kwargs, serialized, n_messaggi)

    def on_llm_start(self, serialized, prompts, **kwargs):
        self._inizio_llm(kwargs, serialized, len(prompts or []))

    def _inizio_llm(self, kwargs, serialized, n_messaggi: int) -> None:
        modello = ((kwargs.get("invocation_params") or {}).get("model")
                   or (kwargs.get("metadata") or {}).get("ls_model_name")
                   or "modello")
        self._in_corso[kwargs.get("run_id")] = {
            "t0": time.perf_counter(), "modello": modello, "messaggi": n_messaggi,
        }
        self._attesa.avvia(
            f"[dim]{escape(self.attore)} sta pensando… "
            f"({n_messaggi} messaggi → {escape(str(modello))})[/dim]")

    def on_llm_end(self, response, **kwargs):
        self._attesa.ferma()
        dati = self._in_corso.pop(kwargs.get("run_id"), {})
        durata = time.perf_counter() - dati.get("t0", time.perf_counter())
        tok_in, tok_out, letti, scritti = _estrai_token(response)

        self.turno_llm += 1
        self.turno_in += tok_in
        self.turno_out += tok_out
        quota = self.per_attore[self.attore]
        quota["in"] += tok_in
        quota["out"] += tok_out
        quota["chiamate"] += 1
        contesto = tok_in + tok_out
        self.turno_contesto = max(self.turno_contesto, contesto)
        self.picco_contesto = max(self.picco_contesto, contesto)

        # costo esatto: possibile solo quando il modello è in listino
        # (cioè col motore Anthropic); qui tok_in include già la cache
        self.cache_lette += letti
        self.cache_scritte += scritti
        modello = dati.get("modello", "")
        self.modelli_visti[modello] += 1
        usd = costo_esatto(modello, max(0, tok_in - letti - scritti), tok_out,
                           letti, scritti)
        if usd is not None:
            self.costo_usd += usd
            self.costo_calcolabile = True

        # sotto i 2 decimi di secondo la velocità non è una misura, è rumore
        velocita = f" · {tok_out / durata:.0f} tok/s" if durata > 0.2 and tok_out else ""
        frazione = contesto / self.max_contesto if self.max_contesto else 0
        colore = _colore_contesto(frazione)
        conteggio = (f"in {_num(tok_in)} ({dati.get('messaggi', 0)} msg) → "
                     f"out {_num(tok_out)}" if tok_in or tok_out
                     else "token non riportati dal motore")

        self._stampa(
            f"   [magenta]🧠[/magenta] [dim]{escape(dati.get('modello', ''))}[/dim] "
            f"{durata:.1f}s · {conteggio}{velocita} · "
            f"[{colore}]ctx {frazione:.0%}[/{colore}]")

    def on_llm_error(self, error, **kwargs):
        self._attesa.ferma()
        self._in_corso.pop(kwargs.get("run_id"), None)
        self._stampa(f"   [red]❌ errore dal modello:[/red] {escape(_taglia(error))}")

    # ── eventi dei tool ──────────────────────────────────────────────────

    def on_tool_start(self, serialized, input_str, **kwargs):
        nome = (serialized or {}).get("name", "tool")
        argomenti = kwargs.get("inputs")
        if isinstance(argomenti, dict):
            resa = ", ".join(f"{k}={v!r}" for k, v in argomenti.items())
        else:
            resa = _taglia(input_str, 120)
        self._in_corso[kwargs.get("run_id")] = {"t0": time.perf_counter(), "nome": nome}
        self.turno_tool += 1
        self.tool_usati[nome] += 1
        self._stampa(f"   [yellow]🔧[/yellow] [bold]{escape(nome)}[/bold]"
                     f"([dim]{escape(resa)}[/dim])")

    def on_tool_end(self, output, **kwargs):
        dati = self._in_corso.pop(kwargs.get("run_id"), {})
        durata = time.perf_counter() - dati.get("t0", time.perf_counter())
        testo = getattr(output, "content", output)
        self._stampa(f"      [dim]↳ {durata:.2f}s · {len(str(testo))} caratteri · "
                     f"{escape(_taglia(testo))}[/dim]", una_riga=True)

    def on_tool_error(self, error, **kwargs):
        dati = self._in_corso.pop(kwargs.get("run_id"), {})
        self._stampa(f"      [red]❌ il tool {escape(dati.get('nome', ''))} "
                     f"è fallito:[/red] {escape(_taglia(error))}")

    # ── annotazioni degli orchestratori ──────────────────────────────────

    def router_deciso(self, incarichi: list, disponibili=None) -> None:
        """incarichi: [{"specialista", "domanda"}] — vuoto = risposta diretta."""
        elenco = f" [dim](tra: {', '.join(disponibili)})[/dim]" if disponibili else ""
        if not incarichi:
            self._stampa(f"   [magenta]🧭 nessuno specialista:[/magenta] "
                         f"risponde l'orchestratore{elenco}")
        elif len(incarichi) == 1:
            i = incarichi[0]
            sotto = (f" [dim]· «{escape(_taglia(i['domanda'], 90))}»[/dim]"
                     if i.get("domanda") else "")
            self._stampa(f"   [magenta]🧭 specialista scelto:[/magenta] "
                         f"[bold cyan]{escape(i['specialista'])}[/bold cyan]"
                         f"{sotto}{elenco}")
        else:
            self._stampa(f"   [magenta]🧭 domanda scomposta in "
                         f"{len(incarichi)} incarichi in parallelo:[/magenta]{elenco}")
            for i in incarichi:
                self._stampa(f"      → [bold cyan]{escape(i['specialista'])}"
                             f"[/bold cyan]: [dim]«{escape(_taglia(i.get('domanda') or '(domanda intera)', 90))}»[/dim]")

    def specialista_inizio(self, nome: str) -> None:
        self.attore = nome
        self._stampa(f"\n  [bold cyan]🤖 {escape(nome)}[/bold cyan]")

    def specialista_fine(self) -> None:
        self.attore = "orchestratore"

    # ── turni e riepiloghi ───────────────────────────────────────────────

    def inizio_turno(self, numero: int, domanda: str, etichetta: str = "") -> None:
        self._attesa.spegni_tutto()
        self._reset_turno()
        self.attore = "orchestratore"
        self.console.rule(f"[bold]Turno {numero}[/bold]"
                          + (f" · {escape(etichetta)}" if etichetta else ""))
        self.console.print(f"[bold]▶ Domanda:[/bold] {escape(domanda)}\n")
        self.console.print("  [magenta]🧭 orchestratore · router[/magenta]")

    def fine_turno(self, risposta: str) -> None:
        self._attesa.spegni_tutto()
        durata = time.perf_counter() - self._t0_turno
        self.turni += 1
        self.sessione_in += self.turno_in
        self.sessione_out += self.turno_out
        self.sessione_llm += self.turno_llm
        self.sessione_tool += self.turno_tool
        self.sessione_durata += durata

        self._stampa(f"\n  [bold green]💬 Risposta:[/bold green] {escape(risposta)}\n")
        frazione = self.turno_contesto / self.max_contesto if self.max_contesto else 0
        colore = _colore_contesto(frazione)
        self.console.print(Panel(
            f"{durata:.1f}s · "
            f"{_plurale(self.turno_llm, 'chiamata al modello', 'chiamate al modello')} · "
            f"{_plurale(self.turno_tool, 'tool', 'tool')}\n"
            f"token: in {_num(self.turno_in)} · out {_num(self.turno_out)}\n"
            f"contesto massimo: [{colore}]{_num(self.turno_contesto)} / "
            f"{_num(self.max_contesto)} ({frazione:.0%})[/{colore}]",
            title="riepilogo turno", border_style="dim", expand=False))

    def riepilogo_sessione(self) -> None:
        self._attesa.spegni_tutto()
        if not self.turni:
            return
        frazione = self.picco_contesto / self.max_contesto if self.max_contesto else 0
        piu_usati = ", ".join(f"{n} ({c})" for n, c in self.tool_usati.most_common(5))
        totale = self.sessione_in + self.sessione_out
        self.console.print(Panel(
            f"{_plurale(self.turni, 'turno', 'turni')} · "
            f"{self.sessione_durata:.1f}s totali "
            f"({self.sessione_durata / self.turni:.1f}s a turno)\n"
            f"{_plurale(self.sessione_llm, 'chiamata al modello', 'chiamate al modello')} · "
            f"{_plurale(self.sessione_tool, 'tool', 'tool')}\n"
            f"[bold]token in ingresso:  {_num(self.sessione_in)}[/bold]\n"
            f"[bold]token in uscita:    {_num(self.sessione_out)}[/bold]\n"
            f"[bold]token totali:       {_num(totale)}[/bold]  "
            f"[dim]({_num(round(totale / self.turni))} a turno)[/dim]\n"
            f"picco di contesto: [{_colore_contesto(frazione)}]"
            f"{_num(self.picco_contesto)} / {_num(self.max_contesto)} "
            f"({frazione:.0%})[/{_colore_contesto(frazione)}]"
            + (f"\ntool più usati: {piu_usati}" if piu_usati else ""),
            title="riepilogo sessione", border_style="cyan", expand=False))

        self._tabella_attori()
        self._tabella_costi()

    def _tabella_attori(self) -> None:
        """Dove vanno i token: utile per capire quale specialista costa."""
        if not self.per_attore:
            return
        t = Table(title="token per attore", border_style="dim", expand=False)
        t.add_column("attore")
        t.add_column("chiamate", justify="right")
        t.add_column("token in", justify="right")
        t.add_column("token out", justify="right")
        t.add_column("% del totale", justify="right")
        totale = self.sessione_in + self.sessione_out
        for nome, d in sorted(self.per_attore.items(),
                              key=lambda kv: -(kv[1]["in"] + kv[1]["out"])):
            quota = (d["in"] + d["out"]) / totale if totale else 0
            t.add_row(nome, str(d["chiamate"]), _num(d["in"]), _num(d["out"]),
                      f"{quota:.0%}")
        self.console.print(t)

    def _tabella_costi(self) -> None:
        """Il costo di questa sessione: esatto col motore Anthropic (i token
        li riporta l'API), stimato col motore vLLM."""
        if not (self.sessione_in or self.sessione_out):
            return
        if self.costo_calcolabile:
            self._pannello_costo_reale()
            return
        t = Table(title="stima costi sull'API Anthropic (€)",
                  border_style="dim", expand=False)
        t.add_column("modello")
        t.add_column("sessione", justify="right")
        t.add_column("a turno", justify="right")
        t.add_column("1.000 turni", justify="right")
        for r in stima(self.sessione_in, self.sessione_out):
            per_turno = r["eur_con_cache"] / self.turni
            t.add_row(
                r["modello"],
                f"{r['eur_senza_cache']:.4f} → [green]{r['eur_con_cache']:.4f}[/green]",
                f"{per_turno:.4f}",
                f"{per_turno * 1000:.2f}",
            )
        self.console.print(t)
        self.console.print(
            f"[dim]Due valori per la sessione: senza prompt caching → con "
            f"caching (quota ipotizzata {QUOTA_CACHE_TIPICA:.0%}); «a turno» e "
            f"«1.000 turni» usano il valore con caching.\n"
            f"Stima indicativa: i token li conta il tokenizer di Qwen3, non "
            f"quello di Claude. Per il numero esatto: "
            f"python -m scripts.conta_token (endpoint count_tokens di "
            f"Anthropic). Listino giugno 2026, vedi tools/costi.py.[/dim]")

    def _pannello_costo_reale(self) -> None:
        """Costo effettivo: i token sono quelli fatturati dall'API Anthropic."""
        eur = self.costo_usd * CAMBIO_EUR_USD
        per_turno = eur / self.turni if self.turni else 0
        modelli = ", ".join(f"{prezzi(m)['nome'] if prezzi(m) else m} ({n})"
                            for m, n in self.modelli_visti.most_common())
        cache_tot = self.cache_lette + self.cache_scritte
        quota = self.cache_lette / self.sessione_in if self.sessione_in else 0
        if cache_tot:
            riga_cache = (f"cache: {_num(self.cache_lette)} token riletti "
                          f"(un decimo del prezzo) · "
                          f"{_num(self.cache_scritte)} scritti\n"
                          f"quota di input servita dalla cache: "
                          f"[green]{quota:.0%}[/green]")
        else:
            riga_cache = ("[yellow]nessun token servito dalla cache[/yellow] — "
                          "con la storia rimandata a ogni messaggio il caching "
                          "è la voce che decide il prezzo: verifica "
                          "ANTHROPIC_CACHING nel .env")
        self.console.print(Panel(
            f"modello: {escape(modelli)}\n"
            f"{riga_cache}\n\n"
            f"[bold]costo sessione: {eur:.4f} € ({self.costo_usd:.4f} $)[/bold]\n"
            f"a turno: {per_turno:.4f} €  ·  1.000 turni: {per_turno * 1000:.2f} €",
            title="costo effettivo (token fatturati dall'API)",
            border_style="green", expand=False))
        self.console.print(
            "[dim]Non è una stima: sono i token che l'API Anthropic riporta "
            "come fatturati. Listino giugno 2026, vedi tools/costi.py.[/dim]")


# ── singleton e annotazioni no-op ────────────────────────────────────────
# Gli orchestratori chiamano queste funzioni: se nessuno ha attivato la
# traccia (es. server.py in Fase 3) non fanno assolutamente nulla.

_corrente: Traccia | None = None


def attiva(max_contesto: int = MAX_CONTESTO) -> Traccia:
    """Accende la traccia e la restituisce: va passata a invoke() come
    callback, es. agente.invoke(stato, {"callbacks": [traccia]})."""
    global _corrente
    _corrente = Traccia(max_contesto=max_contesto)
    return _corrente


def pannello_avvio(titolo: str, dettagli: dict[str, str]) -> None:
    console = _corrente.console if _corrente else Console()
    righe = "\n".join(f"[dim]{escape(k)}:[/dim] {escape(str(v))}"
                      for k, v in dettagli.items())
    console.print(Panel(righe, title=titolo, border_style="cyan", expand=False))


def router_deciso(incarichi: list, disponibili=None) -> None:
    if _corrente:
        _corrente.router_deciso(incarichi, disponibili)


def specialista_inizio(nome: str) -> None:
    if _corrente:
        _corrente.specialista_inizio(nome)


def specialista_fine() -> None:
    if _corrente:
        _corrente.specialista_fine()
