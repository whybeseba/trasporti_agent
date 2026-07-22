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
def clienti_in_variazione(soglia_pct: float = 25) -> str:
    """[USO INTERNO] Clienti il cui ultimo mese si discosta oltre la soglia
    percentuale (default 25) dalla media dei loro 3 mesi precedenti:
    cali (rischio abbandono), crescite forti e clienti azzerati."""
    df = query("""
        SELECT c.nome_dkv AS cliente, d.periodo, SUM(d.litri) AS litri
        FROM dkv_mensile d JOIN clienti c ON c.id = d.cliente_id
        GROUP BY c.nome_dkv, d.periodo
    """)
    if df.empty:
        return "Nessun dato."
    ultimo = df["periodo"].max()
    righe = []
    for cliente, g in df.groupby("cliente"):
        g = g.sort_values("periodo")
        prec = g[g["periodo"] < ultimo].tail(3)
        if prec.empty:
            continue
        media = prec["litri"].mean()
        attuale = g[g["periodo"] == ultimo]["litri"].sum()   # 0 se assente = azzerato
        if media > 0:
            var = (attuale - media) / media * 100
            if abs(var) >= soglia_pct:
                righe.append((var, f"{cliente}: {attuale:.0f} l in {ultimo} "
                                   f"vs media {media:.0f} ({var:+.0f}%)"))
    if not righe:
        return f"Nessun cliente oltre la soglia ±{soglia_pct}% nel mese {ultimo}."
    righe.sort()   # prima i cali peggiori
    return (f"Variazioni oltre ±{soglia_pct}% nel mese {ultimo}:\n"
            + "\n".join(r for _, r in righe))


TOOLS_PORTAFOGLIO = [classifica_clienti, clienti_in_variazione]
