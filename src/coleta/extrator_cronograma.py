"""
Extrator de cronograma de amortização de dívida a partir de
Conference Call Slides, Presentations e Earnings Releases via Gemini.
"""

import os
import re
import json
import time
from datetime import datetime

GEMINI_API_KEY = "AIzaSyCgS_Lzye1ogf2punzTtr0tg_C4tf79eUM"

PROMPT_CRONOGRAMA = """Analyze this entire document carefully, including ALL charts, graphs, bar charts, and tables.

TASK: Find and extract the DEBT MATURITY SCHEDULE / MATURITY PROFILE.
This information may appear as:
- A bar chart showing debt amounts by year (e.g. "Annual Debt Maturity Profile")
- A table with maturity dates and amounts
- Text mentioning principal repayments by year
- Numbers near year labels like $24 MM, $48 MM, $367 MM next to years 2026, 2027, 2029
- "Maturity wall" or "debt schedule" graphics

ALSO look for:
- Total principal debt amount
- Cash and cash equivalents
- Recent debt repayments or reductions
- Any reference date for the schedule

Return ONLY valid JSON (no markdown, no comments). Values in MILLIONS of USD.
If no maturity information is found at all, return {"encontrado": false}.

JSON:
{"encontrado":true,"data_referencia":"YYYY-MM-DD","caixa":0,"vencimentos":{"2026":0,"2027":0,"2028":0,"2029":0,"2030":0},"divida_total":0,"notas":"description"}

RULES:
- data_referencia = reference date of the schedule or presentation date
- caixa = cash position if mentioned
- vencimentos = amounts by year in MILLIONS USD. Only include years with amounts > 0.
- "thereafter"/"beyond" goes into key "longo_prazo"
- divida_total = sum of all vencimentos
"""


def _read_doc_text(path: str) -> str:
    """Lê texto de PDF ou HTML."""
    ext = path.lower().rsplit(".", 1)[-1]

    if ext in ("htm", "html"):
        from html import unescape
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            html = f.read()
        text = re.sub(r"<style[^>]*>.*?</style>", " ", html, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<script[^>]*>.*?</script>", " ", text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<[^>]+>", " ", text)
        text = unescape(text)
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    if ext == "pdf":
        try:
            import fitz
            doc = fitz.open(path)
            text = ""
            for page in doc:
                text += page.get_text() + "\n"
            return text.strip()
        except Exception:
            return ""

    return ""


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
    texto = re.sub(r'(-?\d+\.?\d*)\s*\n\s*"', r'\1,\n"', texto)

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


def extrair_cronograma_doc(doc_path: str) -> dict | None:
    """
    Extrai cronograma de amortização de um documento (PDF ou HTML).

    Returns:
        dict com cronograma ou None
    """
    nome = os.path.basename(doc_path)
    ext = nome.lower().rsplit(".", 1)[-1]

    print(f"[CRONOGRAMA] Processando: {nome}")

    try:
        import google.generativeai as genai
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel("gemini-2.5-flash")
        gen_config = genai.GenerationConfig(temperature=0, max_output_tokens=2048)

        if ext == "pdf":
            uploaded = genai.upload_file(doc_path, mime_type="application/pdf")
            content_ref = uploaded
        else:
            texto = _read_doc_text(doc_path)
            if len(texto) < 200:
                return None
            content_ref = f"DOCUMENT CONTENT:\n\n{texto[:50000]}"

        # Extrair cronograma direto
        response = model.generate_content(
            [PROMPT_CRONOGRAMA, content_ref],
            generation_config=gen_config,
        )

        dados = _parse_response(response.text)
        if not dados or not dados.get("encontrado"):
            # Tentar prompt mais direto
            time.sleep(1)
            response2 = model.generate_content(
                ["Extract ALL debt maturity amounts by year from this document. "
                 "Look at bar charts, tables, and text. Include amounts in $MM. "
                 "Return JSON: {\"encontrado\":true,\"data_referencia\":\"YYYY-MM-DD\","
                 "\"caixa\":0,\"vencimentos\":{\"YEAR\":AMOUNT_IN_MM},\"divida_total\":0}",
                 content_ref],
                generation_config=gen_config,
            )
            dados = _parse_response(response2.text)
            if not dados or not dados.get("encontrado"):
                print(f"[CRONOGRAMA] Não conseguiu extrair de: {nome}")
                return None

        # Converter vencimentos de milhões para unidades
        vencimentos = {}
        for k, v in dados.get("vencimentos", {}).items():
            if v and v > 0:
                vencimentos[k] = v * 1e6

        if not vencimentos:
            return None

        # Vincular ao trimestre fechado mais próximo (não usar datas de apresentação)
        data_ref = dados.get("data_referencia", "")
        # Se a data não é fim de trimestre, ajustar para o último fim de tri
        fins_tri = ["03-31", "06-30", "09-30", "12-31"]
        if data_ref and data_ref[-5:] not in fins_tri:
            from datetime import datetime as _dt
            try:
                dt = _dt.strptime(data_ref, "%Y-%m-%d")
                # Recuar para o fim do trimestre anterior
                mes = dt.month
                ano = dt.year
                if mes <= 3:
                    data_ref = f"{ano - 1}-12-31"
                elif mes <= 6:
                    data_ref = f"{ano}-03-31"
                elif mes <= 9:
                    data_ref = f"{ano}-06-30"
                else:
                    data_ref = f"{ano}-09-30"
            except ValueError:
                pass

        cronograma = {
            "data_referencia": data_ref,
            "caixa": (dados.get("caixa") or 0) * 1e6 if dados.get("caixa") else None,
            "vencimentos": vencimentos,
            "divida_total": sum(vencimentos.values()),
            "arquivo": f"Extraído de {nome} via Gemini",
        }

        print(f"[CRONOGRAMA] Encontrado: {len(vencimentos)} faixas, total ${cronograma['divida_total']/1e9:.1f}B")
        return cronograma

    except Exception as e:
        print(f"[CRONOGRAMA] Erro: {e}")
        return None


def extrair_cronogramas_pasta(pasta_empresa: str, ticker: str) -> list[dict]:
    """
    Busca presentations/slides na pasta Documentos e extrai cronogramas.
    Salva no cronogramas.json existente (adiciona, não sobrescreve).

    Returns:
        lista de cronogramas extraídos
    """
    pasta_docs = os.path.join(pasta_empresa, "Documentos")
    if not os.path.isdir(pasta_docs):
        return []

    # Listar documentos que podem ter cronograma (presentations, slides, earnings)
    candidatos = []
    for f in os.listdir(pasta_docs):
        fl = f.lower()
        if not fl.endswith((".pdf", ".htm", ".html")):
            continue
        # Priorizar presentations/slides, mas também checar earnings releases grandes
        is_presentation = any(kw in fl for kw in ["presentation", "slide", "conference", "investor"])
        is_earnings = any(kw in fl for kw in ["earning", "press", "release", "ex99"])
        if is_presentation or (is_earnings and os.path.getsize(os.path.join(pasta_docs, f)) > 100_000):
            candidatos.append(os.path.join(pasta_docs, f))

    if not candidatos:
        return []

    # Carregar cronogramas existentes
    cronogramas_path = os.path.join(pasta_empresa, "Dados_EDGAR", "cronogramas.json")
    cronogramas_existentes = []
    if os.path.exists(cronogramas_path):
        with open(cronogramas_path, "r", encoding="utf-8") as f:
            cronogramas_existentes = json.load(f)

    # Verificar quais documentos já foram processados
    fontes_existentes = {c.get("arquivo", "") for c in cronogramas_existentes}

    novos = []
    for doc_path in sorted(candidatos, reverse=True):  # Mais recentes primeiro
        nome = os.path.basename(doc_path)
        fonte_id = f"Extraído de {nome} via Gemini"
        if fonte_id in fontes_existentes:
            print(f"[CRONOGRAMA] Já processado: {nome}")
            continue

        cronograma = extrair_cronograma_doc(doc_path)
        if cronograma:
            # Não salvar se já existe XBRL para a mesma data com dívida maior
            dr = cronograma.get("data_referencia", "")
            xbrl_mesmo_tri = [
                c for c in cronogramas_existentes
                if c.get("data_referencia") == dr and "Gemini" not in c.get("arquivo", "")
            ]
            if xbrl_mesmo_tri and xbrl_mesmo_tri[0].get("divida_total", 0) > cronograma.get("divida_total", 0):
                print(f"[CRONOGRAMA] XBRL já existe para {dr} com dívida maior, pulando")
                continue
            novos.append(cronograma)
            cronogramas_existentes.append(cronograma)

        # Rate limit do Gemini
        time.sleep(2)

    # Salvar
    if novos:
        os.makedirs(os.path.dirname(cronogramas_path), exist_ok=True)
        with open(cronogramas_path, "w", encoding="utf-8") as f:
            json.dump(cronogramas_existentes, f, ensure_ascii=False, indent=2)
        print(f"[CRONOGRAMA] {len(novos)} novo(s) cronograma(s) salvo(s)")

    return novos
