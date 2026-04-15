"""
Extrator de dados financeiros suplementares - Mercedes-Benz Group AG (MBG).

Fonte primaria: Fact Sheets trimestrais (PDF) publicados em
https://group.mercedes-benz.com/investors/

Cada fact sheet contem uma tabela rotativa com 5 trimestres (Q-4..Q-atual).
A funcao varre todos os fact sheets disponiveis na pasta e consolida em
um JSON unico, convertendo EUR -> USD via taxa de cambio media trimestral.

Saidas em pasta_destino:
  - supplement_data.json
  - contas_chave.json   (formato nao-financeiro, valores em USD UNIDADES)
  - cronogramas.json    (vazio)
  - ratings.json
  - ri_website.json
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Optional

try:
    import fitz  # PyMuPDF
except ImportError as e:
    raise ImportError("PyMuPDF (fitz) is required: pip install pymupdf") from e


# ---------------------------------------------------------------------------
# FX EUR -> USD (medias trimestrais aproximadas)
# ---------------------------------------------------------------------------
EURUSD: dict[str, float] = {
    "2021-03-31": 1.21, "2021-06-30": 1.21, "2021-09-30": 1.18, "2021-12-31": 1.14,
    "2022-03-31": 1.12, "2022-06-30": 1.06, "2022-09-30": 1.01, "2022-12-31": 1.03,
    "2023-03-31": 1.08, "2023-06-30": 1.09, "2023-09-30": 1.07, "2023-12-31": 1.08,
    "2024-03-31": 1.08, "2024-06-30": 1.08, "2024-09-30": 1.10, "2024-12-31": 1.06,
    "2025-03-31": 1.07, "2025-06-30": 1.13, "2025-09-30": 1.17, "2025-12-31": 1.10,
}

QUARTER_END = {1: "03-31", 2: "06-30", 3: "09-30", 4: "12-31"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
_NUM_RE = re.compile(r"-?\d{1,3}(?:[.,]\d{3})*(?:[.,]\d+)?")


def _to_float(token: str) -> Optional[float]:
    """Converte string numerica europeia (ponto = milhar) -> float."""
    if token is None:
        return None
    t = token.strip().replace("\u2013", "-").replace("\u2212", "-")
    t = t.replace(" ", "").replace("\xa0", "")
    if t in {"", "-", ".", "�", "."}:
        return None
    # remove sufixos %
    t = t.rstrip("%")
    # MBG usa virgulas como separador de milhar nos fact sheets recentes
    # ex.: "34,528" = 34528 ; "1.81" = 1.81
    if "," in t and "." in t:
        # ambos -> ponto = decimal, virgula = milhar (formato US)
        t = t.replace(",", "")
    elif "," in t:
        # somente virgula -> separador de milhar
        t = t.replace(",", "")
    try:
        return float(t)
    except ValueError:
        return None


def _extract_numbers_from_line(line: str) -> list[float]:
    out: list[float] = []
    for m in _NUM_RE.findall(line):
        v = _to_float(m)
        if v is not None:
            out.append(v)
    return out


def _page_lines(page) -> list[str]:
    return [ln.strip() for ln in page.get_text().splitlines() if ln.strip()]


def _find_quarter_columns(lines: list[str]) -> Optional[list[str]]:
    """
    Encontra a sequencia de cabecalhos de coluna [Qx, Qy, ..., Qz] e a linha
    de anos correspondente, devolvendo lista de strings 'YYYY-MM-DD' (5 itens).

    Suporta dois layouts:
      A) Linhas: 'Q3 2024' 'Q4 2024' 'Q1 2025' 'Q2 2025' 'Q3 2025'
      B) Linhas: 'Q3' 'Q4' 'Q1' 'Q2' 'Q3' (depois 5 anos)
    """
    qre = re.compile(r"^Q([1-4])(?:\s+(\d{4}))?$")
    # Procura sequencia de 5 Q-headers consecutivos
    for i in range(len(lines) - 4):
        seq = lines[i:i + 5]
        ms = [qre.match(s) for s in seq]
        if not all(ms):
            continue
        quarters = [int(m.group(1)) for m in ms]
        years_inline = [m.group(2) for m in ms]
        if all(years_inline):
            years = [int(y) for y in years_inline]
        else:
            # procura proximas 5 linhas que sao anos puros (apos cabecalhos)
            years = None
            for j in range(i + 5, min(i + 25, len(lines) - 4)):
                cand = lines[j:j + 5]
                if all(re.fullmatch(r"\d{4}", c) for c in cand):
                    years = [int(c) for c in cand]
                    break
            if years is None:
                continue
        # Sanidade: trimestres devem ser sequenciais
        out = []
        for q, y in zip(quarters, years):
            out.append(f"{y}-{QUARTER_END[q]}")
        return out
    return None


def _extract_row_after_label(
    lines: list[str],
    label_substrings: list[str],
    n_values: int = 5,
    exact: bool = False,
) -> Optional[list[float]]:
    """
    Acha a primeira linha contendo TODOS os substrings de label_substrings,
    e devolve os primeiros n_values numeros encontrados nas linhas seguintes.
    Se exact=True, exige match exato (case-insensitive) com o primeiro substring.
    """
    for i, ln in enumerate(lines):
        low = ln.lower().strip()
        if exact:
            if low != label_substrings[0].lower():
                continue
        else:
            if not all(s.lower() in low for s in label_substrings):
                continue
        nums: list[float] = []
        # primeiro tenta na propria linha
        nums.extend(_extract_numbers_from_line(ln))
        j = i + 1
        while len(nums) < n_values and j < len(lines) and j < i + 30:
            nxt = lines[j]
            # parar se for outro label (linha sem numeros e com letras)
            if re.search(r"[A-Za-z]{3,}", nxt) and not _extract_numbers_from_line(nxt):
                # mas alguns labels quebram em duas linhas; permitir seguir
                pass
            nums.extend(_extract_numbers_from_line(nxt))
            j += 1
        if len(nums) >= n_values:
            return nums[:n_values]
    return None


def _trimestre_label(periodo: str) -> str:
    y, m, _ = periodo.split("-")
    q = {3: 1, 6: 2, 9: 3, 12: 4}[int(m)]
    return f"{q}Q{y[2:]}"


# ---------------------------------------------------------------------------
# Parser de UM fact sheet
# ---------------------------------------------------------------------------
def _parse_fact_sheet(pdf_path: Path) -> dict[str, dict]:
    """
    Devolve dict[periodo] = {dados em EUR milhoes} para cada uma das 5 colunas.
    """
    doc = fitz.open(pdf_path)
    out: dict[str, dict] = {}
    quarters: Optional[list[str]] = None

    # Junta texto por pagina e tenta extrair por pagina (cada tabela e uma pagina)
    all_pages_lines = [_page_lines(p) for p in doc]

    # So consideramos paginas que tem cabecalho de 5 trimestres (paginas-tabela)
    pages_lines = [pl for pl in all_pages_lines if _find_quarter_columns(pl)]

    # Encontra os trimestres (a partir da primeira pagina-tabela)
    for lines in pages_lines:
        q = _find_quarter_columns(lines)
        if q:
            quarters = q
            break
    if not quarters:
        return out

    for periodo in quarters:
        out[periodo] = {"_fonte": pdf_path.name}

    def _set(periodo_idx_values: Optional[list[float]], key: str, neg_ok: bool = True):
        if not periodo_idx_values:
            return
        for idx, periodo in enumerate(quarters):
            v = periodo_idx_values[idx]
            if v is None:
                continue
            if not neg_ok and v < 0:
                v = abs(v)
            out[periodo][key] = v

    def _row(labels: list[str], exact: bool = False) -> Optional[list[float]]:
        for lines in pages_lines:
            r = _extract_row_after_label(lines, labels, n_values=5, exact=exact)
            if r:
                return r
        return None

    # ---- Key Figures (labels devem ser linhas exatas) ----
    _set(_row(["Revenue"], exact=True), "revenue")
    _set(_row(["EBIT"], exact=True), "ebit_group")
    _set(_row(["Net profit"], exact=True), "net_profit")
    _set(_row(["Free cash flow industrial business"], exact=True), "fcf_ib")
    _set(_row(["Investment in property, plant and equipment"]), "capex")

    # ---- EBIT page (consolidated income statement) ----
    _set(_row(["Cost of sales"]), "cost_of_sales")
    _set(_row(["Gross profit"]), "gross_profit")

    # ---- Segment revenues (a pagina "Revenue by Segment" lista os 3) ----
    _set(_row(["Mercedes-Benz Cars"]), "cars_revenue")
    _set(_row(["Mercedes-Benz Vans"]), "vans_revenue")
    _set(_row(["Mercedes-Benz Mobility"]), "mobility_revenue")

    # ---- Segment EBITs: parsear pagina especifica de cada um ----
    # As paginas "EBIT of Mercedes-Benz Cars/Vans/Mobility" tem a row "EBIT" no fim.
    def _ebit_in_page_with(label: str) -> Optional[list[float]]:
        for lines in pages_lines:
            joined = " ".join(lines).lower()
            if label.lower() in joined and "ebit" in joined and "cost of sales" in joined:
                # Pega a ULTIMA row "EBIT" da pagina (a da linha-base)
                # mas precisa ser a row de EBIT do segmento, nao "EBIT adjusted"
                ebit_rows: list[list[float]] = []
                for i, ln in enumerate(lines):
                    if ln.strip().lower() == "ebit":
                        nums: list[float] = []
                        j = i + 1
                        while len(nums) < 5 and j < len(lines) and j < i + 15:
                            nums.extend(_extract_numbers_from_line(lines[j]))
                            j += 1
                        if len(nums) >= 5:
                            ebit_rows.append(nums[:5])
                if ebit_rows:
                    return ebit_rows[0]
        return None

    _set(_ebit_in_page_with("EBIT) of Mercedes-Benz Cars"), "cars_ebit")
    _set(_ebit_in_page_with("EBIT) of Mercedes-Benz Vans"), "vans_ebit")
    _set(_ebit_in_page_with("EBIT) of Mercedes-Benz Mobility"), "mobility_ebit")

    # Fallback para variantes do label de EBIT por segmento
    if not any("cars_ebit" in out[p] for p in quarters):
        _set(_ebit_in_page_with("Mercedes-Benz Cars"), "cars_ebit")

    # ---- Liquidity page ----
    _set(_row(["Cash and cash equivalents"]), "cash")
    _set(_row(["Gross liquidity"]), "gross_liquidity")
    _set(_row(["Financing liabilities"]), "gross_debt")
    _set(_row(["Net debt"]), "net_debt_group")
    _set(_row(["Net liquidity", "end of the period"]), "net_industrial_liquidity")

    return out


# ---------------------------------------------------------------------------
# Funcao principal
# ---------------------------------------------------------------------------
def extrair_supplement_mbg(pasta_docs: str, pasta_destino: str) -> list[dict]:
    pasta = Path(pasta_docs)
    destino = Path(pasta_destino)
    destino.mkdir(parents=True, exist_ok=True)

    fact_sheets = sorted(pasta.glob("fact-sheet-Q*-*.pdf"))
    if not fact_sheets:
        raise FileNotFoundError(f"Nenhum fact sheet encontrado em {pasta}")

    # Acumula por periodo. Versoes mais recentes (ordem alfabetica do nome do
    # arquivo nao garante isso) -> ordenamos por (ano, trimestre) crescente,
    # e a versao mais recente sobrescreve as anteriores.
    def _key(p: Path) -> tuple[int, int]:
        m = re.search(r"Q([1-4])-(\d{4})", p.name)
        return (int(m.group(2)), int(m.group(1))) if m else (0, 0)

    fact_sheets_sorted = sorted(fact_sheets, key=_key)

    consolidated: dict[str, dict] = {}
    for fs in fact_sheets_sorted:
        try:
            parsed = _parse_fact_sheet(fs)
        except Exception as e:
            print(f"  [WARN] Falha ao parsear {fs.name}: {e}")
            continue
        for periodo, dados in parsed.items():
            # Mantem o mais recente (sobrescreve)
            existing = consolidated.get(periodo, {})
            existing.update({k: v for k, v in dados.items() if v is not None})
            consolidated[periodo] = existing

    # Constroi a saida no formato supplement_data.json
    supplement: list[dict] = []
    for periodo in sorted(consolidated.keys()):
        d = consolidated[periodo]
        if "revenue" not in d:
            continue
        fx = EURUSD.get(periodo, 1.10)

        def usd(v: Optional[float]) -> Optional[float]:
            return round(v * fx, 2) if v is not None else None

        revenue = d.get("revenue")
        cost = d.get("cost_of_sales")
        if cost is not None and cost > 0:
            cost = -cost  # garante sinal negativo
        gross = d.get("gross_profit")
        if gross is None and revenue is not None and cost is not None:
            gross = revenue + cost
        ebit = d.get("ebit_group")
        capex = d.get("capex")
        if capex is not None and capex > 0:
            capex_signed = -capex
        else:
            capex_signed = capex
        fcf = d.get("fcf_ib")
        # Aproximacao de FCO a partir de FCF + capex (industrial)
        fco = None
        if fcf is not None and capex is not None:
            fco = fcf + capex  # capex positivo

        gross_debt = d.get("gross_debt")
        if gross_debt is not None and gross_debt < 0:
            gross_debt = -gross_debt
        cash = d.get("cash")
        net_debt = d.get("net_debt_group")
        if net_debt is not None and net_debt < 0:
            net_debt = -net_debt

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
                "depreciacao_amortizacao": None,
                "ebitda": None,
                "net_income": usd(d.get("net_profit")),
            },
            "balance_sheet": {
                "total_assets": None,
                "total_equity": None,
                "cash": usd(cash),
                "gross_debt": usd(gross_debt),
                "net_debt": usd(net_debt),
                "net_industrial_liquidity": usd(d.get("net_industrial_liquidity")),
            },
            "cash_flow": {
                "fco": usd(fco),
                "capex": usd(capex_signed),
                "fcf": usd(fcf),
                "dividends_paid": None,
            },
            "segments": {
                "cars_revenue": usd(d.get("cars_revenue")),
                "cars_ebit": usd(d.get("cars_ebit")),
                "vans_revenue": usd(d.get("vans_revenue")),
                "vans_ebit": usd(d.get("vans_ebit")),
                "mobility_revenue": usd(d.get("mobility_revenue")),
                "mobility_ebit": usd(d.get("mobility_ebit")),
            },
        }
        supplement.append(entry)

    # ----- Salva arquivos -----
    (destino / "supplement_data.json").write_text(
        json.dumps(supplement, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    # cronogramas vazio
    (destino / "cronogramas.json").write_text(
        json.dumps({"cronogramas": []}, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    # ratings
    ratings = {
        "empresa": "Mercedes-Benz Group AG",
        "ticker": "MBG",
        "ratings_atuais": {
            "Moodys": {"rating": "A2", "outlook": "Stable"},
            "SP": {"rating": "A", "outlook": "Stable"},
            "Fitch": {"rating": "A", "outlook": "Stable"},
        },
        "fonte": "Public ratings agencies",
    }
    (destino / "ratings.json").write_text(
        json.dumps(ratings, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    # RI
    ri = {
        "empresa": "Mercedes-Benz Group AG",
        "ticker": "MBG",
        "ri_url": "https://group.mercedes-benz.com/investors/",
        "documentos_url": "https://group.mercedes-benz.com/investors/reports-news/financial-reports/",
    }
    (destino / "ri_website.json").write_text(
        json.dumps(ri, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    # ----- contas_chave.json (formato nao-financeiro, valores em USD UNIDADES) -----
    contas_chave = {"empresa": "MBG", "fonte": "MBG Fact Sheets", "ITR": {}}
    for entry in supplement:
        periodo = entry["periodo"]
        is_ = entry["income_statement"]
        bs = entry["balance_sheet"]
        cf = entry["cash_flow"]

        def m(v):
            return v * 1e6 if v is not None else None

        contas_chave["ITR"][periodo] = {
            "ITR_dre": {
                "receita_liquida": m(is_["total_income"]),
                "custo": m(is_["custo"]),
                "resultado_bruto": m(is_["resultado_bruto"]),
                "ebit": m(is_["ebit"]),
                "ebitda": m(is_["ebitda"]),
                "lucro_liquido": m(is_["net_income"]),
                "despesa_juros": None,
                "depreciacao_amortizacao": m(is_["depreciacao_amortizacao"]),
            },
            "ITR_bpa": {
                "ativo_total": m(bs["total_assets"]),
                "caixa": m(bs["cash"]),
                "investimentos_titulos": None,
                "imobilizado": None,
                "intangivel": None,
                "ativo_circulante": None,
                "ativo_nao_circulante": None,
            },
            "ITR_bpp": {
                "passivo_total": None,
                "emprestimos_cp": None,
                "emprestimos_lp": m(bs["gross_debt"]),
                "passivo_circulante": None,
                "patrimonio_liquido": m(bs["total_equity"]),
            },
            "ITR_dfc": {
                "fco": m(cf["fco"]),
                "capex": m(cf["capex"]),
                "fcl": m(cf["fcf"]),
                "dividendos_pagos": m(cf["dividends_paid"]),
                "juros_pagos": None,
            },
        }
    (destino / "contas_chave.json").write_text(
        json.dumps(contas_chave, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    return supplement


# ---------------------------------------------------------------------------
if __name__ == "__main__":
    pasta_docs = r"G:\Meu Drive\Análise de Crédito Global\MBG\Documentos"
    pasta_destino = r"G:\Meu Drive\Análise de Crédito Global\MBG\Dados_EDGAR"

    print(f"Lendo fact sheets de: {pasta_docs}")
    dados = extrair_supplement_mbg(pasta_docs, pasta_destino)
    print(f"\nTotal de trimestres extraidos: {len(dados)}")
    print(f"Salvo em: {pasta_destino}\n")

    print("=" * 70)
    print("ULTIMOS 3 TRIMESTRES:")
    print("=" * 70)
    for entry in dados[-3:]:
        print(json.dumps(entry, indent=2, ensure_ascii=False))
        print("-" * 70)
