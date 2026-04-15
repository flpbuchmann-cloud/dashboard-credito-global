"""
Cálculo de indicadores financeiros para Empresas Financeiras e Asset Managers.

Indicadores específicos:
- Bancos/Cards: NIM, Efficiency Ratio, Provision Ratio, ROA, ROE
- Asset Managers: FRE, FRE Margin, Distributable Earnings, AUM
- Comuns: Alavancagem, cobertura de juros, FCO, cronograma de dívida
"""

import json
import pandas as pd
import numpy as np
from pathlib import Path


def carregar_contas(caminho_json: str) -> list[dict]:
    with open(caminho_json, "r", encoding="utf-8") as f:
        return json.load(f)


def _montar_df_contas(contas: list[dict], prefixo_tipo: str) -> pd.DataFrame:
    registros = [c for c in contas if c["tipo"].startswith(prefixo_tipo)]
    if not registros:
        return pd.DataFrame()
    rows = []
    for r in registros:
        row = {"periodo": r["periodo"], "tipo": r["tipo"]}
        row.update(r["contas"])
        rows.append(row)
    df = pd.DataFrame(rows)
    df["periodo"] = pd.to_datetime(df["periodo"])
    df = df.sort_values("periodo").drop_duplicates(subset=["periodo"], keep="last")
    return df.set_index("periodo")


def _detectar_fy_end_month(df: pd.DataFrame) -> int:
    """Detecta o mês de encerramento do ano fiscal a partir das linhas DFP."""
    dfp_rows = df[df["tipo"].str.startswith("DFP")] if "tipo" in df.columns else pd.DataFrame()
    if not dfp_rows.empty:
        # Mês mais frequente nos DFPs = mês de encerramento fiscal
        return dfp_rows.index.month.value_counts().idxmax()
    return 12  # default: ano calendário


def _desacumular(df: pd.DataFrame, colunas: list[str], alertas: list[dict] | None = None) -> pd.DataFrame:
    df = df.copy()
    fy_end_month = _detectar_fy_end_month(df)
    # Atribuir ano fiscal: períodos após o mês de encerramento pertencem ao próximo FY
    df["ano_fiscal"] = df.index.year
    if fy_end_month != 12:
        mask_next_fy = df.index.month > fy_end_month
        df.loc[mask_next_fy, "ano_fiscal"] = df.loc[mask_next_fy].index.year + 1
    df["trimestre"] = (df.index.month - 1) // 3 + 1
    for col in colunas:
        if col not in df.columns:
            continue
        col_tri = f"{col}_tri"
        df[col_tri] = np.nan
        for fy in df["ano_fiscal"].unique():
            mask = df["ano_fiscal"] == fy
            dados = df.loc[mask].sort_index()
            # Se FY tem apenas 1 período e é o DFP (anual), valor é o full year, não trimestral
            if len(dados) == 1 and dados.index[0].month == fy_end_month:
                continue  # deixa NaN — não é dado trimestral
            for i, (idx, row) in enumerate(dados.iterrows()):
                if i == 0:
                    df.loc[idx, col_tri] = row[col]
                else:
                    prev_idx = dados.index[i - 1]
                    df.loc[idx, col_tri] = row[col] - df.loc[prev_idx, col]
    return df


def _safe_get(df, col, default=np.nan):
    if col in df.columns:
        return df[col]
    return pd.Series(default, index=df.index)


def _extrair_cp_do_cronograma(caminho_cronogramas: str) -> dict:
    """Retorna {data_referencia: valor_vencendo_em_ate_1_ano} a partir do cronograma."""
    try:
        with open(caminho_cronogramas, "r", encoding="utf-8") as f:
            cronogramas = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

    cp_por_data = {}
    for c in cronogramas:
        data_ref = c.get("data_referencia")
        vencimentos = c.get("vencimentos", {})
        if not data_ref or not vencimentos:
            continue
        ref_date = pd.Timestamp(data_ref)
        ano_limite = ref_date.year + 1
        total_cp = 0
        for ano_str, valor in vencimentos.items():
            if ano_str == "longo_prazo" or valor is None:
                continue
            try:
                ano_int = int(ano_str)
            except ValueError:
                continue
            # Incluir vencimentos do ano corrente (restante) e do próximo ano
            if ano_int <= ano_limite:
                total_cp += valor
        cp_por_data[ref_date] = total_cp
    return cp_por_data


def _carregar_supplement(caminho_supplement: str) -> pd.DataFrame:
    """Carrega dados do Financial Supplement em DataFrame indexado por data."""
    try:
        with open(caminho_supplement, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return pd.DataFrame()
    rows = []
    for entry in data:
        row = {"periodo": pd.Timestamp(entry["periodo"])}
        for section in ["avg_balances", "yields_rates", "capital", "credit_quality"]:
            if section in entry and entry[section]:
                for k, v in entry[section].items():
                    row[f"sup_{k}"] = v
        rows.append(row)
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows).set_index("periodo").sort_index()
    return df


def _calcular_indicadores_supplement_only(caminho_supplement: str,
                                           alertas: list[dict]) -> tuple[pd.DataFrame, list[dict]]:
    """Calcula indicadores para bancos europeus (BCS, UBS) que reportam em IFRS.

    Os dados não vêm do XBRL US-GAAP da SEC, mas dos PDFs de quarterly reports
    parseados pelos extratores específicos (extrator_supplement_barclays/ubs).
    """
    try:
        with open(caminho_supplement, "r", encoding="utf-8") as f:
            sup = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return pd.DataFrame(), alertas

    if not sup:
        return pd.DataFrame(), alertas

    # Helper: convert from millions to units (multiply by 1e6)
    # All monetary fields in BCS/UBS supplement are reported in USD millions,
    # but the dashboard expects values in USD units (consistent with US banks XBRL)
    M = 1_000_000

    def _to_units(v):
        """Convert millions to units, preserving None/NaN."""
        if v is None:
            return None
        try:
            return float(v) * M
        except (TypeError, ValueError):
            return None

    rows = []
    for entry in sup:
        periodo = entry.get("periodo")
        if not periodo:
            continue
        inc = entry.get("income_statement", {}) or {}
        bs = entry.get("balance_sheet", {}) or {}
        cap = entry.get("capital", {}) or {}
        cq = entry.get("credit_quality", {}) or {}
        yr = entry.get("yields_rates", {}) or {}
        ab = entry.get("avg_balances", {}) or {}

        row = {"periodo": pd.Timestamp(periodo)}
        # Income Statement (convert millions -> units)
        row["receita_liquida"] = _to_units(inc.get("total_income") or inc.get("total_revenues"))
        row["nii"] = _to_units(inc.get("nii"))
        row["receita_nao_juros"] = _to_units(inc.get("non_interest_income") or inc.get("noninterest_income"))
        row["provisao_credito"] = _to_units(inc.get("credit_impairment"))
        row["despesas_operacionais"] = _to_units(inc.get("operating_costs") or inc.get("total_opex"))
        row["lucro_antes_ir"] = _to_units(inc.get("profit_before_tax"))
        row["lucro_liquido"] = _to_units(inc.get("net_income"))
        row["ebit"] = _to_units(inc.get("profit_before_tax"))
        row["ebitda"] = _to_units(inc.get("profit_before_tax"))
        # If NII not in income_statement, derive from receita_juros (UBS doesn't break it down)
        if row["nii"] is None and row["receita_liquida"]:
            # For wealth/asset managers like UBS, NII is a portion of receita
            # Use nim * loans as proxy if available
            nim_val = yr.get("nim")
            loans_val = ab.get("avg_loans") or bs.get("loans")
            if nim_val and loans_val:
                row["nii"] = nim_val * loans_val * M / 4  # quarterly
        # Receita_nao_juros = receita_liquida - nii
        if row["receita_nao_juros"] is None and row["receita_liquida"] and row["nii"]:
            row["receita_nao_juros"] = row["receita_liquida"] - row["nii"]

        # Balance Sheet (convert millions -> units)
        row["ativo_total"] = _to_units(bs.get("total_assets") or ab.get("avg_total_assets"))
        row["patrimonio_liquido"] = _to_units(bs.get("equity"))
        # Cash: prefer hqla_pool, then derived from total assets
        cash_m = cap.get("hqla_pool") or bs.get("cash") or bs.get("caixa")
        row["caixa"] = _to_units(cash_m)
        row["depositos"] = _to_units(ab.get("avg_total_deposits") or bs.get("deposits"))
        row["emprestimos_concedidos"] = _to_units(ab.get("avg_loans") or bs.get("loans"))

        # Capital (ratios são puros, valores monetários em milhões -> unidades)
        row["cet1_ratio"] = cap.get("cet1_ratio")
        row["cet1_capital"] = _to_units(cap.get("cet1_capital"))
        row["tier1_ratio"] = cap.get("tier1_ratio") or cap.get("cet1_ratio")
        row["total_capital_ratio"] = cap.get("total_capital_ratio")
        row["slr"] = cap.get("slr") or cap.get("leverage_ratio")
        # leverage_ratio (Equity/Assets) é calculado mais abaixo, não sobrescrever
        row["lcr"] = cap.get("lcr")
        row["nsfr"] = cap.get("nsfr")
        row["rwa_implied"] = _to_units(cap.get("rwa_standardized"))
        row["rwa_real"] = _to_units(cap.get("rwa_standardized"))
        row["hqla_pool"] = _to_units(cap.get("hqla_pool"))

        # Credit Quality (valores monetários em milhões -> unidades, ratios puros)
        row["npl_total"] = _to_units(cq.get("npl"))
        row["npl_ratio"] = cq.get("npl_ratio")
        row["coverage_ratio"] = cq.get("coverage_ratio")
        row["carteira_credito_bruta"] = _to_units(cq.get("carteira_credito_bruta"))
        row["provisao_acumulada"] = _to_units(cq.get("provisao_acumulada"))

        # Profitability
        row["roe"] = yr.get("roe") or yr.get("rote")
        row["rotce"] = yr.get("rote")
        row["nim"] = yr.get("nim")
        row["efficiency_ratio"] = yr.get("efficiency_ratio") or yr.get("cost_income_ratio")
        row["loan_to_deposit"] = yr.get("loan_to_deposit") or ab.get("loan_to_deposit")
        row["nco_ratio"] = yr.get("nco_ratio") or yr.get("loan_loss_rate")

        rows.append(row)

    df = pd.DataFrame(rows).set_index("periodo").sort_index()
    df["ano"] = df.index.year
    df["trimestre"] = (df.index.month - 1) // 3 + 1
    df["label"] = df.apply(
        lambda r: f"{int(r['trimestre'])}T{int(r['ano']) % 100:02d}", axis=1
    )

    # Calculate derived metrics where possible
    # Margem líquida
    receita_nz = df["receita_liquida"].replace(0, np.nan)
    df["margem_liquida"] = df["lucro_liquido"] / receita_nz
    df["margem_ebit"] = df["ebit"] / receita_nz
    df["margem_ebitda"] = df["ebitda"] / receita_nz

    # ROA from net income / total assets
    at_avg = ((df["ativo_total"] + df["ativo_total"].shift(1)) / 2).replace(0, np.nan)
    df["roa"] = (df["lucro_liquido"] * 4) / at_avg

    # LTM Metrics (rolling 4 quarters)
    df["receita_ltm"] = df["receita_liquida"].rolling(4).sum()
    df["lucro_ltm"] = df["lucro_liquido"].rolling(4).sum()
    df["ebitda_ltm"] = df["ebitda"].rolling(4).sum()
    df["ebit_ltm"] = df["ebit"].rolling(4).sum()

    # Debt metrics: usar cronograma de divida quando disponivel
    df["divida_bruta"] = 0.0
    df["divida_liquida"] = 0.0
    for entry in sup:
        per = entry.get("periodo")
        cron = entry.get("cronograma_divida")
        if cron and per:
            try:
                idx_per = pd.Timestamp(per)
                if idx_per in df.index:
                    # cronograma total_usd_m é em milhões, converter para unidades
                    total_units = cron.get("total_usd_m", 0) * M
                    df.loc[idx_per, "divida_bruta"] = total_units
                    caixa_v = df.loc[idx_per, "caixa"] if "caixa" in df.columns else 0
                    if caixa_v is None or (isinstance(caixa_v, float) and np.isnan(caixa_v)):
                        caixa_v = 0
                    df.loc[idx_per, "divida_liquida"] = total_units - caixa_v
            except Exception:
                pass
    df["divida_liq_ebitda"] = np.nan
    df["divida_total_pl"] = np.nan
    df["interest_coverage_ebitda"] = np.nan
    df["interest_coverage_ebit"] = np.nan
    df["interest_coverage_ebitda_5y"] = np.nan
    df["divida_bruta_ebitda"] = np.nan
    df["divida_liq_fco"] = np.nan

    # Bank-specific derived metrics
    # PPNR = NII + Non-Interest Income - Opex (Pre-Provision Net Revenue)
    # Para UBS/BCS, usamos receita total - opex (sem provisões)
    opex_abs = df["despesas_operacionais"].abs() if "despesas_operacionais" in df.columns else 0
    df["ppnr"] = df["receita_liquida"] - opex_abs

    # Fill all expected bank columns with NaN if not already present
    expected_cols = [
        "acl_loans_sup", "acl_pct_loans_sup", "acoes_outstanding",
        "allowance_to_loans", "amortizacao_divida", "asset_yield",
        "avg_earning_assets", "avg_ib_deposits", "avg_loans",
        "avg_nib_deposits", "avg_total_assets", "avg_total_deposits",
        "capex", "captacao_divida", "casa_ratio", "compensacao",
        "contas_a_receber", "conversao_caixa", "cost_all_deposits",
        "cost_ib_deposits", "cost_ib_liabilities", "depositos_em_bancos",
        "depositos_interest_bearing_domestic", "depositos_interest_bearing_foreign",
        "depositos_noninterest_bearing", "depositos_yoy",
        "depreciacao_amortizacao", "despesa_juros", "dividendo_por_acao",
        "dividendos_pagos", "emprestimos_cp", "emprestimos_lp",
        "equity_multiplier", "fair_pbv", "fcf_financiamento", "fci", "fcl",
        "fcl_ltm", "fco", "fco_ltm", "fco_lucro_ratio", "hqla_pool",
        "imobilizado", "intangivel", "interest_spread",
        "investimentos_titulos", "ir_csll", "juros_pagos", "liquidez_total",
        "loan_growth_yoy", "loans_yield", "lpa_diluido", "lucro_yoy",
        "lucros_retidos", "marketing", "marketing_receita", "mix_juros",
        "mix_nao_juros", "nco_total", "nim_supplement", "npa", "npl",
        "operating_leverage", "passivo_circulante", "passivo_nao_circulante",
        "payout", "provision_nco", "provision_ratio", "receita_juros",
        "receita_yoy", "recompra_acoes", "revenue_stability",
        "risk_adjusted_nim", "rwa_density", "spread_alavancagem",
        "sustainable_growth", "tangible_book_value", "texas_ratio",
        "total_shareholder_return_pl",
    ]
    for col in expected_cols:
        if col not in df.columns:
            df[col] = np.nan

    # Calculate some derived metrics that we have data for
    if "receita_liquida" in df.columns:
        df["receita_yoy"] = df["receita_liquida"].pct_change(4)
    if "lucro_liquido" in df.columns:
        df["lucro_yoy"] = df["lucro_liquido"].pct_change(4)
    if "provisao_credito" in df.columns and "receita_liquida" in df.columns:
        rec_nz = df["receita_liquida"].replace(0, np.nan)
        df["provision_ratio"] = df["provisao_credito"].abs() / rec_nz

    # Loan-to-Deposit Ratio
    if "emprestimos_concedidos" in df.columns and "depositos" in df.columns:
        dep_nz = df["depositos"].replace(0, np.nan)
        df["loan_to_deposit"] = df["emprestimos_concedidos"] / dep_nz

    # Equity Multiplier = AT / PL
    if "ativo_total" in df.columns and "patrimonio_liquido" in df.columns:
        pl_nz = df["patrimonio_liquido"].replace(0, np.nan)
        df["equity_multiplier"] = df["ativo_total"] / pl_nz
        # leverage ratio (PL / AT)
        at_nz = df["ativo_total"].replace(0, np.nan)
        df["leverage_ratio"] = df["patrimonio_liquido"] / at_nz

    # Tangible Book Value (PL - intangíveis; sem dado de intangível, usar PL)
    if "patrimonio_liquido" in df.columns:
        df["tangible_book_value"] = df["patrimonio_liquido"]

    # NCO Ratio (using credit impairment / loans)
    if "provisao_credito" in df.columns and "emprestimos_concedidos" in df.columns:
        loans_nz = df["emprestimos_concedidos"].replace(0, np.nan)
        df["nco_ratio"] = (df["provisao_credito"].abs() * 4) / loans_nz

    # Risk-adjusted NIM = (NII - provisão) / earning assets (proxy: loans)
    if "nim" in df.columns:
        df["risk_adjusted_nim"] = df["nim"]  # without subtraction (no detailed data)

    # Receita LTM, Deposit YoY
    if "depositos" in df.columns:
        df["depositos_yoy"] = df["depositos"].pct_change(4)
    if "emprestimos_concedidos" in df.columns:
        df["loan_growth_yoy"] = df["emprestimos_concedidos"].pct_change(4)

    # FCO LTM/Lucro ratio (sem FCO, NaN)
    df["fco_lucro_ratio"] = np.nan

    return df, alertas


def calcular_indicadores(caminho_json: str, caminho_cronogramas: str | None = None,
                         caminho_supplement: str | None = None) -> tuple[pd.DataFrame, list[dict]]:
    """
    Calcula indicadores para empresas financeiras e asset managers.

    Returns:
        (DataFrame, lista de alertas)
    """
    alertas = []
    try:
        contas = carregar_contas(caminho_json)
    except (FileNotFoundError, json.JSONDecodeError):
        contas = []

    # SUPPLEMENT-ONLY MODE: bancos europeus (BCS, UBS) não têm contas_chave
    # XBRL US-GAAP. Se não há contas mas há supplement, construir tudo a partir
    # do supplement_data.json
    if not contas and caminho_supplement:
        return _calcular_indicadores_supplement_only(caminho_supplement, alertas)

    df_dre_itr = _montar_df_contas(contas, "ITR_dre")
    df_dre_dfp = _montar_df_contas(contas, "DFP_dre")
    df_bpa_itr = _montar_df_contas(contas, "ITR_bpa")
    df_bpa_dfp = _montar_df_contas(contas, "DFP_bpa")
    df_bpp_itr = _montar_df_contas(contas, "ITR_bpp")
    df_bpp_dfp = _montar_df_contas(contas, "DFP_bpp")
    df_dfc_itr = _montar_df_contas(contas, "ITR_dfc")
    df_dfc_dfp = _montar_df_contas(contas, "DFP_dfc")

    # DRE: DFP (annual cumulative) tem prioridade sobre ITR para desacumulação correta
    df_dre_itr_only = df_dre_itr.drop(df_dre_dfp.index.intersection(df_dre_itr.index), errors="ignore")
    df_dre = pd.concat([df_dre_itr_only, df_dre_dfp]).sort_index()
    # Para BPA/BPP: DFP tem prioridade, mas se trouxe 0 e o ITR tem valor, usar ITR
    df_bpa_itr_only = df_bpa_itr.drop(df_bpa_dfp.index.intersection(df_bpa_itr.index), errors="ignore")
    df_bpa = pd.concat([df_bpa_itr_only, df_bpa_dfp]).sort_index()
    # Preencher zeros do DFP com valores do ITR para datas duplicadas
    for idx in df_bpa_dfp.index.intersection(df_bpa_itr.index):
        for col in df_bpa.columns:
            if col == "tipo":
                continue
            if df_bpa.loc[idx, col] == 0 and col in df_bpa_itr.columns:
                itr_val = df_bpa_itr.loc[idx, col] if idx in df_bpa_itr.index else 0
                if itr_val != 0:
                    df_bpa.loc[idx, col] = itr_val

    df_bpp_itr_only = df_bpp_itr.drop(df_bpp_dfp.index.intersection(df_bpp_itr.index), errors="ignore")
    df_bpp = pd.concat([df_bpp_itr_only, df_bpp_dfp]).sort_index()
    for idx in df_bpp_dfp.index.intersection(df_bpp_itr.index):
        for col in df_bpp.columns:
            if col == "tipo":
                continue
            if df_bpp.loc[idx, col] == 0 and col in df_bpp_itr.columns:
                itr_val = df_bpp_itr.loc[idx, col] if idx in df_bpp_itr.index else 0
                if itr_val != 0:
                    df_bpp.loc[idx, col] = itr_val
    # DFC: DFP (annual cumulative) tem prioridade sobre ITR para desacumulação correta
    df_dfc_itr_only = df_dfc_itr.drop(df_dfc_dfp.index.intersection(df_dfc_itr.index), errors="ignore")
    df_dfc = pd.concat([df_dfc_itr_only, df_dfc_dfp]).sort_index()

    # Regulatory ratios (pure units)
    df_reg_itr = _montar_df_contas(contas, "ITR_reg")
    df_reg_dfp = _montar_df_contas(contas, "DFP_reg")
    df_reg = pd.concat([df_reg_itr, df_reg_dfp]).sort_index()
    df_reg = df_reg[~df_reg.index.duplicated(keep="last")] if not df_reg.empty else df_reg

    # Desacumular DRE e DFC
    # Se não há DFP (só ITR), os dados já são trimestrais — pular desacumulação
    _has_dfp = df_dre_dfp is not None and not df_dre_dfp.empty
    colunas_dre = [
        "receita_liquida", "receita_juros", "despesa_juros", "nii",
        "receita_nao_juros", "provisao_credito", "despesas_operacionais",
        "compensacao", "marketing", "ebit", "lucro_antes_ir", "ir_csll",
        "lucro_liquido", "depreciacao_amortizacao",
    ]
    colunas_dfc = [
        "fco", "depreciacao_amortizacao", "fci", "capex", "fcf",
        "amortizacao_divida", "captacao_divida", "dividendos_pagos",
        "juros_pagos", "recompra_acoes",
    ]
    if _has_dfp:
        df_dre = _desacumular(df_dre, colunas_dre, alertas)
        df_dfc = _desacumular(df_dfc, colunas_dfc, alertas)
    else:
        # Dados já trimestrais (non-US banks) — criar colunas _tri como cópia direta
        for col in colunas_dre:
            if col in df_dre.columns:
                df_dre[f"{col}_tri"] = df_dre[col]
        for col in colunas_dfc:
            if col in df_dfc.columns:
                df_dfc[f"{col}_tri"] = df_dfc[col]

    # Montar resultado
    resultado = pd.DataFrame(index=df_dre.index)
    resultado["ano"] = resultado.index.year
    resultado["trimestre"] = (resultado.index.month - 1) // 3 + 1
    resultado["label"] = resultado.apply(
        lambda r: f"{int(r['trimestre'])}T{int(r['ano']) % 100:02d}", axis=1
    )

    def _tri(col):
        return df_dre.get(f"{col}_tri", df_dre.get(col))

    def _tri_dfc(col):
        return df_dfc.get(f"{col}_tri", df_dfc.get(col))

    # =====================================================================
    # 1. DRE
    # =====================================================================
    resultado["receita_liquida"] = _tri("receita_liquida")
    resultado["receita_juros"] = _tri("receita_juros")
    resultado["despesa_juros"] = _tri("despesa_juros")
    resultado["nii"] = _tri("nii")
    resultado["receita_nao_juros"] = _tri("receita_nao_juros")
    resultado["provisao_credito"] = _tri("provisao_credito")
    resultado["despesas_operacionais"] = _tri("despesas_operacionais")
    resultado["compensacao"] = _tri("compensacao")
    resultado["marketing"] = _tri("marketing")
    resultado["ebit"] = _tri("ebit")
    resultado["lucro_antes_ir"] = _tri("lucro_antes_ir")
    resultado["ir_csll"] = _tri("ir_csll")
    resultado["lucro_liquido"] = _tri("lucro_liquido")
    resultado["depreciacao_amortizacao"] = _tri_dfc("depreciacao_amortizacao")

    # EBITDA
    da = _safe_get(resultado, "depreciacao_amortizacao", 0).fillna(0)
    resultado["ebitda"] = resultado["ebit"] + da

    # Margens
    receita = resultado["receita_liquida"].replace(0, np.nan)
    resultado["margem_liquida"] = resultado["lucro_liquido"] / receita
    resultado["margem_ebitda"] = resultado["ebitda"] / receita
    resultado["margem_ebit"] = resultado["ebit"] / receita

    # NIM (Net Interest Margin) — NII / Earning Assets (proxy: NII * 4 / Ativo Total)
    # Será calculado após balanço

    # Efficiency Ratio = Despesas Operacionais / Receita Total
    # Para bancos (NII > 0): receita = NII + Receita Não-Juros
    # Para cards/outros (NII <= 0): usar receita_liquida diretamente
    nii_eff = _safe_get(resultado, "nii", 0).fillna(0)
    rnj_eff = _safe_get(resultado, "receita_nao_juros", 0).fillna(0)
    receita_banco = (nii_eff + rnj_eff).replace(0, np.nan)
    # Só usar fórmula de banco quando NII é positivo (banco de verdade)
    receita_eff = receita_banco.where(nii_eff > 0, receita)
    resultado["efficiency_ratio"] = (
        _safe_get(resultado, "despesas_operacionais", 0).fillna(0).abs() / receita_eff
    )

    # Provision Ratio = Provisão para Crédito / Receita
    resultado["provision_ratio"] = (
        _safe_get(resultado, "provisao_credito", 0).fillna(0).abs() / receita
    )

    # Revenue Mix: % receita de juros e % receita não-juros sobre receita total
    rec_juros = _safe_get(resultado, "receita_juros", 0).fillna(0)
    rec_nao_juros = _safe_get(resultado, "receita_nao_juros", 0).fillna(0)
    resultado["mix_juros"] = rec_juros / receita
    resultado["mix_nao_juros"] = rec_nao_juros / receita

    # Marketing / Receita (card member rewards para card companies)
    mkt = _safe_get(resultado, "marketing", 0).fillna(0).abs()
    resultado["marketing_receita"] = mkt / receita

    # Growth
    resultado["receita_yoy"] = resultado["receita_liquida"].pct_change(4)
    resultado["lucro_yoy"] = resultado["lucro_liquido"].pct_change(4)

    # =====================================================================
    # 2. FLUXO DE CAIXA
    # =====================================================================
    resultado["fco"] = _tri_dfc("fco")
    resultado["fci"] = _tri_dfc("fci")
    resultado["fcf_financiamento"] = _tri_dfc("fcf")
    resultado["capex"] = _tri_dfc("capex")
    capex = _safe_get(resultado, "capex", 0).fillna(0)
    resultado["fcl"] = resultado["fco"] + capex
    resultado["juros_pagos"] = _tri_dfc("juros_pagos")
    resultado["amortizacao_divida"] = _tri_dfc("amortizacao_divida")
    resultado["captacao_divida"] = _tri_dfc("captacao_divida")
    resultado["dividendos_pagos"] = _tri_dfc("dividendos_pagos")
    resultado["recompra_acoes"] = _tri_dfc("recompra_acoes")

    # Conversão de caixa
    ebitda_nz = resultado["ebitda"].replace(0, np.nan)
    resultado["conversao_caixa"] = resultado["fco"] / ebitda_nz

    # =====================================================================
    # 3. BALANÇO
    # =====================================================================
    if not df_bpa.empty:
        resultado["ativo_total"] = _safe_get(df_bpa, "ativo_total")
        resultado["caixa"] = _safe_get(df_bpa, "caixa")
        resultado["investimentos_titulos"] = _safe_get(df_bpa, "investimentos_titulos")
        resultado["depositos_em_bancos"] = _safe_get(df_bpa, "depositos_em_bancos")
        resultado["hqla_pool"] = _safe_get(df_bpa, "hqla_pool")
        resultado["emprestimos_concedidos"] = _safe_get(df_bpa, "emprestimos_concedidos")
        resultado["contas_a_receber"] = _safe_get(df_bpa, "contas_a_receber")
        resultado["imobilizado"] = _safe_get(df_bpa, "imobilizado")
        resultado["intangivel"] = _safe_get(df_bpa, "intangivel")
        resultado["carteira_credito_bruta"] = _safe_get(df_bpa, "carteira_credito_bruta")
        resultado["provisao_acumulada"] = _safe_get(df_bpa, "provisao_acumulada")
        resultado["npl"] = _safe_get(df_bpa, "npl")
        resultado["lucros_retidos"] = _safe_get(df_bpa, "lucros_retidos")

    if not df_bpp.empty:
        resultado["depositos"] = _safe_get(df_bpp, "depositos")
        resultado["depositos_noninterest_bearing"] = _safe_get(df_bpp, "depositos_noninterest_bearing")
        resultado["depositos_interest_bearing_domestic"] = _safe_get(df_bpp, "depositos_interest_bearing_domestic")
        resultado["depositos_interest_bearing_foreign"] = _safe_get(df_bpp, "depositos_interest_bearing_foreign")
        resultado["emprestimos_cp"] = _safe_get(df_bpp, "emprestimos_cp")
        stb = _safe_get(df_bpp, "short_term_borrowings", 0).fillna(0)
        emp_cp_val = _safe_get(resultado, "emprestimos_cp", 0).fillna(0)
        resultado["emprestimos_cp"] = emp_cp_val + stb
        resultado["emprestimos_lp"] = _safe_get(df_bpp, "emprestimos_lp")
        resultado["patrimonio_liquido"] = _safe_get(df_bpp, "patrimonio_liquido")
        resultado["passivo_circulante"] = _safe_get(df_bpp, "passivo_circulante")
        resultado["passivo_nao_circulante"] = _safe_get(df_bpp, "passivo_nao_circulante")

    # Dívida CP via cronograma: se EDGAR não trouxe tag de CP, usar vencimentos <= 1 ano
    emp_cp_serie = _safe_get(resultado, "emprestimos_cp", 0).fillna(0)
    emp_lp_serie = _safe_get(resultado, "emprestimos_lp", 0).fillna(0)
    if caminho_cronogramas:
        cp_cron = _extrair_cp_do_cronograma(caminho_cronogramas)
        if cp_cron:
            for idx in resultado.index:
                if emp_cp_serie.loc[idx] == 0 and idx in cp_cron and cp_cron[idx] > 0:
                    emp_cp_serie.loc[idx] = cp_cron[idx]
                    # Subtrair do LP para não contar em dobro
                    emp_lp_serie.loc[idx] = max(0, emp_lp_serie.loc[idx] - cp_cron[idx])
            resultado["emprestimos_cp"] = emp_cp_serie
            resultado["emprestimos_lp"] = emp_lp_serie

    # Dívida
    emp_cp = emp_cp_serie
    emp_lp = emp_lp_serie
    caixa_val = _safe_get(resultado, "caixa", 0).fillna(0)

    resultado["divida_bruta"] = emp_cp + emp_lp
    resultado["liquidez_total"] = caixa_val
    resultado["divida_liquida"] = resultado["divida_bruta"] - resultado["liquidez_total"]

    # =====================================================================
    # 4. INDICADORES ESPECÍFICOS FINANCEIRAS
    # =====================================================================
    at = _safe_get(resultado, "ativo_total").replace(0, np.nan)
    pl = _safe_get(resultado, "patrimonio_liquido").replace(0, np.nan)
    ll = resultado["lucro_liquido"]

    # Médias (Assaf Neto: usar média do período para evitar distorções sazonais)
    at_avg = ((at + at.shift(1)) / 2).replace(0, np.nan)
    pl_avg = ((pl + pl.shift(1)) / 2).replace(0, np.nan)

    # ROA = Lucro Líquido (anualizado) / Ativo Total Médio
    resultado["roa"] = (ll * 4) / at_avg

    # ROE = Lucro Líquido (anualizado) / PL Médio
    resultado["roe"] = (ll * 4) / pl_avg

    # NIM = NII (anualizado) / Ativo Total Médio
    nii = _safe_get(resultado, "nii", 0).fillna(0)
    resultado["nim"] = (nii * 4) / at_avg

    # Equity Multiplier = AT / PL (usa média para consistência com DuPont)
    resultado["equity_multiplier"] = at_avg / pl_avg

    # DuPont: Contribuição da alavancagem = ROA × (Equity Multiplier - 1)
    resultado["spread_alavancagem"] = resultado["roa"] * (resultado["equity_multiplier"] - 1)

    # Debt-to-Equity = Dívida Bruta / PL
    resultado["divida_total_pl"] = resultado["divida_bruta"] / pl

    # Tangible Book Value = PL - Intangíveis
    intangivel = _safe_get(resultado, "intangivel", 0).fillna(0)
    resultado["tangible_book_value"] = _safe_get(resultado, "patrimonio_liquido", 0).fillna(0) - intangivel

    # Equity-to-Assets = PL / Ativo Total
    resultado["leverage_ratio"] = pl / at

    # Loan-to-Deposit Ratio
    emprestimos_conc = _safe_get(resultado, "emprestimos_concedidos", 0).fillna(0)
    depositos_val = _safe_get(resultado, "depositos", 0).fillna(0).replace(0, np.nan)
    resultado["loan_to_deposit"] = emprestimos_conc / depositos_val

    # Deposit Growth YoY
    depositos_raw = _safe_get(resultado, "depositos")
    resultado["depositos_yoy"] = depositos_raw.pct_change(4) if depositos_raw is not None else np.nan

    # NPL Coverage Ratio (provisão acumulada / carteira bruta - como proxy)
    prov_acum = _safe_get(resultado, "provisao_acumulada", 0).fillna(0).abs()
    cart_bruta = _safe_get(resultado, "carteira_credito_bruta", 0).fillna(0).replace(0, np.nan)
    resultado["allowance_to_loans"] = prov_acum / cart_bruta

    # =====================================================================
    # 4B. INDICADORES ESPECÍFICOS DE BANCOS
    # =====================================================================

    # --- Regulatory Ratios (do XBRL, unidade pure) ---
    if not df_reg.empty:
        for col in ["tier1_ratio", "total_capital_ratio", "slr", "cet1_ratio"]:
            if col in df_reg.columns:
                resultado[col] = df_reg[col].reindex(resultado.index, method="ffill")

    # --- Depósitos: breakdown e CASA ---
    dep_nib = _safe_get(resultado, "depositos_noninterest_bearing", 0).fillna(0)
    dep_total = _safe_get(resultado, "depositos", 0).fillna(0).replace(0, np.nan)
    resultado["casa_ratio"] = dep_nib / dep_total

    # --- NPL e Coverage Ratio (ACL / NPL) --- Frost p.444
    npl = _safe_get(resultado, "npl", 0).fillna(0)
    resultado["npl_total"] = npl
    npl_nz = npl.replace(0, np.nan)
    resultado["coverage_ratio"] = prov_acum / npl_nz

    # --- NPL Ratio = NPL / Carteira Bruta (inadimplência >90 dias / total empréstimos) ---
    resultado["npl_ratio"] = npl / cart_bruta

    # --- Texas Ratio = NPL / (TCE + ACL) ---
    tce = _safe_get(resultado, "tangible_book_value", 0).fillna(0)
    resultado["texas_ratio"] = npl / (tce + prov_acum).replace(0, np.nan)

    # --- PPNR = NII + Non-Interest Income - Opex (Frost: "pre-provision operating profit") ---
    nii_val = _safe_get(resultado, "nii", 0).fillna(0)
    receita_nao_juros = _safe_get(resultado, "receita_nao_juros", 0).fillna(0)
    opex = _safe_get(resultado, "despesas_operacionais", 0).fillna(0).abs()
    resultado["ppnr"] = nii_val + receita_nao_juros - opex

    # --- RoTCE = LL (anualizado) / TCE médio ---
    tce_avg = ((tce + tce.shift(1)) / 2).replace(0, np.nan)
    resultado["rotce"] = (ll * 4) / tce_avg

    # --- Risk-Adjusted NIM = (NII - Provisão) anualizado / Ativo Total Médio ---
    # Idealmente usaria Earning Assets, mas proxy com AT médio (como NIM)
    provisao = _safe_get(resultado, "provisao_credito", 0).fillna(0).abs()
    resultado["risk_adjusted_nim"] = ((nii_val - provisao) * 4) / at_avg

    # --- RWA Density = RWA / Ativo Total ---
    # RWA derivado: se temos tier1_ratio e tier1_capital, RWA = Tier1Capital / Tier1Ratio
    # Proxy: se temos total_capital_ratio, RWA ≈ (PL proxy) / total_capital_ratio
    # Como não temos RWA direto em USD, usamos o CET1/Tier1 ratios já extraídos
    # e calculamos RWA implícito
    tier1_ratio = _safe_get(resultado, "tier1_ratio", 0).fillna(0)
    if (tier1_ratio > 0).any():
        # Tier1 Capital ≈ PL (proxy simplificado para bancos)
        pl_proxy = _safe_get(resultado, "patrimonio_liquido", 0).fillna(0)
        rwa_implied = pl_proxy / tier1_ratio.replace(0, np.nan)
        resultado["rwa_density"] = rwa_implied / at.replace(0, np.nan)
    else:
        resultado["rwa_density"] = np.nan

    # --- Operating Leverage Y/Y = Revenue Growth% - Opex Growth% ---
    # Para bancos: usar NII + Receita Não-Juros (receita_liquida tem problemas de desacumulação)
    receita_ol = (nii_val + receita_nao_juros).where(nii_val.abs() > 0, resultado["receita_liquida"])
    receita_yoy_pct = receita_ol.pct_change(4)
    opex_yoy_pct = opex.pct_change(4)
    resultado["operating_leverage"] = receita_yoy_pct - opex_yoy_pct

    # --- Reserve / Loans (ACL / Gross Loans) --- já temos como allowance_to_loans ---

    # --- Average Loan Growth YoY (proxy com saldo fim de período) ---
    loans = _safe_get(resultado, "emprestimos_concedidos", 0).fillna(0)
    resultado["loan_growth_yoy"] = loans.pct_change(4)

    # --- RWA implícito (para gráfico de evolução) ---
    if (tier1_ratio > 0).any():
        pl_proxy = _safe_get(resultado, "patrimonio_liquido", 0).fillna(0)
        resultado["rwa_implied"] = pl_proxy / tier1_ratio.replace(0, np.nan)

    # --- Efficiency Ratio já calculado acima ---

    # =====================================================================
    # 5. MÚLTIPLOS LTM
    # =====================================================================
    resultado["ebitda_ltm"] = resultado["ebitda"].rolling(4).sum()
    resultado["ebit_ltm"] = resultado["ebit"].rolling(4).sum()
    resultado["fco_ltm"] = resultado["fco"].rolling(4).sum()
    resultado["receita_ltm"] = resultado["receita_liquida"].rolling(4).sum()
    resultado["lucro_ltm"] = resultado["lucro_liquido"].rolling(4).sum()
    resultado["fcl_ltm"] = resultado["fcl"].rolling(4).sum()

    ebitda_ltm = resultado["ebitda_ltm"].replace(0, np.nan)
    fco_ltm = resultado["fco_ltm"].replace(0, np.nan)

    resultado["divida_liq_ebitda"] = resultado["divida_liquida"] / ebitda_ltm
    resultado["divida_bruta_ebitda"] = resultado["divida_bruta"] / ebitda_ltm
    resultado["divida_liq_fco"] = resultado["divida_liquida"] / fco_ltm

    # Interest Coverage
    desp_juros_ltm = _safe_get(resultado, "despesa_juros", 0).fillna(0).abs().rolling(4).sum().replace(0, np.nan)
    resultado["interest_coverage_ebitda"] = ebitda_ltm / desp_juros_ltm
    resultado["interest_coverage_ebit"] = resultado["ebit_ltm"] / desp_juros_ltm

    # Payout
    div_pagos_ltm = _safe_get(resultado, "dividendos_pagos", 0).fillna(0).abs().rolling(4).sum()
    lucro_ltm_pos = resultado["lucro_ltm"].where(resultado["lucro_ltm"] > 0, np.nan)
    resultado["payout"] = div_pagos_ltm / lucro_ltm_pos

    # Shareholder Yield = (Dividendos + Recompra) / PL
    recompra_ltm = _safe_get(resultado, "recompra_acoes", 0).fillna(0).abs().rolling(4).sum()
    resultado["total_shareholder_return_pl"] = (div_pagos_ltm + recompra_ltm) / pl

    # Sustainable Growth Rate = ROE × (1 - Payout)
    resultado["sustainable_growth"] = resultado["roe"] * (1 - resultado["payout"].fillna(0))

    # Qualidade de Lucros: FCO LTM / Lucro LTM
    resultado["fco_lucro_ratio"] = fco_ltm / lucro_ltm_pos

    # Revenue Stability (Moody's) = mean(YoY) / std(YoY) sobre 20 trimestres
    receita_yoy = resultado["receita_liquida"].pct_change(4)
    resultado["receita_yoy"] = receita_yoy
    mean_yoy = receita_yoy.rolling(20, min_periods=8).mean()
    std_yoy = receita_yoy.rolling(20, min_periods=8).std().replace(0, np.nan)
    resultado["revenue_stability"] = mean_yoy / std_yoy

    # EBITDA/Interest Coverage média 5 anos (Moody's: 20 trimestres)
    resultado["interest_coverage_ebitda_5y"] = (
        ebitda_ltm.rolling(20, min_periods=8).mean()
        / desp_juros_ltm.rolling(20, min_periods=8).mean().replace(0, np.nan)
    )

    # Fair P/BV teórico = Payout × (ROE - g) / (Ke - g) — Damodaran DDM
    # Usa Ke=10% como proxy; g = sustainable growth (ROE × retention)
    ke_proxy = 0.10
    payout_ratio = resultado["payout"].fillna(0).clip(0, 1)
    g_sustainable = resultado["roe"] * (1 - payout_ratio)
    # Limitar g para não exceder Ke (evita divisão por zero ou valores negativos)
    g_capped = g_sustainable.clip(upper=ke_proxy - 0.005)
    resultado["fair_pbv"] = payout_ratio * (resultado["roe"] - g_capped) / (ke_proxy - g_capped)

    # =====================================================================
    # 6. PER-SHARE DATA
    # =====================================================================
    df_psd_itr = _montar_df_contas(contas, "ITR_psd")
    df_psd_dfp = _montar_df_contas(contas, "DFP_psd")
    df_psd = pd.concat([df_psd_itr, df_psd_dfp]).sort_index()
    df_psd = df_psd[~df_psd.index.duplicated(keep="last")]

    if not df_psd.empty:
        resultado["lpa_diluido"] = _safe_get(df_psd, "lpa_diluido")
        resultado["dividendo_por_acao"] = _safe_get(df_psd, "dividendo_por_acao")
        resultado["acoes_outstanding"] = _safe_get(df_psd, "acoes_outstanding")

    # WACC proxy
    alertas.append({
        "tipo": "proxy",
        "indicador": "WACC",
        "mensagem": "WACC não calculado para financeiras (estrutura de capital diferente). Use ROE e ROA como referência.",
    })

    # =====================================================================
    # 8. DADOS DO FINANCIAL SUPPLEMENT (sobrescreve proxies do XBRL)
    # =====================================================================
    if caminho_supplement:
        df_sup = _carregar_supplement(caminho_supplement)
        if not df_sup.empty:
            # Mapear colunas do supplement para o resultado
            sup_mapping = {
                # Capital (real, não proxy)
                "sup_cet1_ratio": "cet1_ratio",
                "sup_cet1_capital": "cet1_capital",
                "sup_rwa_standardized": "rwa_real",
                "sup_slr": "slr",
                "sup_lcr": "lcr",
                "sup_nsfr": "nsfr",
                "sup_total_capital_ratio": "total_capital_ratio",
                "sup_tier1_ratio": "tier1_ratio",
                "sup_hqla_pool": "hqla_pool",
                # Average Balances (BK format)
                "sup_avg_total_assets": "avg_total_assets",
                "sup_avg_earning_assets": "avg_earning_assets",
                "sup_avg_loans": "avg_loans",
                "sup_avg_total_deposits": "avg_total_deposits",
                "sup_avg_ib_deposits": "avg_ib_deposits",
                "sup_avg_nib_deposits": "avg_nib_deposits",
                # Average Balances (Barclays format)
                "sup_avg_customer_deposits": "avg_total_deposits",
                "sup_avg_customer_loans": "avg_loans",
                # Yields & Rates (BK format)
                "sup_avg_earning_assets_yield": "asset_yield",
                "sup_avg_loans_yield": "loans_yield",
                "sup_avg_ib_deposits_rate": "cost_ib_deposits",
                "sup_avg_total_ib_liabilities_rate": "cost_ib_liabilities",
                "sup_nim": "nim_supplement",
                "sup_interest_spread": "interest_spread",
                # Yields & Rates (Barclays format)
                "sup_rote": "rote_supplement",
                "sup_loan_loss_rate": "nco_ratio_supplement",
                "sup_nco_ratio": "nco_ratio_supplement",
                "sup_loan_to_deposit": "loan_to_deposit_supplement",
                # Credit Quality (BK format)
                "sup_nco_total": "nco_total",
                "sup_npa": "npa",
                "sup_acl_loans": "acl_loans_sup",
                "sup_acl_pct_loans": "acl_pct_loans_sup",
                # Credit Quality (Barclays format)
                "sup_carteira_credito_bruta": "carteira_credito_bruta_sup",
                "sup_provisao_acumulada": "provisao_acumulada_sup",
                "sup_npl": "npl_sup",
                "sup_coverage_ratio": "coverage_ratio_sup",
                "sup_reserve_ratio": "reserve_ratio_sup",
            }
            for sup_col, res_col in sup_mapping.items():
                if sup_col in df_sup.columns:
                    resultado[res_col] = df_sup[sup_col].reindex(resultado.index)

            # Para bancos europeus (BCS): caixa = hqla_pool * 1e6 (supplement em milhões)
            # converter para unidades para ser consistente com o resto do contas_chave
            if "sup_hqla_pool" in df_sup.columns:
                hqla_sup = df_sup["sup_hqla_pool"].reindex(resultado.index) * 1e6
                resultado["hqla_pool"] = hqla_sup
                if "caixa" in resultado.columns:
                    caixa_atual = resultado["caixa"]
                    mask = (caixa_atual.isna() | (caixa_atual == 0)) & hqla_sup.notna()
                    resultado.loc[mask, "caixa"] = hqla_sup[mask]
                else:
                    resultado["caixa"] = hqla_sup

            # Calcular indicadores derivados do supplement
            # NIM real (do supplement) sobrescreve o proxy
            if "nim_supplement" in resultado.columns:
                nim_sup = resultado["nim_supplement"]
                resultado["nim"] = nim_sup.where(nim_sup.notna(), resultado["nim"])

            # NIB Deposits % (CASA real com averages)
            avg_nib = _safe_get(resultado, "avg_nib_deposits", 0).fillna(0)
            avg_dep = _safe_get(resultado, "avg_total_deposits", 0).fillna(0).replace(0, np.nan)
            casa_sup = avg_nib / avg_dep
            resultado["casa_ratio"] = casa_sup.where(casa_sup.notna(), resultado["casa_ratio"])

            # Cost of All Deposits = Interest on Deposits / Avg Total Deposits
            # Aproximação: cost_ib_deposits × (avg_ib_deposits / avg_total_deposits)
            ib_dep = _safe_get(resultado, "avg_ib_deposits", 0).fillna(0)
            cost_ib = _safe_get(resultado, "cost_ib_deposits", 0).fillna(0)
            resultado["cost_all_deposits"] = cost_ib * (ib_dep / avg_dep)

            # NCO Ratio = NCO (anualizado) / Avg Loans
            # NCO do supplement está em milhões, avg_loans também em milhões
            nco = _safe_get(resultado, "nco_total", 0).fillna(0)
            avg_loans = _safe_get(resultado, "avg_loans", 0).fillna(0).replace(0, np.nan)
            resultado["nco_ratio"] = (nco * 4) / avg_loans  # anualizado, ambos em milhões

            # Provision / NCOs — provisão do XBRL em unidades, NCO em milhões → converter
            # Indica se o banco está provisionando mais (>1x) ou menos (<1x) do que perde
            prov_tri = _safe_get(resultado, "provisao_credito", 0).fillna(0).abs() / 1e6  # converter para milhões
            nco_abs = nco.abs().replace(0, np.nan)  # NCO já em milhões
            resultado["provision_nco"] = prov_tri / nco_abs

            # RWA real e CET1 real sobrescrevem proxies
            rwa_real = _safe_get(resultado, "rwa_real", 0).fillna(0)
            if (rwa_real > 0).any():
                at_sup = _safe_get(resultado, "avg_total_assets", 0).fillna(0).replace(0, np.nan)
                resultado["rwa_density"] = (rwa_real * 1e6) / (at_sup * 1e6)  # ambos em milhões
                resultado["rwa_implied"] = rwa_real * 1e6  # converter para unidade consistente

            # Barclays-style credit quality: sobrescrever com dados do supplement
            cart_sup = _safe_get(resultado, "carteira_credito_bruta_sup", 0).fillna(0)
            if (cart_sup > 0).any():
                # Supplement tem dados em milhões — converter para unidades
                for col_sup, col_res in [
                    ("carteira_credito_bruta_sup", "carteira_credito_bruta"),
                    ("provisao_acumulada_sup", "provisao_acumulada"),
                    ("npl_sup", "npl_total"),
                ]:
                    vals = _safe_get(resultado, col_sup, 0).fillna(0)
                    if (vals > 0).any():
                        resultado[col_res] = vals * 1e6  # milhões → unidades

            # Coverage ratio do supplement (já calculado no parser)
            cov_sup = _safe_get(resultado, "coverage_ratio_sup", 0).fillna(0)
            if (cov_sup > 0).any():
                resultado["coverage_ratio"] = cov_sup.where(cov_sup > 0, resultado.get("coverage_ratio", np.nan))

            # Loan-to-deposit do supplement
            ltd_sup = _safe_get(resultado, "loan_to_deposit_supplement", 0).fillna(0)
            if (ltd_sup > 0).any():
                resultado["loan_to_deposit"] = ltd_sup.where(ltd_sup > 0, resultado.get("loan_to_deposit", np.nan))

            # NCO ratio do supplement (loan loss rate)
            nco_sup = _safe_get(resultado, "nco_ratio_supplement", 0).fillna(0)
            if (nco_sup.abs() > 0).any():
                resultado["nco_ratio"] = nco_sup.where(nco_sup.abs() > 0, resultado.get("nco_ratio", np.nan))

            # NPA do supplement complementa NPL quando XBRL é zero
            npa_sup = _safe_get(resultado, "npa", 0).fillna(0)
            npl_atual = _safe_get(resultado, "npl_total", 0).fillna(0)
            for idx in resultado.index:
                if npl_atual.loc[idx] == 0 and npa_sup.loc[idx] > 0:
                    resultado.loc[idx, "npl_total"] = npa_sup.loc[idx] * 1e6

            # Recalcular coverage/texas/npl_ratio com NPL atualizado
            npl_upd = resultado["npl_total"].replace(0, np.nan)
            prov_acum_upd = _safe_get(resultado, "provisao_acumulada", 0).fillna(0).abs()
            cart_bruta_upd = _safe_get(resultado, "carteira_credito_bruta", 0).fillna(0).replace(0, np.nan)
            if "coverage_ratio" not in resultado.columns or resultado["coverage_ratio"].isna().all():
                resultado["coverage_ratio"] = prov_acum_upd / npl_upd

            tce_upd = _safe_get(resultado, "tangible_book_value", 0).fillna(0)
            resultado["texas_ratio"] = resultado["npl_total"] / (tce_upd + prov_acum_upd).replace(0, np.nan)
            resultado["npl_ratio"] = resultado["npl_total"] / cart_bruta_upd

    return resultado, alertas


# =========================================================================
# TABELAS FORMATADAS
# =========================================================================

def formatar_tabela_dre(df: pd.DataFrame, setor: str = "Card / Outros") -> pd.DataFrame:
    if setor == "Banco":
        colunas = {
            "label": "Período",
            "receita_liquida": "Receita Total",
            "nii": "NII",
            "receita_nao_juros": "Receita Não-Juros",
            "provisao_credito": "Provisão p/ Crédito",
            "despesas_operacionais": "Despesas Operacionais",
            "ppnr": "PPNR",
            "efficiency_ratio": "Efficiency Ratio",
            "lucro_liquido": "Lucro Líquido",
        }
    elif setor == "Asset Manager":
        colunas = {
            "label": "Período",
            "receita_liquida": "Receita Total",
            "despesas_operacionais": "Despesas Operacionais",
            "efficiency_ratio": "Efficiency Ratio",
            "ebit": "EBIT",
            "margem_ebit": "Margem EBIT",
            "ebitda": "EBITDA",
            "margem_ebitda": "Margem EBITDA",
            "lucro_antes_ir": "Lucro Antes IR",
            "ir_csll": "IR",
            "lucro_liquido": "Lucro Líquido",
            "margem_liquida": "Margem Líquida",
        }
    else:
        colunas = {
            "label": "Período",
            "receita_liquida": "Receita Total",
            "nii": "NII (Net Interest Income)",
            "receita_nao_juros": "Receita Não-Juros",
            "provisao_credito": "Provisão p/ Crédito",
            "despesas_operacionais": "Despesas Operacionais",
            "efficiency_ratio": "Efficiency Ratio",
            "ebit": "EBIT",
            "margem_ebit": "Margem EBIT",
            "ebitda": "EBITDA",
            "margem_ebitda": "Margem EBITDA",
            "lucro_antes_ir": "Lucro Antes IR",
            "ir_csll": "IR",
            "lucro_liquido": "Lucro Líquido",
            "margem_liquida": "Margem Líquida",
        }
    cols = [c for c in colunas if c in df.columns]
    tabela = df[cols].copy()
    tabela.columns = [colunas[c] for c in cols]
    return tabela


def formatar_tabela_fluxo_caixa(df: pd.DataFrame) -> pd.DataFrame:
    colunas = {
        "label": "Período",
        "fco": "FCO",
        "conversao_caixa": "FCO/EBITDA",
        "capex": "Capex",
        "fcl": "FCL",
        "juros_pagos": "Juros Pagos",
        "amortizacao_divida": "Amortiz. Dívida",
        "captacao_divida": "Captação",
        "dividendos_pagos": "Dividendos Pagos",
        "recompra_acoes": "Recompra de Ações",
        "fcf_financiamento": "FC Financiamento",
    }
    cols = [c for c in colunas if c in df.columns]
    tabela = df[cols].copy()
    tabela.columns = [colunas[c] for c in cols]
    return tabela


def formatar_tabela_banco_capital(df: pd.DataFrame) -> pd.DataFrame:
    """Tabela: Capital e Solvência (bancos)."""
    colunas = {
        "label": "Período",
        "cet1_ratio": "CET1 Ratio",
        "tier1_ratio": "Tier 1 Ratio",
        "total_capital_ratio": "Total Capital Ratio",
        "slr": "Leverage Ratio (SLR)",
        "rwa_implied": "RWA ($)",
        "rwa_density": "RWA Density",
        "leverage_ratio": "Equity-to-Assets",
        "tangible_book_value": "Tangible Book Value",
    }
    cols = [c for c in colunas if c in df.columns]
    tabela = df[cols].copy()
    tabela.columns = [colunas[c] for c in cols]
    return tabela


def formatar_tabela_banco_liquidez(df: pd.DataFrame) -> pd.DataFrame:
    """Tabela: Liquidez e Funding (bancos)."""
    colunas = {
        "label": "Período",
        "depositos": "Depósitos Totais",
        "depositos_noninterest_bearing": "Depósitos Não-Remunerados",
        "casa_ratio": "CASA Ratio",
        "loan_to_deposit": "Loan-to-Deposit",
        "lcr": "LCR",
        "nsfr": "NSFR",
        "depositos_yoy": "Depósitos YoY",
    }
    cols = [c for c in colunas if c in df.columns]
    tabela = df[cols].copy()
    tabela.columns = [colunas[c] for c in cols]
    return tabela


def formatar_tabela_banco_credito(df: pd.DataFrame) -> pd.DataFrame:
    """Tabela: Qualidade de Crédito (bancos)."""
    colunas = {
        "label": "Período",
        "carteira_credito_bruta": "Carteira Bruta",
        "loan_growth_yoy": "Loan Growth YoY",
        "provisao_acumulada": "Provisão (ACL)",
        "npl_total": "NPL (Nonaccrual)",
        "npl_ratio": "NPL Ratio",
        "allowance_to_loans": "Reserve / Loans",
        "coverage_ratio": "Coverage (ACL/NPL)",
        "texas_ratio": "Texas Ratio",
        "provisao_credito": "Provisão (DRE tri)",
        "provision_ratio": "Provision Ratio",
    }
    cols = [c for c in colunas if c in df.columns]
    tabela = df[cols].copy()
    tabela.columns = [colunas[c] for c in cols]
    return tabela


def formatar_tabela_banco_rentabilidade(df: pd.DataFrame) -> pd.DataFrame:
    """Tabela: Rentabilidade e Eficiência (bancos) — Prateleira 1 + 2 do ranking."""
    colunas = {
        "label": "Período",
        "rotce": "RoTCE (anualizado)",
        "roe": "ROE (anualizado)",
        "roa": "ROA (anualizado)",
        "nim": "NIM",
        "risk_adjusted_nim": "Risk-Adj NIM",
        "asset_yield": "Asset Yield",
        "cost_ib_deposits": "Cost of IB Deposits",
        "cost_all_deposits": "Cost of All Deposits",
        "interest_spread": "Interest Spread",
        "ppnr": "PPNR",
        "efficiency_ratio": "Efficiency Ratio",
        "operating_leverage": "Oper. Leverage YoY",
        "nco_ratio": "NCO Ratio (anual.)",
        "provision_nco": "Provision / NCOs",
        "payout": "Payout (LTM)",
    }
    cols = [c for c in colunas if c in df.columns]
    tabela = df[cols].copy()
    tabela.columns = [colunas[c] for c in cols]
    return tabela


def formatar_tabela_estrutura_capital(df: pd.DataFrame) -> pd.DataFrame:
    colunas = {
        "label": "Período",
        "caixa": "Caixa",
        "depositos": "Depósitos",
        "emprestimos_cp": "Dívida CP",
        "emprestimos_lp": "Dívida LP",
        "divida_bruta": "Dívida Bruta",
        "divida_liquida": "Dívida Líquida",
        "patrimonio_liquido": "Patrimônio Líquido",
        "tangible_book_value": "Tangible Book Value",
        "divida_liq_ebitda": "Dív.Líq/EBITDA",
        "divida_liq_fco": "Dív.Líq/FCO",
    }
    cols = [c for c in colunas if c in df.columns]
    tabela = df[cols].copy()
    tabela.columns = [colunas[c] for c in cols]
    return tabela


def formatar_tabela_multiplos(df: pd.DataFrame, setor: str = "Card / Outros") -> pd.DataFrame:
    if setor == "Asset Manager":
        colunas = {
            "label": "Período",
            "roe": "ROE (anualizado)",
            "roa": "ROA (anualizado)",
            "margem_ebit": "Margem EBIT",
            "margem_ebitda": "Margem EBITDA",
            "margem_liquida": "Margem Líquida",
            "efficiency_ratio": "Efficiency Ratio",
            "equity_multiplier": "Equity Multiplier",
            "spread_alavancagem": "Spread Alavancagem",
            "divida_liq_ebitda": "Dív.Líq/EBITDA",
            "divida_bruta_ebitda": "Dív.Bruta/EBITDA",
            "divida_liq_fco": "Dív.Líq/FCO",
            "interest_coverage_ebitda": "EBITDA/Desp.Fin (LTM)",
            "interest_coverage_ebitda_5y": "EBITDA/Desp.Fin (5A)",
            "divida_total_pl": "Dív.Total/PL",
            "leverage_ratio": "Equity-to-Assets",
            "revenue_stability": "Estab. Receita (Moody's)",
            "payout": "Payout (LTM)",
            "sustainable_growth": "Cresc. Sustentável",
            "fco_lucro_ratio": "FCO/Lucro (LTM)",
            "fair_pbv": "Fair P/BV Teórico",
            "total_shareholder_return_pl": "Retorno ao Acionista/PL",
        }
    else:
        colunas = {
            "label": "Período",
            "roe": "ROE (anualizado)",
            "roa": "ROA (anualizado)",
            "nim": "NIM (anualizado)",
            "efficiency_ratio": "Efficiency Ratio",
            "provision_ratio": "Provision Ratio",
            "equity_multiplier": "Equity Multiplier",
            "spread_alavancagem": "Spread Alavancagem",
            "marketing_receita": "Marketing/Receita",
            "divida_liq_ebitda": "Dív.Líq/EBITDA",
            "divida_bruta_ebitda": "Dív.Bruta/EBITDA",
            "divida_liq_fco": "Dív.Líq/FCO",
            "interest_coverage_ebitda": "EBITDA/Desp.Fin (LTM)",
            "interest_coverage_ebitda_5y": "EBITDA/Desp.Fin (5A)",
            "divida_total_pl": "Dív.Total/PL",
            "leverage_ratio": "Equity-to-Assets",
            "revenue_stability": "Estab. Receita (Moody's)",
            "payout": "Payout (LTM)",
            "sustainable_growth": "Cresc. Sustentável",
            "fco_lucro_ratio": "FCO/Lucro (LTM)",
            "fair_pbv": "Fair P/BV Teórico",
            "total_shareholder_return_pl": "Retorno ao Acionista/PL",
        }
    cols = [c for c in colunas if c in df.columns]
    tabela = df[cols].copy()
    tabela.columns = [colunas[c] for c in cols]
    return tabela
