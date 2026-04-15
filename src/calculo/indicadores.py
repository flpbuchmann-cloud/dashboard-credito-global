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


def _detectar_fiscal_year(df_dre, df_dfp) -> int:
    """Detecta o mês de encerramento do fiscal year (ex: 12=dez, 9=set, 6=jun).
    Retorna o mês do DFP/10-K mais recente."""
    if df_dfp is not None and not df_dfp.empty:
        ultimo_dfp = df_dfp.index.max()
        return ultimo_dfp.month
    return 12  # default: ano calendário


def _desacumular_dre_dfc(
    df: pd.DataFrame, colunas_fluxo: list[str], alertas: list[dict] | None = None,
    fy_end_month: int = 12
) -> pd.DataFrame:
    """
    ITR da CVM/SEC vem acumulado (YTD). Calcula o valor do trimestre isolado.
    Suporta fiscal years não-calendário (ex: Visa FY out-set, fy_end_month=9).
    """
    df = df.copy()
    df["trimestre"] = (df.index.month - 1) // 3 + 1

    # Atribuir "ano fiscal" baseado no mês de encerramento
    if fy_end_month == 12:
        df["ano_fiscal"] = df.index.year
    else:
        # Ex: FY end=9 (set), then Oct 2024 belongs to FY2025
        df["ano_fiscal"] = df.index.year
        mask_next = df.index.month > fy_end_month
        df.loc[mask_next, "ano_fiscal"] = df.loc[mask_next].index.year + 1
    df["ano"] = df["ano_fiscal"]

    # Determinar qual trimestre é o "Q1 fiscal" (primeiro do fiscal year)
    fy_q1_month = (fy_end_month % 12) + 1  # ex: FY end=9 → Q1 starts in Oct (month 10)
    fy_q1_trimestre = (fy_q1_month - 1) // 3 + 1  # ex: month 10 → trimestre 4

    anomalias_detectadas = set()

    for col in colunas_fluxo:
        if col not in df.columns:
            continue
        col_tri = f"{col}_tri"
        df[col_tri] = np.nan

        for ano_f in df["ano_fiscal"].unique():
            mask_ano = df["ano_fiscal"] == ano_f
            dados_ano = df.loc[mask_ano].sort_index()

            valores_tri = []
            for i, (idx, row) in enumerate(dados_ano.iterrows()):
                tri = row["trimestre"]
                if tri == fy_q1_trimestre or i == 0:
                    val = row[col]
                else:
                    prev_idx = dados_ano.index[i - 1]
                    val = row[col] - df.loc[prev_idx, col]

                df.loc[idx, col_tri] = val
                valores_tri.append((idx, tri, val))

            # Validação: detectar anomalia de discontinued operations no Q4
            # Se Q4 desacumulado é < 30% da média dos outros trimestres (para receita/fco),
            # ou se o sinal mudou inesperadamente, a base provavelmente é inconsistente
            if len(valores_tri) >= 3 and col in ("receita_liquida", "fco"):
                q4_entries = [(idx, tri, v) for idx, tri, v in valores_tri if tri == 4]
                outros = [v for _, tri, v in valores_tri if tri != 4 and v != 0 and not np.isnan(v)]

                if q4_entries and outros:
                    q4_val = q4_entries[-1][2]
                    media_outros = np.mean(np.abs(outros))

                    if media_outros > 0 and not np.isnan(q4_val):
                        ratio = abs(q4_val) / media_outros
                        # Q4 menor que 30% da média ou com sinal trocado
                        if ratio < 0.30 or (q4_val < 0 and all(v > 0 for v in outros)):
                            anomalias_detectadas.add((col, ano_f, q4_val, media_outros))

    # Gerar alertas para anomalias detectadas
    if alertas is not None and anomalias_detectadas:
        for col, ano_f, q4_val, media in sorted(anomalias_detectadas):
            nome_col = col.replace("_", " ").title()
            alertas.append({
                "tipo": "inconsistente",
                "indicador": f"{nome_col} (Q4/{ano_f})",
                "mensagem": (
                    f"Q4/{ano_f} desacumulado ({q4_val/1e9:.2f}B) é inconsistente com "
                    f"a média dos outros trimestres ({media/1e9:.2f}B). "
                    f"Provável reclassificação de discontinued operations entre 10-Q e 10-K. "
                    f"Recomendado conferir com o Earnings Release."
                ),
            })

    return df


def _safe_get(df: pd.DataFrame, col: str, default=np.nan):
    """Retorna coluna do DataFrame ou Series com valor default."""
    if col in df.columns:
        return df[col]
    return pd.Series(default, index=df.index)


def calcular_indicadores(caminho_json: str) -> tuple[pd.DataFrame, list[dict]]:
    """
    Calcula todos os indicadores do briefing.

    Returns:
        (DataFrame com uma linha por trimestre, lista de alertas de qualidade de dados)
        Cada alerta: {"tipo": "proxy"|"ausente"|"inconsistente",
                      "indicador": str, "mensagem": str}
    """
    alertas = []
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

    # Se não há DFP (só ITR), os dados já são trimestrais — pular desacumulação
    # Isto acontece para empresas non-US cujo parser já entrega dados por trimestre
    _has_dfp = df_dre_dfp is not None and not df_dre_dfp.empty
    fy_month = _detectar_fiscal_year(df_dre, df_dre_dfp)
    if _has_dfp:
        df_dre = _desacumular_dre_dfc(df_dre, colunas_fluxo_dre, alertas, fy_end_month=fy_month)
        df_dfc = _desacumular_dre_dfc(df_dfc, colunas_fluxo_dfc, alertas, fy_end_month=fy_month)
    else:
        # Dados já trimestrais — criar colunas _tri como cópia direta
        for col in colunas_fluxo_dre:
            if col in df_dre.columns:
                df_dre[f"{col}_tri"] = df_dre[col]
        for col in colunas_fluxo_dfc:
            if col in df_dfc.columns:
                df_dfc[f"{col}_tri"] = df_dfc[col]

    # Montar DataFrame consolidado
    resultado = pd.DataFrame(index=df_dre.index)
    # Normalizar mês: dias próximos ao início/fim do mês pertencem ao trimestre correto
    # Ex: Pfizer 2023-10-01 é Q3 2023, não Q4. Se dia <= 15 e mês é início de tri (1,4,7,10), pertence ao anterior
    def _quarter_from_date(idx):
        m, d, y = idx.month, idx.day, idx.year
        if d <= 15 and m in (1, 4, 7, 10):
            if m == 1:
                return 4, y - 1
            return (m - 1) // 3, y  # m=4->1, 7->2, 10->3
        return (m - 1) // 3 + 1, y
    quarters = [_quarter_from_date(x) for x in resultado.index]
    resultado["trimestre"] = [q[0] for q in quarters]
    resultado["ano"] = [q[1] for q in quarters]
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

    # Validação: Custo e Resultado Bruto podem estar incorretos em empresas E&P
    # que não reportam CostOfRevenue no XBRL (ex: Oil & Gas Full Cost Method).
    # Detectar: se margem bruta > 100% ou custo > 0, o custo está errado.
    # Correção: derivar custo = Receita - EBIT - D&A - Desp.Operacionais (proxy)
    # ou resultado_bruto = Receita + Custo (custo é negativo)
    rec = resultado["receita_liquida"]
    margem_bruta_raw = resultado["resultado_bruto"] / rec.replace(0, np.nan)
    custo_invalido = (margem_bruta_raw.abs() > 1) | (resultado["custo"] > 0)

    if custo_invalido.any():
        n_invalidos = custo_invalido.sum()
        periodos_afetados = resultado.loc[custo_invalido, "label"].tolist()
        alertas.append({
            "tipo": "proxy",
            "indicador": "CPV / Resultado Bruto",
            "mensagem": (
                f"CostOfRevenue não encontrado no XBRL para {n_invalidos} período(s) "
                f"({', '.join(periodos_afetados[-3:])}). "
                f"CPV calculado como proxy: -(Receita - EBIT - SG&A)."
            ),
        })
        ebit_val = resultado["ebit"].fillna(0)
        sgna = (_safe_get(resultado, "despesas_vendas", 0).fillna(0).abs() +
                _safe_get(resultado, "despesas_ga", 0).fillna(0).abs())

        custo_derivado = -(rec - ebit_val - sgna)
        resultado.loc[custo_invalido, "custo"] = custo_derivado[custo_invalido]
        resultado.loc[custo_invalido, "resultado_bruto"] = (
            rec[custo_invalido] + resultado.loc[custo_invalido, "custo"]
        )

    # D&A vem da DFC (ajuste no lucro líquido)
    def _tri_dfc(col):
        return df_dfc.get(f"{col}_tri", df_dfc.get(col))

    resultado["depreciacao_amortizacao"] = _tri_dfc("depreciacao_amortizacao")

    if resultado["depreciacao_amortizacao"].isna().all():
        alertas.append({
            "tipo": "ausente",
            "indicador": "D&A (Depreciação e Amortização)",
            "mensagem": "DepreciationDepletionAndAmortization não encontrado na DFC. EBITDA será igual a EBIT.",
        })

    # EBITDA — duplo cálculo com reconciliação:
    # Top-down (padrão): EBIT + D&A
    # Bottom-up (matriz): LL + Desp.Fin + IR + D&A
    # Usa top-down como primário; se EBIT não disponível, usa bottom-up
    da = _safe_get(resultado, "depreciacao_amortizacao", 0).fillna(0)
    ebitda_topdown = resultado["ebit"] + da

    ll = _safe_get(resultado, "lucro_liquido", 0).fillna(0)
    desp_fin = _safe_get(resultado, "despesas_financeiras", 0).fillna(0).abs()
    ir = _safe_get(resultado, "ir_csll", 0).fillna(0).abs()
    ebitda_bottomup = ll + desp_fin + ir + da

    # Usar top-down quando disponível, fallback para bottom-up
    ebit_ausente = resultado["ebit"].isna()
    resultado["ebitda"] = ebitda_topdown.where(~ebit_ausente, ebitda_bottomup)

    if ebit_ausente.any():
        alertas.append({
            "tipo": "proxy",
            "indicador": "EBITDA",
            "mensagem": (
                f"OperatingIncomeLoss (EBIT) não disponível em {ebit_ausente.sum()} período(s). "
                f"EBITDA calculado bottom-up: LL + Desp.Financeiras + IR + D&A."
            ),
        })

    # Margens
    receita = resultado["receita_liquida"].replace(0, np.nan)
    resultado["margem_bruta"] = resultado["resultado_bruto"] / receita
    resultado["margem_ebitda"] = resultado["ebitda"] / receita
    resultado["margem_ebit"] = resultado["ebit"] / receita
    resultado["margem_liquida"] = resultado["lucro_liquido"] / receita

    # Growth QoQ (comparar com trimestre imediatamente anterior)
    resultado["receita_qoq"] = resultado["receita_liquida"].pct_change(1)
    resultado["ebitda_qoq"] = resultado["ebitda"].pct_change(1)
    resultado["lucro_qoq"] = resultado["lucro_liquido"].pct_change(1)

    # Growth YoY (comparar com mesmo trimestre do ano anterior)
    resultado["receita_yoy"] = resultado["receita_liquida"].pct_change(4)
    resultado["ebitda_yoy"] = resultado["ebitda"].pct_change(4)
    resultado["lucro_yoy"] = resultado["lucro_liquido"].pct_change(4)

    # =====================================================================
    # 2. FLUXO DE CAIXA
    # =====================================================================
    resultado["fco"] = _tri_dfc("fco")
    if resultado["fco"].isna().all():
        alertas.append({
            "tipo": "ausente",
            "indicador": "FCO (Fluxo de Caixa Operacional)",
            "mensagem": "NetCashProvidedByOperatingActivities não encontrado. Indicadores de fluxo de caixa indisponíveis.",
        })
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
    if df_bpa.empty:
        alertas.append({
            "tipo": "ausente",
            "indicador": "Balanço Patrimonial (Ativos)",
            "mensagem": "Nenhum dado de ativo encontrado (BPA). Indicadores de estrutura de capital, liquidez e Fleuriet indisponíveis.",
        })
    if df_bpp.empty:
        alertas.append({
            "tipo": "ausente",
            "indicador": "Balanço Patrimonial (Passivos)",
            "mensagem": "Nenhum dado de passivo/PL encontrado (BPP). Indicadores de alavancagem e Fleuriet indisponíveis.",
        })

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
        # Dívida CP = LongTermDebtCurrent + ShortTermBorrowings (conforme matriz)
        ltd_current = _safe_get(df_bpp, "emprestimos_cp", 0).fillna(0)
        stb = _safe_get(df_bpp, "short_term_borrowings", 0).fillna(0)
        resultado["emprestimos_cp"] = ltd_current + stb
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

    # Interest Coverage
    # Denominador: despesas_financeiras (InterestExpense) da DRE como primário (conforme matriz),
    # com fallback para juros_pagos (DFC) quando mais conservador
    juros_pagos_ltm = _safe_get(resultado, "juros_pagos", 0).fillna(0).abs().rolling(4).sum().replace(0, np.nan)
    desp_fin_ltm = resultado["despesas_financeiras"].abs().rolling(4).sum().replace(0, np.nan)
    # Usar o maior entre juros_pagos e despesas_financeiras (o mais conservador)
    denominador_juros = pd.DataFrame({
        "juros": juros_pagos_ltm, "desp_fin": desp_fin_ltm
    }).max(axis=1).replace(0, np.nan)

    # EBITDA / Interest (padrão crédito)
    resultado["interest_coverage_ebitda"] = ebitda_ltm / denominador_juros
    # EBIT / Interest (Damodaran / agências de rating)
    resultado["interest_coverage_ebit"] = resultado["ebit_ltm"] / denominador_juros
    # Bottom-up conforme matriz: (LL + IR + Interest) / Interest = EBIT / Interest
    # Já coberto pelo interest_coverage_ebit acima, pois EBIT = LL + IR + Interest

    resultado["divida_total_pl"] = resultado["divida_bruta"] / pl

    # DSCR (Debt Service Coverage Ratio) = FCO LTM / |Amortização + Juros| LTM
    amort_ltm = _safe_get(resultado, "amortizacao_divida", 0).fillna(0).abs().rolling(4).sum()
    juros_ltm = _safe_get(resultado, "juros_pagos", 0).fillna(0).abs().rolling(4).sum()
    servico_divida = (amort_ltm + juros_ltm).replace(0, np.nan)
    resultado["dscr"] = fco_ltm / servico_divida

    # Capex / EBITDA
    capex_ltm = _safe_get(resultado, "capex", 0).fillna(0).abs().rolling(4).sum()
    resultado["capex_ebitda"] = capex_ltm / ebitda_ltm

    # Payout (dividendos / lucro líquido) — só quando LL > 0
    div_pagos_ltm = _safe_get(resultado, "dividendos_pagos", 0).fillna(0).abs().rolling(4).sum()
    lucro_ltm_positivo = resultado["lucro_ltm"].where(resultado["lucro_ltm"] > 0, np.nan)
    resultado["payout"] = div_pagos_ltm / lucro_ltm_positivo

    # Custo da Dívida = |Despesas Financeiras| LTM / Dívida Bruta média (atual + anterior)
    db_media = resultado["divida_bruta"].rolling(2).mean().replace(0, np.nan)
    resultado["custo_divida"] = desp_fin_ltm / db_media

    # Solvência = Ativo Total / (Passivo Circulante + Passivo Não Circulante)
    pnc = _safe_get(resultado, "passivo_nao_circulante", 0).fillna(0)
    passivo_total = _safe_get(resultado, "passivo_circulante", 0).fillna(0) + pnc
    resultado["solvencia"] = at / passivo_total.replace(0, np.nan)

    # Fluxos como % da Receita
    resultado["fco_receita"] = resultado["fco"] / receita
    resultado["fcl_receita"] = resultado["fcl"] / receita

    # =====================================================================
    # 6. ROIC, WACC e EVA (Assaf Neto / Damodaran)
    # =====================================================================
    # Taxa marginal de IR (21% US federal — McKinsey/Assaf Neto: usar taxa marginal,
    # não efetiva, para NOPAT ser neutro à estrutura de capital)
    TAXA_MARGINAL_IR = 0.21

    # NOPAT = EBIT LTM × (1 - Taxa Marginal IR)
    resultado["nopat_ltm"] = resultado["ebit_ltm"] * (1 - TAXA_MARGINAL_IR)

    # Capital Investido = Dívida Líquida + PL (McKinsey: excluir caixa excedente)
    pl_fill = _safe_get(resultado, "patrimonio_liquido", 0).fillna(0)
    capital_investido = (resultado["divida_liquida"] + pl_fill).rolling(2).mean().replace(0, np.nan)
    resultado["capital_investido"] = capital_investido

    # ROIC = NOPAT LTM / Capital Investido médio
    resultado["roic"] = resultado["nopat_ltm"] / capital_investido

    # WACC simplificado (book value):
    # Rd = custo_divida (já calculado)
    # Re = 10% (premissa padrão US large cap — Rf ~4.5% + ERP ~5.5%)
    # Pesos: D/(D+PL) e PL/(D+PL)
    RE_PREMISSA = 0.10
    d_peso = resultado["divida_bruta"] / (resultado["divida_bruta"] + pl_fill).replace(0, np.nan)
    e_peso = 1 - d_peso
    rd_after_tax = resultado["custo_divida"] * (1 - TAXA_MARGINAL_IR)
    resultado["wacc"] = e_peso * RE_PREMISSA + d_peso * rd_after_tax

    alertas.append({
        "tipo": "proxy",
        "indicador": "WACC",
        "mensagem": (
            f"Custo do equity (Re) fixado em {RE_PREMISSA:.0%} (premissa: Rf ~4.5% + ERP ~5.5%). "
            f"Pesos calculados a valor contábil (book value), não de mercado. "
            f"ROIC e EVA são aproximações."
        ),
    })

    # EVA = (ROIC - WACC) × Capital Investido
    resultado["eva"] = (resultado["roic"] - resultado["wacc"]) * capital_investido

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

    return resultado, alertas


# =========================================================================
# TABELAS FORMATADAS PARA O DASHBOARD
# =========================================================================

def formatar_tabela_dre(df: pd.DataFrame) -> pd.DataFrame:
    """Formata a tabela de DRE para exibição no dashboard."""
    colunas = {
        "label": "Período",
        "receita_liquida": "Receita Líquida",
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
        "divida_liq_receita": "Dív.Líq/Receita",
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
    df, alertas = calcular_indicadores(caminho)
    if alertas:
        print("\n=== ALERTAS ===")
        for a in alertas:
            print(f"[{a['tipo'].upper()}] {a['indicador']}: {a['mensagem']}")
    print(df[["label", "receita_liquida", "ebitda", "depreciacao_amortizacao", "lucro_liquido", "divida_liquida", "divida_liq_ebitda"]].to_string())
