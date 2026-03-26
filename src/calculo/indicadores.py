"""
Cálculo de indicadores financeiros a partir dos dados da CVM.

Recebe o contas_chave.json e produz um DataFrame consolidado com todos os
indicadores do briefing: DRE, Fluxo de Caixa, Estrutura de Capital,
Balanço, Capital de Giro e Múltiplos de Alavancagem/Liquidez.
"""

import json
import pandas as pd
import numpy as np
from pathlib import Path


def carregar_contas(caminho_json: str) -> list[dict]:
    with open(caminho_json, "r", encoding="utf-8") as f:
        return json.load(f)


def _montar_df_contas(contas: list[dict], prefixo_tipo: str) -> pd.DataFrame:
    """Monta DataFrame com uma linha por período para um tipo de demonstração."""
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


def _desacumular_dre_dfc(df: pd.DataFrame, colunas_fluxo: list[str]) -> pd.DataFrame:
    """
    ITR da CVM vem acumulado (YTD). Calcula o valor do trimestre isolado.
    Q1 = valor Q1, Q2 = valor Q2 - valor Q1, Q3 = valor Q3 - valor Q2.
    Q4 (DFP) já é o acumulado anual, então Q4 = DFP - ITR_Q3.
    """
    df = df.copy()
    df["ano"] = df.index.year
    df["trimestre"] = (df.index.month - 1) // 3 + 1

    for col in colunas_fluxo:
        if col not in df.columns:
            continue
        col_tri = f"{col}_tri"
        df[col_tri] = np.nan

        for ano in df["ano"].unique():
            mask_ano = df["ano"] == ano
            dados_ano = df.loc[mask_ano].sort_index()

            for i, (idx, row) in enumerate(dados_ano.iterrows()):
                tri = row["trimestre"]
                if tri == 1 or i == 0:
                    df.loc[idx, col_tri] = row[col]
                else:
                    prev_idx = dados_ano.index[i - 1]
                    df.loc[idx, col_tri] = row[col] - df.loc[prev_idx, col]

    return df


def _safe_get(df: pd.DataFrame, col: str, default=np.nan):
    """Retorna coluna do DataFrame ou Series com valor default."""
    if col in df.columns:
        return df[col]
    return pd.Series(default, index=df.index)


def calcular_indicadores(caminho_json: str) -> pd.DataFrame:
    """
    Calcula todos os indicadores do briefing.

    Returns:
        DataFrame com uma linha por trimestre e colunas para cada indicador.
    """
    contas = carregar_contas(caminho_json)

    # Montar DataFrames por tipo (ITR + DFP)
    df_dre_itr = _montar_df_contas(contas, "ITR_dre")
    df_dre_dfp = _montar_df_contas(contas, "DFP_dre")
    df_bpa_itr = _montar_df_contas(contas, "ITR_bpa")
    df_bpa_dfp = _montar_df_contas(contas, "DFP_bpa")
    df_bpp_itr = _montar_df_contas(contas, "ITR_bpp")
    df_bpp_dfp = _montar_df_contas(contas, "DFP_bpp")
    df_dfc_itr = _montar_df_contas(contas, "ITR_dfc")
    df_dfc_dfp = _montar_df_contas(contas, "DFP_dfc")

    # Combinar (DFP sobrescreve ITR para mesmo período)
    df_dre = pd.concat([df_dre_itr, df_dre_dfp]).sort_index()
    df_dre = df_dre[~df_dre.index.duplicated(keep="last")]
    df_bpa = pd.concat([df_bpa_itr, df_bpa_dfp]).sort_index()
    df_bpa = df_bpa[~df_bpa.index.duplicated(keep="last")]
    df_bpp = pd.concat([df_bpp_itr, df_bpp_dfp]).sort_index()
    df_bpp = df_bpp[~df_bpp.index.duplicated(keep="last")]
    df_dfc = pd.concat([df_dfc_itr, df_dfc_dfp]).sort_index()
    df_dfc = df_dfc[~df_dfc.index.duplicated(keep="last")]

    # Desacumular DRE e DFC (valores YTD -> trimestre isolado)
    colunas_fluxo_dre = [
        "receita_liquida", "custo", "resultado_bruto", "despesas_operacionais",
        "despesas_vendas", "despesas_ga", "resultado_equivalencia",
        "ebit", "resultado_financeiro", "receitas_financeiras",
        "despesas_financeiras", "lucro_antes_ir", "ir_csll", "lucro_liquido",
    ]
    colunas_fluxo_dfc = [
        "fco", "caixa_gerado_operacoes", "depreciacao_amortizacao",
        "juros_emprestimos_dfc", "var_ativos_passivos", "juros_pagos",
        "fci", "capex", "fcf",
        "amortizacao_divida", "dividendos_pagos", "captacao_divida",
    ]

    df_dre = _desacumular_dre_dfc(df_dre, colunas_fluxo_dre)
    df_dfc = _desacumular_dre_dfc(df_dfc, colunas_fluxo_dfc)

    # Montar DataFrame consolidado
    resultado = pd.DataFrame(index=df_dre.index)
    resultado["ano"] = resultado.index.year
    resultado["trimestre"] = (resultado.index.month - 1) // 3 + 1
    resultado["label"] = resultado.apply(
        lambda r: f"{int(r['trimestre'])}T{int(r['ano']) % 100:02d}", axis=1
    )

    # =====================================================================
    # 1. DEMONSTRAÇÃO DE RESULTADOS (DRE)
    # =====================================================================
    def _tri(col):
        """Pega coluna trimestral desacumulada, fallback para original."""
        return df_dre.get(f"{col}_tri", df_dre.get(col))

    resultado["receita_liquida"] = _tri("receita_liquida")
    resultado["custo"] = _tri("custo")
    resultado["resultado_bruto"] = _tri("resultado_bruto")
    resultado["despesas_operacionais"] = _tri("despesas_operacionais")
    resultado["despesas_vendas"] = _tri("despesas_vendas")
    resultado["despesas_ga"] = _tri("despesas_ga")
    resultado["resultado_equivalencia"] = _tri("resultado_equivalencia")
    resultado["ebit"] = _tri("ebit")
    resultado["resultado_financeiro"] = _tri("resultado_financeiro")
    resultado["receitas_financeiras"] = _tri("receitas_financeiras")
    resultado["despesas_financeiras"] = _tri("despesas_financeiras")
    resultado["lucro_antes_ir"] = _tri("lucro_antes_ir")
    resultado["ir_csll"] = _tri("ir_csll")
    resultado["lucro_liquido"] = _tri("lucro_liquido")

    # D&A vem da DFC (ajuste no lucro líquido)
    def _tri_dfc(col):
        return df_dfc.get(f"{col}_tri", df_dfc.get(col))

    resultado["depreciacao_amortizacao"] = _tri_dfc("depreciacao_amortizacao")

    # EBITDA = EBIT + D&A
    da = _safe_get(resultado, "depreciacao_amortizacao", 0).fillna(0)
    resultado["ebitda"] = resultado["ebit"] + da

    # Margens
    receita = resultado["receita_liquida"].replace(0, np.nan)
    resultado["margem_bruta"] = resultado["resultado_bruto"] / receita
    resultado["margem_ebitda"] = resultado["ebitda"] / receita
    resultado["margem_ebit"] = resultado["ebit"] / receita
    resultado["margem_liquida"] = resultado["lucro_liquido"] / receita

    # Growth YoY (comparar com mesmo trimestre do ano anterior)
    resultado["receita_yoy"] = resultado["receita_liquida"].pct_change(4)
    resultado["ebitda_yoy"] = resultado["ebitda"].pct_change(4)
    resultado["lucro_yoy"] = resultado["lucro_liquido"].pct_change(4)

    # =====================================================================
    # 2. FLUXO DE CAIXA
    # =====================================================================
    resultado["fco"] = _tri_dfc("fco")
    resultado["fci"] = _tri_dfc("fci")
    resultado["fcf_financiamento"] = _tri_dfc("fcf")

    # Capex real (aquisição de imobilizado e intangível) — valor negativo
    resultado["capex"] = _tri_dfc("capex")

    # FCL = FCO + Capex (Capex é negativo)
    capex = _safe_get(resultado, "capex", 0).fillna(0)
    resultado["fcl"] = resultado["fco"] + capex

    # Juros pagos (valor negativo na DFC)
    resultado["juros_pagos"] = _tri_dfc("juros_pagos")

    # Amortização de dívida, dividendos, captação
    resultado["amortizacao_divida"] = _tri_dfc("amortizacao_divida")
    resultado["dividendos_pagos"] = _tri_dfc("dividendos_pagos")
    resultado["captacao_divida"] = _tri_dfc("captacao_divida")

    # Conversão de caixa
    ebitda_nz = resultado["ebitda"].replace(0, np.nan)
    resultado["conversao_caixa"] = resultado["fco"] / ebitda_nz

    # Capex / Receita
    resultado["capex_receita"] = resultado["capex"].abs() / receita

    # =====================================================================
    # 3. BALANÇO E ESTRUTURA DE CAPITAL (dados de estoque, não fluxo)
    # =====================================================================
    if not df_bpa.empty:
        resultado["ativo_total"] = _safe_get(df_bpa, "ativo_total")
        resultado["ativo_circulante"] = _safe_get(df_bpa, "ativo_circulante")
        resultado["caixa"] = _safe_get(df_bpa, "caixa")
        resultado["aplicacoes_financeiras_cp"] = _safe_get(df_bpa, "aplicacoes_financeiras_cp")
        resultado["contas_a_receber"] = _safe_get(df_bpa, "contas_a_receber")
        resultado["estoques"] = _safe_get(df_bpa, "estoques_cp")
        resultado["imobilizado"] = _safe_get(df_bpa, "imobilizado")
        resultado["investimentos"] = _safe_get(df_bpa, "investimentos")
        resultado["intangivel"] = _safe_get(df_bpa, "intangivel")
        resultado["ativo_nao_circulante"] = _safe_get(df_bpa, "ativo_nao_circulante")

    if not df_bpp.empty:
        resultado["passivo_circulante"] = _safe_get(df_bpp, "passivo_circulante")
        resultado["fornecedores"] = _safe_get(df_bpp, "fornecedores")
        resultado["obrigacoes_fiscais_cp"] = _safe_get(df_bpp, "obrigacoes_fiscais_cp")
        resultado["emprestimos_cp"] = _safe_get(df_bpp, "emprestimos_cp")
        resultado["outras_obrigacoes_cp"] = _safe_get(df_bpp, "outras_obrigacoes_cp")
        resultado["provisoes_cp"] = _safe_get(df_bpp, "provisoes_cp")
        resultado["passivo_nao_circulante"] = _safe_get(df_bpp, "passivo_nao_circulante")
        resultado["emprestimos_lp"] = _safe_get(df_bpp, "emprestimos_lp")
        resultado["outras_obrigacoes_lp"] = _safe_get(df_bpp, "outras_obrigacoes_lp")
        resultado["provisoes_lp"] = _safe_get(df_bpp, "provisoes_lp")
        resultado["patrimonio_liquido"] = _safe_get(df_bpp, "patrimonio_liquido")
        resultado["capital_social"] = _safe_get(df_bpp, "capital_social")

    # Dívida
    emp_cp = _safe_get(resultado, "emprestimos_cp", 0).fillna(0)
    emp_lp = _safe_get(resultado, "emprestimos_lp", 0).fillna(0)
    caixa_val = _safe_get(resultado, "caixa", 0).fillna(0)
    aplic_cp = _safe_get(resultado, "aplicacoes_financeiras_cp", 0).fillna(0)

    resultado["divida_bruta"] = emp_cp + emp_lp
    resultado["liquidez_total"] = caixa_val + aplic_cp
    resultado["divida_liquida"] = resultado["divida_bruta"] - resultado["liquidez_total"]

    # =====================================================================
    # 4. CAPITAL DE GIRO
    # =====================================================================
    ar = _safe_get(resultado, "contas_a_receber", 0).fillna(0)
    est = _safe_get(resultado, "estoques", 0).fillna(0)
    forn = _safe_get(resultado, "fornecedores", 0).fillna(0)

    resultado["capital_de_giro"] = ar + est - forn

    # Ciclo de conversão de caixa (em dias) — usa receita e custo LTM
    receita_ltm = resultado["receita_liquida"].rolling(4).sum()
    custo_ltm = resultado["custo"].abs().rolling(4).sum()
    receita_dia = receita_ltm.replace(0, np.nan) / 360
    custo_dia = custo_ltm.replace(0, np.nan) / 360

    resultado["dso"] = ar / receita_dia  # Dias de Recebimento
    resultado["dio"] = est / custo_dia   # Dias de Estoque
    resultado["dpo"] = forn / custo_dia  # Dias de Pagamento
    resultado["ciclo_caixa"] = (
        _safe_get(resultado, "dso", 0).fillna(0) +
        _safe_get(resultado, "dio", 0).fillna(0) -
        _safe_get(resultado, "dpo", 0).fillna(0)
    )

    # =====================================================================
    # 5. MÚLTIPLOS (usar EBITDA/FCO LTM - últimos 12 meses)
    # =====================================================================
    resultado["ebitda_ltm"] = resultado["ebitda"].rolling(4).sum()
    resultado["ebit_ltm"] = resultado["ebit"].rolling(4).sum()
    resultado["fco_ltm"] = resultado["fco"].rolling(4).sum()
    resultado["receita_ltm"] = receita_ltm
    resultado["lucro_ltm"] = resultado["lucro_liquido"].rolling(4).sum()
    resultado["fcl_ltm"] = resultado["fcl"].rolling(4).sum()
    resultado["da_ltm"] = resultado["depreciacao_amortizacao"].rolling(4).sum()

    ebitda_ltm = resultado["ebitda_ltm"].replace(0, np.nan)
    fco_ltm = resultado["fco_ltm"].replace(0, np.nan)

    resultado["divida_liq_ebitda"] = resultado["divida_liquida"] / ebitda_ltm
    resultado["divida_liq_fco"] = resultado["divida_liquida"] / fco_ltm
    resultado["divida_liq_receita"] = resultado["divida_liquida"] / receita_ltm.replace(0, np.nan)

    # Alavancagem e Liquidez
    at = _safe_get(resultado, "ativo_total").replace(0, np.nan)
    pl = _safe_get(resultado, "patrimonio_liquido").replace(0, np.nan)
    pc = _safe_get(resultado, "passivo_circulante").replace(0, np.nan)
    db = resultado["divida_bruta"].replace(0, np.nan)

    resultado["equity_multiplier"] = at / pl
    resultado["debt_to_assets"] = resultado["divida_bruta"] / at
    resultado["divida_cp_total"] = emp_cp / db
    resultado["liquidez_corrente"] = _safe_get(resultado, "ativo_circulante") / pc
    resultado["liquidez_seca"] = (_safe_get(resultado, "ativo_circulante", 0).fillna(0) - est) / pc
    resultado["cash_ratio"] = resultado["liquidez_total"] / pc

    # Interest Coverage — EBITDA LTM / |Despesas Financeiras LTM|
    desp_fin_ltm = resultado["despesas_financeiras"].abs().rolling(4).sum().replace(0, np.nan)
    resultado["interest_coverage_ebitda"] = ebitda_ltm / desp_fin_ltm
    resultado["interest_coverage_ebit"] = resultado["ebit_ltm"] / desp_fin_ltm

    resultado["divida_total_pl"] = resultado["divida_bruta"] / pl

    # DSCR (Debt Service Coverage Ratio) = FCO LTM / |Amortização + Juros| LTM
    amort_ltm = _safe_get(resultado, "amortizacao_divida", 0).fillna(0).abs().rolling(4).sum()
    juros_ltm = _safe_get(resultado, "juros_pagos", 0).fillna(0).abs().rolling(4).sum()
    servico_divida = (amort_ltm + juros_ltm).replace(0, np.nan)
    resultado["dscr"] = fco_ltm / servico_divida

    # Capex / EBITDA
    capex_ltm = _safe_get(resultado, "capex", 0).fillna(0).abs().rolling(4).sum()
    resultado["capex_ebitda"] = capex_ltm / ebitda_ltm

    # Payout (dividendos / lucro líquido)
    div_pagos_ltm = _safe_get(resultado, "dividendos_pagos", 0).fillna(0).abs().rolling(4).sum()
    resultado["payout"] = div_pagos_ltm / resultado["lucro_ltm"].abs().replace(0, np.nan)

    # Custo da Dívida = |Despesas Financeiras| LTM / Dívida Bruta média
    resultado["custo_divida"] = desp_fin_ltm / db

    # Solvência = Ativo Total / (Passivo Circulante + Passivo Não Circulante)
    pnc = _safe_get(resultado, "passivo_nao_circulante", 0).fillna(0)
    passivo_total = _safe_get(resultado, "passivo_circulante", 0).fillna(0) + pnc
    resultado["solvencia"] = at / passivo_total.replace(0, np.nan)

    # Fluxos como % da Receita
    resultado["fco_receita"] = resultado["fco"] / receita
    resultado["fcl_receita"] = resultado["fcl"] / receita

    # =====================================================================
    # 7. MODELO FLEURIET (Análise Dinâmica de Capital de Giro)
    # =====================================================================
    # CDG (Capital de Giro) = (PL + Passivo Não Circulante) - Ativo Não Circulante
    pl_val = _safe_get(resultado, "patrimonio_liquido", 0).fillna(0)
    pnc_val = _safe_get(resultado, "passivo_nao_circulante", 0).fillna(0)
    anc_val = _safe_get(resultado, "ativo_nao_circulante", 0).fillna(0)
    resultado["fleuriet_cdg"] = pl_val + pnc_val - anc_val

    # NCG (Necessidade de Capital de Giro) = Ativo Cíclico - Passivo Cíclico
    # Ativo Cíclico: contas a receber + estoques
    # Passivo Cíclico: fornecedores + obrigações fiscais CP
    ativo_ciclico = ar + est
    obrig_fiscais = _safe_get(resultado, "obrigacoes_fiscais_cp", 0).fillna(0)
    passivo_ciclico = forn + obrig_fiscais
    resultado["fleuriet_ncg"] = ativo_ciclico - passivo_ciclico

    # T (Saldo de Tesouraria) = CDG - NCG
    # Equivale a: Ativo Errático - Passivo Errático
    resultado["fleuriet_t"] = resultado["fleuriet_cdg"] - resultado["fleuriet_ncg"]

    # Classificação Fleuriet aprimorada (nota 1 a 10)
    # Combina classificação por sinais (6 tipos) com análise de magnitude:
    # - CDG/NCG: cobertura do capital de giro permanente sobre a necessidade
    # - T/Receita: tesouraria relativa ao porte da empresa
    #
    # Escala:
    # 10: CDG+, NCG-, T+ forte (excelente — recebe antes de pagar, folga ampla)
    #  9: CDG+, NCG-, T+ moderado (excelente — mesma estrutura, menor folga)
    #  8: CDG+, NCG+, T+ com CDG/NCG > 1.5 (sólida — ampla cobertura)
    #  7: CDG+, NCG+, T+ com CDG/NCG 1.2-1.5 (sólida — boa cobertura)
    #  6: CDG+, NCG+, T+ com CDG/NCG 1.0-1.2 (sólida — cobertura justa)
    #  5: CDG+, NCG+, T- com T/|NCG| > -0.2 (insatisfatória leve)
    #  4: CDG+, NCG+, T- com T/|NCG| <= -0.2 (insatisfatória severa)
    #     OU CDG-, NCG-, T+ (alto risco — instável)
    #  3: CDG-, NCG-, T- (muito ruim)
    #  2: CDG-, NCG+, T- com T/|NCG| > -0.5 (péssima moderada)
    #  1: CDG-, NCG+, T- com T/|NCG| <= -0.5 (péssima — risco de insolvência)
    def _classificar_fleuriet(row):
        cdg = row.get("fleuriet_cdg", np.nan)
        ncg = row.get("fleuriet_ncg", np.nan)
        t = row.get("fleuriet_t", np.nan)
        rec = row.get("receita_liquida", np.nan)
        if pd.isna(cdg) or pd.isna(ncg) or pd.isna(t):
            return np.nan, ""

        cdg_pos = cdg >= 0
        ncg_pos = ncg >= 0
        t_pos = t >= 0

        # Razões de magnitude
        ncg_abs = abs(ncg) if ncg != 0 else 1
        cdg_ncg = cdg / ncg if ncg > 0 else (2.0 if cdg_pos else -1.0)
        t_ncg = t / ncg_abs

        # Tipo I: CDG+, NCG-, T+ → Excelente (9-10)
        if cdg_pos and not ncg_pos and t_pos:
            if t_ncg > 1.5:
                return 10, "Excelente"
            return 9, "Excelente"

        # Tipo II: CDG+, NCG+, T+ → Sólida (6-8)
        if cdg_pos and ncg_pos and t_pos:
            if cdg_ncg > 1.5:
                return 8, "Sólida"
            elif cdg_ncg > 1.2:
                return 7, "Sólida"
            return 6, "Sólida"

        # Tipo III: CDG+, NCG+, T- → Insatisfatória (4-5)
        if cdg_pos and ncg_pos and not t_pos:
            if t_ncg > -0.2:
                return 5, "Insatisfatória"
            return 4, "Insatisfatória"

        # Tipo IV: CDG-, NCG-, T+ → Alto Risco (4)
        if not cdg_pos and not ncg_pos and t_pos:
            return 4, "Alto Risco"

        # Tipo V: CDG-, NCG-, T- → Muito Ruim (3)
        if not cdg_pos and not ncg_pos and not t_pos:
            return 3, "Muito Ruim"

        # Tipo VI: CDG-, NCG+, T- → Péssima (1-2)
        if not cdg_pos and ncg_pos and not t_pos:
            if t_ncg > -0.5:
                return 2, "Péssima"
            return 1, "Péssima"

        return np.nan, ""

    notas_tipos = resultado.apply(_classificar_fleuriet, axis=1)
    resultado["fleuriet_nota"] = notas_tipos.apply(lambda x: x[0])
    resultado["fleuriet_tipo"] = notas_tipos.apply(lambda x: x[1])

    # Indicadores complementares Fleuriet
    ncg_nz = resultado["fleuriet_ncg"].replace(0, np.nan)
    resultado["fleuriet_cdg_ncg"] = resultado["fleuriet_cdg"] / ncg_nz  # Cobertura CDG/NCG
    resultado["fleuriet_t_receita"] = resultado["fleuriet_t"] / receita  # T como % da receita

    return resultado


# =========================================================================
# TABELAS FORMATADAS PARA O DASHBOARD
# =========================================================================

def formatar_tabela_dre(df: pd.DataFrame) -> pd.DataFrame:
    """Formata a tabela de DRE para exibição no dashboard."""
    colunas = {
        "label": "Período",
        "receita_liquida": "Receita Líquida",
        "receita_yoy": "Growth YoY",
        "custo": "CPV",
        "resultado_bruto": "Resultado Bruto",
        "margem_bruta": "Margem Bruta",
        "despesas_vendas": "Despesas com Vendas",
        "despesas_ga": "Despesas G&A",
        "ebit": "EBIT",
        "margem_ebit": "Margem EBIT",
        "depreciacao_amortizacao": "D&A",
        "ebitda": "EBITDA",
        "margem_ebitda": "Margem EBITDA",
        "ebitda_yoy": "EBITDA YoY",
        "resultado_financeiro": "Resultado Financeiro",
        "receitas_financeiras": "Receitas Financeiras",
        "despesas_financeiras": "Despesas Financeiras",
        "lucro_antes_ir": "Lucro Antes IR",
        "ir_csll": "IR/CSLL",
        "lucro_liquido": "Lucro Líquido",
        "margem_liquida": "Margem Líquida",
    }
    cols_disponiveis = [c for c in colunas.keys() if c in df.columns]
    tabela = df[cols_disponiveis].copy()
    tabela.columns = [colunas[c] for c in cols_disponiveis]
    return tabela


def formatar_tabela_fluxo_caixa(df: pd.DataFrame) -> pd.DataFrame:
    colunas = {
        "label": "Período",
        "fco": "FCO",
        "conversao_caixa": "FCO/EBITDA",
        "fco_receita": "FCO/Receita",
        "capex": "Capex",
        "capex_receita": "Capex/Receita",
        "fcl": "FCL",
        "fcl_receita": "FCL/Receita",
        "juros_pagos": "Juros Pagos",
        "amortizacao_divida": "Amortiz. Dívida",
        "captacao_divida": "Captação",
        "dividendos_pagos": "Dividendos Pagos",
        "fcf_financiamento": "FC Financiamento",
    }
    cols_disponiveis = [c for c in colunas.keys() if c in df.columns]
    tabela = df[cols_disponiveis].copy()
    tabela.columns = [colunas[c] for c in cols_disponiveis]
    return tabela


def formatar_tabela_estrutura_capital(df: pd.DataFrame) -> pd.DataFrame:
    colunas = {
        "label": "Período",
        "caixa": "Caixa",
        "aplicacoes_financeiras_cp": "Aplicações Fin. CP",
        "liquidez_total": "Liquidez Total",
        "emprestimos_cp": "Dívida CP",
        "emprestimos_lp": "Dívida LP",
        "divida_bruta": "Dívida Bruta",
        "divida_liquida": "Dívida Líquida",
        "patrimonio_liquido": "Patrimônio Líquido",
        "divida_liq_ebitda": "Dív.Líq/EBITDA",
        "divida_liq_fco": "Dív.Líq/FCO",
    }
    cols_disponiveis = [c for c in colunas.keys() if c in df.columns]
    tabela = df[cols_disponiveis].copy()
    tabela.columns = [colunas[c] for c in cols_disponiveis]
    return tabela


def formatar_tabela_capital_giro(df: pd.DataFrame) -> pd.DataFrame:
    colunas = {
        "label": "Período",
        "contas_a_receber": "Contas a Receber",
        "estoques": "Estoques",
        "fornecedores": "Fornecedores",
        "capital_de_giro": "Capital de Giro",
        "dso": "DSO (dias)",
        "dio": "DIO (dias)",
        "dpo": "DPO (dias)",
        "ciclo_caixa": "Ciclo de Caixa (dias)",
    }
    cols_disponiveis = [c for c in colunas.keys() if c in df.columns]
    tabela = df[cols_disponiveis].copy()
    tabela.columns = [colunas[c] for c in cols_disponiveis]
    return tabela


def formatar_tabela_multiplos(df: pd.DataFrame) -> pd.DataFrame:
    colunas = {
        "label": "Período",
        "divida_liq_ebitda": "Dív.Líq/EBITDA",
        "divida_liq_fco": "Dív.Líq/FCO",
        "interest_coverage_ebitda": "EBITDA/Desp.Fin (LTM)",
        "interest_coverage_ebit": "EBIT/Desp.Fin (LTM)",
        "dscr": "DSCR",
        "equity_multiplier": "Equity Multiplier",
        "debt_to_assets": "Debt-to-Assets",
        "divida_cp_total": "Dív.CP / Dív.Total",
        "liquidez_corrente": "Liquidez Corrente",
        "liquidez_seca": "Liquidez Seca",
        "cash_ratio": "Cash Ratio",
        "solvencia": "Solvência Geral",
        "divida_total_pl": "Dív.Total / PL",
        "custo_divida": "Custo da Dívida",
        "capex_ebitda": "Capex/EBITDA (LTM)",
        "payout": "Payout (LTM)",
    }
    cols_disponiveis = [c for c in colunas.keys() if c in df.columns]
    tabela = df[cols_disponiveis].copy()
    tabela.columns = [colunas[c] for c in cols_disponiveis]
    return tabela


def formatar_tabela_fleuriet(df: pd.DataFrame) -> pd.DataFrame:
    colunas = {
        "label": "Período",
        "fleuriet_cdg": "CDG (Capital de Giro)",
        "fleuriet_ncg": "NCG (Nec. Capital de Giro)",
        "fleuriet_t": "Saldo de Tesouraria (T)",
        "fleuriet_cdg_ncg": "CDG / NCG",
        "fleuriet_t_receita": "T / Receita",
        "fleuriet_nota": "Nota Fleuriet",
        "fleuriet_tipo": "Classificação",
    }
    cols_disponiveis = [c for c in colunas.keys() if c in df.columns]
    tabela = df[cols_disponiveis].copy()
    tabela.columns = [colunas[c] for c in cols_disponiveis]
    return tabela


if __name__ == "__main__":
    import sys
    caminho = sys.argv[1] if len(sys.argv) > 1 else "G:/Meu Drive/Análise de Crédito/CSN Mineração/Dados_CVM/contas_chave.json"
    df = calcular_indicadores(caminho)
    print(df[["label", "receita_liquida", "ebitda", "depreciacao_amortizacao", "lucro_liquido", "divida_liquida", "divida_liq_ebitda"]].to_string())
