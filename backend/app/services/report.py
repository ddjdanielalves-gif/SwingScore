"""Natural-language report generation.

Uses the local OpenAI-compatible endpoint (9router) when available and falls
back to a template so the platform never breaks. Language is strictly
probabilistic: no buy/sell advice, no promises, max ~150 words.
"""

from __future__ import annotations

import json
import logging

from openai import AsyncOpenAI

from ..config import settings

logger = logging.getLogger("swing.report")

_SYSTEM_PROMPT = """Você é um analista quantitativo que escreve relatórios em português do Brasil.
Regras obrigatórias:
- Máximo de 150 palavras.
- Use linguagem probabilística e estatística. NUNCA diga "vai subir", "compre", "venda",
  "recomendo" ou prometa resultados.
- Fale de: situação financeira, situação do setor, riscos, oportunidades.
- Termine com uma frase sobre as condições atuais.
- Tom sóbrio, linguagem simples, sem jargão excessivo."""


def _context(scoring: dict, tech: dict, fund: dict, macro: dict, scenarios: dict, targets: dict, meta: dict) -> dict:
    return {
        "ativo": meta.get("ticker"),
        "empresa": meta.get("name"),
        "score": scoring["swing_score"],
        "confianca": scoring["confidence"],
        "pilares": scoring["pillars"],
        "tecnico": {
            "rsi": tech.get("rsi"),
            "estado_rsi": tech.get("rsi_state"),
            "preco_vs_mm21": tech.get("ma_status", {}).get("sma21"),
            "preco_vs_mm200": tech.get("ma_status", {}).get("sma200"),
            "suporte": tech.get("nearest_support"),
            "resistencia": tech.get("nearest_resistance"),
            "tendencia": {
                "suporte": tech.get("trend_support"),
                "resistencia": tech.get("trend_resistance"),
            },
        },
        "fundamentos": {
            "pl": fund.get("data", {}).get("pe"),
            "pvp": fund.get("data", {}).get("pvp"),
            "roe": fund.get("data", {}).get("roe"),
            "crescimento_lucro": fund.get("data", {}).get("earnings_growth"),
            "dividend_yield": fund.get("data", {}).get("dividend_yield"),
            "setor": fund.get("data", {}).get("sector"),
            "rotulo": fund.get("label"),
        },
        "macro": macro,
        "cenarios": scenarios,
        "alvos": targets,
    }


def _template(context: dict) -> str:
    c = context
    name = c.get("empresa") or c.get("ativo")
    score = c["score"]
    fund = c.get("fundamentos", {})
    tech = c.get("tecnico", {})
    scen = c.get("cenarios", {})

    lines = [
        f"{name} apresenta, nas condições atuais, um cenário "
        f"{'favorável' if score >= 65 else 'neutro' if score >= 45 else 'desfavorável'} "
        f"para os próximos meses (SwingScore {score:.0f}).",
    ]
    if fund.get("pl") and fund.get("roe") is not None:
        lines.append(
            f"Nos fundamentos, o P/L está em {fund['pl']:.1f} e o ROE em "
            f"{fund['roe'] * 100:.1f}%, o que caracteriza um quadro "
            f"{fund.get('rotulo', 'neutro')}."
        )
    elif fund.get("rotulo"):
        lines.append(f"Nos fundamentos, o quadro é {fund['rotulo']}.")
    if tech.get("estado_rsi"):
        lines.append(f"No gráfico, o RSI sinaliza {tech['estado_rsi']}.")
    if scen:
        lines.append(
            f"Historicamente, a distribuição estatística aponta "
            f"{scen.get('favoravel', 0):.0f}% de chance de cenário favorável, "
            f"{scen.get('neutro', 0):.0f}% de cenário neutro e "
            f"{scen.get('desfavoravel', 0):.0f}% de cenário desfavorável."
        )
    lines.append(
        "Riscos e oportunidades dependem do comportamento dos juros, da inflação "
        "e do setor. Estes números são uma estimativa probabilística, não uma "
        "recomendação de compra ou venda."
    )
    return " ".join(lines)[:1500]


async def generate(scoring: dict, tech: dict, fund: dict, macro: dict, scenarios: dict, targets: dict, meta: dict) -> str:
    context = _context(scoring, tech, fund, macro, scenarios, targets, meta)
    if not settings.llm_enabled:
        return _template(context)
    payload = json.dumps(context, ensure_ascii=False, default=str)

    try:
        client = AsyncOpenAI(
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key,
            timeout=settings.llm_timeout,
        )
        response = await client.chat.completions.create(
            model=settings.llm_model,
            temperature=0.4,
            max_tokens=320,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": f"Dados do sistema:\n{payload}\n\nEscreva o relatório:"},
            ],
        )
        text = (response.choices[0].message.content or "").strip()
        if text:
            return text[:1500]
    except Exception as exc:
        logger.warning("LLM report failed, using template: %s", exc)
    return _template(context)
