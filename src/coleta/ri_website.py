"""
Busca o site de Relações com Investidores (Investor Relations) de empresas.

Usa o website registrado no SEC EDGAR e testa padrões comuns de URL de RI.
"""

import os
import json
import time
import requests
from datetime import datetime, timedelta

USER_AGENT = "DashboardCredito/1.0 (contact: flpbuchmann@gmail.com)"
EDGAR_BASE = "https://data.sec.gov"
TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
CACHE_DIAS = 180

# Padrões comuns de URL de RI (ordem de prioridade)
RI_PATHS = [
    "/investor-relations",
    "/investors",
    "/ir",
    "/investor",
    "/stockholders",
    "/shareholder-information",
]


def _get_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": USER_AGENT})
    return s


def _get_cik(ticker: str, session: requests.Session) -> str:
    time.sleep(0.12)
    resp = session.get(TICKERS_URL, timeout=30)
    resp.raise_for_status()
    for entry in resp.json().values():
        if entry.get("ticker", "").upper() == ticker.upper():
            return str(entry["cik_str"]).zfill(10)
    return ""


def _get_company_info(cik: str, session: requests.Session) -> tuple[str | None, str]:
    """Obtém website e nome da empresa registrado no SEC EDGAR."""
    if not cik:
        return None, ""
    url = f"{EDGAR_BASE}/submissions/CIK{cik}.json"
    time.sleep(0.12)
    try:
        resp = session.get(url, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        name = data.get("name", "")
        website = data.get("website", "")
        if website:
            if not website.startswith("http"):
                website = f"https://{website}"
            return website.rstrip("/"), name
        return None, name
    except Exception:
        pass
    return None, ""


def _guess_website_from_ticker(ticker: str, company_name: str, session: requests.Session) -> str | None:
    """Tenta adivinhar o website testando padrões comuns."""
    # Padrões comuns baseados no ticker e nome
    candidates = [
        f"https://www.{ticker.lower()}.com",
        f"https://investor.{ticker.lower()}.com",
    ]

    # Tentar extrair nome simplificado da empresa
    if company_name:
        # Ex: "OCCIDENTAL PETROLEUM CORP" -> "occidental", "occidentalpetroleum"
        import re
        name_clean = re.sub(r'\b(CORP|INC|LTD|LLC|PLC|CO|GROUP|HOLDINGS?|INTERNATIONAL|ENTERPRISES?)\b',
                            '', company_name, flags=re.IGNORECASE).strip()
        words = name_clean.lower().split()
        if words:
            candidates.append(f"https://www.{words[0]}.com")
            if len(words) > 1:
                candidates.append(f"https://www.{''.join(words[:2])}.com")

    for url in candidates:
        if _check_url(url, session):
            return url
    return None


def _check_url(url: str, session: requests.Session) -> bool:
    """Verifica se uma URL retorna 200."""
    try:
        resp = session.head(url, timeout=8, allow_redirects=True)
        return resp.status_code < 400
    except Exception:
        return False


def _find_ir_url(website: str, session: requests.Session) -> str | None:
    """Testa padrões comuns de URL de RI a partir do website base."""
    if not website:
        return None

    for path in RI_PATHS:
        candidate = f"{website}{path}"
        if _check_url(candidate, session):
            return candidate

    # Testar subdomínio investor.{domain}
    try:
        from urllib.parse import urlparse
        parsed = urlparse(website)
        domain = parsed.hostname or ""
        # Remove www. se presente
        if domain.startswith("www."):
            domain = domain[4:]
        investor_url = f"https://investor.{domain}"
        if _check_url(investor_url, session):
            return investor_url
    except Exception:
        pass

    return None


def buscar_ri_website(ticker: str, pasta_empresa: str) -> dict:
    """
    Busca o site de RI de uma empresa.

    Returns:
        {"website": "https://...", "ri_url": "https://...", "ticker": "OXY", ...}
    """
    cache_path = os.path.join(pasta_empresa, "ri_website.json")

    # Verificar cache
    if os.path.exists(cache_path):
        with open(cache_path, "r", encoding="utf-8") as f:
            cached = json.load(f)
        # Se tem URL manual, respeitar sempre
        if cached.get("fonte") == "manual":
            return cached
        dt_str = cached.get("data_consulta")
        if dt_str:
            try:
                dt = datetime.fromisoformat(dt_str)
                if datetime.now() - dt < timedelta(days=CACHE_DIAS):
                    return cached
            except ValueError:
                pass

    session = _get_session()
    resultado = {"website": None, "ri_url": None, "ticker": ticker}

    try:
        cik = _get_cik(ticker, session)
        website, company_name = _get_company_info(cik, session)
        resultado["website"] = website

        if not website:
            # Tentar adivinhar website a partir do ticker/nome
            website = _guess_website_from_ticker(ticker, company_name, session)
            resultado["website"] = website

        if website:
            ri_url = _find_ir_url(website, session)
            resultado["ri_url"] = ri_url or website
        else:
            resultado["ri_url"] = None

    except Exception as e:
        print(f"[RI] Erro ao buscar RI para {ticker}: {e}")

    # Salvar cache
    resultado["data_consulta"] = datetime.now().isoformat()
    resultado["fonte"] = "SEC EDGAR"
    os.makedirs(pasta_empresa, exist_ok=True)
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(resultado, f, ensure_ascii=False, indent=2)

    return resultado
