"""
Reconciliador de dados: XBRL (SEC EDGAR) vs Earnings Release (PDF/Gemini).

Compara os dados de ambas as fontes, detecta divergências significativas,
e produz o dataset final usando a fonte mais confiável para cada indicador.

Regras de prioridade:
1. Se não há anomalia no XBRL, usa XBRL (fonte oficial estruturada)
2. Se há anomalia de desacumulação (discontinued ops), usa Earnings Release
3. Earnings Release sempre prevalece para: receita, custos e lucro (visão gerencial)
4. XBRL prevalece para: balanço patrimonial (dados de estoque, não desacumulados)
"""

import pandas as pd
import numpy as np


def reconciliar(df_xbrl: pd.DataFrame, dados_earnings: dict | None,
                alertas: list[dict]) -> pd.DataFrame:
    """
    Reconcilia DataFrame do XBRL com dados extraídos do Earnings Release.

    Args:
        df_xbrl: DataFrame calculado pelo indicadores.py (fonte XBRL)
        dados_earnings: dict do extrator_earnings (fonte PDF) ou None
        alertas: lista de alertas para adicionar divergências encontradas

    Returns:
        DataFrame reconciliado
    """
    if not dados_earnings or not dados_earnings.get("periodos"):
        return df_xbrl

    # Montar DataFrame dos earnings release
    periodos_er = dados_earnings["periodos"]
    er_by_date = {}
    for p in periodos_er:
        dt = pd.Timestamp(p["periodo"])
        er_by_date[dt] = p

    if not er_by_date:
        return df_xbrl

    df = df_xbrl.copy()
    n_correcoes = 0

    # Verificar cada período que tem dados do earnings release
    for dt, er_data in er_by_date.items():
        if dt not in df.index:
            continue

        dre = er_data.get("dre") or {}
        bal = er_data.get("balanco") or {}
        cf = er_data.get("fluxo_caixa") or {}

        # --- DRE: corrigir quando XBRL tem anomalia ---
        # Receita: se diverge > 20%, usar earnings release
        er_receita = dre.get("receita_liquida")
        xbrl_receita = df.loc[dt, "receita_liquida"] if "receita_liquida" in df.columns else None

        if er_receita and xbrl_receita and not np.isnan(xbrl_receita):
            ratio = abs(xbrl_receita - er_receita) / abs(er_receita) if er_receita != 0 else 0
            if ratio > 0.20:
                tri_label = df.loc[dt, "label"] if "label" in df.columns else str(dt)
                alertas.append({
                    "tipo": "inconsistente",
                    "indicador": f"Receita ({tri_label}) — corrigido",
                    "mensagem": (
                        f"XBRL: {xbrl_receita/1e9:.2f}B vs Earnings Release: {er_receita/1e9:.2f}B "
                        f"(divergência {ratio:.0%}). Usando valor do Earnings Release."
                    ),
                })
                df.loc[dt, "receita_liquida"] = er_receita
                n_correcoes += 1

                # Se corrigiu receita, recalcular margens
                rec = er_receita if er_receita != 0 else np.nan
                if "margem_bruta" in df.columns and dre.get("resultado_bruto"):
                    df.loc[dt, "resultado_bruto"] = dre["resultado_bruto"]
                    df.loc[dt, "margem_bruta"] = dre["resultado_bruto"] / rec
                if dre.get("custo"):
                    df.loc[dt, "custo"] = dre["custo"]

        # EBIT: corrigir se diverge > 30%
        er_ebit = dre.get("ebit")
        xbrl_ebit = df.loc[dt, "ebit"] if "ebit" in df.columns else None

        if er_ebit and xbrl_ebit and not np.isnan(xbrl_ebit):
            ratio = abs(xbrl_ebit - er_ebit) / abs(er_ebit) if er_ebit != 0 else 0
            if ratio > 0.30:
                df.loc[dt, "ebit"] = er_ebit
                n_correcoes += 1

        # Lucro Líquido: corrigir se diverge > 30%
        er_ll = dre.get("lucro_liquido")
        xbrl_ll = df.loc[dt, "lucro_liquido"] if "lucro_liquido" in df.columns else None

        if er_ll and xbrl_ll and not np.isnan(xbrl_ll):
            ratio = abs(xbrl_ll - er_ll) / abs(er_ll) if er_ll != 0 else 0
            if ratio > 0.30:
                df.loc[dt, "lucro_liquido"] = er_ll
                n_correcoes += 1

        # D&A: usar earnings release se disponível e XBRL está zerado
        er_dda = dre.get("depreciacao_amortizacao")
        xbrl_dda = df.loc[dt, "depreciacao_amortizacao"] if "depreciacao_amortizacao" in df.columns else None

        if er_dda and (xbrl_dda is None or np.isnan(xbrl_dda) or xbrl_dda == 0):
            df.loc[dt, "depreciacao_amortizacao"] = abs(er_dda)
            n_correcoes += 1

        # --- BALANÇO: corrigir campos zerados com dados do Earnings Release ---
        campos_balanco = {
            "caixa": bal.get("caixa"),
            "ativo_total": bal.get("ativo_total"),
            "ativo_circulante": bal.get("ativo_circulante"),
            "passivo_circulante": bal.get("passivo_circulante"),
            "contas_a_receber": bal.get("contas_a_receber"),
            "estoques": bal.get("estoques"),
            "fornecedores": bal.get("fornecedores"),
            "emprestimos_cp": bal.get("emprestimos_cp"),
            "emprestimos_lp": bal.get("emprestimos_lp"),
            "patrimonio_liquido": bal.get("patrimonio_liquido"),
        }
        for campo, er_val in campos_balanco.items():
            if er_val and campo in df.columns:
                xbrl_val = df.loc[dt, campo]
                if pd.isna(xbrl_val) or xbrl_val == 0:
                    df.loc[dt, campo] = er_val
                    n_correcoes += 1

    # Recalcular indicadores derivados após correções
    if n_correcoes > 0:
        rec = df["receita_liquida"].replace(0, np.nan)
        df["margem_bruta"] = df["resultado_bruto"] / rec
        df["margem_liquida"] = df["lucro_liquido"] / rec

        # EBITDA
        da = df["depreciacao_amortizacao"].fillna(0)
        df["ebitda"] = df["ebit"] + da
        df["margem_ebitda"] = df["ebitda"] / rec
        df["margem_ebit"] = df["ebit"] / rec

        # Recalcular LTM
        df["ebitda_ltm"] = df["ebitda"].rolling(4).sum()
        df["ebit_ltm"] = df["ebit"].rolling(4).sum()
        df["receita_ltm"] = df["receita_liquida"].rolling(4).sum()
        df["lucro_ltm"] = df["lucro_liquido"].rolling(4).sum()

        # Recalcular estrutura de capital
        emp_cp = df["emprestimos_cp"].fillna(0) if "emprestimos_cp" in df.columns else 0
        emp_lp = df["emprestimos_lp"].fillna(0) if "emprestimos_lp" in df.columns else 0
        caixa_val = df["caixa"].fillna(0) if "caixa" in df.columns else 0
        aplic = df["aplicacoes_financeiras_cp"].fillna(0) if "aplicacoes_financeiras_cp" in df.columns else 0

        df["divida_bruta"] = emp_cp + emp_lp
        df["liquidez_total"] = caixa_val + aplic
        df["divida_liquida"] = df["divida_bruta"] - df["liquidez_total"]

        # Liquidez
        pc = df["passivo_circulante"].replace(0, np.nan) if "passivo_circulante" in df.columns else np.nan
        ac = df["ativo_circulante"] if "ativo_circulante" in df.columns else np.nan
        df["liquidez_corrente"] = ac / pc
        df["cash_ratio"] = df["liquidez_total"] / pc

        # Recalcular múltiplos que dependem de EBITDA LTM
        ebitda_ltm = df["ebitda_ltm"].replace(0, np.nan)
        df["divida_liq_ebitda"] = df["divida_liquida"] / ebitda_ltm

        alertas.append({
            "tipo": "proxy",
            "indicador": "Reconciliação XBRL ↔ Earnings Release",
            "mensagem": (
                f"{n_correcoes} valor(es) corrigido(s) usando dados do Earnings Release. "
                f"Indicadores derivados (margens, LTM, múltiplos) foram recalculados."
            ),
        })

    return df
