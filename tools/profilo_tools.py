"""Profilo dell'azienda cliente: lettura e aggiornamento.

Sono quattro informazioni che non stanno nell'export DKV ma cambiano la
risposta corretta — soprattutto sulla normativa: le regole di cabotaggio,
tempi di guida e distacco non sono le stesse per un conto terzi
internazionale da 40 tonnellate e per un conto proprio locale sotto le 3,5.

Si raccolgono in chat, UNA ALLA VOLTA e anche in sessioni diverse: ogni
campo è NULL finché il cliente non lo dice, e NULL significa «non lo so
ancora», non «no». Una volta salvato resta: è questo che rende il profilo
persistente e permette di non richiedere le stesse cose a ogni accesso.

Isolamento multi-tenant: come per i dati DKV i tool nascono da una fabbrica
che li inchioda al cliente_id della sessione. Il modello non ha alcun
parametro per indicare un'altra azienda, e le colonne scrivibili sono solo
quelle dichiarate in tools.db.COLONNE_PROFILO — mai un nome deciso da lui.
"""
from langchain_core.tools import tool

from tools.db import COLONNE_PROFILO, esegui, query

# Per ogni campo: etichetta leggibile, come si rende il valore, e la domanda
# da fare al cliente quando manca.
CAMPI = {
    "conto_terzi": {
        "etichetta": "trasporto conto terzi",
        "rendi": lambda v: "conto terzi" if v else "conto proprio",
        "domanda": "se l'azienda fa trasporto conto terzi o conto proprio",
    },
    "internazionale": {
        "etichetta": "ambito internazionale",
        "rendi": lambda v: "sì, anche internazionale" if v else "solo nazionale",
        "domanda": "se viaggia anche all'estero o solo in Italia",
    },
    "trasporto_attivita_principale": {
        "etichetta": "il trasporto è l'attività principale",
        "rendi": lambda v: "sì" if v else "no, è accessoria",
        "domanda": "se il trasporto è l'attività principale dell'azienda",
    },
    "massa_massima_t": {
        "etichetta": "massa massima a pieno carico",
        "rendi": lambda v: f"{float(v):g} tonnellate",
        "domanda": "qual è la massa massima a pieno carico dei veicoli (in tonnellate)",
    },
}

NON_INDICATO = "non ancora indicato"


def leggi_profilo(cliente_id: int) -> dict:
    """I quattro campi del profilo; il valore è None se non ancora saputo."""
    colonne = ", ".join(COLONNE_PROFILO)
    df = query(f"SELECT {colonne} FROM clienti WHERE id = :cid",
               {"cid": cliente_id})
    if df.empty:
        return {c: None for c in COLONNE_PROFILO}
    riga = df.iloc[0]
    return {c: (None if riga[c] is None or riga[c] != riga[c] else riga[c])
            for c in COLONNE_PROFILO}


def campi_mancanti(cliente_id: int) -> list[str]:
    return [c for c, v in leggi_profilo(cliente_id).items() if v is None]


def descrivi_profilo(cliente_id: int, con_domande: bool = True) -> str:
    """Il profilo in forma leggibile dal modello: cosa si sa e cosa manca."""
    valori = leggi_profilo(cliente_id)
    righe = []
    for campo, info in CAMPI.items():
        v = valori.get(campo)
        righe.append(f"- {info['etichetta']}: "
                     + (NON_INDICATO if v is None else info["rendi"](v)))
    testo = "Profilo dell'azienda cliente:\n" + "\n".join(righe)
    mancanti = [c for c, v in valori.items() if v is None]
    if mancanti and con_domande:
        testo += ("\nDa chiedere, se serve per rispondere bene: "
                  + "; ".join(CAMPI[c]["domanda"] for c in mancanti) + ".")
    return testo


def _salva(cliente_id: int, campo: str, valore) -> None:
    if campo not in COLONNE_PROFILO:          # difesa: solo colonne dichiarate
        raise ValueError(f"campo di profilo sconosciuto: {campo}")
    esegui(f"UPDATE clienti SET {campo} = :v WHERE id = :cid",
           {"v": valore, "cid": cliente_id})


def costruisci_tools_profilo(cliente_id: int) -> list:
    """Fabbrica: i tool del profilo ancorati al cliente della sessione."""

    @tool
    def mio_profilo() -> str:
        """Le informazioni sull'azienda del cliente già registrate in
        precedenza (anche in sessioni passate): trasporto conto terzi o
        conto proprio, se viaggia all'estero, se il trasporto è l'attività
        principale, massa massima a pieno carico. Dice anche quali di
        queste informazioni non sono ancora note. Consultalo PRIMA di
        chiedere qualcosa al cliente: quello che è già registrato non va
        richiesto."""
        return descrivi_profilo(cliente_id)

    @tool
    def aggiorna_profilo(conto_terzi: bool | None = None,
                         internazionale: bool | None = None,
                         trasporto_attivita_principale: bool | None = None,
                         massa_massima_t: float | None = None) -> str:
        """Registra una o più informazioni sull'azienda del cliente, così da
        non doverle richiedere in futuro. Passa SOLO i campi che il cliente
        ha effettivamente dichiarato in questa conversazione: quelli lasciati
        vuoti restano come sono. Non dedurre né inventare valori.

        conto_terzi: true se fa trasporto conto terzi (per altri), false se
            conto proprio (merci proprie).
        internazionale: true se viaggia anche all'estero, false se solo Italia.
        trasporto_attivita_principale: true se il trasporto è l'attività
            principale dell'azienda, false se accessoria.
        massa_massima_t: massa massima a pieno carico in tonnellate (es. 40)."""
        nuovi = {
            "conto_terzi": conto_terzi,
            "internazionale": internazionale,
            "trasporto_attivita_principale": trasporto_attivita_principale,
            "massa_massima_t": massa_massima_t,
        }
        salvati = []
        for campo, valore in nuovi.items():
            if valore is None:
                continue
            if campo == "massa_massima_t":
                try:
                    valore = float(valore)
                except (TypeError, ValueError):
                    return (f"Valore non valido per {CAMPI[campo]['etichetta']}: "
                            "serve un numero di tonnellate.")
                if not 0 < valore <= 100:
                    return ("La massa massima a pieno carico deve essere tra 0 e "
                            "100 tonnellate: chiedi conferma al cliente.")
            else:
                valore = bool(valore)
            _salva(cliente_id, campo, valore)
            salvati.append(f"{CAMPI[campo]['etichetta']}: {CAMPI[campo]['rendi'](valore)}")

        if not salvati:
            return ("Nessuna informazione da registrare: passa almeno un campo, "
                    "e solo se il cliente lo ha davvero dichiarato.")
        mancanti = campi_mancanti(cliente_id)
        esito = "Registrato — " + "; ".join(salvati) + "."
        if mancanti:
            esito += (" Non risulta ancora: "
                      + "; ".join(CAMPI[c]["etichetta"] for c in mancanti) + ".")
        return esito

    return [mio_profilo, aggiorna_profilo]
