"""Fundamentals.

Uses Yahoo quoteSummary data (via Ticker.info). Comparisons are always done
against the company's own history where available and against a sector
reference table (a static approximation of typical multiples, kept on file
and easy to update).

Missing fields are handled gracefully — the score degrades, and confidence
reflects how much of the picture is available.
"""

from __future__ import annotations

import logging

import pandas as pd
import yfinance as yf

logger = logging.getLogger("swing.fundamentals")

# Reference multiples by sector (typical/target ranges). Static snapshot that
# can be refreshed periodically or replaced by a proper data feed later.
SECTOR_REFERENCE = {
    "Energia": {"pe": 6.0, "dy": 0.08, "roe": 0.18},
    "Petróleo e Gás": {"pe": 6.5, "dy": 0.07, "roe": 0.20},
    "Siderurgia": {"pe": 7.0, "dy": 0.04, "roe": 0.15},
    "Mineração": {"pe": 8.0, "dy": 0.05, "roe": 0.18},
    "Bancos": {"pe": 8.0, "dy": 0.06, "roe": 0.16},
    "Serviços Financeiros": {"pe": 10.0, "dy": 0.04, "roe": 0.14},
    "Consumo Cíclico": {"pe": 15.0, "dy": 0.02, "roe": 0.15},
    "Consumo Não Cíclico": {"pe": 14.0, "dy": 0.03, "roe": 0.18},
    "Varejo": {"pe": 16.0, "dy": 0.02, "roe": 0.16},
    "Saúde": {"pe": 16.0, "dy": 0.02, "roe": 0.15},
    "Tecnologia": {"pe": 22.0, "dy": 0.01, "roe": 0.20},
    "Comunicação": {"pe": 15.0, "dy": 0.02, "roe": 0.15},
    "Utilities": {"pe": 12.0, "dy": 0.05, "roe": 0.14},
    "Bens Industriais": {"pe": 13.0, "dy": 0.02, "roe": 0.16},
    "Agro": {"pe": 9.0, "dy": 0.04, "roe": 0.16},
    "Transporte": {"pe": 14.0, "dy": 0.03, "roe": 0.15},
    "Imobiliário": {"pe": 12.0, "dy": 0.05, "roe": 0.12},
    "Papel e Celulose": {"pe": 9.0, "dy": 0.04, "roe": 0.16},
    "Demonstração": {"pe": 10.0, "dy": 0.03, "roe": 0.15},
}


def _num(value, default=None):
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _clamp(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, x))


def collect(info: dict, currency: str) -> dict:
    """Extract and normalize the fundamentals we need."""
    eps = None
    pe = _num(info.get("trailingPE"))
    price = _num(info.get("currentPrice")) or _num(info.get("regularMarketPrice"))
    if pe and price:
        eps = price / pe

    sector = (info.get("sector") or info.get("industry") or "Não informado").strip()
    ref = SECTOR_REFERENCE.get(sector, SECTOR_REFERENCE["Demonstração"])

    dy = _num(info.get("dividendYield"))
    if dy is not None and dy < 0.1:
        dy = dy * 100.0  # Yahoo sometimes returns fraction

    return {
        "sector": sector,
        "industry": info.get("industry") or sector,
        "pe": pe,
        "forward_pe": _num(info.get("forwardPE")),
        "pvp": _num(info.get("priceToBook")),
        "roe": _num(info.get("returnOnEquity")),
        "profit_margin": _num(info.get("profitMargins")),
        "avg_volume": _num(info.get("averageVolume")),
        "free_cashflow": _num(info.get("freeCashflow")),
        "operating_cashflow": _num(info.get("operatingCashflow")),
        "net_income": _num(info.get("netIncome")),
        "revenue": _num(info.get("totalRevenue")),
        "revenue_growth": _num(info.get("revenueGrowth")),
        "earnings_growth": _num(info.get("earningsGrowth")),
        "dividend_yield": dy,
        "payout": _num(info.get("payoutRatio")),
        "debt_to_equity": _num(info.get("debtToEquity")),
        "total_debt": _num(info.get("totalDebt")),
        "total_cash": _num(info.get("totalCash")),
        "ebitda": _num(info.get("ebitda")),
        "book_value": _num(info.get("bookValue")),
        "eps": eps,
        "currency": currency,
        "reference": ref,
        "earnings_5y_growth": _num(info.get("earningsQuarterlyGrowth")),
    }


def _row(frame: pd.DataFrame | None, *labels: str) -> pd.Series | None:
    if frame is None or frame.empty:
        return None
    for lab in labels:
        if lab in frame.index:
            try:
                return frame.loc[lab].astype(float)
            except Exception:
                return None
    return None


def history(ticker: str) -> dict:
    """5-year trailing averages from annual financial statements.

    Uses Yahoo income statement + balance sheet (last ~4 fiscal years) plus
    the trailing year, and 5y price history for valuation multiples. Every
    value is guarded: on any failure the entry stays None and the UI shows a
    dash instead of crashing.
    """
    out: dict = {
        "years": 0,
        "roe_5y": None,
        "margin_5y": None,
        "pe_5y": None,
        "pvp_5y": None,
        "revenue_growth_5y": None,
        "dy_5y": None,
    }
    try:
        tk = yf.Ticker(ticker)
        info = tk.info or {}
        shares = _num(info.get("sharesOutstanding")) or _num(info.get("impliedSharesOutstanding"))
        inc = tk.income_stmt
        if inc is None or inc.empty or not shares:
            return out
        net_income = _row(inc, "Net Income", "Net Income Common Stockholders", "Net Income Including Noncontrolling Interests")
        revenue = _row(inc, "Total Revenue", "Operating Revenue")
        bs = tk.balance_sheet
        equity = _row(bs, "Stockholders Equity", "Total Stockholder Equity", "Common Stock Equity", "Total Equity Gross Minority Interest")
        if net_income is None:
            return out

        roes: list[float] = []
        margins: list[float] = []
        eps_list: list[float] = []
        revs: list[tuple] = []
        for year in net_income.index:
            ni = float(net_income[year]) if pd.notna(net_income[year]) else None
            if not ni:
                continue
            rev = float(revenue[year]) if revenue is not None and pd.notna(revenue[year]) else None
            eq = float(equity[year]) if equity is not None and pd.notna(equity[year]) else None
            if eq:
                roes.append(ni / eq)
            if rev:
                margins.append(ni / rev)
                revs.append((year, rev))
            if ni > 0:
                eps_list.append(ni / shares)

        hist = tk.history(period="5y", auto_adjust=True)
        avg_price = float(hist["Close"].mean()) if hist is not None and len(hist) else 0.0

        if roes:
            out["roe_5y"] = round(sum(roes) / len(roes), 6)
        if margins:
            out["margin_5y"] = round(sum(margins) / len(margins), 6)
        if eps_list and avg_price:
            # Median is robust to one-off (e.g. record-profit) years.
            pes = sorted(avg_price / e for e in eps_list if e > 0)
            if pes:
                mid = len(pes) // 2
                median_pe = pes[mid] if len(pes) % 2 else (pes[mid - 1] + pes[mid]) / 2
                if 0.1 <= median_pe <= 200:
                    out["pe_5y"] = round(median_pe, 2)
        if equity is not None and len(equity.dropna()):
            eq_latest = float(equity.dropna().iloc[-1])
            if eq_latest and avg_price:
                out["pvp_5y"] = round(avg_price / (eq_latest / shares), 4)
        if len(revs) >= 2:
            revs.sort(key=lambda x: x[0])
            growths = [revs[i][1] / revs[i - 1][1] - 1 for i in range(1, len(revs)) if revs[i - 1][1]]
            if growths:
                out["revenue_growth_5y"] = round(sum(growths) / len(growths), 6)

        try:
            divs = tk.dividends
            if divs is not None and len(divs):
                last5 = divs[divs.index >= divs.index.max() - pd.DateOffset(years=5)]
                total = float(last5.sum())
                if total and avg_price:
                    span = max((last5.index.max() - last5.index.min()).days / 365.0, 1.0)
                    out["dy_5y"] = round((total / span) / avg_price, 6)
        except Exception:
            pass

        out["years"] = max(len(roes), len(margins), len(eps_list))
    except Exception as exc:
        logger.warning("fundamentals history failed for %s: %s", ticker, exc)
    return out


def _pe_score(pe, ref_pe):
    if pe is None or pe <= 0 or not ref_pe:
        return 50.0, "P/L não disponível"
    ratio = pe / ref_pe
    if ratio <= 0.7:
        return 90, f"P/L {pe:.1f} abaixo da média setorial ({ref_pe:.1f})"
    if ratio <= 1.0:
        return 70, f"P/L {pe:.1f} levemente abaixo da média setorial ({ref_pe:.1f})"
    if ratio <= 1.3:
        return 50, f"P/L {pe:.1f} perto da média setorial ({ref_pe:.1f})"
    return 25, f"P/L {pe:.1f} acima da média setorial ({ref_pe:.1f})"


def _pvp_score(pvp):
    if pvp is None:
        return 50.0, "P/VPA não disponível"
    if pvp <= 1:
        return 80, f"P/VPA {pvp:.2f} indica avaliação contida"
    if pvp <= 2.5:
        return 60, f"P/VPA {pvp:.2f} em patamar moderado"
    if pvp <= 5:
        return 40, f"P/VPA {pvp:.2f} exige crescimento para justificar"
    return 20, f"P/VPA {pvp:.2f} historicamente alto"


def _roe_score(roe, ref_roe):
    if roe is None:
        return 50.0, "ROE não disponível"
    if roe > 0.25:
        return 90, f"ROE de {roe * 100:.1f}% bem acima da média setorial"
    if roe > ref_roe:
        return 75, f"ROE de {roe * 100:.1f}% acima da média setorial"
    if roe > 0.10:
        return 55, f"ROE de {roe * 100:.1f}% próximo da média"
    if roe > 0:
        return 35, f"ROE de {roe * 100:.1f}% abaixo do desejável"
    return 10, "ROE negativo sinaliza destruição de valor"


def _growth_score(earnings_growth, revenue_growth):
    scores = []
    notes = []
    if earnings_growth is not None:
        if earnings_growth > 0.2:
            scores.append(90)
            notes.append(f"lucro crescendo {earnings_growth * 100:.0f}%")
        elif earnings_growth > 0.05:
            scores.append(70)
            notes.append(f"lucro crescendo {earnings_growth * 100:.0f}%")
        elif earnings_growth > 0:
            scores.append(50)
            notes.append("crescimento do lucro modesto")
        else:
            scores.append(15)
            notes.append("lucro em retração")
    if revenue_growth is not None:
        if revenue_growth > 0.15:
            scores.append(85)
        elif revenue_growth > 0.05:
            scores.append(65)
        elif revenue_growth > 0:
            scores.append(50)
        else:
            scores.append(25)
    if not scores:
        return 50.0, "dados de crescimento não disponíveis"
    return sum(scores) / len(scores), " · ".join(notes) if notes else "crescimento estável"


def _dy_score(dy, ref_dy, payout):
    scores = []
    if dy is None:
        scores.append(40)
    elif dy <= 0.001:
        scores.append(20)
        if payout is None:
            return 20, "não paga dividendos"
    else:
        if dy >= ref_dy:
            scores.append(85)
        elif dy >= ref_dy * 0.5:
            scores.append(65)
        else:
            scores.append(45)
    if payout is not None:
        if payout <= 0.6:
            scores.append(75)
        elif payout <= 0.9:
            scores.append(55)
        else:
            scores.append(25)
    avg = sum(scores) / len(scores)
    note = (
        f"dividend yield de {dy:.1f}% a.a."
        if dy and dy > 0.001
        else "sem histórico relevante de dividendos"
    )
    return avg, note


def _debt_score(dte, total_debt, ebitda, total_cash):
    if dte is None and (total_debt is None or ebitda is None):
        return 50.0, "nível de endividamento não disponível"
    if dte is not None:
        if dte <= 40:
            return 85, f"endividamento baixo (D/E {dte:.0f}%)"
        if dte <= 80:
            return 65, f"endividamento moderado (D/E {dte:.0f}%)"
        if dte <= 150:
            return 40, f"endividamento elevado (D/E {dte:.0f}%)"
        return 20, f"endividamento alto (D/E {dte:.0f}%)"
    net = (total_debt or 0) - (total_cash or 0)
    if ebitda and net / ebitda <= 2.0:
        return 75, "dívida líquida confortável frente ao Ebitda"
    return 40, "dívida líquida pressionada frente ao Ebitda"


def score(fund: dict) -> dict:
    ref = fund.get("reference") or SECTOR_REFERENCE["Demonstração"]
    components: list[dict] = []

    pe, pe_note = _pe_score(fund.get("pe"), ref.get("pe"))
    pvp, pvp_note = _pvp_score(fund.get("pvp"))
    roe, roe_note = _roe_score(fund.get("roe"), ref.get("roe"))
    growth, growth_note = _growth_score(fund.get("earnings_growth"), fund.get("revenue_growth"))
    dy, dy_note = _dy_score(fund.get("dividend_yield"), ref.get("dy"), fund.get("payout"))
    debt, debt_note = _debt_score(
        fund.get("debt_to_equity"),
        fund.get("total_debt"),
        fund.get("ebitda"),
        fund.get("total_cash"),
    )

    components = [
        {"key": "valuation", "score": (pe + pvp) / 2, "note": f"{pe_note}; {pvp_note}", "weight": 0.30},
        {"key": "profitability", "score": roe, "note": roe_note, "weight": 0.20},
        {"key": "growth", "score": growth, "note": growth_note, "weight": 0.20},
        {"key": "dividends", "score": dy, "note": dy_note, "weight": 0.15},
        {"key": "leverage", "score": debt, "note": debt_note, "weight": 0.15},
    ]
    total = sum(c["score"] * c["weight"] for c in components)

    available = sum(1 for c in components if not c["note"].startswith(("não disponível", "não paga")))
    completeness = available / len(components)
    if completeness < 0.5:
        total = total * 0.5 + 50 * (1 - completeness)

    label = (
        "fundamentos fortes"
        if total >= 65
        else "fundamentos neutros" if total >= 45 else "fundamentos fracos"
    )
    return {
        "score": round(_clamp(total), 1),
        "label": label,
        "completeness": round(completeness, 2),
        "components": components,
        "data": fund,
    }
