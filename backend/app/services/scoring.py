"""SwingScore model.

Blend of three pillars:

  fundamentals  40%
  technical     35%
  macro         25%

Each pillar is a 0-100 score produced by the dedicated services. Confidence
measures how much data supported the analysis.
"""

from __future__ import annotations

import math

from . import macro as macro_service


def technical_score(tech: dict) -> dict:
    """0-100 technical score from the indicators module output."""
    scores: list[tuple[float, float, str]] = []  # (score, weight, note)

    # --- Trend vs moving averages -------------------------------------
    price = tech["price"]
    dist = tech["ma_distance"]
    slopes = tech["ma_slopes"]
    status = tech["ma_status"]

    if "sma200" in dist:
        d200 = dist["sma200"]
        score = 50 + max(-40, min(40, d200 * 2))
        scores.append((score, 0.25, f"preço {status['sma200']} da média de 200 sessões ({(d200):.1f}%)"))
    if "sma21" in dist:
        d21 = dist["sma21"]
        score = 50 + max(-40, min(40, d21 * 3))
        scores.append((score, 0.15, f"preço {status['sma21']} da média curta"))
    if slopes.get("sma200") is not None:
        slope = slopes["sma200"]
        if slope > 0.05:
            scores.append((75, 0.10, "média de 200 sessões em inclinação de alta"))
        elif slope < -0.05:
            scores.append((25, 0.10, "média de 200 sessões em inclinação de baixa"))
        else:
            scores.append((50, 0.10, "média de 200 sessões lateralizada"))

    # --- RSI -----------------------------------------------------------
    rsi = tech["rsi"]
    state = tech["rsi_state"]
    if state == "sobrevenda":
        scores.append((80, 0.10, f"RSI em {rsi:.0f}: região historicamente favorável"))
    elif state == "sobrecompra":
        scores.append((30, 0.10, f"RSI em {rsi:.0f}: região de sobrecompra"))
    elif state == "viés comprador":
        scores.append((65, 0.10, f"RSI em {rsi:.0f}: compradores no comando, sem exagero"))
    elif state == "viés vendedor":
        scores.append((40, 0.10, f"RSI em {rsi:.0f}: pressão vendedora, ainda sem excesso"))
    else:
        scores.append((50, 0.10, f"RSI em {rsi:.0f}: equilíbrio entre compradores e vendedores"))

    div = tech.get("rsi_divergence")
    if div:
        if div["type"] == "bullish":
            scores.append((80, 0.10, "divergência positiva (preço faz fundo, RSI não)"))
        else:
            scores.append((20, 0.10, "divergência negativa (preço faz topo, RSI não)"))

    # --- Support / resistance ------------------------------------------
    sup = tech.get("nearest_support")
    res = tech.get("nearest_resistance")
    if sup:
        distance = (price - sup["price"]) / price * 100
        touches = sup["touches"]
        score = 50 + touches * 8 + max(-25, min(25, 25 - distance * 3))
        scores.append((score, 0.15, f"suporte próximo a {distance:.1f}% de distância, respeitado {touches}x"))
    if res:
        distance = (res["price"] - price) / price * 100
        touches = res["touches"]
        score = 50 - touches * 4 + max(-25, min(30, distance * 2))
        scores.append((score, 0.15, f"resistência próxima a {distance:.1f}%, testada {touches}x"))

    # --- Trend lines ----------------------------------------------------
    tsup = tech.get("trend_support")
    tres = tech.get("trend_resistance")
    if tsup:
        base = 80 if tsup["strength"] == "forte" else 65
        if tsup["broken"]:
            base -= 20
        scores.append((base, 0.15, f"linha de tendência de alta com {tsup['touches']} toques"))
    if tres:
        base = 80 if tres["strength"] == "forte" else 65
        if tres["broken"]:
            base -= 25
        scores.append((base, 0.15, f"linha de tendência de baixa com {tres['touches']} toques"))

    if not scores:
        return {"score": 50.0, "label": "padrão técnico neutro", "notes": [], "components": []}

    weight_sum = sum(w for _, w, _ in scores)
    total = sum(s * w for s, w, _ in scores) / weight_sum
    total = max(0.0, min(100.0, total))
    label = (
        "padrão técnico favorável"
        if total >= 60
        else "padrão técnico misto" if total >= 45 else "padrão técnico desfavorável"
    )
    return {
        "score": round(total, 1),
        "label": label,
        "notes": [n for _, _, n in scores][:5],
        "components": [{"score": s, "weight": w, "note": n} for s, w, n in scores],
    }


def compute(fund: dict, tech: dict, macro_data: dict, market: str) -> dict:
    fund_score = fund["score"]
    tech_result = technical_score(tech)
    macro_result = macro_service.score(macro_data, market=market)

    swing = (
        fund_score * 0.40
        + tech_result["score"] * 0.35
        + macro_result["score"] * 0.25
    )
    swing = max(0.0, min(100.0, swing))

    # --- Confidence -----------------------------------------------------
    confidence = 0.55
    confidence += 0.10 * fund["completeness"]
    confidence += min(0.10, tech.get("atr_pct", 10.0) / 100.0)  # sensible vol
    touches = [
        (tech.get("nearest_support") or {}).get("touches", 0),
        (tech.get("nearest_resistance") or {}).get("touches", 0),
    ]
    confidence += 0.05 * min(2.0, max(touches)) if touches else 0.0
    if tech.get("trend_support") or tech.get("trend_resistance"):
        confidence += 0.05
    if macro_data:
        available = sum(1 for v in macro_data.values() if v)
        confidence += 0.05 * (available / max(1, len(macro_data)))
    if abs(swing - 50) > 20:
        confidence += 0.05
    confidence = min(0.97, confidence)

    label = (
        "cenário favorável" if swing >= 65 else "cenário neutro" if swing >= 45 else "cenário desfavorável"
    )

    return {
        "swing_score": round(swing, 1),
        "confidence": round(confidence * 100, 1),
        "label": label,
        "pillars": {
            "fundamentals": {"score": fund_score, "label": fund["label"]},
            "technical": {"score": tech_result["score"], "label": tech_result["label"]},
            "macro": {"score": macro_result["score"], "label": macro_result["label"]},
        },
        "notes": tech_result["notes"],
    }
