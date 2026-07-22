"""Tool dell'agente CLIENTE. Ogni funzione è legata a un solo cliente_id,
deciso dal codice (mai dal modello): è questo che rende impossibile,
per costruzione, vedere i dati di un'altra azienda."""
import yaml
from langchain_core.tools import tool

from tools.db import query


def costruisci_tools_cliente(cliente_id: int) -> list:
    """Fabbrica: restituisce i tool 'ancorati' al cliente indicato."""

    @tool
    def mio_riepilogo(mese_inizio: str, mese_fine: str) -> str:
        """Totali della TUA azienda tra due mesi: litri di carburante, spesa
        carburante in euro, spesa pedaggi in euro. Mesi in formato AAAA-MM,
        esempio 2026-03."""
        df = query("""
            SELECT COALESCE(SUM(litri),0)              AS litri,
                   COALESCE(SUM(importo_carburante),0) AS carburante_eur,
                   COALESCE(SUM(importo_pedaggi),0)    AS pedaggi_eur,
                   COUNT(DISTINCT periodo)             AS mesi
            FROM dkv_mensile
            WHERE cliente_id = :cid AND periodo BETWEEN :a AND :b
        """, {"cid": cliente_id, "a": mese_inizio, "b": mese_fine})
        r = df.iloc[0]
        if r["mesi"] == 0:
            return "Nessun dato nel periodo indicato."
        return (f"Periodo {mese_inizio} → {mese_fine} ({int(r['mesi'])} mesi con dati): "
                f"{r['litri']:.0f} litri, {r['carburante_eur']:.2f} € di carburante, "
                f"{r['pedaggi_eur']:.2f} € di pedaggi.")

    @tool
    def mio_andamento(mese_inizio: str, mese_fine: str) -> str:
        """Andamento mese per mese della TUA azienda: litri, spesa carburante,
        spesa pedaggi. Mesi in formato AAAA-MM."""
        df = query("""
            SELECT periodo,
                   ROUND(SUM(litri),0)              AS litri,
                   ROUND(SUM(importo_carburante),2) AS carburante_eur,
                   ROUND(SUM(importo_pedaggi),2)    AS pedaggi_eur
            FROM dkv_mensile
            WHERE cliente_id = :cid AND periodo BETWEEN :a AND :b
            GROUP BY periodo ORDER BY periodo
        """, {"cid": cliente_id, "a": mese_inizio, "b": mese_fine})
        return "Nessun dato nel periodo." if df.empty else df.to_string(index=False)

    @tool
    def mie_nazioni(mese_inizio: str, mese_fine: str) -> str:
        """Ripartizione per nazione dei consumi della TUA azienda nel periodo:
        litri, spesa carburante, spesa pedaggi e prezzo medio al litro pagato.
        Mesi in formato AAAA-MM."""
        df = query("""
            SELECT nazione,
                   ROUND(SUM(litri),0)              AS litri,
                   ROUND(SUM(importo_carburante),2) AS carburante_eur,
                   ROUND(SUM(importo_pedaggi),2)    AS pedaggi_eur,
                   ROUND(SUM(importo_carburante)/NULLIF(SUM(litri),0),3) AS eur_litro
            FROM dkv_mensile
            WHERE cliente_id = :cid AND periodo BETWEEN :a AND :b
            GROUP BY nazione ORDER BY litri DESC
        """, {"cid": cliente_id, "a": mese_inizio, "b": mese_fine})
        return "Nessun dato nel periodo." if df.empty else df.to_string(index=False)

    @tool
    def mie_variazioni() -> str:
        """Confronta l'ultimo mese disponibile della TUA azienda con la media
        dei 3 mesi precedenti: dice se consumi e spese stanno salendo o
        scendendo."""
        df = query("""
            SELECT periodo, SUM(litri) AS litri,
                   SUM(importo_carburante + importo_pedaggi) AS spesa
            FROM dkv_mensile WHERE cliente_id = :cid
            GROUP BY periodo ORDER BY periodo
        """, {"cid": cliente_id})
        if len(df) < 2:
            return "Servono almeno due mesi di dati per un confronto."
        ultimo = df.iloc[-1]
        prec = df.iloc[-4:-1] if len(df) >= 4 else df.iloc[:-1]
        med_litri, med_spesa = prec["litri"].mean(), prec["spesa"].mean()
        var_l = (ultimo["litri"] - med_litri) / med_litri * 100 if med_litri else 0
        var_s = (ultimo["spesa"] - med_spesa) / med_spesa * 100 if med_spesa else 0
        return (f"Mese {ultimo['periodo']}: {ultimo['litri']:.0f} litri "
                f"({var_l:+.1f}% rispetto alla media dei 3 mesi precedenti), "
                f"spesa totale {ultimo['spesa']:.2f} € ({var_s:+.1f}%).")

    @tool
    def servizi_utili() -> str:
        """Verifica quali servizi aggiuntivi potrebbero far risparmiare la TUA
        azienda (recupero accise, recupero IVA estera, servizio pedaggi,
        consulenza cabotaggio) in base alle nazioni in cui opera."""
        with open("config/regole_servizi.yml", encoding="utf-8") as f:
            regole = yaml.safe_load(f)["servizi"]
        df = query("""
            SELECT periodo, nazione, SUM(litri) AS litri,
                   SUM(importo_carburante + importo_pedaggi) AS spesa,
                   SUM(importo_pedaggi) AS pedaggi
            FROM dkv_mensile WHERE cliente_id = :cid
            GROUP BY periodo, nazione ORDER BY periodo
        """, {"cid": cliente_id})
        if df.empty:
            return "Nessun dato disponibile."

        mesi = sorted(df["periodo"].unique())[-3:]        # ultimo trimestre coi dati
        df3 = df[df["periodo"].isin(mesi)]
        naz = df3.groupby("nazione").agg(
            litri_mese=("litri", lambda s: s.sum() / len(mesi)),
            spesa_tot=("spesa", "sum"),
            pedaggi_tot=("pedaggi", "sum"))

        proposte = []
        r = regole["recupero_accise"]
        for n in naz.index:
            if n in r["nazioni"] and naz.loc[n, "litri_mese"] >= r["litri_min_mese"]:
                proposte.append(f"- {r['nome']}: rifornisci in media "
                                f"{naz.loc[n,'litri_mese']:.0f} l/mese in {n}.")
        r = regole["recupero_iva"]
        for n in naz.index:
            if n not in r.get("escludi_nazioni", []) and naz.loc[n, "spesa_tot"] >= r["importo_min_trimestre"]:
                proposte.append(f"- {r['nome']}: {naz.loc[n,'spesa_tot']:.0f} € di spese "
                                f"in {n} nell'ultimo trimestre.")
        r = regole["servizio_pedaggi"]
        for n in naz.index:
            if naz.loc[n, "litri_mese"] >= r["litri_min_mese"] and naz.loc[n, "pedaggi_tot"] == 0:
                proposte.append(f"- {r['nome']}: operi in {n} ma i pedaggi non "
                                f"risultano sulla tua carta.")
        r = regole["cabotaggio"]
        for n in naz.index:
            mesi_naz = df[df["nazione"] == n]["periodo"].nunique()
            if n not in r.get("escludi_nazioni", []) and mesi_naz >= r["mesi_presenza"]:
                proposte.append(f"- {r['nome']}: presenza ricorrente in {n} "
                                f"({mesi_naz} mesi).")

        if not proposte:
            return "Al momento nessun servizio aggiuntivo risulta particolarmente indicato."
        return "Servizi che potrebbero interessarti:\n" + "\n".join(sorted(set(proposte)))

    return [mio_riepilogo, mio_andamento, mie_nazioni, mie_variazioni, servizi_utili]
