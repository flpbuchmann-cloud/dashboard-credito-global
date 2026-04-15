"""
Extrator de Results Announcement PDFs do Barclays PLC.

Lê os PDFs trimestrais de Results Announcements e extrai dados estruturados
(P&L, Capital, Liquidity, NIM) convertendo de GBP para USD.

Fonte principal: página "Quarterly Results Summary" presente em todos os PDFs.
Fonte complementar: página "Margins and Balances" para NIM.
"""

import os
import re
import json
import glob
from pathlib import Path

import pdfplumber

# ---------------------------------------------------------------------------
# FX rates (approximate quarterly averages GBP/USD)
# ---------------------------------------------------------------------------

GBPUSD = {
    "2021-03-31": 1.38, "2021-06-30": 1.40, "2021-09-30": 1.37, "2021-12-31": 1.35,
    "2022-03-31": 1.34, "2022-06-30": 1.26, "2022-09-30": 1.17, "2022-12-31": 1.21,
    "2023-03-31": 1.22, "2023-06-30": 1.26, "2023-09-30": 1.26, "2023-12-31": 1.27,
    "2024-03-31": 1.27, "2024-06-30": 1.27, "2024-09-30": 1.30, "2024-12-31": 1.26,
    "2025-03-31": 1.29, "2025-06-30": 1.33, "2025-09-30": 1.32, "2025-12-31": 1.26,
}


# ---------------------------------------------------------------------------
# Utilidades de parsing
# ---------------------------------------------------------------------------

def _parse_number(text: str) -> float | None:
    """Converte texto numérico para float. Parênteses = negativo. Traço = 0."""
    text = text.strip().replace("£", "").replace("%", "").replace("$", "").strip()
    # Remove footnote markers like superscript numbers
    text = re.sub(r'[¹²³⁴⁵⁶⁷⁸⁹⁰]', '', text)
    text = re.sub(r'\([a-z]\)', '', text).strip()
    if not text:
        return None
    if text in ("\u2014", "\u2013", "\u2015", "—", "–", "―", "\ufffd", "-", "�"):
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


def _quarter_label_to_date(label: str) -> str | None:
    """Converte 'Q425' -> '2025-12-31', 'Q121' -> '2021-03-31', etc."""
    m = re.match(r"Q(\d)(\d{2})", label)
    if not m:
        return None
    q = int(m.group(1))
    yr = 2000 + int(m.group(2))
    end_dates = {1: "03-31", 2: "06-30", 3: "09-30", 4: "12-31"}
    return f"{yr}-{end_dates.get(q, '12-31')}"


def _date_to_trimestre(date_str: str) -> str:
    """'2025-12-31' -> '4Q25'"""
    parts = date_str.split("-")
    yr = int(parts[0]) % 100
    month = int(parts[1])
    q_map = {3: 1, 6: 2, 9: 3, 12: 4}
    q = q_map.get(month, 4)
    return f"{q}Q{yr:02d}"


def _get_fx(date_str: str) -> float:
    """Retorna taxa GBP/USD para o período."""
    return GBPUSD.get(date_str, 1.27)  # fallback


def _file_period(filename: str) -> tuple[str, str]:
    """Extrai período e tipo do nome do arquivo.
    Ex: 'results-announcement-FY-2025.pdf' -> ('FY', '2025')
        'results-announcement-Q1-2021.pdf' -> ('Q1', '2021')
    """
    m = re.search(r"results-announcement-(FY|H1|Q1|Q3)-(\d{4})\.pdf", filename)
    if m:
        return m.group(1), m.group(2)
    return ("", "")


# ---------------------------------------------------------------------------
# Quarterly Results Summary parser
# ---------------------------------------------------------------------------

def _find_quarterly_results_page(pdf) -> str | None:
    """Encontra a página 'Quarterly Results Summary' com dados tabulares."""
    for page in pdf.pages:
        text = page.extract_text() or ""
        if "quarterly results summary" in text.lower() and "total income" in text.lower():
            return text
    return None


def _parse_quarterly_columns(text: str) -> dict[str, dict]:
    """
    Parseia a página Quarterly Results Summary.
    Retorna dict {quarter_label: {field: value}} ex: {'Q425': {'nii': 3734, ...}}
    """
    lines = text.split("\n")

    # Find the header line with quarter labels (e.g., Q425 Q325 Q225 ...)
    quarter_labels = []
    header_line_idx = None
    for idx, line in enumerate(lines):
        # Look for line with multiple Q\d\d\d patterns
        labels = re.findall(r"Q\d\d\d", line)
        if len(labels) >= 4:
            quarter_labels = labels
            header_line_idx = idx
            break

    if not quarter_labels:
        return {}

    n_cols = len(quarter_labels)
    result = {ql: {} for ql in quarter_labels}

    # Define field mappings: (regex_pattern, output_key, is_percentage)
    field_patterns = [
        (r"^Net interest income", "nii", False),
        (r"^Total income", "total_income", False),
        (r"^Total operating expenses", "total_opex", False),
        (r"^Credit impairment", "credit_impairment", False),
        (r"^Profit before tax", "profit_before_tax", False),
        (r"^Attributable profit", "net_income", False),
        (r"^Return on average tangible", "rote", True),
        (r"^Cost[:\s]*income ratio", "efficiency_ratio", True),
        (r"^Loan loss rate", "loan_loss_rate_bps", True),
        (r"^Common equity tier 1 ratio", "cet1_ratio", True),
        (r"^Common equity tier 1 capital", "cet1_capital", False),
        (r"^Risk weighted assets", "rwa", False),
        (r"^(?:UK )?[Ll]everage ratio", "leverage_ratio", True),
        (r"^(?:UK )?[Ll]everage exposure", "leverage_exposure", False),
        (r"^Liquidity coverage ratio", "lcr", True),
        (r"^Net stable funding ratio", "nsfr", True),
        (r"^Deposits at amortised cost", "deposits", False),
        (r"^Loans and advances at amortised cost(?!\s+impairment)", "loans", False),
        (r"^Total assets", "total_assets", False),
        (r"^Loan[:\s]*deposit ratio", "loan_deposit_ratio", True),
        (r"^Group liquidity pool", "liquidity_pool", False),
        (r"^Operating costs", "operating_costs", False),
    ]

    # Parse data lines after header
    for line in lines[header_line_idx + 1:]:
        line_stripped = line.strip()
        if not line_stripped:
            continue

        for pattern, key, is_pct in field_patterns:
            if re.search(pattern, line_stripped, re.IGNORECASE):
                # Extract numbers from the line
                # Strategy: remove the label text, then parse remaining numbers
                # Numbers can be: 3,734  (535)  14.3%  170.0%  48  (0.9)%

                # Find where the label ends and numbers begin
                # Use a robust approach: find all number-like tokens
                if is_pct:
                    # For percentages, look for patterns like 14.3% or 14.3 or (0.9)% or 48
                    tokens = re.findall(
                        r'\([\d.]+\)[%p]?|[\d,]+\.?\d*[%p]?|\([\d,.]+\)',
                        line_stripped
                    )
                else:
                    # For monetary values in £m or £bn
                    tokens = re.findall(
                        r'\([\d,]+(?:\.\d+)?\)|[\d,]+(?:\.\d+)?',
                        line_stripped
                    )

                # Filter out numbers that are part of the label (like "tier 1")
                # Take the last n_cols tokens as the column values
                if len(tokens) >= n_cols:
                    values = tokens[-n_cols:]
                    for i, ql in enumerate(quarter_labels):
                        val = _parse_number(values[i])
                        if val is not None:
                            result[ql][key] = val
                elif len(tokens) > 0 and len(tokens) < n_cols:
                    # Partial data (some columns might have dashes rendered as empty)
                    # Try to align from the right
                    offset = n_cols - len(tokens)
                    for i, token in enumerate(tokens):
                        val = _parse_number(token)
                        if val is not None:
                            result[quarter_labels[i + offset]][key] = val
                break

    return result


# ---------------------------------------------------------------------------
# Margins and Balances parser (for NIM)
# ---------------------------------------------------------------------------

def _find_margins_pages(pdf) -> list[str]:
    """Encontra páginas de Margins and Balances (pode ser multi-página).
    Pula Table of Contents e busca a página real com dados de NIM."""
    texts = []
    collecting = False
    for page in pdf.pages:
        text = page.extract_text() or ""
        lower = text.lower()
        # Skip Table of Contents pages
        if "table of contents" in lower:
            continue
        if "margins and balances" in lower:
            collecting = True
            texts.append(text)
        elif collecting and ("quarterly analysis" in lower or
                            "total barclays uk" in lower or
                            "group excluding" in lower):
            texts.append(text)
        elif collecting:
            break
    return texts


def _date_str_to_quarter_label(date_str: str) -> str | None:
    """Converte '31.12.21' ou '31.03.21' -> 'Q421' ou 'Q121'."""
    m = re.match(r"(\d{2})\.(\d{2})\.(\d{2})", date_str)
    if not m:
        return None
    day, month, yr = m.groups()
    q_map = {"03": "1", "06": "2", "09": "3", "12": "4"}
    q = q_map.get(month)
    if not q:
        return None
    return f"Q{q}{yr}"


def _parse_nim_from_margins(texts: list[str]) -> dict[str, float]:
    """
    Extrai NIM do Grupo das páginas de Margins and Balances.
    Retorna {quarter_label: nim_value}.

    Handles two formats:
    - 2024+: Columnar format with Q425 Q325 etc. headers and "Group excluding IB"
    - 2021-2023: Vertical format with "Three months ended DD.MM.YY" per quarter
    """
    result = {}
    full_text = "\n".join(texts)
    lines = full_text.split("\n")

    # --- Format 1: Columnar (2024+) ---
    # Look for quarter headers then "Group excluding IB" NIM row
    quarter_headers = []
    nim_section = False
    for idx, line in enumerate(lines):
        lower = line.lower().strip()

        # Detect quarterly headers (e.g., "Q425 Q325 Q225 Q125 Q424")
        qlabels = re.findall(r"Q\d\d\d", line)
        if len(qlabels) >= 2:
            quarter_headers = qlabels

        # Look for "Net interest margin" section header
        if "net interest margin" in lower and "%" in lower:
            nim_section = True
            continue

        # In NIM section, look for group total line
        if nim_section and ("group excluding" in lower or
                           "total barclays uk and barclays international" in lower):
            pcts = re.findall(r'[\d]+\.[\d]+', line)
            if pcts and quarter_headers:
                for i, ql in enumerate(quarter_headers[:len(pcts)]):
                    try:
                        result[ql] = float(pcts[i]) / 100.0
                    except (ValueError, IndexError):
                        pass
            nim_section = False

        # Also try direct columnar match without separate NIM header
        if not nim_section and quarter_headers and (
            "group excluding" in lower or
            "total barclays uk and barclays international" in lower
        ):
            pcts = re.findall(r'[\d]+\.[\d]+', line)
            if len(pcts) >= len(quarter_headers):
                # This could be NIM or NII or assets -- only take if values look like NIM (1-12%)
                potential_nims = [float(p) for p in pcts[-len(quarter_headers):]]
                if all(0.5 < v < 15.0 for v in potential_nims):
                    for i, ql in enumerate(quarter_headers):
                        result[ql] = potential_nims[i] / 100.0

    # --- Format 2: Vertical (2021-2023) ---
    # "Three months ended DD.MM.YY" followed by segment lines with NIM
    if not result:
        current_quarter = None
        for idx, line in enumerate(lines):
            # Detect quarter header
            m = re.search(r"Three months ended (\d{2}\.\d{2}\.\d{2})", line)
            if m:
                current_quarter = _date_str_to_quarter_label(m.group(1))
                continue

            if current_quarter:
                lower = line.lower().strip()
                if "total barclays uk and barclays international" in lower or "group excluding" in lower:
                    pcts = re.findall(r'[\d]+\.[\d]+', line)
                    if pcts:
                        # Last value is typically the NIM
                        nim_val = float(pcts[-1])
                        if 0.5 < nim_val < 15.0:
                            result[current_quarter] = nim_val / 100.0
                    current_quarter = None

    return result


# ---------------------------------------------------------------------------
# Main extraction
# ---------------------------------------------------------------------------

def _build_record(quarter_label: str, data: dict, nim: float | None,
                  filename: str) -> dict:
    """Monta o registro de um trimestre no formato padrão."""
    date_str = _quarter_label_to_date(quarter_label)
    if not date_str:
        return {}

    fx = _get_fx(date_str)
    trimestre = _date_to_trimestre(date_str)

    def to_usd_m(val_gbp_m):
        """Converte £m para $m."""
        if val_gbp_m is None:
            return None
        return round(val_gbp_m * fx, 1)

    def to_usd_bn(val_gbp_bn):
        """Converte £bn para $m."""
        if val_gbp_bn is None:
            return None
        return round(val_gbp_bn * fx * 1000, 1)

    def to_ratio(val_pct):
        """Converte percentual para ratio (14.3 -> 0.143, 0.9 -> 0.009).
        Todos os valores vêm como percentuais inteiros do PDF (ex: 14.3%, 0.9%)."""
        if val_pct is None:
            return None
        return round(val_pct / 100.0, 6)

    # P&L items (in £m in the source)
    nii = data.get("nii")
    total_income = data.get("total_income")
    total_opex = data.get("total_opex")
    credit_imp = data.get("credit_impairment")
    pbt = data.get("profit_before_tax")
    net_income = data.get("net_income")
    operating_costs = data.get("operating_costs")

    # Capital items (£bn in source for CET1 capital, RWA; % for ratios)
    cet1_ratio = data.get("cet1_ratio")
    cet1_capital = data.get("cet1_capital")
    rwa = data.get("rwa")
    leverage_ratio = data.get("leverage_ratio")
    lcr = data.get("lcr")
    nsfr = data.get("nsfr")

    # Balance sheet (£bn in source)
    deposits = data.get("deposits")
    loans = data.get("loans")
    total_assets = data.get("total_assets")

    # Performance measures
    rote = data.get("rote")
    efficiency = data.get("efficiency_ratio")
    llr_bps = data.get("loan_loss_rate_bps")

    record = {
        "periodo": date_str,
        "trimestre": trimestre,
        "moeda_original": "GBP",
        "fx_rate": fx,
        "fonte": filename,
        "income_statement": {
            "total_income": to_usd_m(total_income),
            "nii": to_usd_m(nii),
            "operating_costs": to_usd_m(operating_costs),
            "total_opex": to_usd_m(total_opex),
            "credit_impairment": to_usd_m(credit_imp),
            "profit_before_tax": to_usd_m(pbt),
            "net_income": to_usd_m(net_income),
        },
        "avg_balances": {
            "avg_customer_deposits": to_usd_bn(deposits),
            "avg_customer_loans": to_usd_bn(loans),
            "avg_total_assets": to_usd_bn(total_assets),
        },
        "yields_rates": {
            "nim": nim,
            "rote": to_ratio(rote),
            "efficiency_ratio": to_ratio(efficiency),
            "loan_loss_rate": round(llr_bps / 10000.0, 6) if llr_bps is not None else None,
        },
        "capital": {
            "cet1_ratio": to_ratio(cet1_ratio),
            "cet1_capital": to_usd_bn(cet1_capital),
            "rwa_standardized": to_usd_bn(rwa),
            "leverage_ratio": to_ratio(leverage_ratio),
            "lcr": to_ratio(lcr),
            "nsfr": to_ratio(nsfr),
        },
        "credit_quality": {
            "loan_loss_rate_bps": llr_bps,
        },
    }

    return record


def extrair_supplement_barclays(pasta_docs: str, pasta_destino: str) -> list[dict]:
    """
    Extrai dados dos Results Announcement PDFs do Barclays.

    Estratégia: cada PDF contém uma página "Quarterly Results Summary" com
    dados de 8 trimestres. Processamos todos os PDFs e consolidamos,
    usando a fonte mais recente para cada trimestre (pois terá dados revisados).

    Args:
        pasta_docs: Caminho para a pasta com os PDFs
        pasta_destino: Caminho para salvar o JSON de saída

    Returns:
        Lista de dicts com dados trimestrais
    """
    pdf_files = sorted(glob.glob(os.path.join(pasta_docs, "results-announcement-*.pdf")))

    if not pdf_files:
        print(f"[WARN] Nenhum PDF encontrado em {pasta_docs}")
        return []

    print(f"[INFO] Encontrados {len(pdf_files)} PDFs de Barclays Results Announcements")

    # Collect all quarterly data, keyed by quarter label
    # Later files override earlier ones (more recent = revised data)
    all_quarters: dict[str, dict] = {}  # {quarter_label: {field: value}}
    all_nim: dict[str, float] = {}  # {quarter_label: nim}
    quarter_source: dict[str, str] = {}  # {quarter_label: filename}

    for pdf_path in pdf_files:
        filename = os.path.basename(pdf_path)
        period_type, year = _file_period(filename)

        print(f"  Processando {filename} ({period_type} {year})...")

        try:
            pdf = pdfplumber.open(pdf_path)
        except Exception as e:
            print(f"    [ERRO] Não foi possível abrir: {e}")
            continue

        # 1. Parse Quarterly Results Summary
        qrs_text = _find_quarterly_results_page(pdf)
        if qrs_text:
            quarters_data = _parse_quarterly_columns(qrs_text)
            for ql, data in quarters_data.items():
                if data:  # Only override if we got actual data
                    all_quarters[ql] = data
                    quarter_source[ql] = filename
        else:
            print(f"    [WARN] Quarterly Results Summary não encontrada")

        # 2. Parse Margins and Balances for NIM
        margins_texts = _find_margins_pages(pdf)
        if margins_texts:
            nim_data = _parse_nim_from_margins(margins_texts)
            all_nim.update(nim_data)

        pdf.close()

    # Build final records
    # Determine which quarters we want (Q1-2021 to latest available)
    target_quarters = []
    for yr in range(2021, 2027):
        for q in range(1, 5):
            ql = f"Q{q}{yr % 100:02d}"
            if ql in all_quarters:
                target_quarters.append(ql)

    records = []
    for ql in target_quarters:
        data = all_quarters[ql]
        nim = all_nim.get(ql)
        filename = quarter_source.get(ql, "unknown")

        record = _build_record(ql, data, nim, filename)
        if record:
            records.append(record)

    # Sort by period
    records.sort(key=lambda r: r["periodo"])

    # Save to JSON
    os.makedirs(pasta_destino, exist_ok=True)
    output_path = os.path.join(pasta_destino, "supplement_data.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2, ensure_ascii=False)

    print(f"\n[INFO] Salvos {len(records)} trimestres em {output_path}")

    # Print summary
    print("\n--- Resumo da extração ---")
    for r in records:
        is_data = r["income_statement"]
        cap = r["capital"]
        yr = r["yields_rates"]
        ni = is_data.get("net_income")
        ni_str = f"${ni:,.0f}m" if ni else "N/A"
        cet1 = cap.get("cet1_ratio")
        cet1_str = f"{cet1:.1%}" if cet1 else "N/A"
        nim_val = yr.get("nim")
        nim_str = f"{nim_val:.2%}" if nim_val else "N/A"
        lcr_val = cap.get("lcr")
        lcr_str = f"{lcr_val:.0%}" if lcr_val else "N/A"
        print(f"  {r['trimestre']}: NI={ni_str}  CET1={cet1_str}  NIM={nim_str}  LCR={lcr_str}")

    return records


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    pasta_docs = r"G:\Meu Drive\Análise de Crédito Financeiras\BCS\Documentos"
    pasta_destino = r"G:\Meu Drive\Análise de Crédito Financeiras\BCS\Dados_EDGAR"

    extrair_supplement_barclays(pasta_docs, pasta_destino)
