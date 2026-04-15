"""
Gerador de pareceres tecnicos por empresa baseado em benchmarks
de agencias de rating e literatura de credito/valuation.

Fontes (G:/Meu Drive/Livros e Manuais):
  - Nao-financeiras: Damodaran (Valuation), McKinsey (Koller), Fleuriet,
    Distressed Debt Analysis (Moyer), Financial Shenanigans (Schilit)
  - Bancos: Basel Framework, Bank Analyst's Handbook (Frost),
    Principles of Banking (Choudhry), metodologias Moody's/Fitch
  - Asset Managers: Moody's Methodology for Asset Management Firms
  - Cartoes: Bank Analyst's Handbook + metodologia Fitch

O parecer eh deterministico — para cada metrica chave, classifica o nivel
da empresa contra benchmarks setoriais e gera 1-2 sentencas de leitura
qualitativa. O output e um markdown salvo em
{pasta_empresa}/Dados_EDGAR/parecer.md
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd
import numpy as np


# ---------------------------------------------------------------------------
# Benchmarks por categoria
# Cada tupla: (limites crescentes, labels). Ex: para DL/EBITDA non-fin:
#   thresholds = [1.0, 2.5, 3.5, 5.0]
#   labels =     ["Excelente", "Forte", "Adequado", "Pressionado", "Critico"]
# value <= 1.0 -> Excelente; 1.0 < v <= 2.5 -> Forte; ...; v > 5.0 -> Critico
# ---------------------------------------------------------------------------
def _classify(value: float, thresholds: list[float], labels: list[str],
              reverse: bool = False) -> str:
    if value is None or pd.isna(value):
        return "—"
    if reverse:
        # higher is better (ex: ROIC, margens)
        for i, t in enumerate(thresholds):
            if value < t:
                return labels[i]
        return labels[-1]
    # lower is better (ex: alavancagem)
    for i, t in enumerate(thresholds):
        if value <= t:
            return labels[i]
    return labels[-1]


def _fmt_pct(v):
    return "—" if v is None or pd.isna(v) else f"{v*100:.1f}%"

def _fmt_mult(v):
    return "—" if v is None or pd.isna(v) else f"{v:.2f}x"

def _fmt_bi(v):
    if v is None or pd.isna(v): return "—"
    return f"${v/1e9:.2f}B" if abs(v) >= 1e9 else f"${v/1e6:.0f}M"


# ===========================================================================
# PARECER NAO-FINANCEIRA
# ===========================================================================
def _parecer_nao_financeira(ticker: str, df: pd.DataFrame, ratings: dict) -> str:
    if df is None or df.empty:
        return "*Sem dados suficientes para parecer.*"
    last = df.iloc[-1]
    label = last.get("label", "")

    # Metricas-chave
    rec = last.get("receita_liquida")
    ebitda = last.get("ebitda")
    margem_ebitda = last.get("margem_ebitda")
    margem_liquida = last.get("margem_liquida")
    roic = last.get("roic")
    roe = last.get("roe")
    dl_ebitda = last.get("divida_liq_ebitda")
    cob_juros = last.get("cobertura_juros")
    liq_corrente = last.get("liquidez_corrente")
    cash_ratio = last.get("cash_ratio")
    fco = last.get("fco")
    fcl = last.get("fcl")
    fco_ebitda = last.get("fco_ebitda")
    capex_rec = last.get("capex_receita")
    fleuriet_tipo = last.get("fleuriet_tipo", "")
    fleuriet_nota = last.get("fleuriet_nota")
    eva = last.get("eva")
    wacc = last.get("wacc")

    # === Benchmarks (Damodaran/McKinsey, Moody's Industrial, Fitch Corporates) ===
    # Net Debt/EBITDA — Moody's industrial cross-sector
    cls_dl = _classify(dl_ebitda, [1.0, 2.5, 3.5, 5.0],
        ["Excelente (< 1.0x)", "Forte (1-2.5x)", "Adequado (2.5-3.5x)",
         "Pressionado (3.5-5x)", "Critico (> 5x)"])
    # Cobertura de juros — Fitch corporate
    cls_cob = _classify(cob_juros, [4, 8, 15], ["Fragil (< 4x)", "Adequado (4-8x)",
        "Forte (8-15x)", "Excelente (> 15x)"], reverse=True)
    # Liquidez corrente — Fleuriet/Assaf Neto
    cls_lc = _classify(liq_corrente, [0.8, 1.0, 1.5],
        ["Critico (< 0.8x)", "Justo (0.8-1.0x)", "Adequado (1.0-1.5x)",
         "Confortavel (> 1.5x)"], reverse=True)
    # ROIC vs WACC
    spread_roic = (roic - wacc) if (roic is not None and wacc is not None) else None
    cls_roic = "—"
    if spread_roic is not None:
        if spread_roic > 0.05: cls_roic = "Cria valor (ROIC-WACC > 5pp)"
        elif spread_roic > 0: cls_roic = "Cria valor marginal (0-5pp)"
        elif spread_roic > -0.03: cls_roic = "Neutro (-3pp a 0)"
        else: cls_roic = "Destroi valor (< -3pp)"
    # Margem EBITDA — heuristica setorial
    cls_mebitda = _classify(margem_ebitda, [0.05, 0.10, 0.20, 0.30],
        ["Muito baixa (<5%)", "Baixa (5-10%)", "Mediana (10-20%)",
         "Alta (20-30%)", "Premium (>30%)"], reverse=True)

    # === Construcao do parecer ===
    out = []
    out.append(f"### Parecer Tecnico — {ticker} ({label})")
    out.append("")

    # Resumo executivo: cor geral baseada em DL/EBITDA + cobertura + ROIC-WACC
    sinais = []
    if dl_ebitda is not None:
        if dl_ebitda < 2.5: sinais.append("verde")
        elif dl_ebitda < 4: sinais.append("amarelo")
        else: sinais.append("vermelho")
    if cob_juros is not None:
        if cob_juros > 8: sinais.append("verde")
        elif cob_juros > 4: sinais.append("amarelo")
        else: sinais.append("vermelho")
    if spread_roic is not None:
        if spread_roic > 0: sinais.append("verde")
        else: sinais.append("vermelho")
    n_verde = sinais.count("verde"); n_verm = sinais.count("vermelho")
    if n_verde >= 2 and n_verm == 0:
        consenso = "**Perfil de credito SOLIDO.**"
    elif n_verm >= 2:
        consenso = "**Perfil de credito PRESSIONADO** — atencao requerida."
    else:
        consenso = "**Perfil de credito ADEQUADO** com pontos de atencao."
    out.append(f"**Resumo executivo:** {consenso} Receita {_fmt_bi(rec)}, "
               f"EBITDA {_fmt_bi(ebitda)} (margem {_fmt_pct(margem_ebitda)}), "
               f"DL/EBITDA {_fmt_mult(dl_ebitda)}, cobertura de juros {_fmt_mult(cob_juros)}.")
    out.append("")

    # Solvencia e alavancagem
    out.append("**Solvencia & Alavancagem** _(Moody's/Fitch industrial)_")
    out.append(f"- **Divida Liquida/EBITDA LTM:** {_fmt_mult(dl_ebitda)} → *{cls_dl}*. "
               + ("Confortavel para enfrentar choques setoriais." if (dl_ebitda or 99) < 2.5
                  else ("Refinanciamento e custo da divida sao pontos criticos."
                        if (dl_ebitda or 0) > 4 else "Margem para choques moderada.")))
    out.append(f"- **Cobertura de juros (EBIT/Despesa fin.):** {_fmt_mult(cob_juros)} → *{cls_cob}*. "
               + ("EBIT cobre folgadamente o servico da divida." if (cob_juros or 0) > 8
                  else ("Pressao real do custo financeiro sobre o operacional." if (cob_juros or 99) < 4
                        else "Cobertura adequada mas sem grande margem.")))
    out.append("")

    # Liquidez e capital de giro
    out.append("**Liquidez & Capital de Giro** _(Fleuriet/Assaf Neto)_")
    out.append(f"- **Liquidez corrente:** {_fmt_mult(liq_corrente)} → *{cls_lc}*.")
    out.append(f"- **Cash ratio:** {_fmt_mult(cash_ratio)} "
               + (("(folgada)" if (cash_ratio or 0) > 0.5 else "(estreita)") if cash_ratio is not None else ""))
    if fleuriet_tipo:
        nota_str = f"{fleuriet_nota:.0f}/10" if not pd.isna(fleuriet_nota) else "—"
        interp_fl = {
            "Tipo I": "**solida** — CDG positivo, NCG negativa, T positivo",
            "Tipo II": "**solida com folga** — CDG > NCG > 0",
            "Tipo III": "**insatisfatoria** — CDG > 0, NCG > CDG, T < 0 (financia capital de giro com curto prazo)",
            "Tipo IV": "**pessima** — CDG < 0, NCG > 0, T < 0 (alta dependencia de credito de curto prazo)",
            "Tipo V": "**muito ruim** — CDG < 0, NCG > 0",
            "Tipo VI": "**alto risco** — CDG < 0, NCG < 0",
        }
        out.append(f"- **Modelo Fleuriet:** {fleuriet_tipo} (nota {nota_str}) — situacao "
                   f"{interp_fl.get(fleuriet_tipo, 'analise especifica recomendada')}.")
    out.append("")

    # Rentabilidade e criacao de valor
    out.append("**Rentabilidade & Criacao de Valor** _(Damodaran/McKinsey)_")
    out.append(f"- **Margem EBITDA:** {_fmt_pct(margem_ebitda)} → *{cls_mebitda}*.")
    out.append(f"- **Margem Liquida:** {_fmt_pct(margem_liquida)}.")
    if roic is not None:
        out.append(f"- **ROIC:** {_fmt_pct(roic)} vs WACC {_fmt_pct(wacc)} → *{cls_roic}*.")
        if eva is not None:
            sinal = "destruiu" if eva < 0 else "gerou"
            out.append(f"- **EVA (LTM):** {_fmt_bi(eva)} — empresa {sinal} valor economico no periodo.")
    if roe is not None:
        out.append(f"- **ROE:** {_fmt_pct(roe)}.")
    out.append("")

    # Geracao de caixa
    out.append("**Geracao de Caixa**")
    out.append(f"- **FCO trimestre:** {_fmt_bi(fco)} | **FCL:** {_fmt_bi(fcl)}.")
    if fco_ebitda is not None:
        out.append(f"- **FCO/EBITDA:** {_fmt_pct(fco_ebitda)} "
                   + ("(boa conversao operacional)" if fco_ebitda > 0.6
                      else "(conversao fraca — investigar capital de giro)" if fco_ebitda < 0.3
                      else "(adequada)"))
    if capex_rec is not None:
        intensidade = "intensiva em capital" if capex_rec > 0.10 else "asset-light"
        out.append(f"- **Capex/Receita:** {_fmt_pct(capex_rec)} ({intensidade}).")
    out.append("")

    # Ratings agencia
    if ratings:
        moodys = ratings.get("moodys") or "—"
        sp = ratings.get("sp") or "—"
        fitch = ratings.get("fitch") or "—"
        out.append(f"**Ratings publicos:** Moody's {moodys} · S&P {sp} · Fitch {fitch}")
        out.append("")

    out.append("---")
    out.append(f"*Analise gerada em {datetime.now().strftime('%Y-%m-%d')} usando "
               f"benchmarks de Moody's, Fitch, Damodaran e Modelo Fleuriet. "
               f"Nao constitui recomendacao de investimento.*")
    return "\n".join(out)


# ===========================================================================
# PARECER BANCO
# ===========================================================================
def _parecer_banco(ticker: str, df: pd.DataFrame, ratings: dict) -> str:
    if df is None or df.empty:
        return "*Sem dados suficientes para parecer.*"
    last = df.iloc[-1]
    label = last.get("label", "")

    cet1 = last.get("cet1_ratio")
    tier1 = last.get("tier1_ratio")
    slr = last.get("slr")
    nim = last.get("nim")
    rotce = last.get("rotce")
    roe = last.get("roe")
    eff = last.get("efficiency_ratio")
    nco = last.get("nco_ratio")
    coverage = last.get("coverage_ratio")
    lcr = last.get("lcr")
    nsfr = last.get("nsfr")
    casa = last.get("casa_ratio")

    # Benchmarks Basel III + Moody's banks + Fitch
    cls_cet1 = _classify(cet1, [0.085, 0.11, 0.135],
        ["Insuficiente (<8.5%)", "Adequado (8.5-11%)", "Forte (11-13.5%)",
         "Excelente (>13.5%)"], reverse=True)
    cls_rotce = _classify(rotce, [0.08, 0.12, 0.18],
        ["Fraca (<8%)", "Adequada (8-12%)", "Forte (12-18%)",
         "Excelente (>18%)"], reverse=True)
    cls_eff = _classify(eff, [0.50, 0.60, 0.70, 0.80],
        ["Excelente (<50%)", "Forte (50-60%)", "Adequado (60-70%)",
         "Pressionado (70-80%)", "Fraco (>80%)"])
    cls_nim = _classify(nim, [0.015, 0.025, 0.035],
        ["Compressao (<1.5%)", "Adequado (1.5-2.5%)", "Forte (2.5-3.5%)",
         "Premium (>3.5%)"], reverse=True)

    out = []
    out.append(f"### Parecer Tecnico — {ticker} ({label})")
    out.append("")
    out.append(f"**Resumo executivo:** Banco com CET1 {_fmt_pct(cet1)}, "
               f"RoTCE {_fmt_pct(rotce)}, Efficiency Ratio {_fmt_pct(eff)}, "
               f"NIM {_fmt_pct(nim)}.")
    out.append("")

    # Capital
    out.append("**Capital Regulatorio (Basel III / CRR)**")
    out.append(f"- **CET1 ratio:** {_fmt_pct(cet1)} → *{cls_cet1}*. "
               + ("Buffer confortavel sobre o minimo regulatorio (4.5%) + conservation buffer (2.5%) + GSIB."
                  if (cet1 or 0) > 0.11 else "Buffer estreito — limitacao para distribuir capital."))
    if tier1 is not None:
        out.append(f"- **Tier 1 ratio:** {_fmt_pct(tier1)}.")
    if slr is not None:
        out.append(f"- **SLR (Supplementary Leverage Ratio):** {_fmt_pct(slr)} "
                   + ("(acima do minimo de 5% para GSIB)" if slr > 0.05 else "(atencao ao limite)"))
    out.append("")

    # Rentabilidade
    out.append("**Rentabilidade** _(Bank Analyst's Handbook / Moody's)_")
    out.append(f"- **RoTCE:** {_fmt_pct(rotce)} → *{cls_rotce}*. "
               + ("Acima do custo de equity tipico (~10%)." if (rotce or 0) > 0.10
                  else "Abaixo do COE — pressao sobre P/B."))
    out.append(f"- **NIM (Net Interest Margin):** {_fmt_pct(nim)} → *{cls_nim}*.")
    out.append(f"- **Efficiency Ratio:** {_fmt_pct(eff)} → *{cls_eff}*. "
               + ("Estrutura de custos enxuta." if (eff or 1) < 0.6
                  else "Pressao por reducao de despesas operacionais."))
    if roe is not None:
        out.append(f"- **ROE:** {_fmt_pct(roe)}.")
    out.append("")

    # Qualidade de credito
    if nco is not None or coverage is not None:
        out.append("**Qualidade de Credito**")
        if nco is not None:
            cls_nco = "Excelente" if nco < 0.005 else "Adequado" if nco < 0.015 else "Pressionado"
            out.append(f"- **NCO ratio (Net Charge-Offs):** {_fmt_pct(nco)} → *{cls_nco}*.")
        if coverage is not None:
            out.append(f"- **Coverage ratio (LLR/NPL):** {_fmt_mult(coverage)} "
                       + ("(reservas confortaveis)" if coverage > 1.5 else "(reservas justas)"))
        out.append("")

    # Liquidez
    if lcr is not None or nsfr is not None or casa is not None:
        out.append("**Liquidez & Funding**")
        if lcr is not None:
            out.append(f"- **LCR (Liquidity Coverage Ratio):** {_fmt_pct(lcr)} "
                       "(minimo Basel III: 100%).")
        if nsfr is not None:
            out.append(f"- **NSFR (Net Stable Funding Ratio):** {_fmt_pct(nsfr)} (minimo: 100%).")
        if casa is not None:
            out.append(f"- **CASA ratio:** {_fmt_pct(casa)} "
                       + ("(funding barato e estavel)" if casa > 0.40
                          else "(dependencia de funding caro)"))
        out.append("")

    if ratings:
        out.append(f"**Ratings publicos:** Moody's {ratings.get('moodys') or '—'} · "
                   f"S&P {ratings.get('sp') or '—'} · Fitch {ratings.get('fitch') or '—'}")
        out.append("")

    out.append("---")
    out.append(f"*Analise gerada em {datetime.now().strftime('%Y-%m-%d')} usando Basel III, "
               f"Bank Analyst's Handbook (Frost) e metodologias Moody's/Fitch para bancos.*")
    return "\n".join(out)


# ===========================================================================
# PARECER ASSET MANAGER
# ===========================================================================
def _fmt_am_bi(v_mm):
    """Format AM value that is in millions to display string."""
    if v_mm is None or pd.isna(v_mm) or v_mm == 0:
        return "—"
    units = v_mm * 1e6
    if abs(units) >= 1e12:
        return f"${units/1e12:.2f}T"
    if abs(units) >= 1e9:
        return f"${units/1e9:.2f}B"
    return f"${v_mm:.0f}M"


def _parecer_asset_manager(ticker: str, df: pd.DataFrame, ratings: dict,
                           dados_am: dict | None = None) -> str:
    if (df is None or df.empty) and not dados_am:
        return "*Sem dados suficientes para parecer.*"

    last = df.iloc[-1] if df is not None and not df.empty else {}
    label = last.get("label", "") if isinstance(last, dict) else (last.get("label") if hasattr(last, "get") else "")

    # --- Dados do EDGAR (df principal) ---
    rec = last.get("receita_liquida") if hasattr(last, "get") else None
    margem_ebitda = last.get("margem_ebitda") if hasattr(last, "get") else None
    ebitda_ltm = last.get("ebitda_ltm") if hasattr(last, "get") else None
    divida_bruta = last.get("divida_bruta") if hasattr(last, "get") else None
    divida_liquida = last.get("divida_liquida") if hasattr(last, "get") else None
    cob_juros = last.get("interest_coverage_ebitda") if hasattr(last, "get") else None
    fco = last.get("fco") if hasattr(last, "get") else None
    ll = last.get("lucro_liquido") if hasattr(last, "get") else None

    # --- Dados AM (dados_asset_manager.json, valores em milhoes) ---
    am_last = None
    am_prev = None
    if dados_am and dados_am.get("periodos"):
        periodos = sorted(dados_am["periodos"], key=lambda p: p.get("periodo", ""))
        am_last = periodos[-1]
        if len(periodos) >= 2:
            am_prev = periodos[-2]
        if not label and am_last:
            label = am_last.get("trimestre", "")

    fre = am_last.get("fre") if am_last else None
    fre_margin = am_last.get("fre_margin_pct") if am_last else None  # ja em %
    sre = am_last.get("sre") if am_last else None
    de = am_last.get("de") if am_last else None
    aum = am_last.get("total_aum") if am_last else None
    fpaum = am_last.get("fee_paying_aum") if am_last else None
    dry_powder = am_last.get("dry_powder") if am_last else None
    perm_cap = am_last.get("permanent_capital_pct") if am_last else None
    mgmt_fees = am_last.get("management_fees") if am_last else None
    perf_fees = am_last.get("performance_fees_realized") if am_last else None
    napr = am_last.get("net_accrued_performance") if am_last else None
    comp = am_last.get("compensation_expense") if am_last else None
    gross_debt_am = am_last.get("gross_debt_corp") if am_last else None
    int_exp_am = am_last.get("interest_expense_corp") if am_last else None

    # Variacao trimestral
    fre_prev = am_prev.get("fre") if am_prev else None
    aum_prev = am_prev.get("total_aum") if am_prev else None
    fpaum_prev = am_prev.get("fee_paying_aum") if am_prev else None

    # Metricas derivadas (usando dados AM em milhoes)
    fre_ann = fre * 4 if fre else None  # FRE anualizado (milhoes)
    debt_fre = None
    if divida_bruta and fre_ann:
        debt_fre = divida_bruta / (fre_ann * 1e6)  # divida_bruta esta em units
    elif gross_debt_am and fre_ann:
        debt_fre = gross_debt_am / fre_ann  # ambos em milhoes

    debt_ebitda = None
    if divida_bruta and ebitda_ltm and ebitda_ltm > 0:
        debt_ebitda = divida_bruta / ebitda_ltm

    fpaum_pct = (fpaum / aum * 100) if (fpaum and aum and aum > 0) else None
    perf_pct_de = (perf_fees / de * 100) if (perf_fees and de and de > 0) else None
    comp_fre_pct = (abs(comp) / fre * 100) if (comp and fre and fre > 0) else None
    napr_debt = None
    if napr and divida_bruta:
        napr_debt = (napr * 1e6) / divida_bruta
    elif napr and gross_debt_am and gross_debt_am > 0:
        napr_debt = napr / gross_debt_am

    # === Classificacoes (Moody's AM Methodology) ===
    # FRE Margin: >55% Premium, 40-55% Forte, 25-40% Adequada, <25% Fraca
    cls_fre_margin = "—"
    if fre_margin is not None:
        if fre_margin > 55: cls_fre_margin = "Premium (>55%)"
        elif fre_margin > 40: cls_fre_margin = "Forte (40-55%)"
        elif fre_margin > 25: cls_fre_margin = "Adequada (25-40%)"
        else: cls_fre_margin = "Fraca (<25%)"

    # Debt/EBITDA — Moody's AM
    cls_debt_ebitda = "—"
    if debt_ebitda is not None:
        if debt_ebitda < 1: cls_debt_ebitda = "Aaa-Aa (<1x)"
        elif debt_ebitda < 2: cls_debt_ebitda = "A (1-2x)"
        elif debt_ebitda < 3.5: cls_debt_ebitda = "Baa (2-3.5x)"
        elif debt_ebitda < 5: cls_debt_ebitda = "Ba (3.5-5x)"
        else: cls_debt_ebitda = "B+ (>5x)"

    # Debt/FRE stress test
    cls_debt_fre = "—"
    if debt_fre is not None:
        if debt_fre < 2: cls_debt_fre = "Conservador (<2x)"
        elif debt_fre < 3: cls_debt_fre = "Adequado (2-3x)"
        elif debt_fre < 5: cls_debt_fre = "Pressionado (3-5x)"
        else: cls_debt_fre = "Critico (>5x)"

    # Interest coverage
    cls_cob = "—"
    if cob_juros is not None:
        if cob_juros > 15: cls_cob = "Excelente (>15x)"
        elif cob_juros > 8: cls_cob = "Forte (8-15x)"
        elif cob_juros > 4: cls_cob = "Adequada (4-8x)"
        else: cls_cob = "Fragil (<4x)"

    # Permanent capital — higher = more stable AUM
    cls_perm = "—"
    if perm_cap is not None:
        if perm_cap > 70: cls_perm = "Excelente (>70%)"
        elif perm_cap > 50: cls_perm = "Forte (50-70%)"
        elif perm_cap > 30: cls_perm = "Adequado (30-50%)"
        else: cls_perm = "Fraco (<30%)"

    # === Construcao do parecer ===
    out = []
    out.append(f"### Parecer Tecnico — {ticker} ({label})")
    out.append("")

    # Resumo executivo — classificacao geral
    sinais = []
    if fre_margin is not None:
        sinais.append("verde" if fre_margin > 45 else "amarelo" if fre_margin > 30 else "vermelho")
    if debt_ebitda is not None:
        sinais.append("verde" if debt_ebitda < 2 else "amarelo" if debt_ebitda < 3.5 else "vermelho")
    elif debt_fre is not None:
        sinais.append("verde" if debt_fre < 3 else "amarelo" if debt_fre < 5 else "vermelho")
    if cob_juros is not None:
        sinais.append("verde" if cob_juros > 8 else "amarelo" if cob_juros > 4 else "vermelho")
    if perm_cap is not None:
        sinais.append("verde" if perm_cap > 50 else "amarelo" if perm_cap > 30 else "vermelho")

    n_verde = sinais.count("verde"); n_verm = sinais.count("vermelho")
    if n_verde >= 2 and n_verm == 0:
        consenso = "**Perfil de credito SOLIDO.**"
    elif n_verm >= 2:
        consenso = "**Perfil de credito PRESSIONADO** — atencao requerida."
    else:
        consenso = "**Perfil de credito ADEQUADO** com pontos de atencao."

    resumo_parts = [consenso]
    if aum: resumo_parts.append(f"AUM {_fmt_am_bi(aum)}")
    if fre: resumo_parts.append(f"FRE {_fmt_am_bi(fre)}")
    if fre_margin is not None: resumo_parts.append(f"margem FRE {fre_margin:.1f}%")
    if de: resumo_parts.append(f"DE {_fmt_am_bi(de)}")
    out.append(f"**Resumo executivo:** {' '.join(resumo_parts[:1])} {', '.join(resumo_parts[1:])}.")
    out.append("")

    # 1. Earnings & Qualidade da Receita
    out.append("**Earnings & Qualidade da Receita** _(Moody's AM Methodology)_")
    if fre is not None:
        out.append(f"- **Fee-Related Earnings (FRE):** {_fmt_am_bi(fre)} trimestral "
                   f"({_fmt_am_bi(fre_ann)} anualizado). "
                   "FRE e o indicador mais estavel — Moody's pondera FRE/total earnings como proxy de previsibilidade.")
        if fre_prev and fre_prev > 0:
            var = (fre - fre_prev) / abs(fre_prev) * 100
            out.append(f"  Variacao QoQ: {'+' if var > 0 else ''}{var:.1f}%.")
    if fre_margin is not None:
        out.append(f"- **Margem FRE:** {fre_margin:.1f}% → *{cls_fre_margin}*. "
                   + ("Margem elevada reflete pricing power e controle de custos."
                      if fre_margin > 50 else
                      "Margem saudavel — monitorar pressao competitiva em fees."
                      if fre_margin > 35 else
                      "Margem apertada — risco de compressao por competicao ou mix de AUM."))
    if mgmt_fees is not None:
        out.append(f"- **Management Fees:** {_fmt_am_bi(mgmt_fees)} — receita recorrente base.")
    if perf_fees is not None:
        out.append(f"- **Performance Fees (realizadas):** {_fmt_am_bi(perf_fees)}"
                   + (f" ({perf_pct_de:.0f}% do DE)." if perf_pct_de is not None else ".")
                   + (" Dependencia elevada de carry — volatilidade no DE." if perf_pct_de and perf_pct_de > 40
                      else " Participacao moderada — bom mix entre FRE e carry." if perf_pct_de and perf_pct_de > 20
                      else ""))
    if sre is not None and sre != 0:
        out.append(f"- **Spread-Related Earnings (SRE):** {_fmt_am_bi(sre)} "
                   "— componente de spread de investimento (tipico de insurance-linked AMs). "
                   "Moody's trata como receita menos previsivel que FRE.")
    if de is not None:
        out.append(f"- **Distributable Earnings (DE):** {_fmt_am_bi(de)} "
                   "— resultado distribuivel aos acionistas apos impostos e carry realizado.")
    if comp and fre:
        out.append(f"- **Compensacao/FRE:** {comp_fre_pct:.0f}% "
                   + ("(controle salarial forte)" if comp_fre_pct < 40
                      else "(dentro do padrao do setor)" if comp_fre_pct < 55
                      else "(compensacao elevada — pressao sobre margem)"))
    out.append("")

    # 2. Escala e Estabilidade do AUM
    out.append("**Escala & Estabilidade do AUM** _(Moody's: escala e diversificacao)_")
    if aum is not None:
        out.append(f"- **AUM Total:** {_fmt_am_bi(aum)}."
                   + (" Megaplatform — escala global com vantagem competitiva significativa." if aum > 500000
                      else " Plataforma de grande porte." if aum > 200000
                      else " Porte medio — escala pode limitar diversificacao."))
        if aum_prev and aum_prev > 0:
            var = (aum - aum_prev) / abs(aum_prev) * 100
            out.append(f"  Crescimento QoQ: {'+' if var > 0 else ''}{var:.1f}%.")
    if fpaum is not None:
        out.append(f"- **Fee-Paying AUM:** {_fmt_am_bi(fpaum)}"
                   + (f" ({fpaum_pct:.0f}% do AUM total)." if fpaum_pct else "."))
    if perm_cap is not None:
        out.append(f"- **Capital Permanente:** {perm_cap:.0f}% do AUM → *{cls_perm}*. "
                   + ("Base de AUM altamente estavel — reduz risco de resgate e protege a receita recorrente."
                      if perm_cap > 60 else
                      "Parcela relevante de capital permanente — estabilidade razoavel."
                      if perm_cap > 40 else
                      "AUM com maior risco de fluxo de saida — monitorar captacao vs resgate."))
    if dry_powder is not None:
        out.append(f"- **Dry Powder:** {_fmt_am_bi(dry_powder)} — capital comprometido nao investido "
                   "(potencial de deploy e futuras management fees).")
    out.append("")

    # 3. Solvencia e Alavancagem
    out.append("**Solvencia & Alavancagem** _(Moody's AM Methodology)_")
    if debt_ebitda is not None:
        out.append(f"- **Divida Bruta/EBITDA LTM (Moody's):** {_fmt_mult(debt_ebitda)} → *{cls_debt_ebitda}*. "
                   + ("Alavancagem conservadora — amplo espaco para emissao se necessario."
                      if debt_ebitda < 2 else
                      "Alavancagem moderada — espaco limitado para aquisicoes alavancadas."
                      if debt_ebitda < 3.5 else
                      "Alavancagem elevada para asset manager — risco de downgrade."))
    if debt_fre is not None:
        out.append(f"- **Divida/FRE anualizado (stress test):** {_fmt_mult(debt_fre)} → *{cls_debt_fre}*. "
                   "Stress test: assumindo performance fees = 0, quanto a divida representa vs receita recorrente pura."
                   + (" Empresa paga divida com FRE puro em menos de 3 anos — resiliente."
                      if debt_fre < 3 else
                      " Servico da divida dependeria parcialmente de carry/performance." if debt_fre < 5
                      else " Risco material se performance fees secarem."))
    if divida_bruta:
        out.append(f"- **Divida Bruta Corporativa:** {_fmt_bi(divida_bruta)}.")
    elif gross_debt_am:
        out.append(f"- **Divida Bruta Corporativa:** {_fmt_am_bi(gross_debt_am)}.")
    if cob_juros is not None:
        out.append(f"- **Cobertura de juros (EBITDA/Juros):** {_fmt_mult(cob_juros)} → *{cls_cob}*.")
    if napr is not None:
        out.append(f"- **Net Accrued Performance (NAPR):** {_fmt_am_bi(napr)} — carry nao realizado no balanco.")
        if napr_debt is not None:
            out.append(f"  NAPR/Divida: {napr_debt:.0%} — "
                       + ("gordura futura significativa: carry acumulado cobre parcela relevante da divida."
                          if napr_debt > 0.5 else
                          "carry acumulado adiciona colchao modesto."
                          if napr_debt > 0.2 else
                          "carry acumulado pequeno relativo a divida."))
    out.append("")

    # 4. Geracao de Caixa (EDGAR)
    if fco is not None:
        out.append("**Geracao de Caixa** _(GAAP — 10-K/10-Q)_")
        out.append(f"- **FCO:** {_fmt_bi(fco)}.")
        if rec and rec > 0:
            fco_rec = fco / rec
            out.append(f"- **FCO/Receita:** {_fmt_pct(fco_rec)} "
                       + ("(conversao forte)" if fco_rec > 0.3 else "(conversao moderada)"))
        out.append("")

    # 5. Ratings
    if ratings:
        moodys = ratings.get("moodys") or "—"
        sp = ratings.get("sp") or "—"
        fitch = ratings.get("fitch") or "—"
        out.append(f"**Ratings publicos:** Moody's {moodys} · S&P {sp} · Fitch {fitch}")
        # Concordancia rating vs metricas
        is_ig = any(r and r[0] in ("A", "B") and "B" not in r[1:2]
                     for r in [moodys, sp, fitch] if r != "—")
        if is_ig and debt_ebitda and debt_ebitda > 3.5:
            out.append("  ⚠️ Metricas de alavancagem parecem descasadas com o rating IG — investigar.")
        out.append("")

    out.append("---")
    out.append(f"*Analise gerada em {datetime.now().strftime('%Y-%m-%d')} usando "
               "Moody's Methodology for Asset Management Firms, benchmarks de PE/Alts "
               "e dados EDGAR (10-K/10-Q).*")
    return "\n".join(out)


# ===========================================================================
# PARECER CARD/PAYMENTS
# ===========================================================================
def _parecer_card(ticker: str, df: pd.DataFrame, ratings: dict) -> str:
    if df is None or df.empty:
        return "*Sem dados suficientes para parecer.*"
    last = df.iloc[-1]
    label = last.get("label", "")

    rec = last.get("receita_liquida")
    ll = last.get("lucro_liquido")
    roe = last.get("roe")
    eff = last.get("efficiency_ratio")
    prov = last.get("provision_ratio")
    margem_liq = last.get("margem_liquida")
    dl_ebitda = last.get("divida_liq_ebitda")

    out = []
    out.append(f"### Parecer Tecnico — {ticker} ({label})")
    out.append("")
    out.append(f"**Resumo executivo:** Pagamentos/cartoes — receita {_fmt_bi(rec)}, "
               f"lucro liquido {_fmt_bi(ll)}, ROE {_fmt_pct(roe)}.")
    out.append("")

    out.append("**Indicadores-chave** _(Bank Analyst's Handbook + metodologia Fitch)_")
    if margem_liq is not None:
        cls_ml = ("Premium" if margem_liq > 0.30 else "Forte" if margem_liq > 0.20
                  else "Adequada" if margem_liq > 0.10 else "Pressionada")
        out.append(f"- **Margem liquida:** {_fmt_pct(margem_liq)} → *{cls_ml}*.")
    if roe is not None:
        cls_roe = ("Excelente" if roe > 0.25 else "Forte" if roe > 0.15
                   else "Adequado" if roe > 0.10 else "Fraco")
        out.append(f"- **ROE:** {_fmt_pct(roe)} → *{cls_roe}*.")
    if eff is not None:
        out.append(f"- **Efficiency Ratio:** {_fmt_pct(eff)}.")
    if prov is not None:
        cls_prov = ("Baixa" if prov < 0.02 else "Adequada" if prov < 0.04
                    else "Elevada" if prov < 0.06 else "Estresse")
        out.append(f"- **Provision Ratio:** {_fmt_pct(prov)} → *{cls_prov}* "
                   "(carteira de credito). Acima de 4% sinaliza ciclo de credito adverso.")
    if dl_ebitda is not None:
        out.append(f"- **DL/EBITDA:** {_fmt_mult(dl_ebitda)}.")
    out.append("")

    if ratings:
        out.append(f"**Ratings publicos:** Moody's {ratings.get('moodys') or '—'} · "
                   f"S&P {ratings.get('sp') or '—'} · Fitch {ratings.get('fitch') or '—'}")
        out.append("")
    out.append("---")
    out.append(f"*Analise gerada em {datetime.now().strftime('%Y-%m-%d')}.*")
    return "\n".join(out)


# ===========================================================================
# DISPATCHER
# ===========================================================================
SETOR_FUNCS = {
    "Nao-Financeira": _parecer_nao_financeira,
    "Banco": _parecer_banco,
    "Asset Manager": _parecer_asset_manager,
    "Card / Outros": _parecer_card,
}


def gerar_parecer(ticker: str, setor: str, df: pd.DataFrame,
                  ratings: dict | None = None,
                  dados_am: dict | None = None) -> str:
    """Gera markdown do parecer tecnico para um ticker."""
    func = SETOR_FUNCS.get(setor, _parecer_nao_financeira)
    if setor == "Asset Manager":
        return func(ticker, df, ratings or {}, dados_am=dados_am)
    return func(ticker, df, ratings or {})


def salvar_parecer(ticker: str, setor: str, df: pd.DataFrame,
                   ratings: dict, pasta_destino: str,
                   dados_am: dict | None = None) -> str:
    """Gera e salva o parecer em {pasta_destino}/parecer.md."""
    md = gerar_parecer(ticker, setor, df, ratings, dados_am=dados_am)
    Path(pasta_destino).mkdir(parents=True, exist_ok=True)
    out_path = Path(pasta_destino) / "parecer.md"
    out_path.write_text(md, encoding="utf-8")
    return str(out_path)
