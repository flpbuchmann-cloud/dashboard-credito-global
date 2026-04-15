"""
Extrator de Financial Supplement PDFs do BNY Mellon.

Lê os PDFs de suplementos financeiros trimestrais e extrai dados estruturados
de Average Balances, Capital/Liquidity e Credit Quality para JSON.
"""

import os
import re
import json
import glob
from pathlib import Path


# ---------------------------------------------------------------------------
# Utilidades de parsing
# ---------------------------------------------------------------------------

def _parse_number(text: str) -> float | None:
    """Converte texto numérico (ex: '97,489', '(5)', '—') em float.
    Retorna None se não conseguir parsear ou se o texto for vazio/irrelevante.
    Parênteses indicam valor negativo. Traço ou '—' indica zero.
    """
    text = text.strip().replace("$", "").replace("%", "").strip()
    # Remove footnote markers like (a), (b), (c)
    text = re.sub(r'\([a-z]\)', '', text).strip()
    if not text:
        return None  # Empty after stripping $ and % -> skip
    if text in ("\u2014", "\u2013", "\u2015", "—", "–", "―", "\ufffd"):
        return 0.0
    negative = False
    if text.startswith("(") and text.endswith(")"):
        negative = True
        text = text[1:-1].strip()
    text = text.replace(",", "").replace(" ", "")
    if not text:
        return None
    try:
        val = float(text)
        return -val if negative else val
    except ValueError:
        return None


def _quarter_to_date(quarter_str: str) -> str:
    """Converte '4Q25' -> '2025-12-31', '1Q22' -> '2022-03-31', etc."""
    m = re.match(r"(\d)Q(\d{2})", quarter_str)
    if not m:
        return quarter_str
    q = int(m.group(1))
    yr = 2000 + int(m.group(2))
    end_dates = {1: "03-31", 2: "06-30", 3: "09-30", 4: "12-31"}
    return f"{yr}-{end_dates[q]}"


def _filename_to_quarter(filename: str) -> str:
    """Extrai trimestre do nome do arquivo.
    Ex: 'financial-supplement-4q-2025.pdf' -> '4Q25'
    """
    m = re.search(r"(\d)q[_-](\d{4})", filename, re.IGNORECASE)
    if m:
        q = m.group(1)
        yr = m.group(2)[2:]
        return f"{q}Q{yr}"
    return ""


def _find_page(doc, keyword: str) -> int | None:
    """Encontra página pelo conteúdo (ignora TOC nas primeiras páginas)."""
    for i in range(2, len(doc)):  # Pula capa e TOC
        text = doc[i].get_text()
        if keyword in text:
            return i
    return None


def _extract_first_col_value(lines: list[str], start_idx: int) -> float | None:
    """A partir de um índice de linha de label, busca o primeiro valor numérico
    na(s) linha(s) seguinte(s) que corresponde à primeira coluna de dados."""
    for offset in range(1, 12):
        idx = start_idx + offset
        if idx >= len(lines):
            break
        line = lines[idx].strip()
        # Skip empty lines and lone currency/percent symbols
        if not line or line.replace("$", "").replace("%", "").strip() == "":
            continue
        # Stop if we hit another text label (not a number line)
        if re.match(r'^[A-Z][a-z]', line) and len(line) > 5:
            break
        # Try to parse as number
        val = _parse_number(line)
        if val is not None:
            return val
    return None


def _extract_data_row(text_block: str, label_pattern: str,
                      expect_rate: bool = False) -> tuple[float | None, float | None]:
    """Extrai (balance, rate) de uma linha de dados da tabela Avg Balances.

    O formato PyMuPDF tipicamente gera linhas como:
        Label
        $ 97,489
         3.38%
        $ 94,533
        ...

    Retorna (primeiro_valor, segundo_valor) onde segundo_valor é a rate se expect_rate=True.
    """
    lines = text_block.split("\n")
    balance = None
    rate = None

    # Find the label line
    label_idx = None
    for i, line in enumerate(lines):
        if re.search(label_pattern, line.strip(), re.IGNORECASE):
            label_idx = i
            break

    if label_idx is None:
        return (None, None)

    # Collect values after the label - first two numeric values are balance and rate
    values_found = []
    for offset in range(1, 20):
        idx = label_idx + offset
        if idx >= len(lines):
            break
        line = lines[idx].strip()
        if not line:
            continue
        # Skip lone $ or % symbols
        if line.replace("$", "").replace("%", "").strip() == "":
            continue
        # Stop if we hit another label (a line that starts with a letter and isn't just a footnote)
        if (re.match(r'^[A-Z][a-z]', line) and
                not line.startswith("$") and
                len(line) > 3 and
                not re.match(r'^\(\w\)', line)):
            break
        # Try to extract number
        val = _parse_number(line)
        if val is not None:
            values_found.append(val)
            if len(values_found) >= 2:
                break

    if values_found:
        balance = values_found[0]
    if expect_rate and len(values_found) >= 2:
        rate = values_found[1]

    return (balance, rate)


# ---------------------------------------------------------------------------
# Extração por seção
# ---------------------------------------------------------------------------

def _parse_avg_balances(doc, page_idx: int) -> dict:
    """Parse Average Balances and Interest Rates page."""
    text = doc[page_idx].get_text()
    lines = text.split("\n")
    result = {"avg_balances": {}, "yields_rates": {}}

    # Helper: find label and extract first two numeric values (balance, rate)
    def get_row(pattern: str, need_rate: bool = True):
        bal, rate = _extract_data_row(text, pattern, expect_rate=need_rate)
        return bal, rate

    # Total interest-earning assets
    bal, rate = get_row(r"^Total interest-earning assets")
    result["avg_balances"]["avg_earning_assets"] = bal
    result["yields_rates"]["avg_earning_assets_yield"] = rate / 100 if rate else None

    # Total assets
    # Find "Total assets" line (not "Total interest-earning assets")
    total_assets_bal = None
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped == "Total assets" or stripped.startswith("Total assets"):
            if "interest" not in stripped.lower():
                total_assets_bal = _extract_first_col_value(lines, i)
                break
    result["avg_balances"]["avg_total_assets"] = total_assets_bal

    # Loans - either standalone "Loans" or need to sum Margin + Non-margin
    has_margin_loans = any("Margin loans" in l and "Non-margin" not in l
                          for l in lines)
    if has_margin_loans:
        margin_bal, margin_rate = get_row(r"^Margin loans$")
        non_margin_bal, non_margin_rate = get_row(r"^Total non-margin loans$")
        if margin_bal is not None and non_margin_bal is not None:
            total_loans = margin_bal + non_margin_bal
            # Weighted average rate
            if margin_rate is not None and non_margin_rate is not None:
                loans_rate = (margin_bal * margin_rate + non_margin_bal * non_margin_rate) / total_loans if total_loans else 0
            else:
                loans_rate = None
        else:
            total_loans = margin_bal or non_margin_bal
            loans_rate = margin_rate or non_margin_rate
        result["avg_balances"]["avg_loans"] = total_loans
        result["yields_rates"]["avg_loans_yield"] = loans_rate / 100 if loans_rate else None
    else:
        bal, rate = get_row(r"^Loans$")
        result["avg_balances"]["avg_loans"] = bal
        result["yields_rates"]["avg_loans_yield"] = rate / 100 if rate else None

    # Interest-bearing deposits
    bal, rate = get_row(r"^Total interest-bearing deposits$")
    if bal is None:
        # Some PDFs might use slightly different label
        bal, rate = get_row(r"^Interest-bearing deposits$")
    result["avg_balances"]["avg_ib_deposits"] = bal
    result["yields_rates"]["avg_ib_deposits_rate"] = rate / 100 if rate else None

    # Noninterest-bearing deposits
    nib_bal = None
    for i, line in enumerate(lines):
        if re.search(r"Total noninterest-bearing deposits", line.strip(), re.IGNORECASE):
            nib_bal = _extract_first_col_value(lines, i)
            break
    result["avg_balances"]["avg_nib_deposits"] = nib_bal

    # Total deposits = IB + NIB
    if bal is not None and nib_bal is not None:
        result["avg_balances"]["avg_total_deposits"] = bal + nib_bal
    else:
        result["avg_balances"]["avg_total_deposits"] = None

    # Total interest-bearing liabilities
    bal_ib, rate_ib = get_row(r"^Total interest-bearing liabilities$")
    result["avg_balances"]["avg_total_ib_liabilities"] = bal_ib
    result["yields_rates"]["avg_total_ib_liabilities_rate"] = rate_ib / 100 if rate_ib else None

    # Net interest margin
    nim_val = None
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped == "Net interest margin" or (
            stripped.startswith("Net interest margin") and "FTE" not in stripped and "Non-GAAP" not in stripped
        ):
            nim_val = _extract_first_col_value(lines, i)
            break
    result["yields_rates"]["nim"] = nim_val / 100 if nim_val else None

    # Interest spread = earning assets yield - IB liabilities rate
    ea_yield = result["yields_rates"].get("avg_earning_assets_yield")
    ib_rate = result["yields_rates"].get("avg_total_ib_liabilities_rate")
    if ea_yield is not None and ib_rate is not None:
        result["yields_rates"]["interest_spread"] = round(ea_yield - ib_rate, 6)
    else:
        result["yields_rates"]["interest_spread"] = None

    return result


def _parse_capital(doc, page_idx: int) -> dict:
    """Parse Capital and Liquidity page."""
    text = doc[page_idx].get_text()
    lines = text.split("\n")
    result = {}

    # We need data from Standardized Approach section (first occurrence)
    # Find "Standardized Approach:" then parse CET1, Tier 1, RWA, ratios

    std_start = None
    adv_start = None
    for i, line in enumerate(lines):
        if "Standardized Approach" in line:
            std_start = i
        if "Advanced Approach" in line:
            adv_start = i
            break

    if std_start is None:
        return result

    # Work within Standardized section only
    end_idx = adv_start if adv_start else len(lines)
    section_lines = lines[std_start:end_idx]

    def find_first_value(pattern, section=section_lines):
        for i, line in enumerate(section):
            if re.search(pattern, line.strip(), re.IGNORECASE):
                for off in range(1, 8):
                    idx = i + off
                    if idx >= len(section):
                        break
                    val = _parse_number(section[idx].strip())
                    if val is not None:
                        return val
        return None

    result["cet1_capital"] = find_first_value(r"^CET1 capital$")
    result["tier1_capital"] = find_first_value(r"^Tier 1 capital$")
    result["rwa_standardized"] = find_first_value(r"^Risk-weighted assets$")

    result["cet1_ratio"] = None
    cet1_pct = find_first_value(r"^CET1 ratio$")
    if cet1_pct is not None:
        result["cet1_ratio"] = round(cet1_pct / 100, 6)

    # SLR - find "SLR:" section header, then find the "SLR" value row after "Leverage exposure"
    slr_val = None
    for i, line in enumerate(lines):
        stripped = line.strip()
        if re.match(r"^SLR\b", stripped) and ":" in stripped:
            # Found section header; look for the SLR value row
            for j in range(i + 1, min(i + 20, len(lines))):
                if lines[j].strip() == "SLR":
                    slr_val = _extract_first_col_value(lines, j)
                    break
            break

    result["slr"] = round(slr_val / 100, 6) if slr_val else None

    # LCR
    lcr_val = None
    for i, line in enumerate(lines):
        if re.search(r"Average liquidity coverage ratio", line.strip(), re.IGNORECASE):
            lcr_val = _extract_first_col_value(lines, i)
            break
    result["lcr"] = round(lcr_val / 100, 4) if lcr_val else None

    # NSFR
    nsfr_val = None
    for i, line in enumerate(lines):
        if re.search(r"Average net stable funding ratio", line.strip(), re.IGNORECASE):
            nsfr_val = _extract_first_col_value(lines, i)
            break
    result["nsfr"] = round(nsfr_val / 100, 4) if nsfr_val else None

    return result


def _parse_credit_quality(doc, page_idx: int) -> dict:
    """Parse Allowance for Credit Losses and Nonperforming Assets page."""
    text = doc[page_idx].get_text()
    lines = text.split("\n")
    result = {}

    def find_first_value(pattern):
        for i, line in enumerate(lines):
            if re.search(pattern, line.strip(), re.IGNORECASE):
                for off in range(1, 8):
                    idx = i + off
                    if idx >= len(lines):
                        break
                    raw = lines[idx].strip()
                    if not raw:
                        continue
                    val = _parse_number(raw)
                    if val is not None:
                        return val
        return None

    # Total net recoveries (charge-offs) or Total net (charge-offs) recoveries
    result["nco_total"] = find_first_value(
        r"^Total net (recoveries|charge-offs|\(charge-offs\))"
    )

    # Nonperforming assets
    result["npa"] = find_first_value(r"^Nonperforming assets$")

    # Allowance for loan losses - end of period
    # Need to find the SECOND occurrence (end of period section)
    acl_loans = None
    eop_section = False
    for i, line in enumerate(lines):
        stripped = line.strip()
        if "end of period:" in stripped.lower():
            eop_section = True
            continue
        if eop_section and re.match(r"^Allowance for loan losses$", stripped):
            acl_loans = _extract_first_col_value(lines, i)
            break
    result["acl_loans"] = acl_loans

    # Allowance for credit losses - end of period (total)
    # Find the second "Allowance for credit losses" that ends with "end of period" after the EOP section
    acl_total = None
    eop_count = 0
    for i, line in enumerate(lines):
        stripped = line.strip()
        if re.search(r"Allowance for credit losses.*end of period$", stripped, re.IGNORECASE):
            eop_count += 1
            if eop_count >= 3:  # Third occurrence: the total at end of EOP section
                acl_total = _extract_first_col_value(lines, i)
                break
            if eop_count == 2:
                # Check - might be the total at end of second section
                val = _extract_first_col_value(lines, i)
                # We want the one that matches acl_loans + commitments + other
                acl_total = val

    # Alternative approach: find last "$" value after "Allowance for credit losses" end of period section
    if acl_total is None:
        for i, line in enumerate(lines):
            if re.search(r"^Allowance for credit losses.*end of period$", line.strip(), re.IGNORECASE):
                if eop_section:
                    acl_total = _extract_first_col_value(lines, i)

    result["acl_total"] = acl_total

    # Allowance for loan losses as a percentage of total loans
    acl_pct = find_first_value(r"Allowance for loan losses as a percentage")
    result["acl_pct_loans"] = round(acl_pct / 100, 6) if acl_pct else None

    return result


# ---------------------------------------------------------------------------
# Função principal
# ---------------------------------------------------------------------------

def extrair_supplement_banco(pasta_docs: str, pasta_destino: str) -> list[dict]:
    """Extrai dados de todos os Financial Supplement PDFs do BNY Mellon.

    Args:
        pasta_docs: Caminho para pasta com os PDFs (financial-supplement-*.pdf)
        pasta_destino: Caminho para pasta de destino do JSON

    Returns:
        Lista de dicionários com dados extraídos por trimestre.
    """
    import fitz  # PyMuPDF

    pdfs = sorted(glob.glob(os.path.join(pasta_docs, "financial-supplement-*.pdf")))
    if not pdfs:
        print(f"[WARN] Nenhum PDF encontrado em {pasta_docs}")
        return []

    resultados = []

    for pdf_path in pdfs:
        fname = os.path.basename(pdf_path)
        trimestre = _filename_to_quarter(fname)
        periodo = _quarter_to_date(trimestre)

        print(f"  Processando {fname} ({trimestre})...")

        try:
            doc = fitz.open(pdf_path)
        except Exception as e:
            print(f"    [ERRO] Não conseguiu abrir: {e}")
            continue

        # Find pages by content
        pg_avg = _find_page(doc, "AVERAGE BALANCES AND INTEREST RATES")
        pg_cap = _find_page(doc, "CAPITAL AND LIQUIDITY")
        pg_cred = _find_page(doc, "ALLOWANCE FOR CREDIT LOSSES AND NONPERFORMING ASSETS")

        entry = {
            "periodo": periodo,
            "trimestre": trimestre,
            "fonte": fname,
        }

        # Average Balances
        if pg_avg is not None:
            avg_data = _parse_avg_balances(doc, pg_avg)
            entry["avg_balances"] = avg_data.get("avg_balances", {})
            entry["yields_rates"] = avg_data.get("yields_rates", {})
        else:
            print(f"    [WARN] Página 'Average Balances' não encontrada")
            entry["avg_balances"] = {}
            entry["yields_rates"] = {}

        # Capital and Liquidity
        if pg_cap is not None:
            entry["capital"] = _parse_capital(doc, pg_cap)
        else:
            print(f"    [WARN] Página 'Capital and Liquidity' não encontrada")
            entry["capital"] = {}

        # Credit Quality
        if pg_cred is not None:
            entry["credit_quality"] = _parse_credit_quality(doc, pg_cred)
        else:
            print(f"    [WARN] Página 'Allowance/Credit Losses' não encontrada")
            entry["credit_quality"] = {}

        doc.close()
        resultados.append(entry)

    # Sort by period
    resultados.sort(key=lambda x: x["periodo"])

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

    pasta_docs = sys.argv[1] if len(sys.argv) > 1 else "G:/Meu Drive/Análise de Crédito Financeiras/BK/Documentos"
    pasta_destino = sys.argv[2] if len(sys.argv) > 2 else "G:/Meu Drive/Análise de Crédito Financeiras/BK/Dados_EDGAR"

    dados = extrair_supplement_banco(pasta_docs, pasta_destino)

    if dados:
        print("\n=== Últimos 3 trimestres ===")
        for entry in dados[-3:]:
            print(json.dumps(entry, indent=2, ensure_ascii=False))
