"""
Extrator de dados financeiros - Volkswagen AG (VWAGY).

Le os Interim Reports trimestrais (Q1, H1, Q3) e o Annual Report
publicados em https://www.volkswagen-group.com/en/financial-results-18486

Cada relatorio traz YTD (Q1=3M, H1=6M, Q3=9M, Annual=12M). O parser
desacumula para obter valores trimestrais (Q2=H1-Q1; Q3=9M-H1; Q4=FY-9M).
Balanco patrimonial e ponto-no-tempo.

Saidas em pasta_destino:
  - supplement_data.json
  - contas_chave.json
  - cronogramas.json (vazio)
  - ratings.json
  - ri_website.json
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

import fitz  # PyMuPDF


# EUR -> USD (medias trimestrais aproximadas)
EURUSD: dict[str, float] = {
    "2021-03-31": 1.21, "2021-06-30": 1.21, "2021-09-30": 1.18, "2021-12-31": 1.14,
    "2022-03-31": 1.12, "2022-06-30": 1.06, "2022-09-30": 1.01, "2022-12-31": 1.03,
    "2023-03-31": 1.08, "2023-06-30": 1.09, "2023-09-30": 1.07, "2023-12-31": 1.08,
    "2024-03-31": 1.08, "2024-06-30": 1.08, "2024-09-30": 1.10, "2024-12-31": 1.06,
    "2025-03-31": 1.07, "2025-06-30": 1.13, "2025-09-30": 1.17, "2025-12-31": 1.10,
}

QUARTER_END = {1: "03-31", 2: "06-30", 3: "09-30", 4: "12-31"}

_NUM_RE = re.compile(r"-?\d{1,3}(?:[.,]\d{3})*(?:[.,]\d+)?")


def _to_float(token: str) -> Optional[float]:
    if token is None:
        return None
    t = token.strip().replace("\u2013", "-").replace("\u2212", "-")
    t = t.replace(" ", "").replace("\xa0", "").rstrip("%")
    if t in {"", "-", ".", "."}:
        return None
    if "," in t and "." in t:
        # Formato US: virgula = milhar, ponto = decimal
        t = t.replace(",", "")
    elif "," in t:
        t = t.replace(",", "")
    try:
        return float(t)
    except ValueError:
        return None


def _extract_numbers(line: str) -> list[float]:
    out = []
    # Remover en/em dashes adjacentes a digitos para virarem negativo
    line2 = re.sub(r"[\u2013\u2212](?=\d)", "-", line)
    for m in _NUM_RE.findall(line2):
        v = _to_float(m)
        if v is not None:
            out.append(v)
    return out


def _page_lines(page) -> list[str]:
    return [ln.strip() for ln in page.get_text().splitlines() if ln.strip()]


def _row_value(lines: list[str], label: str, exact: bool = True,
               max_lookahead: int = 12) -> Optional[float]:
    """
    Acha primeira linha igual (ou contendo) `label` e retorna o
    PRIMEIRO numero "grande" das linhas seguintes (current period).
    Quando ha 2 numeros (current + prior year), retorna o primeiro.
    """
    for i, ln in enumerate(lines):
        if exact:
            if ln.strip() != label:
                continue
        else:
            if label.lower() not in ln.lower():
                continue
        nums: list[float] = []
        j = i + 1
        while len(nums) < 4 and j < len(lines) and j < i + max_lookahead:
            nums.extend(_extract_numbers(lines[j]))
            j += 1
        if not nums:
            continue
        # se ha pelo menos 2 numeros: o note (1 digito pequeno) pode aparecer antes.
        # filtrar numeros muito pequenos (<10) se houver outros >>
        big = [n for n in nums if abs(n) >= 10]
        if big:
            return big[0]
        return nums[0]
    return None


def _parse_pdf(pdf_path: Path) -> dict:
    """Extrai income statement (YTD), balance sheet (PIT), cash flow (YTD)."""
    doc = fitz.open(pdf_path)
    out: dict = {}

    # Encontrar paginas relevantes
    is_lines = bs_lines = cf_lines = None
    for i in range(len(doc)):
        t = doc[i].get_text()
        if is_lines is None and "Sales revenue" in t and "Cost of sales" in t and "Gross result" in t:
            is_lines = _page_lines(doc[i])
        if (bs_lines is None
                and "Total assets" in t
                and "Inventories" in t
                and "Financial liabilities" in t
                and "Passenger Cars" not in t
                and "Commercial Vehicles" not in t):
            bs_lines = _page_lines(doc[i])
        if (cf_lines is None
                and "Cash flows from operating activities" in t
                and "Cash flows from investing activities" in t
                and "Cash flows from financing activities" in t
                and "BY DIVISION" not in t
                and "CASH FLOW STATEMENT BY DIVISION" not in t):
            cf_lines = _page_lines(doc[i])
        if is_lines and bs_lines and cf_lines:
            break

    if is_lines:
        out["revenue"] = _row_value(is_lines, "Sales revenue")
        out["cost_of_sales"] = _row_value(is_lines, "Cost of sales")
        out["gross_result"] = _row_value(is_lines, "Gross result")
        out["distribution_expenses"] = _row_value(is_lines, "Distribution expenses")
        out["admin_expenses"] = _row_value(is_lines, "Administrative expenses")
        out["operating_result"] = _row_value(is_lines, "Operating result")
        out["earnings_before_tax"] = _row_value(is_lines, "Earnings before tax")
        out["earnings_after_tax"] = _row_value(is_lines, "Earnings after tax")
        # Financial result (DRE): interim combina; annual separa Interest income/expenses
        out["financial_result"] = _row_value(is_lines, "Financial result")
        out["interest_income"] = _row_value(is_lines, "Interest income")
        out["interest_expenses"] = _row_value(is_lines, "Interest expenses")
        out["interest_result_other"] = _row_value(
            is_lines, "Interest result and other financial result", exact=False)

    if bs_lines:
        out["total_assets"] = _row_value(bs_lines, "Total assets")
        out["non_current_assets"] = _row_value(bs_lines, "Non-current assets")
        out["current_assets"] = _row_value(bs_lines, "Current assets")
        out["equity"] = _row_value(bs_lines, "Equity")
        out["non_current_liab"] = _row_value(bs_lines, "Non-current liabilities")
        out["current_liab"] = _row_value(bs_lines, "Current liabilities")
        out["cash"] = _row_value(bs_lines, "Cash and cash equivalents")
        out["inventories"] = _row_value(bs_lines, "Inventories")
        out["marketable_securities"] = _row_value(
            bs_lines, "Marketable securities", exact=False)
        out["trade_payables"] = _row_value(bs_lines, "Trade payables")
        out["other_receivables_current"] = None
        # trade receivables nao eh destacada explicitamente em VW (vai em "Other receivables")
        for i, ln in enumerate(bs_lines):
            if "Other receivables and financial assets" in ln:
                # Ha 2 (NC e C). Pegar o 2o (current)
                nums_hits = []
                j = i + 1
                while j < len(bs_lines) and j < i + 5:
                    nums = _extract_numbers(bs_lines[j])
                    big = [n for n in nums if abs(n) >= 10]
                    if big:
                        nums_hits.append(big[0])
                        break
                    j += 1
                if nums_hits:
                    if out["other_receivables_current"] is None:
                        out["other_receivables_current"] = nums_hits[0]
                    else:
                        out["other_receivables_current"] = nums_hits[0]  # segunda ocorrencia
        # Financial liabilities aparecem 2 vezes (NC e C). Pegar ambos.
        fin_liabs = []
        for i, ln in enumerate(bs_lines):
            if ln.strip() == "Financial liabilities":
                j = i + 1
                while j < len(bs_lines) and j < i + 6:
                    nums = _extract_numbers(bs_lines[j])
                    big = [n for n in nums if abs(n) >= 10]
                    if big:
                        fin_liabs.append(big[0])
                        break
                    j += 1
        if len(fin_liabs) >= 2:
            out["financial_liab_nc"] = fin_liabs[0]
            out["financial_liab_c"] = fin_liabs[1]
        elif len(fin_liabs) == 1:
            out["financial_liab_nc"] = fin_liabs[0]

    if cf_lines:
        out["fco"] = _row_value(cf_lines, "Cash flows from operating activities")
        out["fci"] = _row_value(cf_lines, "Cash flows from investing activities")
        out["fcf_financing"] = _row_value(cf_lines, "Cash flows from financing activities")
        out["income_taxes_paid"] = _row_value(cf_lines, "Income taxes paid")

        # D&A — labels diferem entre interim e annual. Capturar todos componentes.
        def _find_line(substr: str) -> Optional[float]:
            for i, ln in enumerate(cf_lines):
                if substr in ln:
                    nums: list[float] = []
                    j = i + 1
                    while len(nums) < 2 and j < len(cf_lines) and j < i + 8:
                        nums.extend(_extract_numbers(cf_lines[j]))
                        j += 1
                    big = [n for n in nums if abs(n) >= 10]
                    if big:
                        return big[0]
                    if nums:
                        return nums[0]
            return None

        # Interim: "Depreciation and amortization expense"
        dep_interim = _find_line("Depreciation and amortization expense")
        if dep_interim is not None:
            out["dep_amort"] = dep_interim
        else:
            # Annual: somar componentes de depreciacao/amortizacao
            d1 = _find_line("Depreciation and amortization of, and impairment")
            d2 = _find_line("Amortization of and impairment losses on capitalized development")
            d3 = _find_line("Depreciation of and impairment losses on lease assets")
            parts = [x for x in [d1, d2, d3] if x is not None]
            if parts:
                out["dep_amort"] = sum(parts)

        # Capex: "Investments in intangible assets ... property, plant and equipment"
        # Nos interims aparece como "of which: Investments..."
        for i, ln in enumerate(cf_lines):
            low = ln.lower()
            if ("investments in intangible assets" in low
                    and "property, plant and equipment" in " ".join(cf_lines[i:i+3]).lower()):
                nums: list[float] = []
                j = i + 1
                while len(nums) < 2 and j < len(cf_lines) and j < i + 8:
                    nums.extend(_extract_numbers(cf_lines[j]))
                    j += 1
                big = [n for n in nums if abs(n) >= 10]
                if big:
                    out["capex"] = big[0]
                    break

        # Dividends paid, bonds, unlisted notes (interim nao detalha; annual sim)
        out["dividends_paid"] = _find_line("Dividends paid")
        bonds_iss = _find_line("Proceeds from issuance of bonds")
        bonds_rep = _find_line("Repayments of bonds")
        notes_iss = _find_line("Proceeds from issuance of unlisted notes")
        notes_rep = _find_line("Repayments of unlisted notes")
        if bonds_iss is not None or notes_iss is not None:
            out["debt_issuance"] = (bonds_iss or 0) + (notes_iss or 0)
        if bonds_rep is not None or notes_rep is not None:
            out["debt_repayment"] = (bonds_rep or 0) + (notes_rep or 0)

    return out


def _period_from_filename(name: str) -> Optional[tuple[str, int]]:
    """Retorna (period_end_iso, ytd_months) ou None."""
    m = re.match(r"interim-Q1-(\d{4})\.pdf$", name)
    if m:
        y = m.group(1); return (f"{y}-03-31", 3)
    m = re.match(r"interim-H1-(\d{4})\.pdf$", name)
    if m:
        y = m.group(1); return (f"{y}-06-30", 6)
    m = re.match(r"interim-Q3-(\d{4})\.pdf$", name)
    if m:
        y = m.group(1); return (f"{y}-09-30", 9)
    m = re.match(r"annual-(\d{4})\.pdf$", name)
    if m:
        y = m.group(1); return (f"{y}-12-31", 12)
    return None


def _trimestre_label(periodo: str) -> str:
    y, mo, _ = periodo.split("-")
    q = {3: 1, 6: 2, 9: 3, 12: 4}[int(mo)]
    return f"{q}Q{y[2:]}"


def extrair_supplement_vw(pasta_docs: str, pasta_destino: str) -> list[dict]:
    pasta = Path(pasta_docs)
    destino = Path(pasta_destino)
    destino.mkdir(parents=True, exist_ok=True)

    # Coleta YTD por periodo
    ytd: dict[str, dict] = {}  # periodo -> dados YTD
    for pdf in sorted(pasta.glob("*.pdf")):
        info = _period_from_filename(pdf.name)
        if not info:
            continue
        periodo, ytd_m = info
        try:
            data = _parse_pdf(pdf)
        except Exception as e:
            print(f"  [WARN] {pdf.name}: {e}")
            continue
        data["_ytd_months"] = ytd_m
        data["_fonte"] = pdf.name
        ytd[periodo] = data
        print(f"  OK {pdf.name} -> {periodo} (YTD {ytd_m}M) revenue={data.get('revenue')}")

    # Desacumular DRE/DFC para obter valores trimestrais
    # Chaves de fluxo (acumuladas): revenue, cost_of_sales, gross_result, operating_result,
    # earnings_before_tax, earnings_after_tax, fco, dep_amort, capex
    flow_keys = ["revenue", "cost_of_sales", "gross_result", "distribution_expenses",
                 "admin_expenses", "operating_result", "earnings_before_tax",
                 "earnings_after_tax", "financial_result", "interest_income",
                 "interest_expenses", "interest_result_other",
                 "fco", "fci", "fcf_financing", "income_taxes_paid",
                 "dep_amort", "capex", "dividends_paid", "debt_issuance", "debt_repayment"]

    quarterly: dict[str, dict] = {}
    # Agrupar por ano
    by_year: dict[str, dict[int, dict]] = {}
    for periodo, d in ytd.items():
        y, mo, _ = periodo.split("-")
        q = {3: 1, 6: 2, 9: 3, 12: 4}[int(mo)]
        by_year.setdefault(y, {})[q] = d

    for year, qmap in by_year.items():
        for q in (1, 2, 3, 4):
            if q not in qmap:
                continue
            cur = qmap[q]
            prev = qmap.get(q - 1) if q > 1 else None
            periodo = f"{year}-{QUARTER_END[q]}"
            entry = {k: cur.get(k) for k in cur if not k.startswith("_")}
            # Desacumular fluxos
            if prev:
                for k in flow_keys:
                    cv, pv = cur.get(k), prev.get(k)
                    if cv is not None and pv is not None:
                        entry[k] = round(cv - pv, 2)
            entry["_fonte"] = cur.get("_fonte", "")
            quarterly[periodo] = entry

    # Construir saida supplement_data.json (em USD milhoes)
    supplement: list[dict] = []
    for periodo in sorted(quarterly.keys()):
        d = quarterly[periodo]
        if d.get("revenue") is None:
            continue
        fx = EURUSD.get(periodo, 1.10)

        def usd(v):
            return round(v * fx, 2) if v is not None else None

        revenue = d.get("revenue")
        cost = d.get("cost_of_sales")
        if cost is not None and cost > 0:
            cost = -cost
        gross = d.get("gross_result")
        if gross is None and revenue is not None and cost is not None:
            gross = revenue + cost
        ebit = d.get("operating_result")
        net_income = d.get("earnings_after_tax")
        dep = d.get("dep_amort")
        if dep is not None:
            dep = abs(dep)
        ebitda = (ebit + dep) if (ebit is not None and dep is not None) else None
        capex = d.get("capex")
        if capex is not None and capex > 0:
            capex = -capex

        # DRE financeiro
        fin_result = d.get("financial_result")
        # Interim: usar interest_result_other como proxy para receita/despesa
        int_inc = d.get("interest_income")
        int_exp = d.get("interest_expenses")
        if int_exp is not None and int_exp > 0:
            int_exp = -int_exp
        # Se nao temos breakdown anual, usar financial_result agregado
        if int_inc is None and int_exp is None and fin_result is not None:
            if fin_result >= 0:
                int_inc, int_exp = fin_result, 0.0
            else:
                int_inc, int_exp = 0.0, fin_result

        # Balanco (ponto-no-tempo)
        cash = d.get("cash")
        marketable = d.get("marketable_securities")
        # Divida bruta = financial liabilities NC + C
        fl_nc = d.get("financial_liab_nc") or 0
        fl_c = d.get("financial_liab_c") or 0
        gross_debt = (fl_nc + fl_c) if (fl_nc or fl_c) else None

        # CF detalhes
        div_paid = d.get("dividends_paid")
        if div_paid is not None and div_paid > 0:
            div_paid = -div_paid
        debt_iss = d.get("debt_issuance")
        debt_rep = d.get("debt_repayment")
        if debt_rep is not None and debt_rep > 0:
            debt_rep = -debt_rep
        fco_v = d.get("fco")
        fcl = (fco_v + capex) if (fco_v is not None and capex is not None) else None

        entry = {
            "periodo": periodo,
            "trimestre": _trimestre_label(periodo),
            "moeda_original": "EUR",
            "fx_rate": fx,
            "fonte": d.get("_fonte", ""),
            "income_statement": {
                "total_income": usd(revenue),
                "custo": usd(cost),
                "resultado_bruto": usd(gross),
                "ebit": usd(ebit),
                "depreciacao_amortizacao": usd(dep),
                "ebitda": usd(ebitda),
                "net_income": usd(net_income),
                "financial_result": usd(fin_result),
                "interest_income": usd(int_inc),
                "interest_expenses": usd(int_exp),
            },
            "balance_sheet": {
                "total_assets": usd(d.get("total_assets")),
                "total_equity": usd(d.get("equity")),
                "cash": usd(cash),
                "marketable_securities": usd(marketable),
                "inventories": usd(d.get("inventories")),
                "current_assets": usd(d.get("current_assets")),
                "current_liab": usd(d.get("current_liab")),
                "trade_payables": usd(d.get("trade_payables")),
                "financial_liab_cp": usd(fl_c if fl_c else None),
                "financial_liab_lp": usd(fl_nc if fl_nc else None),
                "gross_debt": usd(gross_debt),
            },
            "cash_flow": {
                "fco": usd(fco_v),
                "fci": usd(d.get("fci")),
                "fcf_financing": usd(d.get("fcf_financing")),
                "capex": usd(capex),
                "fcf": usd(fcl),
                "dividends_paid": usd(div_paid),
                "debt_issuance": usd(debt_iss),
                "debt_repayment": usd(debt_rep),
                "income_taxes_paid": usd(d.get("income_taxes_paid")),
            },
        }
        supplement.append(entry)

    # ----- Salvar -----
    (destino / "supplement_data.json").write_text(
        json.dumps(supplement, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (destino / "cronogramas.json").write_text(
        json.dumps([], ensure_ascii=False), encoding="utf-8"
    )
    ratings = {
        "empresa": "Volkswagen AG",
        "ticker": "VWAGY",
        "ratings_atuais": {
            "Moodys": {"rating": "A3", "outlook": "Stable"},
            "SP": {"rating": "BBB+", "outlook": "Stable"},
            "Fitch": {"rating": "A-", "outlook": "Stable"},
        },
        "fonte": "Public ratings agencies",
    }
    (destino / "ratings.json").write_text(
        json.dumps(ratings, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    ri = {
        "empresa": "Volkswagen AG",
        "ticker": "VWAGY",
        "ri_url": "https://www.volkswagen-group.com/en/investors-15766",
        "documentos_url": "https://www.volkswagen-group.com/en/financial-results-18486",
    }
    (destino / "ri_website.json").write_text(
        json.dumps(ri, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    # ----- contas_chave.json (lista flat) -----
    # IMPORTANTE: como ITR aqui ja vem desacumulado (trimestre isolado),
    # marcamos como DFP_* para evitar a desacumulacao no indicadores.py.
    # Mas BPA/BPP sao point-in-time entao tambem ficam como DFP.
    def m(v):
        return v * 1e6 if v is not None else None

    contas_lista = []
    for entry in supplement:
        periodo = entry["periodo"]
        is_ = entry["income_statement"]
        bs = entry["balance_sheet"]
        cf = entry["cash_flow"]
        ano = int(periodo.split("-")[0])

        rec_fin = m(is_.get("interest_income"))
        desp_fin = m(is_.get("interest_expenses"))
        res_fin = m(is_.get("financial_result"))
        contas_lista.append({"periodo": periodo, "tipo": "ITR_dre", "ano": ano, "contas": {
            "receita_liquida": m(is_["total_income"]),
            "custo": m(is_["custo"]),
            "resultado_bruto": m(is_["resultado_bruto"]),
            "ebit": m(is_["ebit"]),
            "ebitda": m(is_["ebitda"]),
            "lucro_liquido": m(is_["net_income"]),
            "depreciacao_amortizacao": m(is_["depreciacao_amortizacao"]),
            "despesas_financeiras": desp_fin if desp_fin is not None else 0.0,
            "receitas_financeiras": rec_fin if rec_fin is not None else 0.0,
            "resultado_financeiro": res_fin,
        }})
        contas_lista.append({"periodo": periodo, "tipo": "ITR_bpa", "ano": ano, "contas": {
            "ativo_total": m(bs["total_assets"]),
            "caixa": m(bs["cash"]),
            "aplicacoes_financeiras_cp": m(bs.get("marketable_securities")),
            "estoques_cp": m(bs["inventories"]),
            "ativo_circulante": m(bs["current_assets"]),
        }})
        contas_lista.append({"periodo": periodo, "tipo": "ITR_bpp", "ano": ano, "contas": {
            "emprestimos_cp": m(bs["financial_liab_cp"]),
            "emprestimos_lp": m(bs["financial_liab_lp"]),
            "fornecedores": m(bs.get("trade_payables")),
            "passivo_circulante": m(bs["current_liab"]),
            "patrimonio_liquido": m(bs["total_equity"]),
        }})
        contas_lista.append({"periodo": periodo, "tipo": "ITR_dfc", "ano": ano, "contas": {
            "fco": m(cf["fco"]),
            "fci": m(cf.get("fci")),
            "capex": m(cf["capex"]),
            "fcf": m(cf.get("fcf")),
            "depreciacao_amortizacao": m(is_["depreciacao_amortizacao"]),
            "dividendos_pagos": m(cf.get("dividends_paid")),
            "captacao_divida": m(cf.get("debt_issuance")),
            "amortizacao_divida": m(cf.get("debt_repayment")),
            "juros_pagos": None,
            "ir_pago": m(cf.get("income_taxes_paid")),
        }})

    (destino / "contas_chave.json").write_text(
        json.dumps(contas_lista, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    return supplement


if __name__ == "__main__":
    pasta_docs = r"G:\Meu Drive\Análise de Crédito Global\VWAGY\Documentos"
    pasta_destino = r"G:\Meu Drive\Análise de Crédito Global\VWAGY\Dados_EDGAR"
    print(f"Lendo PDFs de: {pasta_docs}")
    dados = extrair_supplement_vw(pasta_docs, pasta_destino)
    print(f"\nTotal trimestres: {len(dados)}")
    print(f"Salvo em: {pasta_destino}")
    if dados:
        print("\nUltimo trimestre:")
        print(json.dumps(dados[-1], indent=2, ensure_ascii=False))
