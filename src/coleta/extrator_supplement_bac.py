"""
Extrator de Supplemental Information PDF do Bank of America (BAC).

Lê os PDFs trimestrais via PyMuPDF e extrai dados estruturados de:
- Average Balances & Interest Rates (yield, NIM, spreads)
- Capital Management (CET1, RWA, SLR, etc.)
- Credit Quality (NCO, NPA, ACL)

Salva em supplement_data.json no mesmo formato que JPM/BK.
"""

import os
import re
import json
import glob

import fitz  # PyMuPDF


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------

def _get_text(page) -> str:
    """Extrai texto de uma página do PDF com sort=True para garantir
    ordem correta em PDFs com layout complexo (vectorized text)."""
    return page.get_text(sort=True)


def _parse_number(text: str) -> float | None:
    """Converte string numérica extraída do PDF em float."""
    if text is None:
        return None
    text = text.strip()
    if not text or text in ("—", "–", "―", "�", "n/m", "N/M", "NM"):
        return None
    text = text.replace("$", "").replace("%", "").replace(",", "").strip()
    if not text or text == "�":
        return None
    negative = False
    if text.startswith("(") and text.endswith(")"):
        negative = True
        text = text[1:-1].strip()
    try:
        v = float(text)
        return -v if negative else v
    except ValueError:
        return None


def _quarter_to_date(quarter_str: str) -> str:
    """Converte '4Q25' -> '2025-12-31', etc."""
    m = re.match(r"(\d)Q(\d{2})", quarter_str)
    if not m:
        return quarter_str
    q = int(m.group(1))
    yr = 2000 + int(m.group(2))
    end_dates = {1: "03-31", 2: "06-30", 3: "09-30", 4: "12-31"}
    return f"{yr}-{end_dates[q]}"


def _filename_to_quarter(filename: str) -> str:
    """Extrai trimestre do nome do arquivo."""
    m = re.search(r"(\d)Q(\d{2})", filename, re.IGNORECASE)
    if m:
        return f"{m.group(1)}Q{m.group(2)}"
    return ""


def _find_page_by_keyword(doc, keyword: str, secondary: str = None) -> int | None:
    """Busca uma página pelo conteúdo (keyword no título/corpo).
    Retorna o índice da página, ou None. Pula a página de TOC (index 1)."""
    for i in range(len(doc)):
        if i == 1:  # Skip TOC page
            continue
        text = _get_text(doc[i])
        header = text[:500]
        if keyword in header:
            if secondary is None or secondary in text:
                return i
    # Fallback: search full text
    for i in range(2, len(doc)):
        text = _get_text(doc[i])
        if keyword in text:
            if secondary is None or secondary in text:
                return i
    return None


def _extract_numbers_from_line(line: str) -> list[float]:
    """Extrai todos os números da porção de dados de uma linha do PDF.
    Separa o label (texto) dos dados (números) usando a presença de $ ou
    um gap de 3+ espaços como delimitador. Isso evita capturar dígitos
    que fazem parte do label (ex: 'tier 1 capital')."""
    nums = []
    # Encontra onde começa a porção de dados:
    # 1) Posição do primeiro $, ou
    # 2) Posição do primeiro gap de 3+ espaços seguido de número/$/parêntese
    data_start = len(line)

    dollar_pos = line.find("$")
    if dollar_pos >= 0:
        data_start = dollar_pos

    # Também procura gap de espaços seguido de número
    gap_match = re.search(r'\s{3,}([\d$(])', line)
    if gap_match:
        data_start = min(data_start, gap_match.start())

    data_part = line[data_start:]

    # Extrai números: com commas (amounts) ou decimais (rates) ou em parênteses (negatives)
    pattern = r'\([\d,]+\.?\d*\)|[\d,]+\.?\d*'
    for m in re.finditer(pattern, data_part):
        val = _parse_number(m.group(0))
        if val is not None:
            nums.append(val)
    return nums


def _find_line(lines: list[str], keyword: str, start: int = 0,
               after_keyword: str = None) -> tuple[int, str] | None:
    """Encontra a primeira linha contendo keyword. Retorna (index, line)."""
    started = after_keyword is None
    for i in range(start, len(lines)):
        stripped = lines[i].strip()
        if not started:
            if after_keyword in stripped:
                started = True
            continue
        if keyword in stripped:
            return (i, stripped)
    return None


# ---------------------------------------------------------------------------
# Parse: Average Balances & Interest Rates
# ---------------------------------------------------------------------------

def _parse_avg_balances(doc) -> dict:
    """Extrai dados da página 'Quarterly Average Balances and Interest Rates'.

    Layout com sort=True: cada linha da tabela tem o label seguido dos números
    das 3 colunas trimestrais. Para cada trimestre: AvgBal, Interest, Yield/Rate.
    A primeira coluna é o trimestre mais recente.
    """
    idx = _find_page_by_keyword(doc, "Quarterly Average Balances and Interest Rates")
    if idx is None:
        print("    [WARN] Página de Average Balances não encontrada")
        return {"avg_balances": {}, "yields_rates": {}}

    text = _get_text(doc[idx])
    lines = text.split("\n")

    ab = {}
    yr = {}

    def extract_bal_and_yield(keyword: str, after: str = None):
        """Encontra linha com keyword e extrai (avg_balance, yield_rate) do 1o trimestre."""
        res = _find_line(lines, keyword, after_keyword=after)
        if not res:
            return None, None
        nums = _extract_numbers_from_line(res[1])
        # Pattern: AvgBal1 Interest1 Yield1 AvgBal2 Interest2 Yield2 ...
        if len(nums) >= 3:
            return nums[0], nums[2]
        elif len(nums) >= 1:
            return nums[0], None
        return None, None

    # --- ASSETS ---
    bal, yld = extract_bal_and_yield("Total earning assets")
    if bal is not None:
        ab["avg_earning_assets"] = bal
    if yld is not None:
        yr["avg_earning_assets_yield"] = round(yld / 100, 6)

    bal, yld = extract_bal_and_yield("Total loans and leases")
    if bal is not None:
        ab["avg_loans"] = bal
    if yld is not None:
        yr["avg_loans_yield"] = round(yld / 100, 6)

    res = _find_line(lines, "Total assets")
    if res:
        nums = _extract_numbers_from_line(res[1])
        if nums:
            ab["avg_total_assets"] = nums[0]

    # --- LIABILITIES ---
    bal, yld = extract_bal_and_yield("Total interest-bearing deposits")
    if bal is not None:
        ab["avg_total_ib_deposits"] = bal
    if yld is not None:
        yr["avg_ib_deposits_rate"] = round(yld / 100, 6)

    res = _find_line(lines, "Noninterest-bearing deposits",
                     after_keyword="Interest-bearing liabilities")
    if res:
        nums = _extract_numbers_from_line(res[1])
        if nums:
            ab["avg_nib_deposits"] = nums[0]

    # Total deposits = IB + NIB
    ib = ab.get("avg_total_ib_deposits")
    nib = ab.get("avg_nib_deposits")
    if ib is not None and nib is not None:
        ab["avg_total_deposits"] = ib + nib

    bal, yld = extract_bal_and_yield("Total interest-bearing liabilities")
    if bal is not None:
        ab["avg_total_ib_liabilities"] = bal
    if yld is not None:
        yr["avg_total_ib_liabilities_rate"] = round(yld / 100, 6)

    # --- NIM & SPREAD ---
    res = _find_line(lines, "Net interest spread")
    if res:
        nums = _extract_numbers_from_line(res[1])
        if nums:
            yr["interest_spread"] = round(nums[0] / 100, 6)

    res = _find_line(lines, "Net interest income/yield on earning assets")
    if res:
        nums = _extract_numbers_from_line(res[1])
        # Format: NII_amount  NIM%  ...
        if len(nums) >= 2:
            # NIM is the small number (1-4 range)
            for n in nums:
                if 0.5 < n < 10:
                    yr["nim"] = round(n / 100, 6)
                    break

    # Fallback: calculate spread from yields
    if "interest_spread" not in yr:
        a_yld = yr.get("avg_earning_assets_yield")
        ib_rate = yr.get("avg_total_ib_liabilities_rate")
        if a_yld is not None and ib_rate is not None:
            yr["interest_spread"] = round(a_yld - ib_rate, 6)

    return {"avg_balances": ab, "yields_rates": yr}


# ---------------------------------------------------------------------------
# Parse: Capital Management
# ---------------------------------------------------------------------------

def _parse_capital(doc) -> dict:
    """Extrai dados da página 'Capital Management'."""
    idx = _find_page_by_keyword(doc, "Capital Management")
    if idx is None:
        print("    [WARN] Página de Capital Management não encontrada")
        return {}

    text = _get_text(doc[idx])
    lines = text.split("\n")
    result = {}

    def find_and_extract(keyword: str, after: str = None) -> list[float]:
        """Find line with keyword (after optional section header) and extract numbers."""
        res = _find_line(lines, keyword, after_keyword=after)
        if res:
            return _extract_numbers_from_line(res[1])
        return []

    # Standardized Approach section
    nums = find_and_extract("Common equity tier 1 capital", after="Standardized")
    # Filter: CET1 capital line has dollar amounts, ratio line has "ratio" in it
    # The keyword search already distinguishes them
    if nums:
        result["cet1_capital"] = nums[0]

    nums = find_and_extract("Risk-weighted assets", after="Standardized")
    if nums:
        result["rwa_standardized"] = nums[0]

    nums = find_and_extract("Common equity tier 1 capital ratio", after="Standardized")
    if nums:
        result["cet1_ratio"] = round(nums[0] / 100, 6)

    nums = find_and_extract("Tier 1 capital ratio", after="Standardized")
    if nums:
        result["tier1_ratio"] = round(nums[0] / 100, 6)

    nums = find_and_extract("Total capital ratio", after="Standardized")
    if nums:
        result["total_capital_ratio"] = round(nums[0] / 100, 6)

    nums = find_and_extract("Supplementary leverage ratio")
    if nums:
        result["slr"] = round(nums[0] / 100, 6)

    nums = find_and_extract("Tier 1 leverage ratio")
    if nums:
        result["leverage_ratio"] = round(nums[0] / 100, 6)

    # LCR / NSFR - preenchido depois via _enrich_lcr_from_10q
    result["lcr"] = None
    result["nsfr"] = None

    return result


# ---------------------------------------------------------------------------
# Parse: Credit Quality (NCO, NPA, ACL)
# ---------------------------------------------------------------------------

def _parse_credit_quality(doc) -> dict:
    """Extrai NCO, NPA, ACL das páginas relevantes."""
    result = {}

    # --- NCO ---
    idx = _find_page_by_keyword(doc, "Quarterly Net Charge-offs")
    if idx is not None:
        text = _get_text(doc[idx])
        lines = text.split("\n")
        for line in lines:
            s = line.strip()
            if "Total net charge-offs" in s:
                nums = _extract_numbers_from_line(s)
                if nums:
                    result["nco_total"] = nums[0]
                break
    else:
        print("    [WARN] Página de NCO não encontrada")

    # --- NPA ---
    # Note: older PDFs use "leases and foreclosed", newer use "leases, and foreclosed"
    idx = _find_page_by_keyword(
        doc, "Nonperforming Loans, Leases and Foreclosed Properties",
        secondary="Total nonperforming loans, leases"
    )
    if idx is not None:
        text = _get_text(doc[idx])
        lines = text.split("\n")
        for line in lines:
            s = line.strip()
            # Match both "leases and foreclosed" and "leases, and foreclosed"
            if "Total nonperforming loans, leases" in s and "foreclosed properties" in s:
                nums = _extract_numbers_from_line(s)
                if nums:
                    result["npa"] = nums[0]
                break
        for line in lines:
            s = line.strip()
            if "Total nonperforming loans and leases" in s and "foreclosed" not in s:
                nums = _extract_numbers_from_line(s)
                if nums:
                    result["npl_total"] = nums[0]
                break
    else:
        print("    [WARN] Página de NPA não encontrada")

    # --- ACL ---
    idx = _find_page_by_keyword(
        doc, "Allocation of the Allowance for Credit Losses",
        secondary="Allowance for loan and lease losses"
    )
    if idx is not None:
        text = _get_text(doc[idx])
        lines = text.split("\n")
        for line in lines:
            s = line.strip()
            if s.startswith("Allowance for loan and lease losses") and "Total" not in s:
                nums = _extract_numbers_from_line(s)
                if nums:
                    result["acl_loans"] = nums[0]
                    if len(nums) >= 2:
                        result["acl_pct_loans"] = round(nums[1] / 100, 6)

            if "Allowance for credit losses" in s and "Allocation" not in s:
                nums = _extract_numbers_from_line(s)
                if nums:
                    result["acl_total"] = nums[0]
    else:
        print("    [WARN] Página de ACL não encontrada")

    return result


# ---------------------------------------------------------------------------
# Função principal
# ---------------------------------------------------------------------------

def _extract_lcr_from_10q(ticker: str, periodos: list[str]) -> dict[str, float]:
    """Extrai LCR dos 10-Q/10-K filings na EDGAR para os períodos solicitados.

    Usa EDGAR XBRL Filing API para encontrar filings por report date,
    depois baixa o HTML e extrai LCR via regex.

    Returns:
        Dict de {periodo_str: lcr_ratio}, ex: {"2025-09-30": 1.13}
    """
    import time
    import requests

    session = requests.Session()
    session.headers.update({"User-Agent": "DashboardCredito/1.0 (contact: flpbuchmann@gmail.com)"})

    # 1. Get CIK
    try:
        time.sleep(0.15)
        resp = session.get("https://www.sec.gov/files/company_tickers.json", timeout=30)
        tickers_data = resp.json()
        cik = None
        for entry in tickers_data.values():
            if entry.get("ticker", "").upper() == ticker.upper():
                cik = str(entry["cik_str"]).zfill(10)
                break
        if not cik:
            return {}
    except Exception:
        return {}

    # 2. Get ALL filings (recent + paginated)
    time.sleep(0.15)
    try:
        resp = session.get(f"https://data.sec.gov/submissions/CIK{cik}.json", timeout=30)
        subs = resp.json()
    except Exception:
        return {}

    # Collect all 10-Q/10-K from recent and paginated files
    def _collect_filings(data: dict) -> list[dict]:
        forms = data.get("form", [])
        report_dates = data.get("reportDate", [])
        accessions = data.get("accessionNumber", [])
        primary_docs = data.get("primaryDocument", [])
        filings = []
        for i in range(len(forms)):
            if forms[i] in ("10-Q", "10-K"):
                filings.append({
                    "form": forms[i],
                    "reportDate": report_dates[i],
                    "accession": accessions[i],
                    "primaryDoc": primary_docs[i],
                })
        return filings

    all_filings = _collect_filings(subs.get("filings", {}).get("recent", {}))

    # If not enough, load paginated files
    periodos_set = set(periodos)
    found_periods = {f["reportDate"] for f in all_filings}
    missing = periodos_set - found_periods
    if missing:
        for file_info in subs.get("filings", {}).get("files", []):
            if not missing:
                break
            fname = file_info["name"]
            time.sleep(0.15)
            try:
                resp = session.get(f"https://data.sec.gov/submissions/{fname}", timeout=30)
                page_data = resp.json()
                page_filings = _collect_filings(page_data)
                all_filings.extend(page_filings)
                found_periods.update(f["reportDate"] for f in page_filings)
                missing = periodos_set - found_periods
            except Exception:
                continue

    # 3. Download and extract LCR from each matching filing
    result = {}
    for periodo in periodos:
        filing = next((f for f in all_filings if f["reportDate"] == periodo), None)
        if not filing:
            continue

        acc_clean = filing["accession"].replace("-", "")
        doc = filing["primaryDoc"]
        url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc_clean}/{doc}"

        time.sleep(0.15)
        try:
            resp = session.get(url, timeout=90)
            if resp.status_code != 200:
                continue
            text = re.sub(r"<[^>]+>", " ", resp.text)
            text = re.sub(r"&[^;]+;", " ", text)
            text = re.sub(r"\s+", " ", text)

            # Patterns: "LCR was 113 percent", "average LCR of 113%", "LCR 110 %"
            for pat in [
                r"(?:our |average |the |Firm )LCR\s+(?:was|of|averaged)\s+(\d{2,3})\s*(?:percent|%)",
                r"LCR\s+(?:was|of|averaged)\s+(?:approximately\s+)?(\d{2,3})\s*(?:percent|%)",
                r"(?:Firm|Corporation).{0,50}?LCR\s+(\d{2,3})\s*%",
                r"\bLCR\s+(\d{2,3})\s+%",
            ]:
                m = re.search(pat, text, re.IGNORECASE)
                if m:
                    lcr_val = int(m.group(1)) / 100
                    result[periodo] = lcr_val
                    print(f"    [LCR] {periodo}: {lcr_val:.0%} (from {filing['form']})")
                    break
        except Exception:
            pass

    return result


def extrair_supplement_bac(pasta_docs: str, pasta_destino: str) -> list[dict]:
    """Extrai dados de todos os Supplemental Information PDFs do BAC.

    Args:
        pasta_docs: Caminho para pasta com os PDFs (supplemental-information-*.pdf)
        pasta_destino: Caminho para pasta de destino do JSON

    Returns:
        Lista de dicionários com dados extraídos por trimestre.
    """
    pdfs = sorted(glob.glob(os.path.join(pasta_docs, "supplemental-information-*.pdf")))
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

        entry = {
            "periodo": periodo,
            "trimestre": trimestre,
            "fonte": fname,
        }

        # Average Balances & Yields
        try:
            avg_data = _parse_avg_balances(doc)
            entry["avg_balances"] = avg_data.get("avg_balances", {})
            entry["yields_rates"] = avg_data.get("yields_rates", {})
        except Exception as e:
            print(f"    [WARN] Erro avg_balances: {e}")
            entry["avg_balances"] = {}
            entry["yields_rates"] = {}

        # Capital
        try:
            entry["capital"] = _parse_capital(doc)
        except Exception as e:
            print(f"    [WARN] Erro capital: {e}")
            entry["capital"] = {}

        # Credit Quality
        try:
            entry["credit_quality"] = _parse_credit_quality(doc)
        except Exception as e:
            print(f"    [WARN] Erro credit_quality: {e}")
            entry["credit_quality"] = {}

        doc.close()
        resultados.append(entry)

    # Enriquecer com LCR dos 10-Q/10-K filings da EDGAR
    periodos = [r["periodo"] for r in resultados]
    print("  Extraindo LCR dos 10-Q/10-K filings...")
    lcr_map = _extract_lcr_from_10q("BAC", periodos)
    for entry in resultados:
        per = entry.get("periodo")
        if per in lcr_map:
            cap = entry.get("capital", {})
            cap["lcr"] = lcr_map[per]
            entry["capital"] = cap

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

    pasta_docs = sys.argv[1] if len(sys.argv) > 1 else "G:/Meu Drive/Análise de Crédito Financeiras/BAC/Documentos"
    pasta_destino = sys.argv[2] if len(sys.argv) > 2 else "G:/Meu Drive/Análise de Crédito Financeiras/BAC/Dados_EDGAR"

    dados = extrair_supplement_bac(pasta_docs, pasta_destino)

    if dados:
        print("\n=== Últimos 2 trimestres ===")
        for entry in dados[-2:]:
            print(json.dumps(entry, indent=2, ensure_ascii=False))
