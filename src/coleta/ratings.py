"""
Busca ratings de crédito (Moody's, S&P, Fitch) a partir dos filings SEC EDGAR.

Extrai menções a ratings no texto do 10-K mais recente e retorna
as notas encontradas. Resultados são cacheados em ratings.json.
"""

import os
import re
import json
import time
import requests
from datetime import datetime, timedelta
from html import unescape

USER_AGENT = "DashboardCredito/1.0 (contact: flpbuchmann@gmail.com)"
EDGAR_BASE = "https://data.sec.gov"
TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
CACHE_DIAS = 90

# ---------------------------------------------------------------------------
# Escalas de rating
# ---------------------------------------------------------------------------
MOODY_RATINGS = [
    "Aaa", "Aa1", "Aa2", "Aa3",
    "A1", "A2", "A3",
    "Baa1", "Baa2", "Baa3",
    "Ba1", "Ba2", "Ba3",
    "B1", "B2", "B3",
    "Caa1", "Caa2", "Caa3", "Ca",
]

SP_FITCH_RATINGS = [
    "AAA",
    "AA+", "AA", "AA-",
    "A+", "A-",
    "BBB+", "BBB", "BBB-",
    "BB+", "BB", "BB-",
    "B+", "B-",
    "CCC+", "CCC", "CCC-",
    "CC",
]

# Regex patterns — ratings SEMPRE em maiúscula, mínimo 2 caracteres para evitar falsos positivos
_MOODY_PAT = "|".join(re.escape(r) for r in MOODY_RATINGS)
_SP_FITCH_PAT = "|".join(re.escape(r) for r in SP_FITCH_RATINGS)

# Padrões para encontrar ratings no texto dos filings.
# Nomes de agências: case-insensitive. Notas de rating: case-sensitive (sempre maiúsculas/title case).
_AGENCY_MOODY = r"[Mm]oody[''\u2019]?s"
_AGENCY_SP = r"(?:S\s*&\s*P|S\s*&\s*P\s+Global|[Ss]tandard\s+(?:&|and)\s+Poor[''\u2019]?s?)"
_AGENCY_FITCH = r"[Ff]itch"
_VERB = r"(?:rat(?:ed|ing|ings)|assign|affirm|downgrad|upgrad|maintain|revis|credit\s+rating)"

RE_MOODY = re.compile(
    rf"""{_AGENCY_MOODY}[^.;]*?{_VERB}[^.;]*?\b({_MOODY_PAT})\b"""
    rf"""|\b({_MOODY_PAT})\b[^.;]*?(?:by|from)\s+{_AGENCY_MOODY}"""
    rf"""|{_AGENCY_MOODY}[^.;]{{0,120}}?\b({_MOODY_PAT})\b""",
    re.DOTALL,
)

RE_SP = re.compile(
    rf"""{_AGENCY_SP}[^.;]*?{_VERB}[^.;]*?\b({_SP_FITCH_PAT})\b"""
    rf"""|\b({_SP_FITCH_PAT})\b[^.;]*?(?:by|from)\s+{_AGENCY_SP}"""
    rf"""|{_AGENCY_SP}[^.;]{{0,120}}?\b({_SP_FITCH_PAT})\b""",
    re.DOTALL,
)

RE_FITCH = re.compile(
    rf"""{_AGENCY_FITCH}[^.;]*?{_VERB}[^.;]*?\b({_SP_FITCH_PAT})\b"""
    rf"""|\b({_SP_FITCH_PAT})\b[^.;]*?(?:by|from)\s+{_AGENCY_FITCH}"""
    rf"""|{_AGENCY_FITCH}[^.;]{{0,120}}?\b({_SP_FITCH_PAT})\b""",
    re.DOTALL,
)

# Padrão para tabelas com rating, ex: "Moody's   Baa3   BBB-   BBB-"
RE_RATING_TABLE = re.compile(
    rf"""{_AGENCY_MOODY}\s+({_MOODY_PAT})"""
    rf"""[\s\S]{{0,200}}?"""
    rf"""{_AGENCY_SP}\s+({_SP_FITCH_PAT})"""
    rf"""[\s\S]{{0,200}}?"""
    rf"""{_AGENCY_FITCH}\s+({_SP_FITCH_PAT})""",
)


def _rate_limit():
    """Respeita rate limit SEC (10 req/s)."""
    time.sleep(0.12)


def _get_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": USER_AGENT})
    return s


def _get_cik(ticker: str, session: requests.Session) -> str:
    """Converte ticker em CIK (10 dígitos)."""
    _rate_limit()
    resp = session.get(TICKERS_URL, timeout=30)
    resp.raise_for_status()
    for entry in resp.json().values():
        if entry.get("ticker", "").upper() == ticker.upper():
            return str(entry["cik_str"]).zfill(10)
    raise ValueError(f"Ticker não encontrado: {ticker}")


def _strip_html(html: str) -> str:
    """Remove tags HTML e decodifica entidades."""
    text = re.sub(r"<style[^>]*>.*?</style>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<script[^>]*>.*?</script>", " ", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = unescape(text)
    text = re.sub(r"\s+", " ", text)
    return text


def _buscar_filing_url(cik: str, session: requests.Session) -> str | None:
    """Retorna URL do documento principal do 10-K mais recente."""
    url = f"{EDGAR_BASE}/submissions/CIK{cik}.json"
    _rate_limit()
    resp = session.get(url, timeout=30)
    resp.raise_for_status()
    subs = resp.json()

    recent = subs.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    accessions = recent.get("accessionNumber", [])
    primary_docs = recent.get("primaryDocument", [])

    for i, form in enumerate(forms):
        if form in ("10-K", "10-K/A"):
            acc_dashes = accessions[i]
            acc_clean = acc_dashes.replace("-", "")
            doc = primary_docs[i]
            return f"https://www.sec.gov/Archives/edgar/data/{cik.lstrip('0')}/{acc_clean}/{doc}"

    return None


def _extrair_do_texto(texto: str) -> dict:
    """Extrai ratings de Moody's, S&P e Fitch do texto."""
    resultado = {"moodys": None, "sp": None, "fitch": None}

    # Primeiro tenta padrão de tabela (mais confiável)
    m_table = RE_RATING_TABLE.search(texto)
    if m_table:
        resultado["moodys"] = m_table.group(1)
        resultado["sp"] = m_table.group(2)
        resultado["fitch"] = m_table.group(3)
        return resultado

    # Moody's
    m = RE_MOODY.search(texto)
    if m:
        resultado["moodys"] = next(g for g in m.groups() if g)

    # S&P
    m = RE_SP.search(texto)
    if m:
        resultado["sp"] = next(g for g in m.groups() if g)

    # Fitch
    m = RE_FITCH.search(texto)
    if m:
        resultado["fitch"] = next(g for g in m.groups() if g)

    return resultado


def buscar_ratings(ticker: str, pasta_empresa: str) -> dict:
    """
    Busca ratings de crédito da Moody's, S&P e Fitch.

    Fluxo:
    1. Verifica cache local (ratings.json)
    2. Se stale (> 90 dias) ou inexistente, busca no 10-K via SEC EDGAR
    3. Extrai ratings com regex
    4. Salva cache

    Returns:
        {"moodys": "Baa3", "sp": "BBB-", "fitch": "BBB-",
         "ticker": "OXY", "data_consulta": "2026-04-02T...",
         "fonte": "10-K 2025"}
    """
    cache_path = os.path.join(pasta_empresa, "ratings.json")

    # Verificar cache
    if os.path.exists(cache_path):
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                cached = json.load(f)
        except (UnicodeDecodeError, json.JSONDecodeError):
            with open(cache_path, "r", encoding="latin-1") as f:
                cached = json.load(f)
        dt_str = cached.get("data_consulta")
        if dt_str:
            try:
                dt = datetime.fromisoformat(dt_str)
                if datetime.now() - dt < timedelta(days=CACHE_DIAS):
                    return cached
            except ValueError:
                pass

    # Buscar no SEC EDGAR
    session = _get_session()
    ratings = {"moodys": None, "sp": None, "fitch": None, "fonte": None}

    try:
        cik = _get_cik(ticker, session)
        filing_url = _buscar_filing_url(cik, session)

        if filing_url:
            _rate_limit()
            # Baixar apenas os primeiros 3MB (ratings ficam no corpo do filing)
            resp = session.get(filing_url, timeout=60, stream=True)
            resp.raise_for_status()

            chunks = []
            tamanho = 0
            for chunk in resp.iter_content(chunk_size=65536, decode_unicode=True):
                if chunk:
                    chunks.append(chunk if isinstance(chunk, str) else chunk.decode("utf-8", errors="ignore"))
                    tamanho += len(chunks[-1])
                    if tamanho > 3_000_000:
                        break

            html = "".join(chunks)
            texto = _strip_html(html)
            ratings = _extrair_do_texto(texto)
            ratings["fonte"] = f"10-K SEC EDGAR"

    except Exception as e:
        print(f"[RATINGS] Erro ao buscar ratings para {ticker}: {e}")

    # Salvar cache (apenas se encontrou pelo menos 1 rating)
    ratings["ticker"] = ticker
    ratings["data_consulta"] = datetime.now().isoformat()
    os.makedirs(pasta_empresa, exist_ok=True)
    has_any = any(ratings.get(k) for k in ("moodys", "sp", "fitch"))
    if has_any:
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(ratings, f, ensure_ascii=False, indent=2)
    else:
        # Não cachear resultado vazio — permite inserção manual sem esperar expiração
        print(f"[RATINGS] Nenhum rating encontrado para {ticker}. Insira manualmente via dashboard.")

    return ratings
