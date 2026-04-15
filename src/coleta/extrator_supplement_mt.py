"""
Extrator de earnings releases da ArcelorMittal (MT, ARCXF, AMSYF).

Fonte: https://corporate.arcelormittal.com/investors/financial-reports
Formato: PDF com tabelas trimestrais rotativas (5 colunas de trimestres,
ja desacumuladas em "three months ended"). Todos os valores em USD milhoes.

Paginas tipicas:
  - Financial highlights (5 trimestres: Sales, OI, NI, EBITDA)
  - Balance Sheet (3 colunas: current q, Dec prior, prior year same q)
  - Income Statement (5 colunas trimestrais, 'Three months ended')
  - Cash Flow Statement (5 colunas trimestrais)
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

import fitz


MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
}

_NUM_RE = re.compile(r"-?\d{1,3}(?:,\d{3})*(?:\.\d+)?")


def _to_float(tok: str) -> Optional[float]:
    if tok is None:
        return None
    t = tok.strip().replace("\u2013", "-").replace("\u2212", "-").replace("\xa0", " ")
    t = t.replace(" ", "").rstrip("%").replace(",", "")
    if t in {"", "-", ".", "—"}:
        return None
    try:
        return float(t)
    except ValueError:
        return None


def _numbers_in(line: str) -> list[float]:
    out = []
    # Parenteses = negativos: "(390)" -> -390
    line2 = re.sub(r"\((\d[\d,]*(?:\.\d+)?)\)", r"-\1", line)
    line2 = re.sub(r"[\u2013\u2212](?=\d)", "-", line2)
    for m in _NUM_RE.findall(line2):
        v = _to_float(m)
        if v is not None:
            out.append(v)
    return out


def _page_lines(page) -> list[str]:
    return [ln.strip() for ln in page.get_text().splitlines() if ln.strip()]


_DATE_RE = re.compile(r"([A-Za-z]+)\.?\s+(\d{1,2}),?\s+(\d{4})")


def _parse_period_header(s: str) -> Optional[str]:
    """Converte 'Mar 31, 2025' -> '2025-03-31'."""
    m = _DATE_RE.search(s)
    if not m:
        return None
    mo_str = m.group(1).lower().rstrip(".")
    mo = MONTHS.get(mo_str[:4]) or MONTHS.get(mo_str[:3])
    if not mo:
        return None
    return f"{int(m.group(3)):04d}-{mo:02d}-{int(m.group(2)):02d}"


def _parse_all_dates(s: str) -> list[str]:
    """Extrai TODAS as datas em uma linha."""
    out = []
    for m in _DATE_RE.finditer(s):
        mo_str = m.group(1).lower().rstrip(".")
        mo = MONTHS.get(mo_str[:4]) or MONTHS.get(mo_str[:3])
        if mo:
            out.append(f"{int(m.group(3)):04d}-{mo:02d}-{int(m.group(2)):02d}")
    return out


def _find_headers_nearby(lines: list[str], start: int, n: int) -> Optional[list[str]]:
    """Procura datas nas proximas ~30 linhas apos start. Suporta:
    - multiplas datas na mesma linha ("Dec 31, 2024 Sept 30, 2024")
    - datas quebradas em 2 linhas ("Dec 31,\n2022")
    """
    datas: list[str] = []
    i = start
    end = min(start + 30, len(lines))
    while i < end:
        ln = lines[i]
        ds = _parse_all_dates(ln)
        if ds:
            datas.extend(ds)
            i += 1
            continue
        # tentar juntar com proxima linha (data quebrada)
        if i + 1 < end:
            joined = ln + " " + lines[i + 1]
            ds2 = _parse_all_dates(joined)
            if ds2:
                datas.extend(ds2)
                i += 2
                continue
        i += 1
    return datas[:n] if datas else None


def _count_quarterly_columns(lines: list[str]) -> int:
    """Retorna quantas colunas 'Three months ended' existem."""
    for k, ln in enumerate(lines):
        if "Three months ended" in ln:
            hdrs = _find_headers_nearby(lines, k + 1, 10)
            return len(hdrs) if hdrs else 0
    return 0


def _collect_row(lines: list[str], label: str, n: int, start_from: int = 0) -> Optional[tuple[int, list[float]]]:
    """Acha primeira linha que contem o label apos start_from e coleta os
    primeiros n numeros das linhas seguintes. Retorna (indice da linha, nums)."""
    for i in range(start_from, len(lines)):
        if label.lower() in lines[i].lower():
            nums: list[float] = []
            j = i + 1
            while len(nums) < n and j < len(lines) and j < i + 20:
                nums.extend(_numbers_in(lines[j]))
                j += 1
            if len(nums) >= n:
                return i, nums[:n]
    return None


def _exact_row(lines: list[str], label: str, n: int, start_from: int = 0) -> Optional[list[float]]:
    """Busca match exato do label (case-insensitive) e extrai n numeros."""
    for i in range(start_from, len(lines)):
        if lines[i].strip().lower() == label.lower():
            nums: list[float] = []
            j = i + 1
            while len(nums) < n and j < len(lines) and j < i + 20:
                nums.extend(_numbers_in(lines[j]))
                j += 1
            if len(nums) >= n:
                return nums[:n]
    return None


# ---------------------------------------------------------------------------
# Parsers por demonstracao
# ---------------------------------------------------------------------------
def _parse_income_statement(doc, report_quarter: int = 1) -> dict[str, dict]:
    """Extrai da pagina 'Condensed Consolidated Statement of Operations'.
    Retorna dict[periodo] = {campo: valor em USD milhoes}."""
    for i in range(len(doc)):
        t = doc[i].get_text()
        if ("Consolidated Statement" in t and "of Operations" in t
                and "Sales" in t and "Operating" in t and "(A)" in t):
            lines = _page_lines(doc[i])
            break
    else:
        return {}

    # Cabecalhos: 5 quarterly se 1Q report, senao 3 quarterly + 2 cumulative
    n_q = 5 if report_quarter == 1 else 3
    headers = None
    for k, ln in enumerate(lines):
        if "Three months ended" in ln:
            all_dates = _find_headers_nearby(lines, k + 1, 10) or []
            headers = all_dates[:n_q]
            if headers:
                break
    if not headers:
        return {}
    n = len(headers)

    out: dict[str, dict] = {p: {} for p in headers}

    def _row(label: str, key: str, exact: bool = False):
        r = (_exact_row(lines, label, n) if exact
             else _collect_row(lines, label, n))
        if r:
            vals = r if exact else r[1]
            for idx, p in enumerate(headers):
                out[p][key] = vals[idx]

    _row("Sales", "revenue", exact=True)
    _row("Depreciation (B)", "depreciacao", exact=False)
    # EBIT row: marcador robusto (pode ser "Operating income (A)" ou "Operating (loss)income (A)")
    for i, ln in enumerate(lines):
        if "(A)" in ln and "Operating" in ln and "margin" not in ln:
            nums: list[float] = []
            j = i + 1
            while len(nums) < n and j < len(lines) and j < i + 20:
                nums.extend(_numbers_in(lines[j])); j += 1
            if len(nums) >= n:
                for idx, p in enumerate(headers):
                    out[p]["ebit"] = nums[idx]
                break
    _row("Income from associates, joint ventures", "equity_income")
    _row("Net interest expense", "net_interest")
    _row("Foreign exchange and other net financing", "fx_other_fin")
    _row("Income before taxes", "ebt")
    _row("Income tax expense (net)", "tax")
    _row("attributable to equity holders of the parent", "net_income")
    _row("EBITDA (A-B+C)", "ebitda")
    return out


def _parse_balance_sheet(doc) -> dict[str, dict]:
    for i in range(len(doc)):
        t = doc[i].get_text()
        if ("Consolidated Statement" in t and "Financial Position" in t
                and "Total Assets" in t and "Total Equity" in t):
            lines = _page_lines(doc[i])
            break
    else:
        return {}

    # Cabecalhos: 3 datas apos "In millions of U.S. dollars"
    headers = None
    for k, ln in enumerate(lines):
        if "In millions of U.S. dollars" in ln:
            headers = _find_headers_nearby(lines, k + 1, 3)
            if headers:
                break
    if not headers:
        return {}

    out: dict[str, dict] = {p: {} for p in headers}

    def _row(label: str, key: str, exact: bool = False):
        r = (_exact_row(lines, label, 3) if exact
             else _collect_row(lines, label, 3))
        if r:
            vals = r if exact else r[1]
            for idx, p in enumerate(headers):
                out[p][key] = vals[idx]

    _row("Cash and cash equivalents", "cash")
    _row("Trade accounts receivable and other", "trade_receivables")
    _row("Inventories", "inventories", exact=True)
    _row("Prepaid expenses and other current assets", "prepaid")
    _row("Total Current Assets", "current_assets")
    _row("Goodwill and intangible assets", "intangibles")
    _row("Property, plant and equipment", "ppe", exact=True)
    _row("Investments in associates and joint ventures", "investments")
    _row("Total Assets", "total_assets", exact=True)
    _row("Short-term debt and current portion of long-term debt", "st_debt")
    _row("Trade accounts payable and other", "trade_payables")
    _row("Accrued expenses and other current liabilities", "accrued")
    _row("Total Current Liabilities", "current_liab")
    _row("Long-term debt, net of current portion", "lt_debt")
    _row("Total Liabilities", "total_liab", exact=True)
    _row("Total Equity", "total_equity", exact=True)
    return out


def _parse_cash_flow(doc, report_quarter: int = 1) -> dict[str, dict]:
    for i in range(len(doc)):
        t = doc[i].get_text()
        if (("Consolidated Statement" in t and "Cash flows" in t)
                or ("Operating activities" in t and "Investing activities" in t
                    and "Financing activities" in t and "Three months ended" in t)):
            lines = _page_lines(doc[i])
            break
    else:
        return {}

    n_q = 5 if report_quarter == 1 else 3
    headers = None
    for k, ln in enumerate(lines):
        if "Three months ended" in ln:
            all_dates = _find_headers_nearby(lines, k + 1, 10) or []
            headers = all_dates[:n_q]
            if headers:
                break
    if not headers:
        return {}
    n = len(headers)

    out: dict[str, dict] = {p: {} for p in headers}

    def _row(label: str, key: str, exact: bool = False):
        r = (_exact_row(lines, label, n) if exact
             else _collect_row(lines, label, n))
        if r:
            vals = r if exact else r[1]
            for idx, p in enumerate(headers):
                out[p][key] = vals[idx]

    _row("operating activities (A)", "fco")
    _row("Purchase of property, plant and equipment", "capex")
    _row("Net cash used in investing activities", "fci")
    _row("Dividends paid to ArcelorMittal shareholders", "dividends")
    _row("Share buyback", "buyback")
    _row("Net cash provided/(used) by financing activities", "fcfin")
    _row("Free cash flow (A+B+C)", "fcf")
    _row("Depreciation and impairments", "dep_amort")
    return out


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def _trimestre_label(periodo: str) -> str:
    y, mo, _ = periodo.split("-")
    q = {3: 1, 6: 2, 9: 3, 12: 4}[int(mo)]
    return f"{q}Q{y[2:]}"


def extrair_supplement_mt(pasta_docs: str, pasta_destino: str) -> list[dict]:
    pasta = Path(pasta_docs)
    destino = Path(pasta_destino)
    destino.mkdir(parents=True, exist_ok=True)

    consolidated: dict[str, dict] = {}
    # ordenar por (ano, tri) crescente para que PDFs mais recentes sobrescrevam
    def _key(p: Path) -> tuple[int, int]:
        m = re.match(r"(\d)q(\d{2})", p.stem)
        if m:
            return (2000 + int(m.group(2)), int(m.group(1)))
        return (0, 0)

    pdfs = sorted(pasta.glob("*q*-earnings-release*.pdf"), key=_key)
    if not pdfs:
        raise FileNotFoundError(f"Nenhum earnings release em {pasta}")

    for pdf in pdfs:
        try:
            rq_match = re.match(r"(\d)q", pdf.stem)
            rq = int(rq_match.group(1)) if rq_match else 1
            doc = fitz.open(pdf)
            is_data = _parse_income_statement(doc, report_quarter=rq)
            bs_data = _parse_balance_sheet(doc)
            cf_data = _parse_cash_flow(doc, report_quarter=rq)
            doc.close()
        except Exception as e:
            print(f"  [WARN] {pdf.name}: {e}")
            continue

        for p, d in is_data.items():
            consolidated.setdefault(p, {}).update({f"is_{k}": v for k, v in d.items()})
        for p, d in bs_data.items():
            consolidated.setdefault(p, {}).update({f"bs_{k}": v for k, v in d.items()})
        for p, d in cf_data.items():
            consolidated.setdefault(p, {}).update({f"cf_{k}": v for k, v in d.items()})
        consolidated.setdefault(next(iter(is_data), ""), {})["_fonte"] = pdf.name
        print(f"  OK {pdf.name} is={len(is_data)} bs={len(bs_data)} cf={len(cf_data)}")

    # Filtrar periodos sem revenue (ruido)
    periodos_validos = sorted(
        [p for p, d in consolidated.items()
         if p and d.get("is_revenue") is not None]
    )

    # ----- supplement_data.json (USD milhoes) -----
    supplement: list[dict] = []
    for periodo in periodos_validos:
        d = consolidated[periodo]
        entry = {
            "periodo": periodo,
            "trimestre": _trimestre_label(periodo),
            "moeda_original": "USD",
            "fx_rate": 1.0,
            "income_statement": {
                "total_income": d.get("is_revenue"),
                "ebit": d.get("is_ebit"),
                "depreciacao_amortizacao": abs(d["is_depreciacao"]) if d.get("is_depreciacao") else None,
                "ebitda": d.get("is_ebitda"),
                "net_income": d.get("is_net_income"),
                "net_interest": d.get("is_net_interest"),
                "equity_income": d.get("is_equity_income"),
                "ebt": d.get("is_ebt"),
                "tax": d.get("is_tax"),
            },
            "balance_sheet": {
                "cash": d.get("bs_cash"),
                "trade_receivables": d.get("bs_trade_receivables"),
                "inventories": d.get("bs_inventories"),
                "current_assets": d.get("bs_current_assets"),
                "ppe": d.get("bs_ppe"),
                "intangibles": d.get("bs_intangibles"),
                "total_assets": d.get("bs_total_assets"),
                "st_debt": d.get("bs_st_debt"),
                "trade_payables": d.get("bs_trade_payables"),
                "current_liab": d.get("bs_current_liab"),
                "lt_debt": d.get("bs_lt_debt"),
                "total_equity": d.get("bs_total_equity"),
            },
            "cash_flow": {
                "fco": d.get("cf_fco"),
                "capex": d.get("cf_capex"),
                "fci": d.get("cf_fci"),
                "dividends_paid": d.get("cf_dividends"),
                "buyback": d.get("cf_buyback"),
                "fcf": d.get("cf_fcf"),
                "dep_amort": d.get("cf_dep_amort"),
            },
        }
        supplement.append(entry)

    (destino / "supplement_data.json").write_text(
        json.dumps(supplement, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    # ----- cronogramas vazio -----
    (destino / "cronogramas.json").write_text(
        json.dumps([], ensure_ascii=False), encoding="utf-8"
    )

    # ----- ratings -----
    # ArcelorMittal: Moodys Baa3 / SP BBB- / Fitch BBB- (investment grade low)
    (destino / "ratings.json").write_text(json.dumps({
        "empresa": "ArcelorMittal",
        "ticker": "MT",
        "ratings_atuais": {
            "Moodys": {"rating": "Baa3", "outlook": "Stable"},
            "SP": {"rating": "BBB-", "outlook": "Stable"},
            "Fitch": {"rating": "BBB-", "outlook": "Stable"},
        },
        "fonte": "Public ratings agencies",
    }, indent=2, ensure_ascii=False), encoding="utf-8")

    # ----- ri_website -----
    (destino / "ri_website.json").write_text(json.dumps({
        "empresa": "ArcelorMittal",
        "ticker": "MT",
        "ri_url": "https://corporate.arcelormittal.com/investors",
        "documentos_url": "https://corporate.arcelormittal.com/investors/financial-reports",
    }, indent=2, ensure_ascii=False), encoding="utf-8")

    # ----- contas_chave.json (lista flat; DFP_* para evitar desacumulacao) -----
    def m(v):
        return v * 1e6 if v is not None else None

    contas: list[dict] = []
    for entry in supplement:
        periodo = entry["periodo"]
        is_ = entry["income_statement"]
        bs = entry["balance_sheet"]
        cf = entry["cash_flow"]
        ano = int(periodo.split("-")[0])

        # Net interest tipicamente negativo (despesa); mapear como despesas_fin
        ni = is_.get("net_interest")
        if ni is not None and ni > 0:
            desp_fin = 0.0
            rec_fin = m(ni)
        else:
            desp_fin = m(ni) if ni is not None else 0.0
            rec_fin = 0.0

        # Custo proxy: earnings release nao discrimina COGS.
        # Usar custo = -(receita - ebitda) como proxy para capital de giro.
        rec_v = is_["total_income"]; ebitda_v = is_["ebitda"]
        custo_proxy = -(rec_v - ebitda_v) if (rec_v is not None and ebitda_v is not None) else 0.0
        contas.append({"periodo": periodo, "tipo": "ITR_dre", "ano": ano, "contas": {
            "receita_liquida": m(is_["total_income"]),
            "custo": m(custo_proxy) if custo_proxy is not None else 0.0,
            "resultado_bruto": m(rec_v + custo_proxy) if (rec_v is not None and custo_proxy is not None) else None,
            "ebit": m(is_["ebit"]),
            "ebitda": m(is_["ebitda"]),
            "depreciacao_amortizacao": m(is_["depreciacao_amortizacao"]),
            "lucro_liquido": m(is_["net_income"]),
            "despesas_financeiras": desp_fin,
            "receitas_financeiras": rec_fin,
            "resultado_financeiro": m(is_.get("net_interest")),
            "lucro_antes_ir": m(is_.get("ebt")),
            "ir_csll": m(is_.get("tax")),
        }})
        contas.append({"periodo": periodo, "tipo": "ITR_bpa", "ano": ano, "contas": {
            "caixa": m(bs["cash"]),
            "contas_a_receber": m(bs["trade_receivables"]),
            "estoques_cp": m(bs["inventories"]),
            "ativo_circulante": m(bs["current_assets"]),
            "imobilizado": m(bs["ppe"]),
            "intangivel": m(bs["intangibles"]),
            "ativo_total": m(bs["total_assets"]),
        }})
        contas.append({"periodo": periodo, "tipo": "ITR_bpp", "ano": ano, "contas": {
            "emprestimos_cp": m(bs["st_debt"]),
            "fornecedores": m(bs["trade_payables"]),
            "passivo_circulante": m(bs["current_liab"]),
            "emprestimos_lp": m(bs["lt_debt"]),
            "patrimonio_liquido": m(bs["total_equity"]),
        }})
        contas.append({"periodo": periodo, "tipo": "ITR_dfc", "ano": ano, "contas": {
            "fco": m(cf["fco"]),
            "capex": m(cf["capex"]),
            "fci": m(cf.get("fci")),
            "fcf": m(cf.get("fcf")),
            "depreciacao_amortizacao": m(is_["depreciacao_amortizacao"]),
            "dividendos_pagos": m(cf.get("dividends_paid")),
            "juros_pagos": None,
        }})

    (destino / "contas_chave.json").write_text(
        json.dumps(contas, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    return supplement


if __name__ == "__main__":
    pasta_docs = r"G:\Meu Drive\Análise de Crédito Global\MT\Documentos"
    pasta_destino = r"G:\Meu Drive\Análise de Crédito Global\MT\Dados_EDGAR"
    print(f"Lendo PDFs de: {pasta_docs}")
    dados = extrair_supplement_mt(pasta_docs, pasta_destino)
    print(f"\nTotal trimestres: {len(dados)}")
    print(f"Salvo em: {pasta_destino}")
    if dados:
        print("\nUltimo trimestre:")
        print(json.dumps(dados[-1], indent=2, ensure_ascii=False))
