"""Tool della vista GESTORE (interna): vedono TUTTI i clienti.
NON vanno mai collegati all'agente esposto ai clienti."""
from langchain_core.tools import tool

from tools.db import query


@tool
def classifica_clienti(mese_inizio: str, mese_fine: str) -> str:
    """[USO INTERNO] Classifica dei clienti per litri e spesa totale nel
    periodo (primi 20). Mesi in formato AAAA-MM."""
    df = query("""
        SELECT c.nome_dkv AS cliente,
               ROUND(SUM(d.litri),0) AS litri,
               ROUND(SUM(d.importo_carburante + d.importo_pedaggi),2) AS spesa_eur
        FROM dkv_mensile d JOIN clienti c ON c.id = d.cliente_id
        WHERE d.periodo BETWEEN :a AND :b
        GROUP BY c.nome_dkv ORDER BY litri DESC LIMIT 20
    """, {"a": mese_inizio, "b": mese_fine})
    return "Nessun dato." if df.empty else df.to_string(index=False)


@tool
def clienti_in_variazione(soglia_pct: float = 25, limit: int = 50) -> str:
    """[USO INTERNO] Clienti il cui ultimo mese si discosta oltre la soglia
    percentuale (default 25) dalla media dei loro 3 mesi precedenti:
    cali (rischio abbandono), crescite forti e clienti azzerati.
    Restituisce il totale oltre soglia e al massimo `limit` risultati
    (default 50, deve essere > 0), ordinati dai cali peggiori."""
    if limit <= 0:
        return "Errore: limit deve essere maggiore di 0."
    df = query("""
        SELECT c.nome_dkv AS cod_cliente, c.ragione_sociale AS cliente,
               d.periodo, SUM(d.litri) AS litri
        FROM dkv_mensile d JOIN clienti c ON c.id = d.cliente_id
        GROUP BY c.nome_dkv, c.ragione_sociale, d.periodo
    """)
    if df.empty:
        return "Nessun dato."
    ultimo = df["periodo"].max()
    righe = []
    for cod_cliente, g in df.groupby("cod_cliente"):
        g = g.sort_values("periodo")
        nome = g["cliente"].iloc[0] or cod_cliente
        prec = g[g["periodo"] < ultimo].tail(3)
        if prec.empty:
            continue
        media = prec["litri"].mean()
        attuale = g[g["periodo"] == ultimo]["litri"].sum()   # 0 se assente = azzerato
        if media > 0:
            var = (attuale - media) / media * 100
            if abs(var) >= soglia_pct:
                righe.append((var, f"{nome} ({cod_cliente}): {attuale:.0f} l in {ultimo} "
                                   f"vs media {media:.0f} ({var:+.0f}%)"))
    if not righe:
        return f"Nessun cliente oltre la soglia ±{soglia_pct}% nel mese {ultimo}."
    righe.sort()   # prima i cali peggiori
    totale = len(righe)
    mostrati = min(limit, totale)
    intestazione = (
        f"{totale} clienti sono oltre alla soglia ±{soglia_pct}% "
        f"nel mese {ultimo}. Ecco i primi {mostrati}:"
    )
    return intestazione + "\n" + "\n".join(r for _, r in righe[:limit])


TOOLS_PORTAFOGLIO = [classifica_clienti, clienti_in_variazione]
