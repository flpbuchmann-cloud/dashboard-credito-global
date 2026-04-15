"""
Extrator de Quarterly Full Reports PDF do UBS Group AG.

Lê os PDFs trimestrais e extrai dados estruturados da página "UBS Group key figures":
- Group Results (Revenue, OpEx, Net Income)
- Capital (CET1, RWA, Leverage)
- Liquidity (LCR, NSFR)
- Credit Quality (NPL ratio)
- Profitability (ROE, ROTE, Cost/Income)

Salva em supplement_data.json no mesmo formato que Barclays/BK.
"""

import os
import re
import json
import glob

import fitz  # PyMuPDF


# ---------------------------------------------------------------------------
# Quarter date mapping
# ---------------------------------------------------------------------------

def _quarter_to_date(quarter_str: str) -> str:
    """Converte '4Q25' -> '2025-12-31', etc."""
    m = re.match(r"(\d)Q(\d{2})", quarter_str)
    if not m:
        return quarter_str
    q = int(m.group(1))
    yr = 2000 + int(m.group(2))
    end_dates = {1: "03-31", 2: "06-30", 3: "09-30", 4: "12-31"}
    return f"{yr}-{end_dates[q]}"


def _date_to_quarter(date_str: str) -> str:
    """Converte '31.12.25' -> '4Q25', '30.9.25' -> '3Q25'."""
    parts = date_str.split(".")
    if len(parts) != 3:
        return date_str
    day, month, yr = int(parts[0]), int(parts[1]), parts[2]
    quarter_map = {3: 1, 6: 2, 9: 3, 12: 4}
    q = quarter_map.get(month, 0)
    return f"{q}Q{yr}" if q else date_str


def _parse_number(text: str) -> float | None:
    """Parse number from text: '12,145' -> 12145, '(1,234)' -> -1234, 'n.m.' -> None."""
    text = text.strip()
    if not text or text in ("n.m.", "–", "—", "N/A"):
        return None
    negative = False
    if text.startswith("(") and text.endswith(")"):
        negative = True
        text = text[1:-1]
    text = text.replace(",", "").replace(" ", "")
    try:
        val = float(text)
        return -val if negative else val
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# PDF Key Figures Parser
# ---------------------------------------------------------------------------

def _find_key_figures_page(doc) -> int | None:
    """Find the page with 'UBS Group key figures' table."""
    for pg in range(min(len(doc), 12)):
        text = doc[pg].get_text()
        if "key figures" in text.lower() and "Total revenues" in text:
            return pg
    return None


def extrair_cronograma_divida_ubs(html_path: str) -> dict | None:
    """Extrai o cronograma de vencimento de dívida do 20-F do UBS.

    Procura por 'Note 23 Maturity analysis of financial liabilities' e extrai
    a tabela de Debt issued measured at amortized cost + Debt issued at fair value.

    Returns:
        Dict com data_referencia, faixas (USD bn) e total
    """
    try:
        with open(html_path, "r", encoding="utf-8") as f:
            html = f.read()
    except FileNotFoundError:
        return None

    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"&[^;]+;", " ", text)
    text = re.sub(r"\s+", " ", text)

    # Find the actual table by looking for specific table header
    # The table starts with: 'Maturity analysis ... <date> USD bn Due within 1 month'
    table_match = re.search(
        r"Maturity analysis of financial liabilities on an undiscounted basis\s+"
        r"(\d{2}\.\d{2}\.\d{2})\s+USD bn\s+Due within 1 month",
        text,
    )
    if not table_match:
        return None
    idx = table_match.start()

    # Get the section text
    section = text[idx:idx + 5000]

    # Match the latest period header (e.g., '31.12.25 USD bn')
    # Pattern: '31.12.25 USD bn Due within 1 month ... Debt issued measured at amortized cost 2 9.4 9.1 46.8 25.7 66.5 82.6 17.6 257.6'
    period_match = re.search(r"(\d{2}\.\d{2}\.\d{2})\s+USD bn", section)
    if not period_match:
        return None
    period_str = period_match.group(1)
    # Convert to ISO date
    parts = period_str.split(".")
    data_ref = f"20{parts[2]}-{parts[1].zfill(2)}-{parts[0].zfill(2)}"

    # Extract Debt issued measured at amortized cost row
    # Pattern: 'Debt issued measured at amortized cost 2 <8 numbers separated by spaces> <total>'
    debt_amortized = re.search(
        r"Debt issued measured at amortized cost\s*\d?\s+"
        r"([\d,]+\.?\d*)\s+([\d,]+\.?\d*)\s+([\d,]+\.?\d*)\s+([\d,]+\.?\d*)\s+"
        r"([\d,]+\.?\d*)\s+([\d,]+\.?\d*)\s+([\d,]+\.?\d*)\s+([\d,]+\.?\d*)",
        section,
    )

    debt_fv = re.search(
        r"Debt issued designated at fair value\s*\d?\s+"
        r"([\d,]+\.?\d*)\s+([\d,]+\.?\d*)\s+([\d,]+\.?\d*)\s+([\d,]+\.?\d*)\s+"
        r"([\d,]+\.?\d*)\s+([\d,]+\.?\d*)\s+([\d,]+\.?\d*)",
        section,
    )

    bucket_labels = [
        "Due within 1 month",
        "Due between 1 and 3 months",
        "Due between 3 and 12 months",
        "Due between 1 and 2 years",
        "Due between 2 and 5 years",
        "Due over 5 years",
        "Perpetual / Not applicable",
    ]

    faixas = []
    if debt_amortized:
        amort_vals = [float(g.replace(",", "")) for g in debt_amortized.groups()[:7]]
        amort_total = float(debt_amortized.group(8).replace(",", ""))
    else:
        return None

    fv_vals = [0.0] * 7
    if debt_fv:
        fv_vals = [float(g.replace(",", "")) for g in debt_fv.groups()[:6]] + [0.0]
        # Insert 0 for Perpetual position (FV debt typically not perpetual)
        # The FV table has 6 buckets without perpetual; align with amortized table

    for i, label in enumerate(bucket_labels):
        valor_bn = amort_vals[i] + fv_vals[i]
        faixas.append({
            "faixa": label,
            "valor_usd_bn": round(valor_bn, 2),
            "valor_usd_m": round(valor_bn * 1000, 1),
        })

    total_bn = round(sum(f["valor_usd_bn"] for f in faixas), 2)

    return {
        "data_referencia": data_ref,
        "moeda": "USD",
        "faixas": faixas,
        "total_usd_bn": total_bn,
        "total_usd_m": round(total_bn * 1000, 1),
        "fonte": "UBS 20-F Note 23b - Maturity analysis of financial liabilities",
    }


def _find_division_pages_usd(doc) -> list[int]:
    """Find pages with division-level data in USD (NIM bps, Customer deposits USD bn).

    UBS reports each division's key figures twice: once in CHF, once in USD.
    We want the USD version for consistency with US banks.
    """
    pages = []
    for pg in range(len(doc)):
        text = doc[pg].get_text()
        if "Customer deposits (USD bn)" in text and "Net interest margin (bps)" in text:
            pages.append(pg)
    return pages


def _extract_division_metrics(doc, page_num: int) -> dict:
    """Extract NIM, Customer Deposits, Loans Gross from a USD division page."""
    text = doc[page_num].get_text()
    lines = text.split("\n")
    metrics = {}

    def _next_number(start_idx: int):
        for j in range(start_idx + 1, min(start_idx + 8, len(lines))):
            v = lines[j].strip()
            if v and (v[0].isdigit() or v.startswith("(") or v.startswith("-")):
                return _parse_number(v)
        return None

    for i, line in enumerate(lines):
        s = line.strip()
        if s == "Net interest margin (bps)1" or s == "Net interest margin (bps)" or s.startswith("Net interest margin (bps)"):
            v = _next_number(i)
            if v is not None and "nim_bps" not in metrics:
                metrics["nim_bps"] = v
                metrics["nim"] = v / 10000  # bps -> decimal
        elif s.startswith("Net interest income"):
            v = _next_number(i)
            if v is not None and "nii" not in metrics:
                metrics["nii"] = v
        elif s == "Customer deposits (USD bn)" or s.startswith("Customer deposits (USD bn)"):
            v = _next_number(i)
            if v is not None:
                metrics["customer_deposits_usd_bn"] = v
                metrics["depositos"] = v * 1000  # bn -> millions
        elif s == "Loans, gross (USD bn)" or s.startswith("Loans, gross (USD bn)"):
            v = _next_number(i)
            if v is not None:
                metrics["loans_gross_usd_bn"] = v
                metrics["loans_gross"] = v * 1000

    return metrics


def _extract_key_figures(doc, page_num: int) -> list[dict]:
    """Extract quarterly data from the UBS Group key figures table.

    Returns list of dicts, one per quarter column in the table.
    """
    text = doc[page_num].get_text()
    lines = text.split("\n")

    # Find column headers (dates like '31.12.25', '30.9.25', '31.12.24')
    # In UBS PDFs each date is on its own line, ordered: 3 quarter columns then 2 year columns
    date_pattern = r"^(\d{1,2}\.\d{1,2}\.\d{2})$"
    header_dates = []
    for line in lines:
        m = re.match(date_pattern, line.strip())
        if m:
            d = m.group(1)
            parts = d.split(".")
            month = int(parts[1])
            if month in (3, 6, 9, 12):
                header_dates.append(d)
        if len(header_dates) >= 5:
            break

    # First 3 dates are the quarterly columns (current Q, prior Q, year-ago Q)
    # Last 2 dates are year-ended columns (skip)
    quarter_dates = header_dates[:3]

    if not quarter_dates:
        return []

    # Define metrics: (label_substring, output_key, is_percentage, section)
    metrics = [
        ("Total revenues", "total_revenues", False, "income_statement"),
        ("Credit loss expense", "credit_loss_expense", False, "income_statement"),
        ("Operating expenses", "operating_expenses", False, "income_statement"),
        ("Operating profit", "operating_profit_before_tax", False, "income_statement"),
        ("Net profit", "net_income", False, "income_statement"),
        ("Return on equity (%)", "roe", True, "profitability"),
        ("Return on tangible equity (%)", "rote", True, "profitability"),
        ("Return on common equity tier 1 capital (%)", "rocet1", True, "profitability"),
        ("Cost / income ratio (%)", "cost_income_ratio", True, "profitability"),
        ("Total assets", "total_assets", False, "balance_sheet"),
        ("Equity attributable to shareholders", "equity", False, "balance_sheet"),
        ("Common equity tier 1 capital", "cet1_capital", False, "capital"),
        ("Risk-weighted assets", "rwa", False, "capital"),
        ("Common equity tier 1 capital ratio (%)", "cet1_ratio", True, "capital"),
        ("Going concern capital ratio (%)", "going_concern_ratio", True, "capital"),
        ("Leverage ratio denominator", "leverage_denominator", False, "capital"),
        ("Common equity tier 1 leverage ratio (%)", "cet1_leverage_ratio", True, "capital"),
        ("Liquidity coverage ratio (%)", "lcr", True, "capital"),
        ("Net stable funding ratio (%)", "nsfr", True, "capital"),
        ("Credit-impaired lending", "npl_ratio", True, "credit_quality"),
    ]

    results = []
    for date_str in quarter_dates:
        quarter = _date_to_quarter(date_str)
        periodo = _quarter_to_date(quarter)
        results.append({
            "periodo": periodo,
            "trimestre": quarter,
            "income_statement": {},
            "profitability": {},
            "balance_sheet": {},
            "capital": {},
            "credit_quality": {},
        })

    # Build a list of (line_idx, label, value_lines[3]) — UBS PDFs put each value
    # on its own line. After a label line, the next 5 lines are the 5 column values
    # (3 quarterly + 2 annual), in order matching quarter_dates order.
    used_indices = set()  # track which (label, line_idx) we've already extracted
    n_quarters = len(quarter_dates)

    for label_substr, key, is_pct, section in metrics:
        for i, line in enumerate(lines):
            line_clean = line.strip()
            if i in used_indices:
                continue
            # Match: line starts with label or label is the entire line
            # Strip footnote digits (e.g., "Common equity tier 1 capital ratio (%)5")
            line_no_footnote = re.sub(r"\d+$", "", line_clean).strip()
            if not (line_clean == label_substr or line_no_footnote == label_substr or line_clean.startswith(label_substr) or line_no_footnote.startswith(label_substr)):
                continue
            # Make sure it's exactly this label, not a subset (e.g. "Common equity tier 1 capital" vs "Common equity tier 1 capital ratio (%)")
            # Check that next non-numeric line doesn't add more text
            # Take next n_quarters lines as values
            values = []
            j = i + 1
            while j < len(lines) and len(values) < n_quarters:
                v = lines[j].strip()
                if v and (v[0].isdigit() or v.startswith("(") or v == "n.m." or v.startswith("-")):
                    values.append(v)
                    j += 1
                elif v == "":
                    j += 1
                else:
                    break
            if len(values) >= n_quarters:
                used_indices.add(i)
                for k in range(n_quarters):
                    val = _parse_number(values[k])
                    if val is not None:
                        if is_pct:
                            val = val / 100
                        results[k][section][key] = val
                break

    return results


# ---------------------------------------------------------------------------
# Build supplement_data format
# ---------------------------------------------------------------------------

def _build_supplement_entry(raw: dict) -> dict:
    """Convert raw extracted data to supplement_data.json format."""
    inc = raw.get("income_statement", {})
    prof = raw.get("profitability", {})
    bs = raw.get("balance_sheet", {})
    cap = raw.get("capital", {})
    cq = raw.get("credit_quality", {})
    div = raw.get("division_metrics", {})

    # Income statement (UBS reports in USD millions)
    entry = {
        "periodo": raw["periodo"],
        "trimestre": raw["trimestre"],
        "moeda_original": "USD",
        "fx_rate": 1.0,
        "fonte": "UBS Group Quarterly Report",
        "income_statement": {
            "total_income": inc.get("total_revenues"),
            "total_revenues": inc.get("total_revenues"),
            "nii": div.get("nii"),  # from division-level extraction
            "credit_impairment": inc.get("credit_loss_expense"),
            "operating_costs": inc.get("operating_expenses"),
            "total_opex": inc.get("operating_expenses"),
            "profit_before_tax": inc.get("operating_profit_before_tax"),
            "net_income": inc.get("net_income"),
        },
        "balance_sheet": {
            "total_assets": bs.get("total_assets"),
            "equity": bs.get("equity"),
        },
        "yields_rates": {
            "rote": prof.get("rote"),
            "roe": prof.get("roe"),
            "rocet1": prof.get("rocet1"),
            "cost_income_ratio": prof.get("cost_income_ratio"),
            "efficiency_ratio": prof.get("cost_income_ratio"),
            "nim": div.get("nim"),
            "nim_bps": div.get("nim_bps"),
        },
        "avg_balances": {
            "customer_deposits_usd_bn": div.get("customer_deposits_usd_bn"),
            "loans_gross_usd_bn": div.get("loans_gross_usd_bn"),
            "avg_total_deposits": div.get("depositos"),
            "avg_loans": div.get("loans_gross"),
        },
    }

    # Capital section (for indicadores_fin.py compatibility)
    capital = {}
    if "cet1_ratio" in cap:
        capital["cet1_ratio"] = cap["cet1_ratio"]
    if "cet1_capital" in cap:
        capital["cet1_capital"] = cap["cet1_capital"]
    if "rwa" in cap:
        capital["rwa_standardized"] = cap["rwa"]
    if "cet1_leverage_ratio" in cap:
        capital["slr"] = cap["cet1_leverage_ratio"]
    if "lcr" in cap:
        capital["lcr"] = cap["lcr"]
    if "nsfr" in cap:
        capital["nsfr"] = cap["nsfr"]
    if "going_concern_ratio" in cap:
        capital["total_capital_ratio"] = cap["going_concern_ratio"]
    if "leverage_denominator" in cap:
        capital["total_leverage_exposure"] = cap["leverage_denominator"]
    entry["capital"] = capital

    # Credit quality
    credit = {}
    if "npl_ratio" in cq:
        credit["npl_ratio"] = cq["npl_ratio"]
    entry["credit_quality"] = credit

    return entry


# ---------------------------------------------------------------------------
# Main extractor
# ---------------------------------------------------------------------------

def extrair_supplement_ubs(pasta_docs: str, pasta_destino: str) -> list[dict]:
    """Extrai dados de todos os UBS Group Quarterly Full Report PDFs.

    Args:
        pasta_docs: Caminho para pasta com os PDFs (full-report-*.pdf)
        pasta_destino: Caminho para pasta de destino do JSON

    Returns:
        Lista de dicionários com dados extraídos por trimestre.
    """
    pdfs = sorted(glob.glob(os.path.join(pasta_docs, "full-report-*.pdf")))
    if not pdfs:
        print(f"[WARN] Nenhum PDF encontrado em {pasta_docs}")
        return []

    all_quarters = {}  # periodo -> entry

    for pdf_path in pdfs:
        fname = os.path.basename(pdf_path)
        print(f"  Processando {fname}...")

        try:
            doc = fitz.open(pdf_path)
        except Exception as e:
            print(f"    [ERRO] Não conseguiu abrir: {e}")
            continue

        page_num = _find_key_figures_page(doc)
        if page_num is None:
            print(f"    [WARN] Página de key figures não encontrada")
            doc.close()
            continue

        raw_entries = _extract_key_figures(doc, page_num)

        # Enrich with division-level metrics (NIM, deposits, loans) from USD pages
        # Aggregate Wealth Management + P&CB customer deposits/loans for total
        division_pages = _find_division_pages_usd(doc)
        agg_metrics = {}  # Per quarter aggregation
        for div_pg in division_pages:
            metrics = _extract_division_metrics(doc, div_pg)
            # Apply only to current quarter (first entry which is the latest)
            if metrics and raw_entries:
                # Use the highest NIM/largest deposits as a proxy for the bank-level number
                for k, v in metrics.items():
                    if k in agg_metrics:
                        if k.startswith(("customer_deposits", "loans_gross", "depositos", "loans")):
                            agg_metrics[k] += v  # sum across divisions
                        # NIM: keep first occurrence (Wealth Management's)
                    else:
                        agg_metrics[k] = v
        if agg_metrics and raw_entries:
            # Apply to first entry (most recent quarter)
            raw_entries[0]["division_metrics"] = agg_metrics

        doc.close()

        for raw in raw_entries:
            per = raw["periodo"]
            entry = _build_supplement_entry(raw)
            # Keep the most recent extraction (later PDFs have updated data)
            if per not in all_quarters:
                all_quarters[per] = entry
                print(f"    {raw['trimestre']}: Rev={raw['income_statement'].get('total_revenues', 'N/A')}  "
                      f"CET1={raw['capital'].get('cet1_ratio', 'N/A')}  "
                      f"LCR={raw['capital'].get('lcr', 'N/A')}  "
                      f"NSFR={raw['capital'].get('nsfr', 'N/A')}")

    resultados = sorted(all_quarters.values(), key=lambda x: x["periodo"])

    # Enriquecer com cronograma de dívida do 20-F
    f20_path = os.path.join(pasta_docs, "ubs-20-F-2025.htm")
    if os.path.exists(f20_path):
        cronograma = extrair_cronograma_divida_ubs(f20_path)
        if cronograma:
            data_ref = cronograma["data_referencia"]
            for entry in resultados:
                if entry.get("periodo") == data_ref:
                    entry["cronograma_divida"] = cronograma
                    print(f"  Cronograma de divida adicionado a {data_ref}")
                    break

    # Save
    os.makedirs(pasta_destino, exist_ok=True)
    out_path = os.path.join(pasta_destino, "supplement_data.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(resultados, f, indent=2, ensure_ascii=False)

    print(f"\n  Salvo {len(resultados)} trimestres em {out_path}")
    return resultados


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    pasta_docs = sys.argv[1] if len(sys.argv) > 1 else "G:/Meu Drive/Análise de Crédito Financeiras/UBS/Documentos"
    pasta_destino = sys.argv[2] if len(sys.argv) > 2 else "G:/Meu Drive/Análise de Crédito Financeiras/UBS/Dados_EDGAR"

    dados = extrair_supplement_ubs(pasta_docs, pasta_destino)
