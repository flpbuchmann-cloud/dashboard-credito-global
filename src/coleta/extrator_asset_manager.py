"""
Extrator de métricas específicas de Asset Managers via Gemini.

Extrai FRE, SRE, DE, AUM, FPAUM, Dry Powder e outras métricas non-GAAP
dos Earnings Releases (HTML/PDF) de gestoras como Apollo, Blackstone, KKR, etc.
"""

import os
import json
import re
from pathlib import Path

GEMINI_API_KEY = "AIzaSyCgS_Lzye1ogf2punzTtr0tg_C4tf79eUM"

PROMPT_AM = """You are a senior credit analyst specialized in alternative asset managers.
Extract QUARTERLY non-GAAP metrics from this Earnings Release / Supplement.

Return ONLY valid JSON (no markdown, no comments). Values in MILLIONS of USD.
Use null if not available. Extract ALL quarters shown.

JSON structure (one object per quarter):
{"periodos":[{
  "periodo": "YYYY-MM-DD",
  "tri": "QX/YY",
  "fre": 0,
  "fre_margin_pct": 0,
  "sre": 0,
  "de": 0,
  "total_aum": 0,
  "fee_paying_aum": 0,
  "permanent_capital_pct": 0,
  "dry_powder": 0,
  "management_fees": 0,
  "advisory_fees": 0,
  "performance_fees_realized": 0,
  "performance_fees_unrealized": 0,
  "net_accrued_performance": 0,
  "total_revenues_segment": 0,
  "compensation_expense": 0,
  "non_comp_expense": 0,
  "interest_expense_corp": 0,
  "gross_debt_corp": 0
}]}

DEFINITIONS:
- fre = Fee-Related Earnings (management fees - operating expenses, excluding performance)
- fre_margin_pct = FRE / Management Fees × 100 (as percentage, e.g. 55.0)
- sre = Spread-Related Earnings (Apollo/Athene specific: investment spread income)
- de = Distributable Earnings (FRE + net realized performance - taxes)
- total_aum = Total Assets Under Management
- fee_paying_aum = Fee-Paying AUM (AUM actually generating fees)
- permanent_capital_pct = Percentage of AUM that is permanent/perpetual capital
- dry_powder = Committed but uncalled capital
- management_fees = Total management/advisory fees received
- advisory_fees = Transaction/advisory fees (if separate)
- performance_fees_realized = Realized carried interest / performance fees
- performance_fees_unrealized = Unrealized (accrued) performance fees
- net_accrued_performance = Net accrued performance revenues (unrealized carry on books)
- compensation_expense = Total compensation and benefits
- non_comp_expense = Non-compensation operating expenses
- interest_expense_corp = Corporate-level interest expense (HoldCo debt service)
- gross_debt_corp = Corporate/HoldCo gross debt outstanding (balance sheet item)
"""


def _read_html_text(path: str) -> str:
    """Lê HTML e retorna texto limpo."""
    from html import unescape
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        html = f.read()
    text = re.sub(r"<style[^>]*>.*?</style>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<script[^>]*>.*?</script>", " ", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = unescape(text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _parse_response(texto: str) -> dict | None:
    """Parseia resposta do Gemini."""
    texto = texto.strip()
    if "```" in texto:
        match = re.search(r'```(?:json)?\s*\n?(.*?)```', texto, re.DOTALL)
        if match:
            texto = match.group(1).strip()
        else:
            texto = texto.replace("```json", "").replace("```", "").strip()
    texto = re.sub(r'//[^\n]*', '', texto)
    texto = re.sub(r',\s*([}\]])', r'\1', texto)
    try:
        return json.loads(texto)
    except json.JSONDecodeError:
        start = texto.find('{')
        end = texto.rfind('}')
        if start >= 0 and end > start:
            try:
                sub = texto[start:end+1]
                sub = re.sub(r'//[^\n]*', '', sub)
                sub = re.sub(r',\s*([}\]])', r'\1', sub)
                return json.loads(sub)
            except json.JSONDecodeError:
                pass
    return None


def extrair_metricas_am(doc_path: str) -> dict | None:
    """Extrai métricas de asset manager de um earnings release."""
    nome = os.path.basename(doc_path)
    ext = nome.lower().rsplit(".", 1)[-1]

    print(f"[AM_EXTRATOR] Processando: {nome}")

    try:
        import google.generativeai as genai
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel("gemini-2.5-flash")
        gen_config = genai.GenerationConfig(temperature=0.1, max_output_tokens=8192)

        if ext == "pdf":
            uploaded = genai.upload_file(doc_path, mime_type="application/pdf")
            content = [PROMPT_AM, uploaded]
        else:
            # HTML: strip style/script but KEEP table HTML structure
            with open(doc_path, "r", encoding="utf-8", errors="ignore") as f:
                raw_html = f.read()
            if len(raw_html) < 500:
                return None
            cleaned = re.sub(r"<style[^>]*>.*?</style>", " ", raw_html, flags=re.DOTALL | re.IGNORECASE)
            cleaned = re.sub(r"<script[^>]*>.*?</script>", " ", cleaned, flags=re.DOTALL | re.IGNORECASE)
            # For large docs, send first 60K + last 30K of cleaned HTML
            if len(cleaned) > 90000:
                texto_enviar = cleaned[:60000] + "\n<!-- TRUNCATED -->\n" + cleaned[-30000:]
            else:
                texto_enviar = cleaned
            content = [PROMPT_AM, f"EARNINGS RELEASE (HTML):\n\n{texto_enviar}"]

        response = model.generate_content(content, generation_config=gen_config)
        dados = _parse_response(response.text)

        if not dados or not dados.get("periodos"):
            print(f"[AM_EXTRATOR] Sem dados extraídos de: {nome}")
            return None

        # Gemini retorna valores em milhoes — manter em milhoes (padrao AM)
        for p in dados["periodos"]:
            if "tri" in p:
                p["trimestre"] = p.pop("tri")

        n = len(dados["periodos"])
        print(f"[AM_EXTRATOR] OK: {n} períodos extraídos")
        return dados

    except Exception as e:
        print(f"[AM_EXTRATOR] Erro: {e}")
        return None


def _listar_earnings_docs(pasta_docs: str) -> list[str]:
    """Lista documentos de earnings release relevantes."""
    if not os.path.isdir(pasta_docs):
        return []
    docs = []
    for f in os.listdir(pasta_docs):
        fl = f.lower()
        if not fl.endswith((".pdf", ".htm", ".html")):
            continue
        is_earnings = any(kw in fl for kw in [
            "earning", "press", "release", "resultado", "ex99",
            "ex991", "exhibit99", "exhibit991",
        ])
        if not is_earnings:
            continue
        caminho = os.path.join(pasta_docs, f)
        if os.path.getsize(caminho) < 50_000:
            continue
        docs.append(caminho)
    return sorted(docs)


def extrair_e_salvar_am(pasta_empresa: str, ticker: str) -> dict | None:
    """
    Extrai métricas AM de todos os earnings releases e salva cache.
    """
    pasta_docs = os.path.join(pasta_empresa, "Documentos")
    cache_path = os.path.join(pasta_empresa, "Dados_Extraidos", "dados_asset_manager.json")

    # Verificar cache
    if os.path.exists(cache_path):
        with open(cache_path, "r", encoding="utf-8") as f:
            cached = json.load(f)
        docs_processados = cached.get("_docs_processados", [])
        docs_atuais = _listar_earnings_docs(pasta_docs)
        if set(docs_processados) == set(os.path.basename(p) for p in docs_atuais):
            print(f"[AM_EXTRATOR] Usando cache: {cache_path}")
            return cached

    docs = _listar_earnings_docs(pasta_docs)
    if not docs:
        print(f"[AM_EXTRATOR] Nenhum earnings release encontrado")
        return None

    import time
    todos_periodos = []
    docs_nomes = []

    for doc_path in docs:
        dados = extrair_metricas_am(doc_path)
        if dados:
            todos_periodos.extend(dados.get("periodos", []))
            docs_nomes.append(os.path.basename(doc_path))
        time.sleep(1)  # Rate limit Gemini

    if not todos_periodos:
        return None

    # Deduplicar por período
    periodos_unicos = {}
    for p in todos_periodos:
        key = p.get("periodo", "")
        periodos_unicos[key] = p

    resultado = {
        "ticker": ticker,
        "fonte": "Earnings Release via Gemini (AM Metrics)",
        "periodos": sorted(periodos_unicos.values(), key=lambda x: x.get("periodo", "")),
        "_docs_processados": docs_nomes,
    }

    os.makedirs(os.path.dirname(cache_path), exist_ok=True)
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(resultado, f, ensure_ascii=False, indent=2)

    print(f"[AM_EXTRATOR] Salvo: {cache_path} ({len(periodos_unicos)} períodos)")
    return resultado


def carregar_dados_am(pasta_empresa: str) -> dict | None:
    """Carrega dados AM extraídos (se existirem)."""
    cache_path = os.path.join(pasta_empresa, "Dados_Extraidos", "dados_asset_manager.json")
    if os.path.exists(cache_path):
        with open(cache_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return None
