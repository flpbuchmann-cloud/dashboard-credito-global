"""
Parser de filings EDGAR para extração de cronograma de amortização de dívida.

Busca tabelas de maturidade de dívida nos 10-K/10-Q filings,
tipicamente na nota "Debt" ou "Borrowings" das notas explicativas.

Uso:
    from src.coleta.filing_parser import extrair_cronograma_edgar
    cronograma = extrair_cronograma_edgar(cik="0001318605", n_recentes=3)
"""

import os
import re
import json
import time
import requests
from bs4 import BeautifulSoup
from datetime import datetime

USER_AGENT = "DashboardCredito/1.0 (contact: flpbuchmann@gmail.com)"

# Palavras-chave para localizar tabelas de maturidade de dívida
DEBT_KEYWORDS = [
    "maturities of long-term debt",
    "aggregate annual maturities",
    "scheduled maturities",
    "maturity of long-term",
    "contractual maturities",
    "debt maturity",
    "aggregate maturities",
    "maturities of outstanding",
    "annual maturities",
    "future minimum payments",
    "principal payments",
    "repayment schedule",
]

DEBT_SECTION_KEYWORDS = [
    "long-term debt",
    "long term debt",
    "notes payable",
    "borrowings",
    "debt and credit",
    "indebtedness",
]


def _limpar_numero(s: str) -> float | None:
    """Converte string numérica americana para float."""
    if not s:
        return None
    s = s.strip().replace(",", "").replace("$", "").replace(" ", "")
    # Handle parentheses for negatives
    if s.startswith("(") and s.endswith(")"):
        s = "-" + s[1:-1]
    # Handle dash for zero
    if s in ("-", "—", "–", ""):
        return 0.0
    try:
        return float(s)
    except ValueError:
        return None


def _detectar_escala(html_text: str) -> float:
    """Detecta se valores estão em thousands, millions, etc."""
    lower = html_text.lower()
    # Check various patterns for "millions"
    if any(p in lower for p in [
        "in millions", "(in millions)", "$ in millions",
        "millions except", "millions,", "millions\n",
    ]):
        return 1_000_000
    # Simple word match at start of text (common in inline XBRL tables)
    if lower.strip().startswith("millions"):
        return 1_000_000
    if "in thousands" in lower or "(in thousands)" in lower:
        return 1_000
    if "in billions" in lower:
        return 1_000_000_000
    return 1  # assume unidade


def _extrair_tabela_maturidade(table_html: str, escala: float = 1) -> dict | None:
    """
    Extrai cronograma de maturidade de uma tabela HTML.

    Procura por tabelas com anos (2025, 2026, ...) e valores.

    Returns:
        {"vencimentos": {"2026": valor, ...}, "divida_total": total} ou None
    """
    soup = BeautifulSoup(table_html, "lxml")
    rows = soup.find_all("tr")

    if not rows:
        return None

    vencimentos = {}
    total = 0

    for row in rows:
        cells = row.find_all(["td", "th"])
        if len(cells) < 2:
            continue

        # Texto da primeira célula
        label = cells[0].get_text(strip=True).lower()

        # Procurar ano no label
        year_match = re.search(r"(20[2-4]\d)", label)
        thereafter = any(kw in label for kw in ["thereafter", "after", "remaining", "later"])
        total_row = label.startswith("total") or "total" in label

        if year_match or thereafter or total_row:
            # Pegar o último valor numérico da linha (geralmente o total)
            valores = []
            for cell in cells[1:]:
                val = _limpar_numero(cell.get_text(strip=True))
                if val is not None:
                    valores.append(val)

            if valores:
                valor = valores[-1] * escala  # Último valor = total consolidado

                if year_match and not total_row:
                    ano = year_match.group(1)
                    vencimentos[ano] = valor
                elif thereafter:
                    vencimentos["longo_prazo"] = valor
                elif total_row:
                    total = valor

    if len(vencimentos) >= 3:
        if total == 0:
            total = sum(v for v in vencimentos.values())
        return {
            "vencimentos": vencimentos,
            "divida_total": total,
        }

    return None


def _buscar_filing_url(cik: str, form_type: str = "10-K",
                       session: requests.Session | None = None) -> list[dict]:
    """
    Busca URLs dos filings recentes de uma empresa.

    Returns:
        Lista de {"accession": "...", "date": "YYYY-MM-DD", "url": "..."}
    """
    if session is None:
        session = requests.Session()
        session.headers.update({"User-Agent": USER_AGENT})

    url = f"https://data.sec.gov/submissions/CIK{cik}.json"
    time.sleep(0.12)
    resp = session.get(url, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    filings = data.get("filings", {}).get("recent", {})
    forms = filings.get("form", [])
    accessions = filings.get("accessionNumber", [])
    dates = filings.get("filingDate", [])
    primary_docs = filings.get("primaryDocument", [])

    # Get the entity CIK (numeric, no leading zeros) from the JSON
    entity_cik = str(data.get("cik", cik)).lstrip("0")

    results = []
    for i, form in enumerate(forms):
        if form.replace("/A", "") == form_type:
            accn = accessions[i].replace("-", "")
            doc = primary_docs[i]
            results.append({
                "accession": accessions[i],
                "date": dates[i],
                "url": f"https://www.sec.gov/Archives/edgar/data/{entity_cik}/{accn}/{doc}",
            })

    return results


def _encontrar_tabela_maturidade_global(html: str, escala: float) -> dict | None:
    """
    Searches entire filing for debt maturity schedule tables.

    Strategy: find all tables containing year numbers AND 'thereafter',
    then pick the one that looks like a debt maturity schedule
    (has Fixed/Variable rate columns or debt-related labels).
    """
    import warnings
    from bs4 import XMLParsedAsHTMLWarning
    warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

    soup = BeautifulSoup(html, "lxml")
    all_tables = soup.find_all("table")
    year_pattern = re.compile(r"^20[2-4]\d$")

    melhor = None
    melhor_score = 0

    for table in all_tables:
        text = table.get_text(" ", strip=True).lower()

        # Must have 'thereafter' or 'after year' and year numbers
        has_thereafter = "thereafter" in text or "after year" in text
        if not has_thereafter:
            continue

        rows = table.find_all("tr")
        if len(rows) < 4:
            continue

        # Count year-like entries in first column
        year_count = 0
        for row in rows:
            cells = row.find_all(["td", "th"])
            if cells:
                first_cell = cells[0].get_text(strip=True)
                if year_pattern.match(first_cell):
                    year_count += 1

        if year_count < 3:
            continue

        # Score: prefer tables with debt-related keywords
        score = year_count
        debt_keywords = ["debt", "rate", "fixed", "variable", "interest",
                         "notes", "principal", "maturity", "maturies"]
        for kw in debt_keywords:
            if kw in text:
                score += 2

        # Penalize lease-only tables
        if "operating lease" in text and "debt" not in text and "note" not in text:
            score -= 10

        # Detect scale from the table itself (inline XBRL often has it inside)
        table_text = table.get_text()
        table_escala = _detectar_escala(table_text)
        if table_escala == 1:
            table_escala = escala  # fallback to global scale

        resultado = _extrair_tabela_maturidade(str(table), table_escala)
        if resultado and resultado["divida_total"] > 0 and score > melhor_score:
            melhor = resultado
            melhor_score = score

    return melhor


def extrair_cronograma_edgar(cik: str, n_recentes: int = 6,
                              cache_dir: str = "data/raw/edgar_api",
                              incluir_10q: bool = True) -> list[dict]:
    """
    Extrai cronogramas de amortização dos filings mais recentes.

    Args:
        cik: CIK da empresa (com zeros à esquerda)
        n_recentes: número de filings recentes a processar
        incluir_10q: se True, inclui 10-Q (trimestrais) além de 10-K

    Returns:
        Lista de cronogramas no formato padrão
    """
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    # Buscar filings 10-K e 10-Q
    filings_10k = _buscar_filing_url(cik, "10-K", session)
    filings_10q = _buscar_filing_url(cik, "10-Q", session) if incluir_10q else []

    # Combinar e ordenar por data
    all_filings = filings_10k + filings_10q
    all_filings.sort(key=lambda x: x["date"], reverse=True)
    recentes = all_filings[:n_recentes]

    print(f"[FilingParser] {len(recentes)} filings para processar")

    cronogramas = []
    for filing in recentes:
        try:
            print(f"[FilingParser] {filing['date']}...", end=" ")

            # Download filing HTML
            time.sleep(0.12)
            resp = session.get(filing["url"], timeout=120)
            if resp.status_code != 200:
                print(f"ERRO ({resp.status_code})")
                continue

            html = resp.text
            if len(html) < 1000:
                print("Filing stub (too short)")
                continue

            escala = _detectar_escala(html[:10000])

            # Strategy 1: Global table search (works for inline XBRL)
            melhor = _encontrar_tabela_maturidade_global(html, escala)

            # Strategy 2: Keyword-proximity search (fallback for traditional HTML)
            if not melhor:
                text_lower = html.lower()
                melhor_total = 0
                for keyword in DEBT_KEYWORDS:
                    pos = text_lower.find(keyword)
                    if pos == -1:
                        continue
                    region = html[max(0, pos - 500):pos + 10000]
                    region_soup = BeautifulSoup(region, "lxml")
                    tables = region_soup.find_all("table")
                    for table in tables:
                        resultado = _extrair_tabela_maturidade(str(table), escala)
                        if resultado and resultado["divida_total"] > melhor_total:
                            melhor = resultado
                            melhor_total = resultado["divida_total"]

            if melhor:
                # Inferir data de referência (período, não data de filing)
                date_str = filing["date"]
                # Try multiple patterns to find the period end date
                period_patterns = [
                    r"(?:period of report|as of|ended|ending)\s*:?\s*(\w+ \d{1,2},? \d{4})",
                    r"(?:September|June|March|December)\s+\d{1,2},?\s+\d{4}",
                    r"for the (?:quarterly |)period ended\s+(\w+ \d{1,2},? \d{4})",
                ]
                for pattern in period_patterns:
                    period_match = re.search(pattern, html[:15000], re.IGNORECASE)
                    if period_match:
                        try:
                            from dateutil import parser as dateparser
                            match_text = period_match.group(1) if period_match.lastindex else period_match.group(0)
                            dt = dateparser.parse(match_text)
                            date_str = dt.strftime("%Y-%m-%d")
                            break
                        except Exception:
                            pass

                # Infer period date from filing date (filings are filed AFTER period end)
                if date_str == filing["date"]:
                    from datetime import datetime as dt_cls
                    try:
                        fd = dt_cls.strptime(filing["date"], "%Y-%m-%d")
                        # Quarter ends BEFORE the filing date
                        quarter_ends = [
                            dt_cls(fd.year, 3, 31),
                            dt_cls(fd.year, 6, 30),
                            dt_cls(fd.year, 9, 30),
                            dt_cls(fd.year, 12, 31),
                            dt_cls(fd.year - 1, 12, 31),
                            dt_cls(fd.year - 1, 9, 30),
                            dt_cls(fd.year - 1, 6, 30),
                        ]
                        # Only consider quarter ends BEFORE the filing date
                        past_ends = [d for d in quarter_ends if d < fd]
                        if past_ends:
                            nearest = max(past_ends)  # most recent quarter end before filing
                            if (fd - nearest).days < 120:
                                date_str = nearest.strftime("%Y-%m-%d")
                    except Exception:
                        pass

                cronograma = {
                    "data_referencia": date_str,
                    "caixa": None,  # Será preenchido pelo indicadores.py
                    "vencimentos": melhor["vencimentos"],
                    "divida_total": melhor["divida_total"],
                    "arquivo": f"EDGAR filing {filing['date']}",
                }
                cronogramas.append(cronograma)
                print(f"OK ({len(melhor['vencimentos'])} vencimentos)")
            else:
                print("Sem tabela de maturidade")

        except Exception as e:
            print(f"ERRO: {e}")

    return cronogramas


def salvar_cronogramas(cronogramas: list[dict], caminho_saida: str):
    """Salva cronogramas em JSON."""
    os.makedirs(os.path.dirname(caminho_saida), exist_ok=True)
    with open(caminho_saida, "w", encoding="utf-8") as f:
        json.dump(cronogramas, f, ensure_ascii=False, indent=2, default=str)
    print(f"[FilingParser] Salvos em {caminho_saida}")
