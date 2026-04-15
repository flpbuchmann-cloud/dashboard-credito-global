"""
Download automático de Earnings Releases e Presentations do SEC EDGAR.

Busca Form 8-K (Earnings Releases) e outros documentos relevantes
diretamente do EDGAR, sem depender de sites de RI (que têm Cloudflare).
"""

import os
import re
import time
import json
import requests
from datetime import datetime

USER_AGENT = "DashboardCredito/1.0 (contact: flpbuchmann@gmail.com)"
EDGAR_BASE = "https://data.sec.gov"
TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"


def _get_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": USER_AGENT})
    return s


def _rate_limit():
    time.sleep(0.12)


def _get_cik(ticker: str, session: requests.Session) -> str:
    _rate_limit()
    resp = session.get(TICKERS_URL, timeout=30)
    resp.raise_for_status()
    for entry in resp.json().values():
        if entry.get("ticker", "").upper() == ticker.upper():
            return str(entry["cik_str"]).zfill(10)
    raise ValueError(f"Ticker não encontrado: {ticker}")


def _get_filings(cik: str, session: requests.Session, form_types: list[str],
                 desde: str = "2023-01-01") -> list[dict]:
    """Retorna lista de filings do tipo especificado."""
    url = f"{EDGAR_BASE}/submissions/CIK{cik}.json"
    _rate_limit()
    resp = session.get(url, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    recent = data.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    dates = recent.get("filingDate", [])
    accessions = recent.get("accessionNumber", [])
    primary_docs = recent.get("primaryDocument", [])
    descriptions = recent.get("primaryDocDescription", [])

    filings = []
    for i, form in enumerate(forms):
        if form not in form_types:
            continue
        filing_date = dates[i] if i < len(dates) else ""
        if filing_date < desde:
            continue

        filings.append({
            "form": form,
            "date": filing_date,
            "accession": accessions[i],
            "primary_doc": primary_docs[i] if i < len(primary_docs) else "",
            "description": descriptions[i] if i < len(descriptions) else "",
            "cik": cik,
        })

    return filings


def _get_filing_documents(cik: str, accession: str, session: requests.Session) -> list[dict]:
    """Lista todos os documentos de um filing específico."""
    acc_clean = accession.replace("-", "")
    url = f"https://www.sec.gov/Archives/edgar/data/{cik.lstrip('0')}/{acc_clean}/index.json"
    _rate_limit()
    resp = session.get(url, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    docs = []
    for item in data.get("directory", {}).get("item", []):
        name = item.get("name", "")
        size = item.get("size", "")
        doc_url = f"https://www.sec.gov/Archives/edgar/data/{cik.lstrip('0')}/{acc_clean}/{name}"
        docs.append({"name": name, "size": size, "url": doc_url})

    return docs


def _is_earnings_doc(name: str, docs: list[dict]) -> bool:
    """Identifica se um documento é um earnings release ou presentation."""
    nl = name.lower()
    # PDFs e HTMLs que são exhibits (99.1 = earnings release)
    if nl.endswith((".pdf", ".htm", ".html")):
        keywords = ["earning", "press", "release", "result", "presentation",
                     "slide", "supplement", "ex99", "exhibit99", "exhibit992"]
        return any(kw in nl for kw in keywords)
    return False


def baixar_documentos(
    ticker: str,
    pasta_empresa: str,
    desde: str = "2023-01-01",
    tipos_form: list[str] | None = None,
) -> list[str]:
    """
    Baixa earnings releases e presentations do SEC EDGAR.

    Args:
        ticker: ticker da empresa (ex: "AA")
        pasta_empresa: pasta base da empresa
        desde: data mínima de filing (YYYY-MM-DD)
        tipos_form: tipos de form para buscar (default: 8-K + 10-K + 10-Q)

    Returns:
        lista de caminhos dos arquivos baixados
    """
    if tipos_form is None:
        tipos_form = ["8-K", "8-K/A"]

    session = _get_session()
    pasta_docs = os.path.join(pasta_empresa, "Documentos")
    os.makedirs(pasta_docs, exist_ok=True)

    print(f"[DOWNLOAD] Buscando filings {tipos_form} para {ticker} desde {desde}...")

    try:
        cik = _get_cik(ticker, session)
    except Exception as e:
        print(f"[DOWNLOAD] Erro ao buscar CIK: {e}")
        return []

    filings = _get_filings(cik, session, tipos_form, desde)
    print(f"[DOWNLOAD] Encontrados {len(filings)} filings")

    arquivos_baixados = []

    for filing in filings:
        acc = filing["accession"]
        filing_date = filing["date"]

        # Listar documentos do filing
        try:
            docs = _get_filing_documents(cik, acc, session)
        except Exception:
            continue

        # Filtrar documentos relevantes (earnings releases, presentations)
        for doc in docs:
            name = doc["name"]
            if not _is_earnings_doc(name, docs):
                continue

            # Gerar nome de arquivo legível
            # ex: AA_2025-02-18_8K_earnings_press_release.pdf
            ext = os.path.splitext(name)[1]
            nome_limpo = re.sub(r'[^a-z0-9]', '_', name.lower().rsplit('.', 1)[0])
            nome_arquivo = f"{ticker}_{filing_date}_{filing['form'].replace('/', '')}_{nome_limpo}{ext}"

            caminho = os.path.join(pasta_docs, nome_arquivo)

            # Pular se já existe
            if os.path.exists(caminho):
                print(f"[DOWNLOAD] Já existe: {nome_arquivo}")
                arquivos_baixados.append(caminho)
                continue

            # Baixar
            try:
                _rate_limit()
                resp = session.get(doc["url"], timeout=30)
                resp.raise_for_status()

                with open(caminho, "wb") as f:
                    f.write(resp.content)

                size_mb = len(resp.content) / 1e6
                print(f"[DOWNLOAD] Baixado: {nome_arquivo} ({size_mb:.1f}MB)")
                arquivos_baixados.append(caminho)
            except Exception as e:
                print(f"[DOWNLOAD] Erro ao baixar {name}: {e}")

    print(f"[DOWNLOAD] Total: {len(arquivos_baixados)} documentos")
    return arquivos_baixados


if __name__ == "__main__":
    import sys
    ticker = sys.argv[1] if len(sys.argv) > 1 else "AA"
    pasta = f"G:/Meu Drive/Análise de Crédito Global/{ticker}"
    desde = sys.argv[2] if len(sys.argv) > 2 else "2023-01-01"
    baixar_documentos(ticker, pasta, desde=desde)
