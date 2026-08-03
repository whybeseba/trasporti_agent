"""Il testo di un messaggio del modello, qualunque forma abbia.

⚠️ `.content` NON è sempre una stringa. Con i modelli Claude che ragionano
— su Claude Sonnet 5 il pensiero adattivo è attivo di default, quindi
capita senza averlo chiesto — la risposta arriva come ELENCO di blocchi
(pensiero, testo, uso di tool). Leggere `.content` alla lettera restituisce
in quel caso una lista, e chi si aspetta una stringa si rompe: è il caso del
router, che cerca il JSON degli incarichi con un'espressione regolare.

Qui il contenuto si normalizza a stringa prendendo SOLO i blocchi di testo:
il pensiero non è una risposta per il cliente, e i blocchi di uso tool sono
già gestiti da LangChain.

Nota: questo serve a leggere e a mostrare. Nella storia della conversazione
i messaggi restano quelli originali, blocchi compresi — vanno rimandati al
modello come sono arrivati."""


def testo_contenuto(contenuto) -> str:
    """Il testo dentro un `content`: stringa, elenco di blocchi, o altro."""
    if contenuto is None:
        return ""
    if isinstance(contenuto, str):
        return contenuto
    if isinstance(contenuto, list):
        parti = []
        for blocco in contenuto:
            if isinstance(blocco, str):
                parti.append(blocco)
            elif isinstance(blocco, dict):
                # solo i blocchi di testo: "thinking", "tool_use" e simili
                # non sono la risposta
                if blocco.get("type") == "text" and blocco.get("text"):
                    parti.append(blocco["text"])
            else:
                testo = getattr(blocco, "text", None)
                if testo and getattr(blocco, "type", "text") == "text":
                    parti.append(testo)
        return "\n".join(parti)
    return str(contenuto)


def testo_messaggio(messaggio) -> str:
    """Il testo di un messaggio, sia esso un dict o un oggetto LangChain."""
    if isinstance(messaggio, dict):
        return testo_contenuto(messaggio.get("content"))
    return testo_contenuto(getattr(messaggio, "content", messaggio))
