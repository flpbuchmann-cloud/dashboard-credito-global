"""
Extrator de dados financeiros de Earnings Releases (PDF) via Google Gemini.

Lê o PDF do earnings release, envia ao Gemini para extração estruturada
de DRE, Balanço e Fluxo de Caixa, e salva em dados_earnings.json.
"""

import os
import json
import glob
from pathlib import Path

GEMINI_API_KEY = "AIzaSyCgS_Lzye1ogf2punzTtr0tg_C4tf79eUM"
LLAMA_PARSE_KEY = "llx-fGAs8gpLnUzgC8BQbsNUkriytL5NPtjXJSNC6U3DaysmOplS"

PROMPT_EXTRACAO = """You are a financial analyst. Extract QUARTERLY financial data from this Earnings Release.

Return ONLY valid JSON (no markdown, no comments). Values in MILLIONS of USD.
Costs and expenses must be NEGATIVE. Use null if not available.
Extract ALL quarters shown in the document (current year Q1-Q4 and prior year if available).
Use CONSOLIDATED TOTAL figures (not just continuing operations).
Revenue = Total Revenues or Net Sales (whichever is more complete).
EBIT = Operating Income or Income Before Interest and Taxes.
Net Income = Net Income attributable to common stockholders.

JSON structure (one object per quarter). Use SHORT field names exactly as shown:
{"periodos":[{"periodo":"YYYY-MM-DD","tri":"QX/YY","dre":{"rev":0,"cogs":0,"gp":0,"sga":0,"ebit":0,"dda":0,"int_exp":0,"ebt":0,"tax":0,"ni":0},"bs":{"assets":0,"ca":0,"cash":0,"ar":0,"inv":0,"cl":0,"std":0,"ltd":0,"eq":0},"cf":{"cfo":0,"capex":0,"div":0}}]}
"""


def _parse_llm_response(texto: str) -> dict | None:
    """Limpa resposta do LLM e parseia JSON."""
    import re

    texto = texto.strip()
    # Remover markdown code blocks
    if "```" in texto:
        match = re.search(r'```(?:json)?\s*\n?(.*?)```', texto, re.DOTALL)
        if match:
            texto = match.group(1).strip()
        else:
            texto = texto.replace("```json", "").replace("```", "").strip()

    # Remover comentários // no JSON (Gemini às vezes adiciona)
    texto = re.sub(r'//[^\n]*', '', texto)
    # Remover trailing commas antes de } ou ]
    texto = re.sub(r',\s*([}\]])', r'\1', texto)
    # Corrigir campos sem vírgula entre eles (ex: "capex": -243\n"div": -26)
    texto = re.sub(r'(-?\d+\.?\d*)\s*\n\s*"', r'\1,\n"', texto)

    try:
        dados = json.loads(texto)
    except json.JSONDecodeError:
        # Tentar encontrar o JSON dentro do texto
        start = texto.find('{')
        end = texto.rfind('}')
        if start >= 0 and end > start:
            try:
                subtexto = texto[start:end+1]
                subtexto = re.sub(r'//[^\n]*', '', subtexto)
                subtexto = re.sub(r',\s*([}\]])', r'\1', subtexto)
                dados = json.loads(subtexto)
            except json.JSONDecodeError as e:
                print(f"[PARSE] JSON inválido mesmo após limpeza: {e}")
                print(f"[PARSE] Trecho: ...{subtexto[max(0,e.pos-50):e.pos+50]}...")
                return None
        else:
            return None

    # Mapear nomes curtos → nomes internos do dashboard + converter milhões → unidades
    SECAO_MAP = {
        "dre": "dre", "bs": "balanco", "cf": "fluxo_caixa",
    }
    FIELD_MAP = {
        # DRE
        "rev": "receita_liquida", "cogs": "custo", "gp": "resultado_bruto",
        "sga": "despesas_ga", "ebit": "ebit", "dda": "depreciacao_amortizacao",
        "int_exp": "despesas_financeiras", "ebt": "lucro_antes_ir",
        "tax": "ir_csll", "ni": "lucro_liquido",
        # Balanço
        "assets": "ativo_total", "ca": "ativo_circulante", "cash": "caixa",
        "ar": "contas_a_receber", "inv": "estoques",
        "cl": "passivo_circulante", "std": "emprestimos_cp",
        "ltd": "emprestimos_lp", "eq": "patrimonio_liquido",
        # Fluxo de Caixa
        "cfo": "fco", "capex": "capex", "div": "dividendos_pagos",
        # Já no formato correto (fallback)
        "tri": "trimestre",
    }

    for periodo in dados.get("periodos", []):
        # Renomear "tri" → "trimestre"
        if "tri" in periodo:
            periodo["trimestre"] = periodo.pop("tri")

        # Renomear seções
        for old_sec, new_sec in SECAO_MAP.items():
            if old_sec in periodo and old_sec != new_sec:
                periodo[new_sec] = periodo.pop(old_sec)

        for secao in ["dre", "balanco", "fluxo_caixa"]:
            if secao in periodo and periodo[secao]:
                secao_data = periodo[secao]
                # Renomear campos
                keys = list(secao_data.keys())
                for old_key in keys:
                    new_key = FIELD_MAP.get(old_key, old_key)
                    if new_key != old_key:
                        secao_data[new_key] = secao_data.pop(old_key)
                # Converter milhões → unidades
                for chave, valor in secao_data.items():
                    if isinstance(valor, (int, float)) and valor is not None:
                        secao_data[chave] = valor * 1e6

    return dados


def _extrair_via_gemini(pdf_path: str) -> dict | None:
    """Extrai via Google Gemini (upload PDF direto)."""
    import google.generativeai as genai
    genai.configure(api_key=GEMINI_API_KEY)

    uploaded_file = genai.upload_file(pdf_path, mime_type="application/pdf")
    model = genai.GenerativeModel("gemini-2.5-flash")
    response = model.generate_content(
        [PROMPT_EXTRACAO, uploaded_file],
        generation_config=genai.GenerationConfig(
            temperature=0.1,
            max_output_tokens=8192,
        ),
    )
    return _parse_llm_response(response.text)


def _extrair_via_llamaparse(pdf_path: str) -> dict | None:
    """Extrai via LlamaParse (converte PDF → markdown → Gemini para estruturar)."""
    from llama_parse import LlamaParse

    # Converter PDF para markdown via LlamaParse
    parser = LlamaParse(
        api_key=LLAMA_PARSE_KEY,
        result_type="markdown",
        language="en",
    )
    documents = parser.load_data(pdf_path)
    markdown_text = "\n\n".join(doc.text for doc in documents)

    if not markdown_text.strip():
        return None

    # Tentar Gemini com texto (sem upload de arquivo — cota diferente)
    try:
        import google.generativeai as genai
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel("gemini-2.5-flash")
        response = model.generate_content(
            [PROMPT_EXTRACAO, f"CONTEÚDO DO EARNINGS RELEASE:\n\n{markdown_text[:50000]}"],
            generation_config=genai.GenerationConfig(temperature=0.1, max_output_tokens=8192),
        )
        return _parse_llm_response(response.text)
    except Exception as e:
        print(f"[LLAMAPARSE] Gemini falhou, tentando extração local: {e}")

    # Fallback: usar pymupdf para ler texto e retornar markdown
    # para posterior processamento manual
    return None


def _extrair_via_pymupdf(pdf_path: str) -> str:
    """Fallback: extrai texto puro do PDF via pymupdf."""
    import fitz
    doc = fitz.open(pdf_path)
    texto = ""
    for page in doc:
        texto += page.get_text() + "\n"
    return texto


def _read_html_text(path: str) -> str:
    """Lê HTML e retorna texto limpo."""
    import re as _re
    from html import unescape
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        html = f.read()
    text = _re.sub(r"<style[^>]*>.*?</style>", " ", html, flags=_re.DOTALL | _re.IGNORECASE)
    text = _re.sub(r"<script[^>]*>.*?</script>", " ", text, flags=_re.DOTALL | _re.IGNORECASE)
    text = _re.sub(r"<[^>]+>", " ", text)
    text = unescape(text)
    text = _re.sub(r"\s+", " ", text)
    return text.strip()


def extrair_dados_doc(doc_path: str) -> dict | None:
    """
    Extrai dados financeiros de um Earnings Release (PDF ou HTML).
    Tenta: Gemini (upload/texto) → LlamaParse → None.

    Returns:
        dict com dados estruturados ou None se falhar
    """
    nome = os.path.basename(doc_path)
    is_html = nome.lower().endswith((".htm", ".html"))

    # Para HTML: extrair texto e enviar como texto ao Gemini
    if is_html:
        print(f"[EXTRATOR] Processando HTML: {nome}")
        try:
            texto = _read_html_text(doc_path)
            if len(texto) < 500:
                print(f"[EXTRATOR] HTML muito curto, pulando")
                return None

            import google.generativeai as genai
            genai.configure(api_key=GEMINI_API_KEY)
            model = genai.GenerativeModel("gemini-2.5-flash")
            response = model.generate_content(
                [PROMPT_EXTRACAO, f"EARNINGS RELEASE CONTENT:\n\n{texto[:60000]}"],
                generation_config=genai.GenerationConfig(temperature=0.1, max_output_tokens=8192),
            )
            dados = _parse_llm_response(response.text)
            if dados:
                print(f"[EXTRATOR] Gemini OK (HTML): {len(dados.get('periodos', []))} períodos")
                dados["_metodo"] = "gemini_html"
                return dados
        except Exception as e:
            print(f"[EXTRATOR] Gemini HTML falhou: {e}")
        return None

    # Para PDF: upload direto ao Gemini
    print(f"[EXTRATOR] Tentando Gemini para: {nome}")
    try:
        dados = _extrair_via_gemini(doc_path)
        if dados:
            print(f"[EXTRATOR] Gemini OK: {len(dados.get('periodos', []))} períodos")
            dados["_metodo"] = "gemini"
            return dados
    except Exception as e:
        print(f"[EXTRATOR] Gemini falhou: {e}")

    # Tentativa 2: LlamaParse → Gemini com texto
    print(f"[EXTRATOR] Tentando LlamaParse para: {nome}")
    try:
        dados = _extrair_via_llamaparse(doc_path)
        if dados:
            print(f"[EXTRATOR] LlamaParse OK: {len(dados.get('periodos', []))} períodos")
            dados["_metodo"] = "llamaparse+gemini"
            return dados
    except Exception as e:
        print(f"[EXTRATOR] LlamaParse falhou: {e}")

    print(f"[EXTRATOR] Todas as tentativas falharam para: {nome}")
    return None


def extrair_e_salvar(pasta_empresa: str, ticker: str) -> dict | None:
    """
    Busca PDFs de earnings release na pasta Documentos, extrai dados e salva.

    Returns:
        dict com dados extraídos ou None
    """
    pasta_docs = os.path.join(pasta_empresa, "Documentos")
    cache_path = os.path.join(pasta_empresa, "Dados_Extraidos", "dados_earnings.json")

    # Verificar cache
    if os.path.exists(cache_path):
        with open(cache_path, "r", encoding="utf-8") as f:
            cached = json.load(f)
        # Se já tem dados e os mesmos PDFs, usar cache
        pdfs_processados = cached.get("_pdfs_processados", [])
        pdfs_atuais = _listar_earnings_docs(pasta_docs, ticker)
        if set(pdfs_processados) == set(os.path.basename(p) for p in pdfs_atuais):
            print(f"[GEMINI] Usando cache: {cache_path}")
            return cached

    # Buscar PDFs
    pdfs = _listar_earnings_docs(pasta_docs, ticker)
    if not pdfs:
        print(f"[GEMINI] Nenhum PDF de earnings release encontrado em {pasta_docs}")
        return None

    # Extrair dados de cada PDF
    todos_periodos = []
    empresa = ticker
    pdfs_nomes = []

    for pdf_path in pdfs:
        dados = extrair_dados_doc(pdf_path)
        if dados:
            empresa = dados.get("empresa", ticker)
            todos_periodos.extend(dados.get("periodos", []))
            pdfs_nomes.append(os.path.basename(pdf_path))

    if not todos_periodos:
        return None

    # Deduplicar por período (manter o mais recente)
    periodos_unicos = {}
    for p in todos_periodos:
        key = p.get("periodo", "")
        periodos_unicos[key] = p

    resultado = {
        "empresa": empresa,
        "ticker": ticker,
        "moeda": "USD",
        "fonte": "Earnings Release via Gemini",
        "periodos": list(periodos_unicos.values()),
        "_pdfs_processados": pdfs_nomes,
    }

    # Salvar
    os.makedirs(os.path.dirname(cache_path), exist_ok=True)
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(resultado, f, ensure_ascii=False, indent=2)

    print(f"[GEMINI] Dados salvos: {cache_path}")
    return resultado


def _listar_earnings_docs(pasta_docs: str, ticker: str) -> list[str]:
    """Lista PDFs e HTMLs de earnings release na pasta de documentos."""
    if not os.path.isdir(pasta_docs):
        return []

    docs = []
    for f in os.listdir(pasta_docs):
        fl = f.lower()
        if not fl.endswith((".pdf", ".htm", ".html")):
            continue
        # Filtrar por keywords de earnings release
        is_earnings = any(kw in fl for kw in [
            "earning", "press", "release", "resultado", "ex99", "exhibit99",
        ])
        if not is_earnings:
            continue
        # Filtrar por tamanho mínimo (earnings releases reais > 100KB)
        caminho = os.path.join(pasta_docs, f)
        if os.path.getsize(caminho) < 100_000:
            continue
        docs.append(caminho)

    return sorted(docs)


def carregar_dados_earnings(pasta_empresa: str) -> dict | None:
    """Carrega dados extraídos do earnings release (se existirem)."""
    cache_path = os.path.join(pasta_empresa, "Dados_Extraidos", "dados_earnings.json")
    if os.path.exists(cache_path):
        with open(cache_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return None
