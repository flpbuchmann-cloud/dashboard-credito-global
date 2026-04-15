"""
Dashboard de Crédito Global - Unified Financial Analysis for US-Listed Companies.

Covers Non-Financial (e.g. OXY, AMZN), Banks (e.g. JPM, BAC),
Card/Other Financials (e.g. AXP, V), and Asset Managers (e.g. BX, KKR, APO).

Usage:
    streamlit run src/dashboard/app.py
"""

import os
import sys
import json
from datetime import datetime
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st
import streamlit.components.v1 as st_components

# Add project root to path
PROJECT_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
sys.path.insert(0, PROJECT_ROOT)

# --- Non-financial imports ---
from src.calculo.indicadores import (
    calcular_indicadores as calcular_indicadores_nf,
    formatar_tabela_dre as fmt_dre_nf,
    formatar_tabela_fluxo_caixa as fmt_fc_nf,
    formatar_tabela_estrutura_capital as fmt_ec_nf,
    formatar_tabela_capital_giro as fmt_cg_nf,
    formatar_tabela_multiplos as fmt_mult_nf,
    formatar_tabela_fleuriet as fmt_fleuriet_nf,
)

# --- Financial imports ---
from src.calculo.indicadores_fin import (
    calcular_indicadores as calcular_indicadores_fin,
    formatar_tabela_dre as fmt_dre_fin,
    formatar_tabela_fluxo_caixa as fmt_fc_fin,
    formatar_tabela_estrutura_capital as fmt_ec_fin,
    formatar_tabela_multiplos as fmt_mult_fin,
    formatar_tabela_banco_capital,
    formatar_tabela_banco_liquidez,
    formatar_tabela_banco_credito,
    formatar_tabela_banco_rentabilidade,
)

# --- Shared modules ---
from src.coleta.ratings import buscar_ratings
from src.coleta.ri_website import buscar_ri_website
from src.coleta.extrator_earnings import extrair_e_salvar, carregar_dados_earnings
from src.coleta.extrator_cronograma import extrair_cronogramas_pasta
from src.calculo.reconciliador import reconciliar
from src.calculo.reconciliador_fin import reconciliar as reconciliar_fin
from src.dashboard.auth import (
    show_login,
    show_registration_form,
    show_admin_panel,
    show_logout,
)

# =========================================================================
# SECTOR DETECTION
# =========================================================================
BANCOS = {
    "BK", "JPM", "BAC", "C", "WFC", "GS", "MS", "USB", "PNC", "TFC",
    "SCHW", "STT", "NTRS", "FITB", "CFG", "KEY", "RF", "HBAN", "ZION",
    "MTB", "BCS", "HSBC", "CS", "DB", "UBS", "BBVA", "SAN", "ING", "BNP",
}
ASSET_MANAGERS = {"APO", "BX", "KKR", "ARES", "OWL", "BAM", "CG", "TPG", "BN", "FIG"}
CARDS = {"AXP", "V", "MA", "DFS", "COF", "SYF"}

SETORES = ["Nao-Financeira", "Banco", "Card / Outros", "Asset Manager"]

def _detectar_setor(ticker: str) -> int:
    """Returns index into SETORES for auto-detection."""
    t = ticker.strip().upper()
    if t in BANCOS:
        return 1
    if t in CARDS:
        return 2
    if t in ASSET_MANAGERS:
        return 3
    return 0  # Nao-Financeira


def _is_financeira(setor: str) -> bool:
    return setor != "Nao-Financeira"


# =========================================================================
# DATA PATHS
# =========================================================================
DEPLOY_DATA_DIR = os.path.join(PROJECT_ROOT, "data", "empresas")
LOCAL_DATA_BASE_NF = "G:/Meu Drive/Análise de Crédito Global"
LOCAL_DATA_BASE_FIN = "G:/Meu Drive/Análise de Crédito Financeiras"
IS_DEPLOYED = os.path.exists(DEPLOY_DATA_DIR) and not os.path.exists(LOCAL_DATA_BASE_NF)


def _pasta_empresa(ticker: str, setor: str) -> str:
    """Returns the correct path for the company's data folder."""
    if IS_DEPLOYED:
        return os.path.join(DEPLOY_DATA_DIR, ticker)
    base = LOCAL_DATA_BASE_FIN if _is_financeira(setor) else LOCAL_DATA_BASE_NF
    return os.path.join(base, ticker)


# Mapeamento ticker -> nome curto da empresa para exibição
TICKER_NAMES = {
    # Bancos US
    "BK": "BNY Mellon", "JPM": "JPMorgan Chase", "BAC": "Bank of America",
    "C": "Citigroup", "WFC": "Wells Fargo", "GS": "Goldman Sachs",
    "MS": "Morgan Stanley", "USB": "US Bancorp", "PNC": "PNC Financial",
    "TFC": "Truist", "SCHW": "Charles Schwab", "STT": "State Street",
    "NTRS": "Northern Trust", "FITB": "Fifth Third", "CFG": "Citizens",
    "KEY": "KeyCorp", "RF": "Regions", "HBAN": "Huntington",
    "ZION": "Zions", "MTB": "M&T Bank",
    # Bancos non-US
    "BCS": "Barclays", "HSBC": "HSBC", "DB": "Deutsche Bank",
    "UBS": "UBS Group", "CS": "Credit Suisse", "BBVA": "BBVA",
    "SAN": "Santander", "ING": "ING Group", "BNP": "BNP Paribas",
    # Asset Managers
    "APO": "Apollo", "BX": "Blackstone", "KKR": "KKR",
    "ARES": "Ares Mgmt", "OWL": "Blue Owl", "BAM": "Brookfield AM",
    "CG": "Carlyle", "TPG": "TPG", "BN": "Brookfield Corp", "FIG": "Fig",
    # Cards / Payments
    "AXP": "American Express", "V": "Visa", "MA": "Mastercard",
    "DFS": "Discover", "COF": "Capital One", "SYF": "Synchrony",
    # Não-financeiras
    "OXY": "Occidental", "AA": "Alcoa", "AAPL": "Apple",
    "MSFT": "Microsoft", "AMZN": "Amazon", "GOOGL": "Alphabet",
    "META": "Meta", "TSLA": "Tesla", "NVDA": "Nvidia",
    "XOM": "Exxon Mobil", "CVX": "Chevron",
    "CVS": "CVS Health", "WBA": "Walgreens", "UNH": "UnitedHealth",
    "JNJ": "Johnson & Johnson", "PFE": "Pfizer", "CI": "Cigna Group",
    "ELV": "Elevance Health", "HUM": "Humana",
    "PSX": "Phillips 66", "VLO": "Valero Energy", "MPC": "Marathon Petroleum",
    "COP": "ConocoPhillips", "EOG": "EOG Resources",
    "MBG": "Mercedes-Benz Group", "BMW": "BMW Group", "VOW": "Volkswagen",
    "VWAGY": "Volkswagen AG",
    "MT": "ArcelorMittal",
    "F": "Ford", "GM": "General Motors",
}


def _listar_empresas() -> list[tuple[str, str]]:
    """Lists tickers with data, returning (ticker, name) tuples."""
    tickers = set()
    # Deploy dir
    if os.path.isdir(DEPLOY_DATA_DIR):
        for d in os.listdir(DEPLOY_DATA_DIR):
            contas = os.path.join(DEPLOY_DATA_DIR, d, "Dados_EDGAR", "contas_chave.json")
            if os.path.exists(contas):
                tickers.add(d)
    # Non-financial local dir
    if os.path.isdir(LOCAL_DATA_BASE_NF):
        for d in os.listdir(LOCAL_DATA_BASE_NF):
            contas = os.path.join(LOCAL_DATA_BASE_NF, d, "Dados_EDGAR", "contas_chave.json")
            if os.path.exists(contas):
                tickers.add(d)
    # Financial local dir
    if os.path.isdir(LOCAL_DATA_BASE_FIN):
        for d in os.listdir(LOCAL_DATA_BASE_FIN):
            contas = os.path.join(LOCAL_DATA_BASE_FIN, d, "Dados_EDGAR", "contas_chave.json")
            if os.path.exists(contas):
                tickers.add(d)
    # Return (ticker, friendly_name)
    result = [(t, TICKER_NAMES.get(t, t)) for t in tickers]
    return sorted(result, key=lambda x: x[0])


def _sync_para_deploy(caminho_local: str, ticker: str, setor: str):
    """Copies a locally saved file to the deploy directory and auto-commits."""
    if IS_DEPLOYED:
        return
    pasta_local = _pasta_empresa(ticker, setor)
    try:
        rel = os.path.relpath(caminho_local, pasta_local)
    except ValueError:
        return
    destino = os.path.join(DEPLOY_DATA_DIR, ticker, rel)
    os.makedirs(os.path.dirname(destino), exist_ok=True)
    import shutil
    shutil.copy2(caminho_local, destino)
    try:
        import subprocess
        subprocess.run(["git", "add", destino], cwd=PROJECT_ROOT, capture_output=True, timeout=10)
        subprocess.run(["git", "commit", "-m", f"Sync {ticker}/{rel} from localhost"],
                       cwd=PROJECT_ROOT, capture_output=True, timeout=10)
        subprocess.run(["git", "push"], cwd=PROJECT_ROOT, capture_output=True, timeout=30)
    except Exception:
        pass


# =========================================================================
# CONFIGURATION
# =========================================================================
st.set_page_config(
    page_title="Dashboard de Credito Global",
    page_icon="\U0001f4ca",
    layout="wide",
    initial_sidebar_state="expanded",
)

CORES = {
    "azul": "#1f77b4",
    "verde": "#2ca02c",
    "vermelho": "#d62728",
    "laranja": "#ff7f0e",
    "roxo": "#9467bd",
    "cinza": "#7f7f7f",
    "azul_claro": "#aec7e8",
    "verde_claro": "#98df8a",
    "vermelho_claro": "#ff9896",
}


# =========================================================================
# FORMATTING FUNCTIONS
# =========================================================================
def _limpar_tabela(display_df):
    """Remove linhas onde todos os valores are '-' ou vazios."""
    mask = display_df.apply(
        lambda row: row.astype(str).str.strip().isin(["-", "", "nan", "0", "$0.00M", "$0.00B"]).all(),
        axis=1,
    )
    return display_df[~mask]


def fmt_bilhoes(valor):
    if pd.isna(valor):
        return "-"
    t = valor / 1e12
    if abs(t) >= 1:
        return f"${t:.2f}T"
    v = valor / 1e9
    if abs(v) >= 1:
        return f"${v:.2f}B"
    return f"${valor / 1e6:.2f}M"


def fmt_milhoes(valor):
    if pd.isna(valor):
        return "-"
    return f"${valor / 1e6:.2f}M"


def fmt_pct(valor):
    if pd.isna(valor):
        return "-"
    return f"{valor:.2%}"


def fmt_multiplo(valor):
    if pd.isna(valor):
        return "-"
    return f"{valor:.2f}x"


def estilo_valor(valor, inverter=False):
    if pd.isna(valor):
        return ""
    positivo = valor > 0
    if inverter:
        positivo = not positivo
    return "color: #2ca02c" if positivo else "color: #d62728"


# =========================================================================
# CHARTS
# =========================================================================
def grafico_barras(df, colunas, nomes, cores, titulo, formato="bilhoes"):
    """Grafico de barras com evolucao temporal."""
    fig = go.Figure()
    labels = df["label"].tolist()
    for col, nome, cor in zip(colunas, nomes, cores):
        valores = df[col].tolist()
        if formato == "bilhoes":
            texto = [
                f"${v/1e9:.2f}B" if not pd.isna(v) and abs(v) >= 1e9
                else (f"${v/1e6:.2f}M" if not pd.isna(v) else "")
                for v in valores
            ]
        else:
            texto = [f"{v:.2%}" if not pd.isna(v) else "" for v in valores]
        fig.add_trace(go.Bar(
            name=nome, x=labels, y=valores, marker_color=cor,
            text=texto, textposition="inside", insidetextanchor="middle",
            textfont=dict(size=8, color="white"),
        ))
    fig.update_layout(
        title=dict(text=titulo, font=dict(size=14), x=0, xanchor="left"),
        barmode="group", height=420, margin=dict(t=85, b=30, l=50, r=20),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5, font=dict(size=10)),
        yaxis=dict(gridcolor="#eee"), plot_bgcolor="white", bargap=0.15, bargroupgap=0.05,
    )
    return fig


def grafico_linhas(df, colunas, nomes, cores, titulo):
    """Grafico de linhas."""
    fig = go.Figure()
    labels = df["label"].tolist()
    for col, nome, cor in zip(colunas, nomes, cores):
        fig.add_trace(go.Scatter(
            name=nome, x=labels, y=df[col].tolist(),
            mode="lines+markers", line=dict(color=cor, width=2), marker=dict(size=5),
        ))
    fig.update_layout(
        title=dict(text=titulo, font=dict(size=14), x=0, xanchor="left"),
        height=380, margin=dict(t=85, b=30, l=50, r=20),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5, font=dict(size=10)),
        yaxis=dict(gridcolor="#eee"), plot_bgcolor="white",
    )
    return fig


def grafico_margens(df, titulo="Evolucao das Margens"):
    """Grafico de linhas de margens (non-financial)."""
    fig = go.Figure()
    labels = df["label"].tolist()
    margens = [
        ("margem_bruta", "Margem Bruta", CORES["azul"]),
        ("margem_ebitda", "Margem EBITDA", CORES["verde"]),
        ("margem_liquida", "Margem Líquida", CORES["laranja"]),
    ]
    for col, nome, cor in margens:
        if col in df.columns:
            fig.add_trace(go.Scatter(
                name=nome, x=labels, y=df[col].tolist(),
                mode="lines+markers", line=dict(color=cor, width=2), marker=dict(size=5),
            ))
    fig.update_layout(
        title=dict(text=titulo, font=dict(size=14), x=0, xanchor="left"),
        height=380, margin=dict(t=85, b=30, l=50, r=20),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5, font=dict(size=10)),
        yaxis=dict(tickformat=".0%", gridcolor="#eee"), plot_bgcolor="white",
    )
    return fig


def grafico_divida_alavancagem(df, titulo="Dívida Líquida vs Alavancagem"):
    """Grafico combo: barras (divida liquida) + linha (DL/EBITDA)."""
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    labels = df["label"].tolist()
    fig.add_trace(
        go.Bar(
            name="Dívida Líquida", x=labels, y=df["divida_liquida"].tolist(),
            marker_color=[CORES["vermelho"] if v > 0 else CORES["verde"] for v in df["divida_liquida"].fillna(0)],
            opacity=0.7,
        ),
        secondary_y=False,
    )
    fig.add_trace(
        go.Scatter(
            name="Dív.Líq/EBITDA (LTM)", x=labels, y=df["divida_liq_ebitda"].tolist(),
            mode="lines+markers", line=dict(color=CORES["roxo"], width=3), marker=dict(size=8),
        ),
        secondary_y=True,
    )
    fig.update_layout(
        title=dict(text=titulo, font=dict(size=14), x=0, xanchor="left"),
        height=420, margin=dict(t=85, b=30, l=60, r=60),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5, font=dict(size=10)),
        plot_bgcolor="white",
    )
    fig.update_yaxes(title_text="USD", gridcolor="#eee", secondary_y=False)
    fig.update_yaxes(title_text="x EBITDA (LTM)", gridcolor="#eee", secondary_y=True)
    return fig


def _label_vencimento(k: str) -> str:
    faixas = {
        "ate_1_ano": "< 1 ano", "1_a_2_anos": "1-2 anos",
        "2_a_5_anos": "2-5 anos", "3_a_5_anos": "3-5 anos",
        "acima_5_anos": "> 5 anos",
    }
    if k == "longo_prazo":
        return "Longo Prazo"
    return faixas.get(k, k)


def _label_periodo(cronograma: dict) -> str:
    dr = cronograma.get("data_referencia", "")
    if not dr:
        return cronograma.get("arquivo", "?")
    partes = dr.split("-")
    if len(partes) == 3:
        ano = partes[0][2:]
        mes = int(partes[1])
        tri = (mes - 1) // 3 + 1
        return f"Q{tri}/{ano}"
    return dr


# =========================================================================
# SHARED: PARECER TECNICO
# =========================================================================
def _render_parecer(pasta: str, ticker: str, setor: str, df, ratings: dict | None = None,
                    dados_am: dict | None = None):
    """Renderiza o parecer tecnico abaixo do cronograma. Gera on-the-fly
    se ainda nao existir, ou recarrega de parecer.md."""
    if ratings is None:
        try:
            ratings = buscar_ratings(ticker, pasta) or {}
        except Exception:
            ratings = {}
    parecer_path = os.path.join(pasta, "Dados_EDGAR", "parecer.md")
    md = None
    if os.path.exists(parecer_path):
        try:
            with open(parecer_path, "r", encoding="utf-8") as f:
                md = f.read()
        except Exception:
            md = None
    if not md:
        try:
            from src.analise.parecer import gerar_parecer
            md = gerar_parecer(ticker, setor, df, ratings, dados_am=dados_am)
        except Exception as e:
            md = f"*Erro ao gerar parecer: {e}*"

    st.markdown("## Parecer Técnico")
    st.caption(
        "Análise gerada automaticamente com base em benchmarks de Moody's, Fitch, Damodaran, "
        "McKinsey, Modelo Fleuriet (não-fin), Basel III + Bank Analyst's Handbook (bancos) e "
        "Moody's Methodology for Asset Management Firms (asset managers)."
    )
    st.markdown(md)


# =========================================================================
# SHARED: CRONOGRAMA DE VENCIMENTO
# =========================================================================
def _render_cronograma(df_completo, pasta, ticker, setor, is_admin, n_periodos):
    """Renders the debt maturity schedule section."""
    caminho_cron = os.path.join(pasta, "Dados_EDGAR", "cronogramas.json")

    cronogramas = []
    if os.path.exists(caminho_cron):
        with open(caminho_cron, "r", encoding="utf-8") as f:
            cronogramas = json.load(f)

    # Extract cronogramas from docs (admin only)
    if is_admin:
        pasta_docs_cron = os.path.join(pasta, "Documentos")
        if os.path.isdir(pasta_docs_cron):
            if st.button("Extrair cronograma de documentos (Gemini)", key="btn_extrair_cron"):
                with st.spinner("Extraindo cronograma via Gemini..."):
                    try:
                        novos_cron = extrair_cronogramas_pasta(pasta, ticker)
                        if novos_cron:
                            with open(caminho_cron, "r", encoding="utf-8") as f:
                                cronogramas = json.load(f)
                            st.success(f"{len(novos_cron)} cronograma(s) extraido(s)!")
                            st.rerun()
                        else:
                            st.info("Nenhum cronograma novo encontrado nos documentos.")
                    except Exception as e:
                        st.error(f"Erro na extracao: {e}")

    # Manual cronograma input (admin)
    if is_admin:
        with st.expander("Inserir/Editar cronograma manualmente", expanded=False):
            st.caption("Use quando o cronograma nao puder ser extraido automaticamente. Valores em **milhoes de USD**.")
            col_ref, col_caixa = st.columns(2)
            with col_ref:
                data_ref_input = st.text_input("Data de referencia (AAAA-MM-DD)", value="2025-12-31", key="cron_data_ref")
            with col_caixa:
                caixa_input = st.number_input("Caixa ($M)", value=0.0, step=100.0, key="cron_caixa")

            st.markdown("**Vencimentos por ano** (preencha os anos relevantes):")
            ano_base = int(data_ref_input[:4]) + 1 if len(data_ref_input) >= 4 else 2026
            cols_anos = st.columns(5)
            venc_inputs = {}
            for j in range(10):
                ano = ano_base + j
                with cols_anos[j % 5]:
                    val = st.number_input(f"{ano}", value=0.0, step=100.0, key=f"cron_{ano}", min_value=0.0)
                    if val > 0:
                        venc_inputs[str(ano)] = val

            arquivo_input = st.text_input("Fonte (ex: 10-K 2024 p.27)", value="Insercao manual", key="cron_arquivo")

            if st.button("Salvar cronograma", key="btn_salvar_cron"):
                if venc_inputs:
                    novo = {
                        "data_referencia": data_ref_input,
                        "caixa": caixa_input * 1_000_000,
                        "vencimentos": {k: v * 1_000_000 for k, v in venc_inputs.items()},
                        "divida_total": sum(v * 1_000_000 for v in venc_inputs.values()),
                        "arquivo": arquivo_input,
                    }
                    cronogramas = [c for c in cronogramas if c.get("data_referencia") != data_ref_input]
                    cronogramas.append(novo)
                    os.makedirs(os.path.dirname(caminho_cron), exist_ok=True)
                    with open(caminho_cron, "w", encoding="utf-8") as f:
                        json.dump(cronogramas, f, ensure_ascii=False, indent=2, default=str)
                    _sync_para_deploy(caminho_cron, ticker, setor)
                    st.success(f"Cronograma {data_ref_input} salvo e sincronizado!")
                    st.rerun()
                else:
                    st.warning("Preencha ao menos um ano de vencimento.")

    if cronogramas:
        ultimo_per = df_completo.index.max().strftime("%Y-%m-%d") if not df_completo.empty else "2099-12-31"
        fins_tri = ("03-31", "06-30", "09-30", "12-31")
        validos = [
            c for c in cronogramas
            if c.get("data_referencia", "")[-5:] in fins_tri
            and c.get("data_referencia", "") <= ultimo_per
            and (c.get("divida_total") or 0) > 0
        ]
        validos = sorted(validos, key=lambda c: (c.get("data_referencia", ""), c.get("divida_total", 0)), reverse=True)
        visto = set()
        dedup = []
        for c in validos:
            dr = c.get("data_referencia", "")
            if dr not in visto:
                visto.add(dr)
                dedup.append(c)
        recentes = dedup[:3]

        # Override caixa from DataFrame
        for cron in recentes:
            dr = cron.get("data_referencia", "")
            if dr:
                match = df_completo[df_completo.index == pd.Timestamp(dr)]
                if not match.empty:
                    if setor == "Banco":
                        hqla_direct = match["hqla_pool"].iloc[0] if "hqla_pool" in match.columns else 0
                        if not pd.isna(hqla_direct) and hqla_direct > 0:
                            cron["caixa"] = hqla_direct
                        else:
                            cx = match["caixa"].iloc[0] if "caixa" in match.columns else 0
                            dep_bancos = match["depositos_em_bancos"].iloc[0] if "depositos_em_bancos" in match.columns else 0
                            titulos = match["investimentos_titulos"].iloc[0] if "investimentos_titulos" in match.columns else 0
                            cron["caixa"] = (cx if not pd.isna(cx) else 0) + (dep_bancos if not pd.isna(dep_bancos) else 0) + (titulos if not pd.isna(titulos) else 0)
                        cron["_label_caixa"] = "HQLA Pool"
                    else:
                        liq = match["liquidez_total"].iloc[0] if "liquidez_total" in match.columns else np.nan
                        cx = match["caixa"].iloc[0] if "caixa" in match.columns else np.nan
                        val = liq if not pd.isna(liq) and liq > 0 else cx
                        if not pd.isna(val) and val > 0:
                            cron["caixa"] = val

        N_ANOS = 5
        cor_caixa = "#5b9bd5"
        cor_vencimento = "#c0504d"

        for idx, cron in enumerate(recentes):
            vencimentos = cron.get("vencimentos", {})
            caixa = cron.get("caixa") or 0
            label_caixa = cron.get("_label_caixa", "Caixa")
            dr = cron.get("data_referencia", "")
            ano_ref = int(dr.split("-")[0]) if dr else 2025
            primeiro_ano = ano_ref + 1

            anos_num = {}
            valor_lp = 0
            tem_faixas = False
            for k, v in vencimentos.items():
                if k in ("longo_prazo", "acima_5_anos"):
                    valor_lp += v
                elif k.startswith("ate_") or k.endswith("_anos"):
                    tem_faixas = True
                else:
                    try:
                        a = int(k)
                        if a >= primeiro_ano:
                            anos_num[a] = v
                    except ValueError:
                        pass

            if tem_faixas:
                chaves_faixa = []
                for k in ["ate_1_ano", "1_a_2_anos", "2_a_5_anos", "3_a_5_anos", "acima_5_anos"]:
                    if k in vencimentos:
                        chaves_faixa.append(k)
                bar_labels = [label_caixa] + [_label_vencimento(k) for k in chaves_faixa]
                bar_valores = [caixa / 1e6] + [vencimentos[k] / 1e6 for k in chaves_faixa]
            else:
                anos_fut = sorted(anos_num.keys())
                anos_ind = anos_fut[:N_ANOS - 1]
                anos_acum = anos_fut[N_ANOS - 1:]

                bar_labels = [label_caixa]
                bar_valores = [caixa / 1e6]

                for a in anos_ind:
                    bar_labels.append(str(a))
                    bar_valores.append(anos_num[a] / 1e6)

                if anos_acum or valor_lp > 0:
                    acum = sum(anos_num[a] for a in anos_acum) + valor_lp
                    lbl = f"{anos_acum[0]}+" if anos_acum else f"{primeiro_ano + N_ANOS - 1}+"
                    bar_labels.append(lbl)
                    bar_valores.append(acum / 1e6)

            cores_bar = [cor_caixa] + [cor_vencimento] * (len(bar_labels) - 1)
            textos = [f"${v/1000:.2f}B" if v >= 1000 else f"${v:,.2f}M" for v in bar_valores]

            label = _label_periodo(cron)
            sufixo = " (Mais Recente)" if idx == 0 else ""

            fig = go.Figure(go.Bar(
                x=bar_labels, y=bar_valores, marker_color=cores_bar,
                text=textos, textposition="inside", insidetextanchor="middle",
                textfont=dict(size=10, color="white"), width=0.6,
            ))
            max_val = max(bar_valores) if bar_valores else 0
            fig.update_layout(
                title=dict(text=f"Posicao em {label}{sufixo}", font=dict(size=14)),
                height=380, margin=dict(t=85, b=30, l=60, r=20),
                plot_bgcolor="white", xaxis=dict(type="category"),
                yaxis=dict(title="USD Milhoes", gridcolor="#eee", range=[0, max_val * 1.15]),
                showlegend=False,
            )
            st.plotly_chart(fig, use_container_width=True, key=f"amort_{idx}")
    else:
        # Fallback: mostra Caixa vs Dívida CP vs Dívida LP dos últimos trimestres
        st.warning(
            "⚠️ Cronograma detalhado de vencimentos por ano não disponível publicamente para esta empresa. "
            "Exibindo visão alternativa: posição de caixa/liquidez vs estrutura de dívida (CP vs LP).",
            icon="ℹ️"
        )
        if not df_completo.empty:
            df_cron_alt = df_completo.tail(min(n_periodos, 8)).copy()
            labels_alt = df_cron_alt["label"].tolist() if "label" in df_cron_alt.columns else [str(i) for i in df_cron_alt.index]

            caixa_vals = df_cron_alt["caixa"].fillna(0) / 1e9 if "caixa" in df_cron_alt.columns else pd.Series(0, index=df_cron_alt.index)
            if "liquidez_total" in df_cron_alt.columns:
                liq_vals = df_cron_alt["liquidez_total"].fillna(0) / 1e9
                caixa_vals = liq_vals.where(liq_vals > 0, caixa_vals)
            cp_vals = df_cron_alt["emprestimos_cp"].fillna(0) / 1e9 if "emprestimos_cp" in df_cron_alt.columns else pd.Series(0, index=df_cron_alt.index)
            lp_vals = df_cron_alt["emprestimos_lp"].fillna(0) / 1e9 if "emprestimos_lp" in df_cron_alt.columns else pd.Series(0, index=df_cron_alt.index)

            fig_alt = go.Figure()
            fig_alt.add_trace(go.Bar(
                name="Caixa / Liquidez",
                x=labels_alt,
                y=caixa_vals.tolist(),
                marker_color="#5b9bd5",
                text=[f"${v:.2f}B" if v > 0.01 else "" for v in caixa_vals],
                textposition="outside",
                textfont=dict(size=9),
            ))
            fig_alt.add_trace(go.Bar(
                name="Dívida CP (<1 ano)",
                x=labels_alt,
                y=cp_vals.tolist(),
                marker_color="#ed7d31",
                text=[f"${v:.2f}B" if v > 0.01 else "" for v in cp_vals],
                textposition="outside",
                textfont=dict(size=9),
            ))
            fig_alt.add_trace(go.Bar(
                name="Dívida LP (>1 ano)",
                x=labels_alt,
                y=lp_vals.tolist(),
                marker_color="#c0504d",
                text=[f"${v:.2f}B" if v > 0.01 else "" for v in lp_vals],
                textposition="outside",
                textfont=dict(size=9),
            ))
            fig_alt.update_layout(
                title=dict(text="Posição de Liquidez vs Estrutura de Dívida", font=dict(size=14), x=0, xanchor="left"),
                barmode="group",
                height=420,
                margin=dict(t=85, b=30, l=60, r=20),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5, font=dict(size=10)),
                yaxis=dict(title="USD Bilhões", gridcolor="#eee"),
                plot_bgcolor="white",
            )
            st.plotly_chart(fig_alt, use_container_width=True, key="cron_fallback_liquidez")
        else:
            st.info("Sem dados de balanço para exibir.")


# =========================================================================
# SHARED: QUALITATIVE TAB
# =========================================================================
def _render_tab_qualitativa(pasta, ticker, setor, is_admin):
    """Renders the qualitative analysis tab."""
    caminho_quali = os.path.join(pasta, "analise_qualitativa.md")
    st.subheader("Analise Qualitativa")

    conteudo_quali = ""
    if os.path.exists(caminho_quali):
        with open(caminho_quali, "r", encoding="utf-8") as f:
            conteudo_quali = f.read()

    if is_admin:
        modo_quali = st.radio("Modo", ["Visualizar", "Editar"], horizontal=True, key="modo_quali")
    else:
        modo_quali = "Visualizar"

    if modo_quali == "Editar":
        novo_conteudo = st.text_area("Conteudo (Markdown)", value=conteudo_quali, height=500, key="editor_quali")
        if st.button("Salvar", key="salvar_quali"):
            os.makedirs(os.path.dirname(caminho_quali), exist_ok=True)
            with open(caminho_quali, "w", encoding="utf-8") as f:
                f.write(novo_conteudo)
            _sync_para_deploy(caminho_quali, ticker, setor)
            st.success("Analise qualitativa salva e sincronizada!")
            st.rerun()
    elif conteudo_quali.strip():
        # Table of contents
        def _slug(texto):
            import re
            slug = texto.lower().strip()
            slug = re.sub(r'[^\w\s-]', '', slug)
            slug = re.sub(r'[\s]+', '-', slug)
            return slug

        def _extrair_titulos(conteudo):
            titulos = []
            for linha in conteudo.split("\n"):
                stripped = linha.strip()
                if stripped.startswith("## "):
                    titulos.append(("h2", stripped[3:].strip(), _slug(stripped[3:].strip())))
                elif stripped.startswith("# "):
                    titulos.append(("h1", stripped[2:].strip(), _slug(stripped[2:].strip())))
            return titulos

        titulos = _extrair_titulos(conteudo_quali)
        if titulos:
            import json as _json
            titulos_js = _json.dumps([{"nivel": n, "texto": t} for n, t, s in titulos], ensure_ascii=False)
            toc_height = 60 + len(titulos) * 28
            toc_component = f"""
            <style>
                body {{ margin: 0; padding: 0; overflow: hidden; }}
                #toc {{ background:#f8f9fa; padding:12px 20px; border-radius:8px; border-left:4px solid #1f77b4; font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif; }}
                #toc p.title {{ font-weight:bold; font-size:16px; margin:0 0 8px 0; }}
                #toc a {{ text-decoration:none; cursor:pointer; display:block; padding:2px 0; }}
                #toc a:hover {{ text-decoration: underline; }}
                #toc .h1-link {{ color:#1f77b4; font-weight:bold; font-size:15px; margin:4px 0; }}
                #toc .h2-link {{ color:#555; font-size:14px; margin:2px 0; padding-left:20px; }}
            </style>
            <div id="toc"><p class="title">Indice</p></div>
            <script>
            (function() {{
                var titulos = {titulos_js};
                var toc = document.getElementById('toc');
                function getMainDoc() {{ try {{ return window.parent.document; }} catch(e) {{ return null; }} }}
                function scrollToHeading(texto, tag) {{
                    var doc = getMainDoc();
                    if (!doc) return;
                    var headings = doc.querySelectorAll('h1, h2, h3, [data-testid="stMarkdown"] h1, [data-testid="stMarkdown"] h2');
                    for (var i = 0; i < headings.length; i++) {{
                        if (headings[i].textContent.trim() === texto.trim()) {{
                            headings[i].scrollIntoView({{behavior: 'smooth', block: 'start'}});
                            return;
                        }}
                    }}
                }}
                titulos.forEach(function(t) {{
                    var a = document.createElement('a');
                    a.textContent = t.texto;
                    a.className = t.nivel === 'h1' ? 'h1-link' : 'h2-link';
                    a.addEventListener('click', function(e) {{
                        e.preventDefault();
                        scrollToHeading(t.texto, t.nivel === 'h1' ? 'H1' : 'H2');
                    }});
                    toc.appendChild(a);
                }});
            }})();
            </script>
            """
            st_components.html(toc_component, height=toc_height, scrolling=False)
            st.markdown("---")

        st.markdown(conteudo_quali, unsafe_allow_html=True)
    else:
        st.info("Nenhuma analise qualitativa registrada.")


# =========================================================================
# SHARED: UPDATES TAB
# =========================================================================
def _render_tab_atualizacoes(pasta, ticker, setor, is_admin):
    """Renders the updates/log tab."""
    caminho_atualiz = os.path.join(pasta, "atualizacoes.json")
    pasta_anexos = os.path.join(pasta, "atualizacoes")

    st.subheader("Log de Atualizacoes")
    st.caption("Registre eventos relevantes: resultados trimestrais, mudancas regulatorias, guidance, M&A, etc.")

    atualizacoes = []
    if os.path.exists(caminho_atualiz):
        with open(caminho_atualiz, "r", encoding="utf-8") as f:
            atualizacoes = json.load(f)

    def _salvar_atualizacoes():
        os.makedirs(os.path.dirname(caminho_atualiz), exist_ok=True)
        with open(caminho_atualiz, "w", encoding="utf-8") as f:
            json.dump(atualizacoes, f, ensure_ascii=False, indent=2)
        _sync_para_deploy(caminho_atualiz, ticker, setor)

    if is_admin:
        def _on_upload_change():
            files = st.session_state.get("a_arqs")
            if files:
                st.session_state["_arqs_buffer"] = [
                    {"name": f.name, "type": f.type or "", "size": f.size, "data": f.getvalue()}
                    for f in files
                ]
            else:
                st.session_state.pop("_arqs_buffer", None)

        with st.expander("Adicionar nova atualizacao", expanded=False):
            col_data, col_cat = st.columns([1, 1])
            with col_data:
                data_atualiz = st.date_input("Data", value=datetime.now().date(), key="atualiz_data")
            with col_cat:
                categoria = st.selectbox(
                    "Categoria",
                    ["Resultados Trimestrais", "Guidance", "Setor / Mercado",
                     "Regulatorio", "M&A", "Rating / Credito",
                     "Update Research", "Noticia", "Outros"],
                    key="atualiz_cat",
                )
            titulo_atualiz = st.text_input("Titulo *", key="atualiz_titulo")
            corpo_atualiz = st.text_area("Descricao (Markdown)", height=150, key="atualiz_corpo")
            st.file_uploader("Anexar arquivos", accept_multiple_files=True, key="a_arqs", on_change=_on_upload_change)

            arqs_buf = st.session_state.get("_arqs_buffer", [])
            if arqs_buf:
                st.caption(f"{len(arqs_buf)} arquivo(s) prontos: {', '.join(a['name'] for a in arqs_buf)}")

            if st.button("Salvar atualizacao", key="btn_salvar_atualiz"):
                if titulo_atualiz.strip():
                    atualiz_id = datetime.now().strftime("%Y%m%d_%H%M%S")
                    arquivos_salvos = []
                    if arqs_buf:
                        pasta_atualiz = os.path.join(pasta_anexos, atualiz_id)
                        os.makedirs(pasta_atualiz, exist_ok=True)
                        for arq in arqs_buf:
                            caminho_arq = os.path.join(pasta_atualiz, arq["name"])
                            with open(caminho_arq, "wb") as f:
                                f.write(arq["data"])
                            arquivos_salvos.append({
                                "nome": arq["name"],
                                "caminho": os.path.relpath(caminho_arq, pasta),
                                "tipo": arq["type"],
                                "tamanho": arq["size"],
                            })

                    nova = {
                        "id": atualiz_id,
                        "data": str(data_atualiz),
                        "categoria": categoria,
                        "titulo": titulo_atualiz.strip(),
                        "corpo": corpo_atualiz.strip(),
                        "arquivos": arquivos_salvos,
                        "criado_em": datetime.now().isoformat(),
                    }
                    atualizacoes.insert(0, nova)
                    _salvar_atualizacoes()
                    st.session_state.pop("_arqs_buffer", None)
                    st.success(f"Registrada! {len(arquivos_salvos)} arquivo(s) anexado(s).")
                    st.rerun()
                else:
                    st.warning("Preencha o titulo.")

    if atualizacoes:
        categorias_existentes = sorted(set(a["categoria"] for a in atualizacoes))
        filtro_cat = st.multiselect("Filtrar por categoria", categorias_existentes, default=categorias_existentes)

        for idx, atualiz in enumerate(atualizacoes):
            if atualiz["categoria"] not in filtro_cat:
                continue

            st.markdown(f"### {atualiz['titulo']}\n**{atualiz['data']}** | {atualiz['categoria']}")
            if atualiz.get("corpo"):
                st.markdown(atualiz["corpo"])

            # Show attached files
            arquivos = atualiz.get("arquivos", [])
            if arquivos:
                for arq_idx, arq in enumerate(arquivos):
                    caminho_arq = os.path.join(pasta, arq["caminho"])
                    nome = arq["nome"]
                    tipo = arq.get("tipo", "")
                    tam = arq.get("tamanho", 0)
                    tam_str = f"{tam/1e6:.1f}MB" if tam > 1e6 else f"{tam/1e3:.0f}KB"
                    dl_key = f"show_dl_{atualiz.get('id', idx)}_{nome}"

                    if os.path.exists(caminho_arq):
                        col_arq1, col_arq2 = st.columns([3, 1])
                        with col_arq1:
                            st.markdown(f"**{nome}** ({tam_str})")
                        with col_arq2:
                            if st.button("Abrir", key=dl_key):
                                st.session_state[f"_show_{dl_key}"] = True
                        if st.session_state.get(f"_show_{dl_key}", False):
                            with open(caminho_arq, "rb") as f_arq:
                                arq_bytes = f_arq.read()
                            st.download_button(
                                f"Baixar {nome}", data=arq_bytes, file_name=nome,
                                mime=tipo or "application/octet-stream",
                                key=f"dlbtn_{atualiz.get('id', idx)}_{nome}",
                            )
                            if tipo.startswith("image/"):
                                st.image(arq_bytes, caption=nome, use_container_width=True)
                    else:
                        st.caption(f"Arquivo nao encontrado: {nome}")

            # Admin actions
            if is_admin:
                col_edit, col_del = st.columns(2)
                edit_key = f"edit_mode_{idx}"
                with col_edit:
                    if st.button("Editar", key=f"btn_edit_{idx}"):
                        st.session_state[edit_key] = True
                with col_del:
                    if st.button("Remover", key=f"del_atualiz_{idx}"):
                        if atualiz.get("id"):
                            import shutil
                            p = os.path.join(pasta_anexos, atualiz["id"])
                            if os.path.isdir(p):
                                shutil.rmtree(p)
                        atualizacoes.pop(idx)
                        _salvar_atualizacoes()
                        st.rerun()

                if st.session_state.get(edit_key, False):
                    st.markdown("---")
                    new_titulo = st.text_input("Titulo", value=atualiz["titulo"], key=f"ed_tit_{idx}")
                    new_data = st.date_input(
                        "Data",
                        value=datetime.strptime(atualiz["data"], "%Y-%m-%d").date() if atualiz.get("data") else datetime.now().date(),
                        key=f"ed_dt_{idx}",
                    )
                    cats = ["Resultados Trimestrais", "Guidance", "Setor / Mercado",
                            "Regulatorio", "M&A", "Rating / Credito",
                            "Update Research", "Noticia", "Outros"]
                    cat_idx_v = cats.index(atualiz["categoria"]) if atualiz.get("categoria") in cats else 0
                    new_cat = st.selectbox("Categoria", cats, index=cat_idx_v, key=f"ed_cat_{idx}")
                    new_corpo = st.text_area("Descricao", value=atualiz.get("corpo", ""), height=150, key=f"ed_corpo_{idx}")

                    col_save, col_cancel = st.columns(2)
                    with col_save:
                        if st.button("Salvar edicao", key=f"save_edit_{idx}"):
                            if not new_titulo.strip():
                                st.error("O campo **Titulo** e obrigatorio.")
                            else:
                                atualizacoes[idx]["titulo"] = new_titulo.strip()
                                atualizacoes[idx]["data"] = str(new_data)
                                atualizacoes[idx]["categoria"] = new_cat
                                atualizacoes[idx]["corpo"] = new_corpo.strip()
                                atualizacoes[idx]["editado_em"] = datetime.now().isoformat()
                                _salvar_atualizacoes()
                                st.session_state.pop(edit_key, None)
                                st.success("Atualizacao editada!")
                                st.rerun()
                    with col_cancel:
                        if st.button("Cancelar", key=f"cancel_edit_{idx}"):
                            st.session_state.pop(edit_key, None)
                            st.rerun()

            st.markdown("---")
    else:
        st.info("Nenhuma atualizacao registrada. Use o formulario acima para adicionar.")


# =========================================================================
# LAYOUT: NAO-FINANCEIRA
# =========================================================================
def _layout_nao_financeira(df, df_completo, pasta, ticker, setor, is_admin, n_periodos, growth_mode):
    """Full quantitative layout for non-financial companies."""
    is_qoq = growth_mode.startswith("QoQ")
    growth_suffix = "qoq" if is_qoq else "yoy"

    # --- DRE ---
    st.header("Demonstração de Resultados (DRE)")
    tab_dre = fmt_dre_nf(df)
    display_dre = tab_dre.set_index("Per\u00edodo").T.astype(object)

    formato_rows = {
        "Receita Líquida": fmt_bilhoes, "CPV": fmt_bilhoes,
        "Resultado Bruto": fmt_bilhoes, "Despesas com Vendas": fmt_bilhoes,
        "Despesas G&A": fmt_bilhoes, "EBIT": fmt_bilhoes,
        "D&A": fmt_bilhoes, "EBITDA": fmt_bilhoes,
        "Resultado Financeiro": fmt_bilhoes, "Receitas Financeiras": fmt_bilhoes,
        "Despesas Financeiras": fmt_bilhoes, "Lucro Antes IR": fmt_bilhoes,
        "IR/CSLL": fmt_bilhoes, "Lucro Líquido": fmt_bilhoes,
        "Margem Bruta": fmt_pct, "Margem EBIT": fmt_pct,
        "Margem EBITDA": fmt_pct, "Margem Líquida": fmt_pct,
    }
    for row_name, fmt_fn in formato_rows.items():
        if row_name in display_dre.index:
            display_dre.loc[row_name] = display_dre.loc[row_name].apply(fmt_fn)

    ocultar_dre = ["CPV", "Resultado Bruto", "Despesas com Vendas", "Despesas G&A", "D&A", "Lucro Antes IR", "IR/CSLL"]
    display_dre = display_dre.drop([r for r in ocultar_dre if r in display_dre.index], axis=0)
    st.dataframe(display_dre, use_container_width=True, height=500)

    col_g1, col_g2 = st.columns(2)
    with col_g1:
        fig = grafico_barras(df, ["receita_liquida", "ebitda", "lucro_liquido"],
                             ["Receita", "EBITDA", "Lucro Líquido"],
                             [CORES["azul"], CORES["verde"], CORES["laranja"]],
                             "Receita, EBITDA e Lucro Líquido")
        st.plotly_chart(fig, use_container_width=True)
    with col_g2:
        fig_margens = grafico_margens(df)
        st.plotly_chart(fig_margens, use_container_width=True)

    st.markdown("---")

    # --- Fluxo de Caixa ---
    st.header("Fluxo de Caixa")
    tab_fc = fmt_fc_nf(df)
    display_fc = tab_fc.set_index("Per\u00edodo").T.astype(object)
    formato_fc = {
        "FCO": fmt_bilhoes, "FCO/EBITDA": fmt_pct, "FCO/Receita": fmt_pct,
        "Capex": fmt_bilhoes, "Capex/Receita": fmt_pct,
        "FCL": fmt_bilhoes, "FCL/Receita": fmt_pct,
        "Juros Pagos": fmt_bilhoes, "Amortiz. Dívida": fmt_bilhoes,
        "Captação": fmt_bilhoes, "Dividendos Pagos": fmt_bilhoes,
        "FC Financiamento": fmt_bilhoes,
    }
    for row_name, fmt_fn in formato_fc.items():
        if row_name in display_fc.index:
            display_fc.loc[row_name] = display_fc.loc[row_name].apply(fmt_fn)
    st.dataframe(display_fc, use_container_width=True, height=420)

    col_fc1, col_fc2 = st.columns(2)
    with col_fc1:
        fig_fc = grafico_barras(df, ["fco", "capex", "fcl"], ["FCO", "Capex", "FCL"],
                                [CORES["azul"], CORES["vermelho"], CORES["verde"]], "FCO vs Capex vs FCL")
        st.plotly_chart(fig_fc, use_container_width=True)
    with col_fc2:
        fig_fc_pct = grafico_linhas(df, ["fco_receita", "capex_receita", "fcl_receita"],
                                    ["FCO/Receita", "Capex/Receita", "FCL/Receita"],
                                    [CORES["azul"], CORES["vermelho"], CORES["verde"]],
                                    "FCO, Capex e FCL como % da Receita")
        fig_fc_pct.update_layout(yaxis=dict(tickformat=".0%"))
        st.plotly_chart(fig_fc_pct, use_container_width=True)

    st.markdown("---")

    # --- Estrutura de Capital ---
    st.header("Estrutura de Capital")
    tab_ec = fmt_ec_nf(df)
    display_ec = tab_ec.set_index("Per\u00edodo").T.astype(object)
    formato_ec = {
        "Caixa": fmt_bilhoes, "Aplicações Fin. CP": fmt_bilhoes, "Liquidez Total": fmt_bilhoes,
        "Dívida CP": fmt_bilhoes, "Dívida LP": fmt_bilhoes, "Dívida Bruta": fmt_bilhoes,
        "Dívida Líquida": fmt_bilhoes, "Patrimônio Líquido": fmt_bilhoes,
        "Dív.Líq/EBITDA": fmt_multiplo, "Dív.Líq/FCO": fmt_multiplo, "Dív.Líq/Receita": fmt_multiplo,
    }
    for row_name, fmt_fn in formato_ec.items():
        if row_name in display_ec.index:
            display_ec.loc[row_name] = display_ec.loc[row_name].apply(fmt_fn)
    st.dataframe(display_ec, use_container_width=True, height=340)

    fig_divida = grafico_divida_alavancagem(df)
    st.plotly_chart(fig_divida, use_container_width=True)

    col_ec1, col_ec2 = st.columns(2)
    labels_ec = df["label"].tolist()
    with col_ec1:
        fig_cp_lp = go.Figure()
        fig_cp_lp.add_trace(go.Bar(name="Dívida CP", x=labels_ec, y=df["emprestimos_cp"].tolist(),
                                   marker_color=CORES["vermelho"],
                                   text=[fmt_bilhoes(v) for v in df["emprestimos_cp"]],
                                   textposition="inside", insidetextanchor="middle",
                                   textfont=dict(size=8, color="white")))
        fig_cp_lp.add_trace(go.Bar(name="Dívida LP", x=labels_ec, y=df["emprestimos_lp"].tolist(),
                                   marker_color=CORES["vermelho_claro"],
                                   text=[fmt_bilhoes(v) for v in df["emprestimos_lp"]],
                                   textposition="inside", insidetextanchor="middle",
                                   textfont=dict(size=8, color="white")))
        fig_cp_lp.update_layout(
            title=dict(text="Composição da Dívida (CP vs LP)", font=dict(size=14), x=0, xanchor="left"),
            barmode="stack", height=420, margin=dict(t=85, b=30, l=50, r=20),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5, font=dict(size=10)),
            yaxis=dict(gridcolor="#eee"), plot_bgcolor="white",
        )
        st.plotly_chart(fig_cp_lp, use_container_width=True)

    with col_ec2:
        fig_db_rec = make_subplots(specs=[[{"secondary_y": True}]])
        fig_db_rec.add_trace(go.Bar(name="Dívida Bruta", x=labels_ec, y=df["divida_bruta"].tolist(),
                                    marker_color=CORES["vermelho"], opacity=0.7), secondary_y=False)
        fig_db_rec.add_trace(go.Scatter(name="Receita Líquida", x=labels_ec, y=df["receita_liquida"].tolist(),
                                        mode="lines+markers", line=dict(color=CORES["azul"], width=3),
                                        marker=dict(size=6)), secondary_y=True)
        fig_db_rec.update_layout(
            title=dict(text="Dívida Bruta vs Receita Líquida", font=dict(size=14), x=0, xanchor="left"),
            height=420, margin=dict(t=85, b=30, l=60, r=60),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5, font=dict(size=10)),
            plot_bgcolor="white",
        )
        fig_db_rec.update_yaxes(title_text="Dívida Bruta (USD)", gridcolor="#eee", secondary_y=False)
        fig_db_rec.update_yaxes(title_text="Receita Líquida (USD)", gridcolor="#eee", secondary_y=True)
        st.plotly_chart(fig_db_rec, use_container_width=True)

    st.markdown("---")

    # --- Capital de Giro ---
    st.header("Capital de Giro")
    tab_cg = fmt_cg_nf(df)
    display_cg = tab_cg.set_index("Per\u00edodo").T.astype(object)
    formato_cg = {
        "Contas a Receber": fmt_bilhoes, "Estoques": fmt_bilhoes, "Fornecedores": fmt_bilhoes,
        "Capital de Giro": fmt_bilhoes,
        "DSO (dias)": lambda v: f"{v:.0f}" if not pd.isna(v) else "-",
        "DIO (dias)": lambda v: f"{v:.0f}" if not pd.isna(v) else "-",
        "DPO (dias)": lambda v: f"{v:.0f}" if not pd.isna(v) else "-",
        "Ciclo de Caixa (dias)": lambda v: f"{v:.0f}" if not pd.isna(v) else "-",
    }
    for row_name, fmt_fn in formato_cg.items():
        if row_name in display_cg.index:
            display_cg.loc[row_name] = display_cg.loc[row_name].apply(fmt_fn)
    st.dataframe(display_cg, use_container_width=True, height=340)

    col_cg1, col_cg2 = st.columns(2)
    with col_cg1:
        fig_cg = grafico_barras(df, ["contas_a_receber", "estoques", "fornecedores"],
                                ["Contas a Receber", "Estoques", "Fornecedores"],
                                [CORES["azul"], CORES["laranja"], CORES["vermelho"]],
                                "Componentes do Capital de Giro")
        st.plotly_chart(fig_cg, use_container_width=True)
    with col_cg2:
        if "ciclo_caixa" in df.columns:
            fig_ciclo = grafico_linhas(df, ["dso", "dio", "dpo", "ciclo_caixa"],
                                       ["DSO", "DIO", "DPO", "Ciclo de Caixa"],
                                       [CORES["azul"], CORES["laranja"], CORES["vermelho"], CORES["roxo"]],
                                       "Ciclo de Conversao de Caixa (dias)")
            fig_ciclo.update_layout(yaxis=dict(tickformat=".0f"))
            st.plotly_chart(fig_ciclo, use_container_width=True)

    st.markdown("---")

    # --- Multiplos ---
    st.header("Multiplos de Alavancagem e Liquidez")
    tab_mult = fmt_mult_nf(df)
    display_mult = tab_mult.set_index("Per\u00edodo").T.astype(object)
    formato_mult = {
        "Dív.Líq/EBITDA": fmt_multiplo, "Dív.Líq/FCO": fmt_multiplo,
        "EBITDA/Desp.Fin (LTM)": fmt_multiplo, "EBIT/Desp.Fin (LTM)": fmt_multiplo,
        "DSCR": fmt_multiplo, "Equity Multiplier": fmt_multiplo,
        "Debt-to-Assets": fmt_pct, "Dív.CP / Dív.Total": fmt_pct,
        "Liquidez Corrente": fmt_multiplo, "Liquidez Seca": fmt_multiplo,
        "Cash Ratio": fmt_multiplo, "Solvência Geral": fmt_multiplo,
        "Dív.Total / PL": fmt_multiplo, "Custo da Dívida": fmt_pct,
        "Capex/EBITDA (LTM)": fmt_pct, "Payout (LTM)": fmt_pct,
    }
    for row_name, fmt_fn in formato_mult.items():
        if row_name in display_mult.index:
            display_mult.loc[row_name] = display_mult.loc[row_name].apply(fmt_fn)
    st.dataframe(display_mult, use_container_width=True, height=500)

    col_m1, col_m2 = st.columns(2)
    with col_m1:
        fig_liq = grafico_linhas(df, ["liquidez_corrente", "liquidez_seca", "cash_ratio"],
                                 ["Liquidez Corrente", "Liquidez Seca", "Cash Ratio"],
                                 [CORES["azul"], CORES["laranja"], CORES["verde"]], "Liquidez")
        st.plotly_chart(fig_liq, use_container_width=True)
    with col_m2:
        fig_alav = grafico_linhas(df, ["divida_liq_ebitda", "divida_total_pl", "interest_coverage_ebitda"],
                                  ["DL/EBITDA", "Dív.Total/PL", "EBITDA/Desp.Fin"],
                                  [CORES["roxo"], CORES["vermelho"], CORES["azul"]],
                                  "Alavancagem e Cobertura de Juros")
        st.plotly_chart(fig_alav, use_container_width=True)

    col_m3, col_m4 = st.columns(2)
    with col_m3:
        fig_solv = grafico_linhas(df, ["solvencia"],
                                  ["Solvencia (Ativo Total / Passivo Total)"],
                                  [CORES["azul"]], "Evolucao da Solvencia")
        st.plotly_chart(fig_solv, use_container_width=True)
    with col_m4:
        fig_custo = grafico_linhas(df, ["custo_divida"],
                                   ["Custo da Dívida (|Desp.Fin| LTM / Div.Bruta)"],
                                   [CORES["vermelho"]], "Evolucao do Custo da Dívida")
        fig_custo.update_layout(yaxis=dict(tickformat=".2%"))
        st.plotly_chart(fig_custo, use_container_width=True)

    # ROIC vs WACC + EVA
    if "roic" in df.columns and "wacc" in df.columns:
        fig_rw = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.08,
                               row_heights=[0.6, 0.4], subplot_titles=("ROIC vs WACC", "EVA (Valor Economico Agregado)"))
        labels_rw = df["label"].tolist()
        fig_rw.add_trace(go.Scatter(name="ROIC", x=labels_rw, y=df["roic"].tolist(),
                                    mode="lines+markers", line=dict(color=CORES["azul"], width=3),
                                    marker=dict(size=7)), row=1, col=1)
        fig_rw.add_trace(go.Scatter(name="WACC", x=labels_rw, y=df["wacc"].tolist(),
                                    mode="lines+markers", line=dict(color=CORES["vermelho"], width=2, dash="dash"),
                                    marker=dict(size=5)), row=1, col=1)
        fig_rw.add_trace(go.Scatter(name="Spread ROIC-WACC", x=labels_rw,
                                    y=((df["roic"] - df["wacc"])).tolist(),
                                    mode="lines", line=dict(color=CORES["verde"], width=1),
                                    fill="tozeroy", fillcolor="rgba(44, 160, 44, 0.15)"), row=1, col=1)
        eva_vals = df["eva"].tolist()
        eva_cores = [CORES["verde"] if not pd.isna(v) and v >= 0 else CORES["vermelho"] for v in eva_vals]
        fig_rw.add_trace(go.Bar(name="EVA", x=labels_rw, y=eva_vals, marker_color=eva_cores,
                                text=[fmt_bilhoes(v) for v in eva_vals], textposition="inside",
                                insidetextanchor="middle", textfont=dict(size=8, color="white"),
                                showlegend=False), row=2, col=1)
        fig_rw.update_layout(height=650, margin=dict(t=85, b=30, l=60, r=20),
                             legend=dict(orientation="h", yanchor="top", y=1.12, xanchor="center", x=0.5, font=dict(size=10)),
                             plot_bgcolor="white")
        fig_rw.layout.annotations[0].update(y=1.05, font=dict(size=13))
        fig_rw.layout.annotations[1].update(font=dict(size=13))
        fig_rw.update_yaxes(tickformat=".2%", gridcolor="#eee", row=1, col=1)
        fig_rw.update_yaxes(gridcolor="#eee", row=2, col=1)
        st.plotly_chart(fig_rw, use_container_width=True)

    st.markdown("---")

    # --- Fleuriet ---
    st.header("Modelo Fleuriet - Analise Dinamica")
    tab_fl = fmt_fleuriet_nf(df)
    display_fl = tab_fl.set_index("Per\u00edodo").T.astype(object)
    formato_fl = {
        "CDG (Capital de Giro)": fmt_bilhoes, "NCG (Nec. Capital de Giro)": fmt_bilhoes,
        "Saldo de Tesouraria (T)": fmt_bilhoes, "CDG / NCG": fmt_multiplo,
        "T / Receita": fmt_pct,
        "Nota Fleuriet": lambda v: f"{v:.0f}/10" if not pd.isna(v) else "-",
    }
    for row_name, fmt_fn in formato_fl.items():
        if row_name in display_fl.index:
            display_fl.loc[row_name] = display_fl.loc[row_name].apply(fmt_fn)
    st.dataframe(display_fl, use_container_width=True, height=320)

    col_fl_g1, col_fl_g2 = st.columns(2)
    with col_fl_g1:
        fig_fl = grafico_barras(df, ["fleuriet_cdg", "fleuriet_ncg", "fleuriet_t"],
                                ["CDG", "NCG", "Saldo de Tesouraria (T)"],
                                [CORES["azul"], CORES["laranja"], CORES["verde"]],
                                "CDG, NCG e Saldo de Tesouraria")
        st.plotly_chart(fig_fl, use_container_width=True)
    with col_fl_g2:
        fig_nota = go.Figure()
        labels = df["label"].tolist()
        notas = df["fleuriet_nota"].tolist()
        tipos = df["fleuriet_tipo"].tolist() if "fleuriet_tipo" in df.columns else [""] * len(labels)
        cores_nota = []
        for n in notas:
            if pd.isna(n):
                cores_nota.append(CORES["cinza"])
            elif n >= 8:
                cores_nota.append(CORES["verde"])
            elif n >= 6:
                cores_nota.append(CORES["azul"])
            elif n >= 4:
                cores_nota.append(CORES["laranja"])
            else:
                cores_nota.append(CORES["vermelho"])
        fig_nota.add_trace(go.Bar(
            x=labels, y=notas, marker_color=cores_nota,
            text=[f"{n:.0f} - {t}" if not pd.isna(n) else "" for n, t in zip(notas, tipos)],
            textposition="inside", insidetextanchor="middle", textfont=dict(size=8, color="white"),
        ))
        fig_nota.update_layout(
            title=dict(text="Evolucao da Nota Fleuriet (1-10)", font=dict(size=14), x=0, xanchor="left"),
            height=420, margin=dict(t=85, b=30, l=50, r=20),
            yaxis=dict(range=[0, 10.5], dtick=1, gridcolor="#eee"), plot_bgcolor="white", showlegend=False,
        )
        fig_nota.add_hrect(y0=7.5, y1=10.5, fillcolor="green", opacity=0.05, line_width=0)
        fig_nota.add_hrect(y0=5.5, y1=7.5, fillcolor="blue", opacity=0.05, line_width=0)
        fig_nota.add_hrect(y0=3.5, y1=5.5, fillcolor="orange", opacity=0.05, line_width=0)
        fig_nota.add_hrect(y0=0, y1=3.5, fillcolor="red", opacity=0.05, line_width=0)
        st.plotly_chart(fig_nota, use_container_width=True)

    st.markdown("---")

    # --- Cronograma ---
    st.header("Cronograma de Vencimento da Divida")
    _render_cronograma(df_completo, pasta, ticker, setor, is_admin, n_periodos)

    st.markdown("---")

    # --- Parecer Tecnico ---
    _render_parecer(pasta, ticker, setor, df_completo)

    st.markdown("---")

    # --- Glossario ---
    with st.expander("Metodologia e Glossario", expanded=False):
        from src.dashboard.glossario import GLOSSARIO_METODOLOGIA
        st.markdown(GLOSSARIO_METODOLOGIA)


# =========================================================================
# LAYOUT: FINANCEIRA (Banco / Card / Asset Manager)
# =========================================================================
def _layout_financeira(df, df_completo, pasta, ticker, setor, is_admin, n_periodos, visao):
    """Full quantitative layout for financial companies."""
    labels = df["label"].tolist()

    # --- 1. DRE ---
    st.header("Demonstração de Resultados")
    tab_dre = fmt_dre_fin(df, setor)
    display_dre = tab_dre.set_index("Per\u00edodo").T.astype(object)
    formato_dre = {
        "Receita Total": fmt_bilhoes, "NII": fmt_bilhoes,
        "NII (Net Interest Income)": fmt_bilhoes,
        "Receita Não-Juros": fmt_bilhoes, "Provisão p/ Crédito": fmt_bilhoes,
        "Despesas Operacionais": fmt_bilhoes, "Efficiency Ratio": fmt_pct,
        "PPNR": fmt_bilhoes, "EBIT": fmt_bilhoes, "EBITDA": fmt_bilhoes,
        "Lucro Antes IR": fmt_bilhoes, "IR": fmt_bilhoes, "Lucro Líquido": fmt_bilhoes,
        "Margem EBIT": fmt_pct, "Margem EBITDA": fmt_pct, "Margem Líquida": fmt_pct,
    }
    for k, fn in formato_dre.items():
        if k in display_dre.index:
            display_dre.loc[k] = display_dre.loc[k].apply(fn)
    display_dre = _limpar_tabela(display_dre)
    st.dataframe(display_dre, use_container_width=True, height=min(450, 40 + len(display_dre) * 35))

    col_g1, col_g2 = st.columns(2)
    if setor == "Banco":
        with col_g1:
            fig = grafico_barras(df, ["nii", "receita_nao_juros", "lucro_liquido"],
                                 ["NII", "Receita Não-Juros", "Lucro Líquido"],
                                 [CORES["azul"], CORES["verde"], CORES["laranja"]],
                                 "NII, Receita Não-Juros e Lucro Líquido")
            st.plotly_chart(fig, use_container_width=True)
        with col_g2:
            fig_ppnr = go.Figure()
            if "ppnr" in df.columns:
                fig_ppnr.add_trace(go.Bar(name="PPNR", x=labels, y=(df["ppnr"].fillna(0) / 1e9).tolist(),
                                          marker_color=CORES["azul"], opacity=0.8))
            if "provisao_credito" in df.columns:
                prov_vals = df["provisao_credito"].fillna(0).abs() / 1e9
                fig_ppnr.add_trace(go.Bar(name="Provisão p/ Crédito", x=labels, y=prov_vals.tolist(),
                                          marker_color=CORES["vermelho"], opacity=0.7))
            fig_ppnr.update_layout(
                title=dict(text="PPNR vs Provisao ($B)", font=dict(size=14), x=0, xanchor="left"),
                barmode="group", height=380, margin=dict(t=85, b=30, l=50, r=20),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5, font=dict(size=10)),
                yaxis=dict(gridcolor="#eee"), plot_bgcolor="white",
            )
            st.plotly_chart(fig_ppnr, use_container_width=True)
    elif setor == "Card / Outros":
        with col_g1:
            fig = grafico_barras(df, ["receita_liquida", "ebit", "lucro_liquido"],
                                 ["Receita", "EBIT", "Lucro Líquido"],
                                 [CORES["azul"], CORES["verde"], CORES["laranja"]],
                                 "Receita, EBIT e Lucro Líquido")
            st.plotly_chart(fig, use_container_width=True)
        with col_g2:
            fig = grafico_linhas(df, ["margem_ebit", "margem_liquida", "efficiency_ratio"],
                                 ["Margem EBIT", "Margem Líquida", "Efficiency Ratio"],
                                 [CORES["verde"], CORES["laranja"], CORES["vermelho"]],
                                 "Margens e Eficiencia")
            fig.update_layout(yaxis=dict(tickformat=".0%"))
            st.plotly_chart(fig, use_container_width=True)
    else:  # Asset Manager
        with col_g1:
            fig = grafico_barras(df, ["receita_liquida", "ebitda", "lucro_liquido"],
                                 ["Receita", "EBITDA", "Lucro Líquido"],
                                 [CORES["azul"], CORES["verde"], CORES["laranja"]],
                                 "Receita, EBITDA e Lucro Líquido")
            st.plotly_chart(fig, use_container_width=True)
        with col_g2:
            fig = grafico_linhas(df, ["margem_ebitda", "margem_ebit", "margem_liquida"],
                                 ["Margem EBITDA", "Margem EBIT", "Margem Líquida"],
                                 [CORES["verde"], CORES["azul"], CORES["laranja"]],
                                 "Margens Operacionais")
            fig.update_layout(yaxis=dict(tickformat=".0%"))
            st.plotly_chart(fig, use_container_width=True)

    st.markdown("---")

    # --- 2. Rentabilidade (exceto Banco) ---
    _show_rentab = setor != "Banco"
    if _show_rentab:
        st.header("Rentabilidade e Eficiência")
        col_b1, col_b2 = st.columns(2)
        with col_b1:
            fig = grafico_linhas(df, ["roe", "roa"], ["ROE (anualizado)", "ROA (anualizado)"],
                                 [CORES["azul"], CORES["verde"]], "ROE e ROA")
            fig.update_layout(yaxis=dict(tickformat=".2%"))
            st.plotly_chart(fig, use_container_width=True)
        with col_b2:
            fig_dp = make_subplots(specs=[[{"secondary_y": True}]])
            fig_dp.add_trace(go.Bar(name="ROA", x=labels, y=df["roa"].tolist(),
                                    marker_color=CORES["verde"], opacity=0.7), secondary_y=False)
            fig_dp.add_trace(go.Scatter(name="Equity Multiplier", x=labels,
                                        y=df["equity_multiplier"].tolist(), mode="lines+markers",
                                        line=dict(color=CORES["roxo"], width=3), marker=dict(size=6)),
                             secondary_y=True)
            fig_dp.update_layout(
                title=dict(text="Decomposicao DuPont (ROE = ROA x Eq.Multiplier)", font=dict(size=14), x=0, xanchor="left"),
                height=380, margin=dict(t=85, b=30, l=60, r=60),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5, font=dict(size=10)),
                plot_bgcolor="white",
            )
            fig_dp.update_yaxes(title_text="ROA", tickformat=".2%", gridcolor="#eee", secondary_y=False)
            fig_dp.update_yaxes(title_text="Equity Multiplier (x)", gridcolor="#eee", secondary_y=True)
            st.plotly_chart(fig_dp, use_container_width=True)

        col_b3, col_b4 = st.columns(2)
        if setor in ("Card / Outros", "Banco"):
            with col_b3:
                fig_eff = make_subplots(specs=[[{"secondary_y": True}]])
                fig_eff.add_trace(go.Scatter(name="Efficiency Ratio", x=labels,
                                             y=df["efficiency_ratio"].tolist(), mode="lines+markers",
                                             line=dict(color=CORES["vermelho"], width=3), marker=dict(size=6)),
                                  secondary_y=False)
                if "provision_ratio" in df.columns:
                    fig_eff.add_trace(go.Scatter(name="Custo de Credito/Receita", x=labels,
                                                 y=df["provision_ratio"].tolist(), mode="lines+markers",
                                                 line=dict(color=CORES["laranja"], width=2), marker=dict(size=5)),
                                      secondary_y=True)
                if "marketing_receita" in df.columns and df["marketing_receita"].abs().sum() > 0:
                    fig_eff.add_trace(go.Scatter(name="Card Rewards/Receita", x=labels,
                                                 y=df["marketing_receita"].tolist(), mode="lines+markers",
                                                 line=dict(color=CORES["roxo"], width=2), marker=dict(size=5)),
                                      secondary_y=True)
                fig_eff.update_layout(
                    title=dict(text="Eficiencia, Custo de Credito e Rewards", font=dict(size=14), x=0, xanchor="left"),
                    height=380, margin=dict(t=85, b=30, l=60, r=60),
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5, font=dict(size=10)),
                    plot_bgcolor="white",
                )
                fig_eff.update_yaxes(title_text="Efficiency Ratio", tickformat=".0%", gridcolor="#eee", secondary_y=False)
                fig_eff.update_yaxes(title_text="Provisao / Rewards", tickformat=".2%", gridcolor="#eee", secondary_y=True)
                st.plotly_chart(fig_eff, use_container_width=True)
            with col_b4:
                fig_mix = go.Figure()
                fig_mix.add_trace(go.Bar(name="Receita de Juros", x=labels,
                                         y=df["receita_juros"].fillna(0).tolist() if "receita_juros" in df.columns else []))
                fig_mix.add_trace(go.Bar(name="Receita Não-Juros", x=labels,
                                         y=df["receita_nao_juros"].fillna(0).tolist() if "receita_nao_juros" in df.columns else [],
                                         marker_color=CORES["verde"]))
                fig_mix.update_layout(
                    title=dict(text="Composição da Receita", font=dict(size=14), x=0, xanchor="left"),
                    barmode="stack", height=380, margin=dict(t=85, b=30, l=50, r=20),
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5, font=dict(size=10)),
                    yaxis=dict(gridcolor="#eee"), plot_bgcolor="white",
                )
                st.plotly_chart(fig_mix, use_container_width=True)
        else:  # Asset Manager
            with col_b3:
                fig = grafico_linhas(df, ["margem_ebit", "margem_liquida", "efficiency_ratio"],
                                     ["Margem EBIT", "Margem Líquida", "Efficiency Ratio"],
                                     [CORES["verde"], CORES["laranja"], CORES["vermelho"]],
                                     "Margens e Eficiencia Operacional")
                fig.update_layout(yaxis=dict(tickformat=".0%"))
                st.plotly_chart(fig, use_container_width=True)
            with col_b4:
                fig_rd = go.Figure()
                fig_rd.add_trace(go.Bar(name="Receita", x=labels,
                                        y=df["receita_liquida"].fillna(0).tolist(), marker_color=CORES["azul"], opacity=0.7))
                fig_rd.add_trace(go.Bar(name="Despesas Operacionais", x=labels,
                                        y=df["despesas_operacionais"].fillna(0).abs().tolist(),
                                        marker_color=CORES["vermelho"], opacity=0.7))
                fig_rd.update_layout(
                    title=dict(text="Receita vs Despesas Operacionais", font=dict(size=14), x=0, xanchor="left"),
                    barmode="group", height=380, margin=dict(t=85, b=30, l=50, r=20),
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5, font=dict(size=10)),
                    yaxis=dict(gridcolor="#eee"), plot_bgcolor="white",
                )
                st.plotly_chart(fig_rd, use_container_width=True)

        # Qualidade de Lucros + Crescimento (Card / Banco only)
        if setor in ("Card / Outros", "Banco"):
            col_b5, col_b6 = st.columns(2)
            with col_b5:
                cols_q = []
                nomes_q = []
                if "fco_lucro_ratio" in df.columns and df["fco_lucro_ratio"].notna().any():
                    cols_q.append("fco_lucro_ratio")
                    nomes_q.append("FCO/Lucro (LTM)")
                if "payout" in df.columns:
                    cols_q.append("payout")
                    nomes_q.append("Payout (LTM)")
                if cols_q:
                    fig = grafico_linhas(df, cols_q, nomes_q,
                                         [CORES["azul"], CORES["laranja"]][:len(cols_q)],
                                         "Qualidade de Lucros e Payout")
                    fig.update_layout(yaxis=dict(tickformat=".0%"))
                    st.plotly_chart(fig, use_container_width=True)
            with col_b6:
                cols_g = []
                nomes_g = []
                if "sustainable_growth" in df.columns and df["sustainable_growth"].notna().any():
                    cols_g.append("sustainable_growth")
                    nomes_g.append("Cresc. Sustentável")
                if "receita_yoy" in df.columns:
                    cols_g.append("receita_yoy")
                    nomes_g.append("Receita YoY")
                if "lucro_yoy" in df.columns:
                    cols_g.append("lucro_yoy")
                    nomes_g.append("Lucro YoY")
                if cols_g:
                    fig = grafico_linhas(df, cols_g, nomes_g,
                                         [CORES["verde"], CORES["azul"], CORES["laranja"]][:len(cols_g)],
                                         "Crescimento")
                    fig.update_layout(yaxis=dict(tickformat=".0%"))
                    st.plotly_chart(fig, use_container_width=True)

        st.markdown("---")

    # --- 2b. Banco-specific sections ---
    if setor == "Banco":
        # I. Capital e Solvencia
        st.header("I. Capital e Solvencia")
        tab_cap = formatar_tabela_banco_capital(df)
        display_cap = tab_cap.set_index("Per\u00edodo").T.astype(object)
        formato_cap = {
            "CET1 Ratio": fmt_pct, "Tier 1 Ratio": fmt_pct,
            "Total Capital Ratio": fmt_pct, "Leverage Ratio (SLR)": fmt_pct,
            "RWA ($)": fmt_bilhoes, "RWA Density": fmt_pct,
            "Equity-to-Assets": fmt_pct, "Tangible Book Value": fmt_bilhoes,
        }
        for k, fn in formato_cap.items():
            if k in display_cap.index:
                display_cap.loc[k] = display_cap.loc[k].apply(fn)
        display_cap = _limpar_tabela(display_cap)
        st.dataframe(display_cap, use_container_width=True, height=min(300, 40 + len(display_cap) * 35))

        col_cap1, col_cap2 = st.columns(2)
        with col_cap1:
            fig_cap = go.Figure()
            for col_name, label, cor in [
                ("tier1_ratio", "Tier 1 Ratio", CORES["azul"]),
                ("total_capital_ratio", "Total Capital Ratio", CORES["verde"]),
                ("slr", "SLR", CORES["laranja"]),
            ]:
                if col_name in df.columns and df[col_name].notna().any():
                    fig_cap.add_trace(go.Scatter(name=label, x=labels, y=df[col_name].tolist(),
                                                 mode="lines+markers", line=dict(width=3),
                                                 marker=dict(size=6, color=cor)))
            fig_cap.update_layout(
                title=dict(text="Ratios de Capital Regulatorio", font=dict(size=14), x=0, xanchor="left"),
                height=380, margin=dict(t=85, b=30, l=60, r=20),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5, font=dict(size=10)),
                yaxis=dict(tickformat=".2%", gridcolor="#eee"), plot_bgcolor="white",
            )
            st.plotly_chart(fig_cap, use_container_width=True)
        with col_cap2:
            _has_cet1 = "cet1_ratio" in df.columns and df["cet1_ratio"].notna().any()
            _has_tier1 = "tier1_ratio" in df.columns and df["tier1_ratio"].notna().any()
            if _has_cet1 or _has_tier1:
                cet1_col = "cet1_ratio" if _has_cet1 else "tier1_ratio"
                cet1_label = "CET1 Ratio" if cet1_col == "cet1_ratio" else "Tier 1 Ratio (proxy CET1)"
                fig_cet1 = go.Figure()
                fig_cet1.add_trace(go.Bar(name=cet1_label, x=labels, y=df[cet1_col].tolist(),
                                          marker_color=CORES["azul"],
                                          text=[fmt_pct(v) for v in df[cet1_col]],
                                          textposition="outside", textfont=dict(size=9)))
                fig_cet1.add_hline(y=0.105, line_dash="dash", line_color="red", line_width=2,
                                   annotation_text="Minimo Regulatorio (10.5%)", annotation_position="top left",
                                   annotation_font=dict(size=10, color="red"))
                fig_cet1.update_layout(
                    title=dict(text=f"{cet1_label} - Evolucao QoQ", font=dict(size=14), x=0, xanchor="left"),
                    height=380, margin=dict(t=85, b=30, l=60, r=20),
                    yaxis=dict(tickformat=".2%", gridcolor="#eee", range=[0, max(df[cet1_col].max() * 1.15, 0.16)]),
                    plot_bgcolor="white", showlegend=False,
                )
                st.plotly_chart(fig_cet1, use_container_width=True)

        if "rwa_implied" in df.columns and df["rwa_implied"].notna().any():
            col_rwa1, col_rwa2 = st.columns(2)
            with col_rwa1:
                rwa_b = df["rwa_implied"].fillna(0) / 1e9
                fig_rwa = go.Figure()
                fig_rwa.add_trace(go.Bar(name="RWA", x=labels, y=rwa_b.tolist(), marker_color=CORES["roxo"],
                                         text=[f"${v:.2f}B" for v in rwa_b], textposition="outside", textfont=dict(size=9)))
                fig_rwa.update_layout(
                    title=dict(text="RWA - Evolucao QoQ ($B)", font=dict(size=14), x=0, xanchor="left"),
                    height=380, margin=dict(t=85, b=30, l=50, r=20),
                    yaxis=dict(gridcolor="#eee"), plot_bgcolor="white", showlegend=False,
                )
                st.plotly_chart(fig_rwa, use_container_width=True)
            with col_rwa2:
                if "rwa_density" in df.columns and df["rwa_density"].notna().any():
                    fig_den = grafico_linhas(df, ["rwa_density"], ["RWA Density"],
                                             [CORES["roxo"]], "RWA Density (RWA / Ativo Total)")
                    fig_den.update_layout(yaxis=dict(tickformat=".2%"))
                    st.plotly_chart(fig_den, use_container_width=True)

        st.markdown("---")

        # II. Liquidez e Funding
        st.header("II. Liquidez e Qualidade do Funding")
        tab_liq = formatar_tabela_banco_liquidez(df)
        display_liq = tab_liq.set_index("Per\u00edodo").T.astype(object)
        formato_liq = {
            "Depósitos Totais": fmt_bilhoes, "Depósitos Não-Remunerados": fmt_bilhoes,
            "CASA Ratio": fmt_pct, "Loan-to-Deposit": fmt_pct,
            "LCR": fmt_pct, "NSFR": fmt_pct, "Depósitos YoY": fmt_pct,
        }
        for k, fn in formato_liq.items():
            if k in display_liq.index:
                display_liq.loc[k] = display_liq.loc[k].apply(fn)
        display_liq = _limpar_tabela(display_liq)
        st.dataframe(display_liq, use_container_width=True, height=min(260, 40 + len(display_liq) * 35))

        col_liq1, col_liq2 = st.columns(2)
        with col_liq1:
            fig_dep = go.Figure()
            dep_nib = df["depositos_noninterest_bearing"].fillna(0) if "depositos_noninterest_bearing" in df.columns else pd.Series(0, index=df.index)
            dep_ib_dom = df["depositos_interest_bearing_domestic"].fillna(0) if "depositos_interest_bearing_domestic" in df.columns else pd.Series(0, index=df.index)
            dep_ib_for = df["depositos_interest_bearing_foreign"].fillna(0) if "depositos_interest_bearing_foreign" in df.columns else pd.Series(0, index=df.index)
            fig_dep.add_trace(go.Bar(name="Não-Remunerados", x=labels, y=(dep_nib / 1e9).tolist(), marker_color=CORES["verde"]))
            fig_dep.add_trace(go.Bar(name="IB Doméstico", x=labels, y=(dep_ib_dom / 1e9).tolist(), marker_color=CORES["azul"]))
            fig_dep.add_trace(go.Bar(name="IB Internacional", x=labels, y=(dep_ib_for / 1e9).tolist(), marker_color=CORES["laranja"]))
            fig_dep.update_layout(
                title=dict(text="Composicao dos Depósitos ($B)", font=dict(size=14), x=0, xanchor="left"),
                barmode="stack", height=380, margin=dict(t=85, b=30, l=50, r=20),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5, font=dict(size=10)),
                yaxis=dict(gridcolor="#eee"), plot_bgcolor="white",
            )
            st.plotly_chart(fig_dep, use_container_width=True)
        with col_liq2:
            fig_casa = grafico_linhas(df, ["casa_ratio", "loan_to_deposit"],
                                      ["CASA Ratio", "Loan-to-Deposit"],
                                      [CORES["verde"], CORES["azul"]], "CASA e LDR")
            fig_casa.update_layout(yaxis=dict(tickformat=".2%"))
            st.plotly_chart(fig_casa, use_container_width=True)

        _has_lcr = "lcr" in df.columns and df["lcr"].notna().any()
        _has_nsfr = "nsfr" in df.columns and df["nsfr"].notna().any()
        if _has_lcr or _has_nsfr:
            fig_lcr = make_subplots(specs=[[{"secondary_y": True}]])
            if _has_lcr:
                fig_lcr.add_trace(go.Scatter(name="LCR", x=labels, y=df["lcr"].tolist(),
                                             mode="lines+markers", line=dict(color=CORES["azul"], width=3),
                                             marker=dict(size=6)), secondary_y=False)
            if _has_nsfr:
                fig_lcr.add_trace(go.Scatter(name="NSFR", x=labels, y=df["nsfr"].tolist(),
                                             mode="lines+markers", line=dict(color=CORES["verde"], width=3),
                                             marker=dict(size=6)), secondary_y=False)
            if _has_lcr and _has_nsfr:
                spread_lcr_nsfr = (df["lcr"] - df["nsfr"]).fillna(0)
                fig_lcr.add_trace(go.Bar(name="Spread LCR - NSFR", x=labels, y=spread_lcr_nsfr.tolist(),
                                         marker_color=[CORES["verde"] if v >= 0 else CORES["vermelho"] for v in spread_lcr_nsfr],
                                         opacity=0.3), secondary_y=True)
            fig_lcr.add_hline(y=1.02, line_dash="dash", line_color="red", line_width=1.5,
                              annotation_text="Minimo 100%", annotation_position="bottom left",
                              annotation_font=dict(size=9, color="red"))
            fig_lcr.update_layout(
                title=dict(text="LCR vs NSFR - Liquidez Regulatoria", font=dict(size=14), x=0, xanchor="left"),
                height=400, margin=dict(t=85, b=30, l=60, r=60),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5, font=dict(size=10)),
                plot_bgcolor="white",
            )
            fig_lcr.update_yaxes(title_text="LCR / NSFR", tickformat=".0%", gridcolor="#eee", secondary_y=False)
            fig_lcr.update_yaxes(title_text="Spread", tickformat=".0%", gridcolor="#eee", secondary_y=True, range=[-0.3, 0.3])
            st.plotly_chart(fig_lcr, use_container_width=True)

        st.markdown("---")

        # III. Qualidade de Credito
        st.header("III. Qualidade de Credito e Inadimplencia")
        tab_cred = formatar_tabela_banco_credito(df)
        display_cred = tab_cred.set_index("Per\u00edodo").T.astype(object)
        formato_cred = {
            "Carteira Bruta": fmt_bilhoes, "Loan Growth YoY": fmt_pct,
            "Provisão (ACL)": fmt_bilhoes, "NPL (Nonaccrual)": fmt_bilhoes,
            "NPL Ratio": fmt_pct, "Reserve / Loans": fmt_pct,
            "Coverage (ACL/NPL)": fmt_multiplo, "Texas Ratio": fmt_pct,
            "Provisão (DRE tri)": fmt_bilhoes, "Provision Ratio": fmt_pct,
        }
        for k, fn in formato_cred.items():
            if k in display_cred.index:
                display_cred.loc[k] = display_cred.loc[k].apply(fn)
        display_cred = _limpar_tabela(display_cred)
        st.dataframe(display_cred, use_container_width=True, height=min(340, 40 + len(display_cred) * 35))

        col_cred1, col_cred2 = st.columns(2)
        with col_cred1:
            cols_cred = []
            nomes_cred = []
            if "coverage_ratio" in df.columns and df["coverage_ratio"].notna().any():
                cols_cred.append("coverage_ratio")
                nomes_cred.append("Coverage Ratio (ACL/NPL)")
            if "allowance_to_loans" in df.columns:
                cols_cred.append("allowance_to_loans")
                nomes_cred.append("ACL / Carteira")
            if cols_cred:
                fig_cov = grafico_linhas(df, cols_cred, nomes_cred,
                                         [CORES["azul"], CORES["verde"]][:len(cols_cred)],
                                         "Cobertura de Crédito")
                st.plotly_chart(fig_cov, use_container_width=True)
        with col_cred2:
            if "texas_ratio" in df.columns:
                fig_tx = grafico_linhas(df, ["texas_ratio"], ["Texas Ratio"],
                                        [CORES["vermelho"]], "Texas Ratio")
                fig_tx.update_layout(yaxis=dict(tickformat=".2%"))
                st.plotly_chart(fig_tx, use_container_width=True)

        st.markdown("---")

        # IV. Rentabilidade Bancaria
        st.header("IV. Rentabilidade e Eficiencia Bancaria")
        tab_rent = formatar_tabela_banco_rentabilidade(df)
        display_rent = tab_rent.set_index("Per\u00edodo").T.astype(object)
        formato_rent = {
            "RoTCE (anualizado)": fmt_pct, "ROE (anualizado)": fmt_pct,
            "ROA (anualizado)": fmt_pct, "NIM": fmt_pct,
            "Risk-Adj NIM": fmt_pct, "Asset Yield": fmt_pct,
            "Cost of IB Deposits": fmt_pct, "Cost of All Deposits": fmt_pct,
            "Interest Spread": fmt_pct, "PPNR": fmt_bilhoes,
            "Efficiency Ratio": fmt_pct, "Oper. Leverage YoY": fmt_pct,
            "NCO Ratio (anual.)": fmt_pct, "Provision / NCOs": fmt_multiplo,
            "Payout (LTM)": fmt_pct,
        }
        for k, fn in formato_rent.items():
            if k in display_rent.index:
                display_rent.loc[k] = display_rent.loc[k].apply(fn)
        display_rent = _limpar_tabela(display_rent)
        st.dataframe(display_rent, use_container_width=True, height=min(380, 40 + len(display_rent) * 35))

        col_rent1, col_rent2 = st.columns(2)
        with col_rent1:
            fig_rotce = grafico_linhas(df, ["rotce", "roe", "roa"], ["RoTCE", "ROE", "ROA"],
                                       [CORES["roxo"], CORES["azul"], CORES["verde"]], "Retornos (anualizados)")
            fig_rotce.update_layout(yaxis=dict(tickformat=".2%"))
            st.plotly_chart(fig_rotce, use_container_width=True)
        with col_rent2:
            fig_nim = grafico_linhas(df, ["nim", "risk_adjusted_nim"], ["NIM", "Risk-Adjusted NIM"],
                                     [CORES["azul"], CORES["vermelho"]], "NIM vs Risk-Adjusted NIM")
            fig_nim.update_layout(yaxis=dict(tickformat=".2%"))
            st.plotly_chart(fig_nim, use_container_width=True)

        col_rent3, col_rent4 = st.columns(2)
        with col_rent3:
            if "operating_leverage" in df.columns and df["operating_leverage"].notna().any():
                fig_ol = go.Figure()
                ol_vals = df["operating_leverage"].fillna(0)
                colors = [CORES["verde"] if v >= 0 else CORES["vermelho"] for v in ol_vals]
                fig_ol.add_trace(go.Bar(name="Operating Leverage", x=labels, y=ol_vals.tolist(),
                                        marker_color=colors, text=[fmt_pct(v) for v in ol_vals],
                                        textposition="outside", textfont=dict(size=9)))
                fig_ol.add_hline(y=0, line_color="gray", line_width=1)
                fig_ol.update_layout(
                    title=dict(text="Operating Leverage YoY (Receita% - Opex%)", font=dict(size=14), x=0, xanchor="left"),
                    height=380, margin=dict(t=85, b=30, l=50, r=20),
                    yaxis=dict(tickformat=".2%", gridcolor="#eee"), plot_bgcolor="white", showlegend=False,
                )
                st.plotly_chart(fig_ol, use_container_width=True)
        with col_rent4:
            fig_eff2 = grafico_linhas(df, ["efficiency_ratio"], ["Efficiency Ratio"],
                                      [CORES["vermelho"]], "Efficiency Ratio")
            fig_eff2.update_layout(yaxis=dict(tickformat=".2%"))
            fig_eff2.add_hline(y=0.55, line_dash="dash", line_color="green", line_width=1,
                               annotation_text="Benchmark 55%", annotation_position="top left",
                               annotation_font=dict(size=9, color="green"))
            st.plotly_chart(fig_eff2, use_container_width=True)

        # Cost of Deposits vs Asset Yield
        _has_yield = "asset_yield" in df.columns and df["asset_yield"].notna().any()
        _has_spread = "interest_spread" in df.columns and df["interest_spread"].notna().any()
        if _has_yield or _has_spread:
            col_rent5, col_rent6 = st.columns(2)
            with col_rent5:
                if _has_yield:
                    fig_cy = go.Figure()
                    if "asset_yield" in df.columns:
                        fig_cy.add_trace(go.Scatter(name="Asset Yield", x=labels, y=df["asset_yield"].tolist(),
                                                    mode="lines+markers", line=dict(color=CORES["azul"], width=3), marker=dict(size=6)))
                    if "cost_all_deposits" in df.columns:
                        fig_cy.add_trace(go.Scatter(name="Cost of All Deposits", x=labels, y=df["cost_all_deposits"].tolist(),
                                                    mode="lines+markers", line=dict(color=CORES["vermelho"], width=3), marker=dict(size=6)))
                    if "cost_ib_deposits" in df.columns:
                        fig_cy.add_trace(go.Scatter(name="Cost of IB Deposits", x=labels, y=df["cost_ib_deposits"].tolist(),
                                                    mode="lines+markers", line=dict(color=CORES["laranja"], width=2, dash="dash"), marker=dict(size=4)))
                    fig_cy.update_layout(
                        title=dict(text="Asset Yield vs Cost of Deposits", font=dict(size=14), x=0, xanchor="left"),
                        height=380, margin=dict(t=85, b=30, l=60, r=20),
                        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5, font=dict(size=10)),
                        yaxis=dict(tickformat=".2%", gridcolor="#eee"), plot_bgcolor="white",
                    )
                    st.plotly_chart(fig_cy, use_container_width=True)
            with col_rent6:
                if _has_spread:
                    spread_vals = df["interest_spread"].fillna(0)
                    fig_sp = go.Figure()
                    fig_sp.add_trace(go.Bar(name="Interest Spread", x=labels, y=spread_vals.tolist(),
                                            marker_color=CORES["azul"], text=[fmt_pct(v) for v in spread_vals],
                                            textposition="outside", textfont=dict(size=9)))
                    fig_sp.update_layout(
                        title=dict(text="Interest Spread (Asset Yield - IB Liabilities Rate)", font=dict(size=14), x=0, xanchor="left"),
                        height=380, margin=dict(t=85, b=30, l=50, r=20),
                        yaxis=dict(tickformat=".2%", gridcolor="#eee"), plot_bgcolor="white", showlegend=False,
                    )
                    st.plotly_chart(fig_sp, use_container_width=True)

        st.markdown("---")

    # --- 2c. Asset Manager metrics ---
    dados_am = None
    if setor == "Asset Manager":
        from src.coleta.extrator_asset_manager import extrair_e_salvar_am, carregar_dados_am
        dados_am = carregar_dados_am(pasta)
        if dados_am is None:
            pasta_docs = os.path.join(pasta, "Documentos")
            if os.path.isdir(pasta_docs):
                st.warning(f"⚠️ **GEMINI EM USO** — {ticker}: Extraindo métricas de Asset Manager (FRE/DE/AUM) via Gemini AI. Considere baixar Financial Supplements oficiais do site de RI para dados mais robustos.", icon="🤖")
                with st.spinner("Extraindo metricas de Asset Manager via Gemini..."):
                    dados_am = extrair_e_salvar_am(pasta, ticker)
                if dados_am:
                    st.success(f"✅ Gemini extraiu métricas AM de {ticker} com sucesso.")

        if dados_am and dados_am.get("periodos"):
            st.header("Metricas de Asset Manager")
            periodos_am = dados_am["periodos"]
            df_am = pd.DataFrame(periodos_am)
            df_am["periodo"] = pd.to_datetime(df_am["periodo"])
            df_am = df_am.sort_values("periodo").drop_duplicates(subset=["periodo"], keep="last")
            df_am = df_am.set_index("periodo")

            _ffill_cols = ["gross_debt_corp", "total_aum", "fee_paying_aum", "dry_powder",
                           "permanent_capital_pct", "net_accrued_performance"]
            for _col in _ffill_cols:
                if _col in df_am.columns:
                    df_am[_col] = df_am[_col].ffill()

            df_am["label"] = df_am.apply(
                lambda r: r.get("trimestre", f"Q{(r.name.month-1)//3+1}/{r.name.year%100:02d}"), axis=1)
            df_am = df_am.tail(n_periodos)

            # AM data is in millions — convert to units for fmt_bilhoes
            def _fmt_am(v):
                """Format AM value (in millions) using fmt_bilhoes (expects units)."""
                if v is None or (isinstance(v, float) and pd.isna(v)) or v == 0:
                    return "-"
                return fmt_bilhoes(v * 1e6)

            if not df_am.empty:
                am_labels = df_am["label"].tolist()

                # KPIs AM
                ultimo_am = df_am.iloc[-1]
                col_am1, col_am2, col_am3, col_am4, col_am5 = st.columns(5)
                with col_am1:
                    v = ultimo_am.get("fre")
                    st.metric("FRE", _fmt_am(v) if v else "-")
                with col_am2:
                    v = ultimo_am.get("fre_margin_pct")
                    st.metric("Margem FRE", f"{v:.1f}%" if v else "-")
                with col_am3:
                    v = ultimo_am.get("de")
                    st.metric("Distrib. Earnings", _fmt_am(v) if v else "-")
                with col_am4:
                    v = ultimo_am.get("total_aum")
                    st.metric("AUM Total", _fmt_am(v) if v else "-")
                with col_am5:
                    v = ultimo_am.get("fee_paying_aum")
                    st.metric("Fee-Paying AUM", _fmt_am(v) if v else "-")

                col_am_g1, col_am_g2 = st.columns(2)
                with col_am_g1:
                    fig_fre = go.Figure()
                    if df_am.get("fre") is not None and df_am["fre"].notna().any():
                        fig_fre.add_trace(go.Bar(name="FRE", x=am_labels, y=df_am["fre"].fillna(0).tolist(),
                                                 marker_color=CORES["azul"],
                                                 text=[_fmt_am(v) if v else "" for v in df_am["fre"].fillna(0)],
                                                 textposition="inside", textfont=dict(size=8, color="white")))
                    if df_am.get("sre") is not None and df_am["sre"].notna().any() and df_am["sre"].abs().sum() > 0:
                        fig_fre.add_trace(go.Bar(name="SRE", x=am_labels, y=df_am["sre"].fillna(0).tolist(),
                                                 marker_color=CORES["verde"]))
                    if df_am.get("de") is not None and df_am["de"].notna().any():
                        fig_fre.add_trace(go.Bar(name="Distrib. Earnings", x=am_labels, y=df_am["de"].fillna(0).tolist(),
                                                 marker_color=CORES["laranja"]))
                    fig_fre.update_layout(
                        title=dict(text="FRE, SRE e Distributable Earnings", font=dict(size=14), x=0),
                        barmode="group", height=420, margin=dict(t=85, b=30, l=50, r=20),
                        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5, font=dict(size=10)),
                        yaxis=dict(gridcolor="#eee"), plot_bgcolor="white",
                    )
                    st.plotly_chart(fig_fre, use_container_width=True)

                with col_am_g2:
                    fig_aum = go.Figure()
                    if df_am.get("fee_paying_aum") is not None and df_am["fee_paying_aum"].notna().any():
                        fig_aum.add_trace(go.Bar(name="Fee-Paying AUM", x=am_labels,
                                                 y=(df_am["fee_paying_aum"].fillna(0) / 1e3).tolist(),
                                                 marker_color=CORES["azul"]))
                    if df_am.get("dry_powder") is not None and df_am["dry_powder"].notna().any():
                        fig_aum.add_trace(go.Bar(name="Dry Powder", x=am_labels,
                                                 y=(df_am["dry_powder"].fillna(0) / 1e3).tolist(),
                                                 marker_color=CORES["verde_claro"]))
                    if df_am.get("total_aum") is not None and df_am["total_aum"].notna().any():
                        fig_aum.add_trace(go.Scatter(name="AUM Total", x=am_labels,
                                                     y=(df_am["total_aum"].fillna(0) / 1e3).tolist(),
                                                     mode="lines+markers", line=dict(color=CORES["roxo"], width=3)))
                    fig_aum.update_layout(
                        title=dict(text="AUM, Fee-Paying AUM e Dry Powder", font=dict(size=14), x=0),
                        barmode="stack", height=420, margin=dict(t=85, b=30, l=50, r=20),
                        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5, font=dict(size=10)),
                        yaxis=dict(title="USD Bilhoes", gridcolor="#eee"), plot_bgcolor="white",
                    )
                    st.plotly_chart(fig_aum, use_container_width=True)

                # FRE Margin + Solvencia
                col_am_g3, col_am_g4 = st.columns(2)
                with col_am_g3:
                    fig_mfre = go.Figure()
                    if df_am.get("fre_margin_pct") is not None and df_am["fre_margin_pct"].notna().any():
                        fig_mfre.add_trace(go.Scatter(name="Margem FRE", x=am_labels,
                                                      y=(df_am["fre_margin_pct"].fillna(0) / 100).tolist(),
                                                      mode="lines+markers", line=dict(color=CORES["azul"], width=3), marker=dict(size=6)))
                    if df_am.get("permanent_capital_pct") is not None and df_am["permanent_capital_pct"].notna().any():
                        fig_mfre.add_trace(go.Scatter(name="% Capital Permanente", x=am_labels,
                                                      y=(df_am["permanent_capital_pct"].fillna(0) / 100).tolist(),
                                                      mode="lines+markers", line=dict(color=CORES["verde"], width=2)))
                    fig_mfre.update_layout(
                        title=dict(text="Margem FRE e Capital Permanente", font=dict(size=14), x=0),
                        height=380, margin=dict(t=85, b=30, l=50, r=20),
                        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5, font=dict(size=10)),
                        yaxis=dict(tickformat=".0%", gridcolor="#eee"), plot_bgcolor="white",
                    )
                    st.plotly_chart(fig_mfre, use_container_width=True)

                with col_am_g4:
                    fig_solv = make_subplots(specs=[[{"secondary_y": True}]])
                    # Use XBRL data for solvency (divida_bruta, ebitda_ltm from main df)
                    _has_debt = "divida_bruta" in df.columns and df["divida_bruta"].notna().any()
                    _has_ebitda = "ebitda_ltm" in df.columns and df["ebitda_ltm"].notna().any()
                    fre_vals = df_am.get("fre")
                    if _has_debt and _has_ebitda:
                        debt_bruta = df["divida_bruta"].reindex(df_am.index, method="nearest").fillna(0)
                        ebitda_ltm_vals = df["ebitda_ltm"].reindex(df_am.index, method="nearest")
                        debt_ebitda = debt_bruta / ebitda_ltm_vals.replace(0, float('nan'))
                        fig_solv.add_trace(go.Bar(name="Dív.Bruta/EBITDA (Moody's)", x=am_labels,
                                                  y=debt_ebitda.tolist(), marker_color=CORES["vermelho"], opacity=0.7),
                                           secondary_y=False)
                        if fre_vals is not None and fre_vals.notna().any():
                            fre_ann = fre_vals.fillna(0) * 4 * 1e6  # convert millions to units
                            debt_fre = debt_bruta / fre_ann.replace(0, float('nan'))
                            fig_solv.add_trace(go.Bar(name="Dív.Bruta/FRE (stress)", x=am_labels,
                                                      y=debt_fre.tolist(), marker_color=CORES["laranja"], opacity=0.5),
                                           secondary_y=False)
                        fig_solv.add_hline(y=2.0, line_dash="dot", line_color="green",
                                           annotation_text="A (Moody's <=2x)", secondary_y=False)
                        fig_solv.add_hline(y=3.0, line_dash="dot", line_color="orange",
                                           annotation_text="Baa (<=3x)", secondary_y=False)
                    if _has_ebitda and "interest_coverage_ebitda" in df.columns:
                        cov_vals = df["interest_coverage_ebitda"].reindex(df_am.index, method="nearest")
                        fig_solv.add_trace(go.Scatter(name="EBITDA/Juros (Moody's)", x=am_labels,
                                                      y=cov_vals.tolist(), mode="lines+markers",
                                                      line=dict(color=CORES["azul"], width=3), marker=dict(size=6)),
                                           secondary_y=True)
                    fig_solv.update_layout(
                        title=dict(text="Solvencia (Moody's): Divida/EBITDA e Cobertura de Juros", font=dict(size=14), x=0),
                        barmode="group", height=420, margin=dict(t=85, b=30, l=60, r=60),
                        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5, font=dict(size=9)),
                        plot_bgcolor="white",
                    )
                    fig_solv.update_yaxes(title_text="Divida / Earnings (x)", gridcolor="#eee", secondary_y=False)
                    fig_solv.update_yaxes(title_text="EBITDA / Juros (x)", gridcolor="#eee", secondary_y=True)
                    st.plotly_chart(fig_solv, use_container_width=True)

                # NAPR/Divida + Stress Test
                _debt_bruta_am = df["divida_bruta"].reindex(df_am.index, method="nearest").fillna(0) if "divida_bruta" in df.columns else None
                col_am_g5, col_am_g6 = st.columns(2)
                with col_am_g5:
                    napr_vals = df_am.get("net_accrued_performance")
                    if napr_vals is not None and _debt_bruta_am is not None and napr_vals.notna().any():
                        napr_debt = (napr_vals.fillna(0) * 1e6) / _debt_bruta_am.replace(0, float('nan'))
                        fig_napr = go.Figure()
                        fig_napr.add_trace(go.Bar(name="NAPR / Divida Corp.", x=am_labels,
                                                  y=napr_debt.tolist(), marker_color=CORES["roxo"], opacity=0.8))
                        fig_napr.update_layout(
                            title=dict(text="NAPR / Divida (gordura futura)", font=dict(size=14), x=0),
                            height=380, margin=dict(t=85, b=30, l=50, r=20),
                            yaxis=dict(tickformat=".0%", gridcolor="#eee"), plot_bgcolor="white",
                        )
                        st.plotly_chart(fig_napr, use_container_width=True)
                    else:
                        st.info("NAPR nao disponivel nos earnings releases.")
                with col_am_g6:
                    if fre_vals is not None and _debt_bruta_am is not None:
                        fre_ann_stress = fre_vals.fillna(0) * 4 * 1e6  # millions to units
                        _debt_clean = _debt_bruta_am.fillna(0)
                        anos_pagar = _debt_clean / fre_ann_stress.replace(0, float('nan'))
                        fig_stress = go.Figure()
                        fig_stress.add_trace(go.Bar(
                            name="Anos p/ pagar divida (so FRE)", x=am_labels, y=anos_pagar.tolist(),
                            marker_color=[CORES["verde"] if v <= 3 else (CORES["laranja"] if v <= 5 else CORES["vermelho"])
                                          for v in anos_pagar.fillna(99)],
                        ))
                        fig_stress.add_hline(y=3.0, line_dash="dot", line_color="green", annotation_text="IG (< 3x)")
                        fig_stress.update_layout(
                            title=dict(text="Stress Test: Divida / FRE (perf. fees = 0)", font=dict(size=14), x=0),
                            height=380, margin=dict(t=85, b=30, l=50, r=20),
                            yaxis=dict(title="Anos", gridcolor="#eee"), plot_bgcolor="white", showlegend=False,
                        )
                        st.plotly_chart(fig_stress, use_container_width=True)

                # Tabela completa AM
                with st.expander("Tabela Completa de Metricas AM", expanded=False):
                    COLS_AM = {
                        "label": "Per\u00edodo", "fre": "FRE", "fre_margin_pct": "Margem FRE %",
                        "sre": "SRE", "de": "Distrib. Earnings",
                        "management_fees": "Management Fees", "performance_fees_realized": "Perf. Fees Realiz.",
                        "net_accrued_performance": "NAPR", "total_aum": "AUM Total",
                        "fee_paying_aum": "Fee-Paying AUM", "permanent_capital_pct": "% Cap. Permanente",
                        "dry_powder": "Dry Powder", "compensation_expense": "Compensacao",
                        "interest_expense_corp": "Juros Corp.", "gross_debt_corp": "Dívida Bruta Corp.",
                    }
                    avail_am = [c for c in COLS_AM if c in df_am.columns and df_am[c].notna().any()]
                    if avail_am:
                        tab_am = df_am[avail_am].copy()
                        tab_am.columns = [COLS_AM[c] for c in avail_am]
                        display_am = tab_am.T
                        for row in display_am.index:
                            if row == "Per\u00edodo":
                                continue
                            if "%" in row:
                                display_am.loc[row] = display_am.loc[row].apply(
                                    lambda v: f"{v:.1f}%" if isinstance(v, (int, float)) and not pd.isna(v) else "-")
                            else:
                                display_am.loc[row] = display_am.loc[row].apply(
                                    lambda v: _fmt_am(v) if isinstance(v, (int, float)) and not pd.isna(v) else "-")
                        display_am = _limpar_tabela(display_am)
                        st.dataframe(display_am, use_container_width=True, height=min(500, 40 + len(display_am) * 35))

            st.markdown("---")

    # --- 3. Fluxo de Caixa (exceto Banco) ---
    if setor != "Banco":
        st.header("Fluxo de Caixa")
        tab_fc = fmt_fc_fin(df)
        display_fc = tab_fc.set_index("Per\u00edodo").T.astype(object)
        formato_fc = {
            "FCO": fmt_bilhoes, "FCO/EBITDA": fmt_pct, "Capex": fmt_bilhoes,
            "FCL": fmt_bilhoes, "Juros Pagos": fmt_bilhoes,
            "Amortiz. Dívida": fmt_bilhoes, "Captação": fmt_bilhoes,
            "Dividendos Pagos": fmt_bilhoes, "Recompra de Ações": fmt_bilhoes,
            "FC Financiamento": fmt_bilhoes,
        }
        for k, fn in formato_fc.items():
            if k in display_fc.index:
                display_fc.loc[k] = display_fc.loc[k].apply(fn)
        display_fc = _limpar_tabela(display_fc)
        st.dataframe(display_fc, use_container_width=True, height=min(380, 40 + len(display_fc) * 35))

        fig_fc = grafico_barras(df, ["fco", "capex", "fcl"], ["FCO", "Capex", "FCL"],
                                [CORES["azul"], CORES["vermelho"], CORES["verde"]], "FCO vs Capex vs FCL")
        st.plotly_chart(fig_fc, use_container_width=True)
        st.markdown("---")

    # --- 4. Estrutura de Capital (exceto Banco) ---
    if setor != "Banco":
        st.header("Estrutura de Capital")
        tab_ec = fmt_ec_fin(df)
        display_ec = tab_ec.set_index("Per\u00edodo").T.astype(object)
        formato_ec = {
            "Caixa": fmt_bilhoes, "Depósitos": fmt_bilhoes,
            "Dívida CP": fmt_bilhoes, "Dívida LP": fmt_bilhoes,
            "Dívida Bruta": fmt_bilhoes, "Dívida Líquida": fmt_bilhoes,
            "Patrimônio Líquido": fmt_bilhoes, "Tangible Book Value": fmt_bilhoes,
            "Dív.Líq/EBITDA": fmt_multiplo, "Dív.Líq/FCO": fmt_multiplo,
        }
        for k, fn in formato_ec.items():
            if k in display_ec.index:
                display_ec.loc[k] = display_ec.loc[k].apply(fn)
        display_ec = _limpar_tabela(display_ec)
        st.dataframe(display_ec, use_container_width=True, height=min(380, 40 + len(display_ec) * 35))

        col_d1, col_d2 = st.columns(2)
        with col_d1:
            fig_stack = go.Figure()
            fig_stack.add_trace(go.Bar(name="Dívida CP", x=labels, y=df["emprestimos_cp"].fillna(0).tolist(),
                                       marker_color=CORES["laranja"],
                                       text=[fmt_bilhoes(v) for v in df["emprestimos_cp"].fillna(0)],
                                       textposition="inside", insidetextanchor="middle",
                                       textfont=dict(size=8, color="white")))
            fig_stack.add_trace(go.Bar(name="Dívida LP", x=labels, y=df["emprestimos_lp"].fillna(0).tolist(),
                                       marker_color=CORES["vermelho"],
                                       text=[fmt_bilhoes(v) for v in df["emprestimos_lp"].fillna(0)],
                                       textposition="inside", insidetextanchor="middle",
                                       textfont=dict(size=8, color="white")))
            fig_stack.update_layout(
                title=dict(text="Composição da Dívida (CP + LP)", font=dict(size=14), x=0, xanchor="left"),
                barmode="stack", height=420, margin=dict(t=85, b=30, l=50, r=20),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5, font=dict(size=10)),
                yaxis=dict(gridcolor="#eee"), plot_bgcolor="white",
            )
            st.plotly_chart(fig_stack, use_container_width=True)
        with col_d2:
            fig_br = make_subplots(specs=[[{"secondary_y": True}]])
            fig_br.add_trace(go.Bar(name="Dívida Bruta", x=labels, y=df["divida_bruta"].fillna(0).tolist(),
                                    marker_color=CORES["vermelho"], opacity=0.7), secondary_y=False)
            fig_br.add_trace(go.Scatter(name="Receita Líquida", x=labels, y=df["receita_liquida"].fillna(0).tolist(),
                                        mode="lines+markers", line=dict(color=CORES["azul"], width=3),
                                        marker=dict(size=6)), secondary_y=True)
            fig_br.update_layout(
                title=dict(text="Dívida Bruta vs Receita", font=dict(size=14), x=0, xanchor="left"),
                height=420, margin=dict(t=85, b=30, l=60, r=60),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5, font=dict(size=10)),
                plot_bgcolor="white",
            )
            fig_br.update_yaxes(title_text="Dívida Bruta", gridcolor="#eee", secondary_y=False)
            fig_br.update_yaxes(title_text="Receita Líquida", gridcolor="#eee", secondary_y=True)
            st.plotly_chart(fig_br, use_container_width=True)

        # Divida liquida vs alavancagem
        fig_div = make_subplots(specs=[[{"secondary_y": True}]])
        fig_div.add_trace(go.Bar(name="Dívida Líquida", x=labels, y=df["divida_liquida"].tolist(),
                                  marker_color=[CORES["vermelho"] if v > 0 else CORES["verde"]
                                                for v in df["divida_liquida"].fillna(0)], opacity=0.7),
                           secondary_y=False)
        fig_div.add_trace(go.Scatter(name="Dív.Líq/EBITDA (LTM)", x=labels,
                                      y=df["divida_liq_ebitda"].tolist(), mode="lines+markers",
                                      line=dict(color=CORES["roxo"], width=3), marker=dict(size=8)),
                           secondary_y=True)
        fig_div.update_layout(
            title=dict(text="Dívida Líquida vs Alavancagem", font=dict(size=14)),
            height=420, margin=dict(t=85, b=30, l=60, r=60),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5),
            plot_bgcolor="white",
        )
        fig_div.update_yaxes(title_text="USD", gridcolor="#eee", secondary_y=False)
        fig_div.update_yaxes(title_text="x EBITDA (LTM)", gridcolor="#eee", secondary_y=True)
        st.plotly_chart(fig_div, use_container_width=True)
        st.markdown("---")

    # --- 5. Multiplos (exceto Banco) ---
    if setor != "Banco":
        st.header("Múltiplos e Indicadores")
        tab_mult = fmt_mult_fin(df, setor)
        display_mult = tab_mult.set_index("Per\u00edodo").T.astype(object)
        formato_mult = {
            "ROE (anualizado)": fmt_pct, "ROA (anualizado)": fmt_pct,
            "NIM (anualizado)": fmt_pct, "Efficiency Ratio": fmt_pct,
            "Provision Ratio": fmt_pct,
            "Margem EBIT": fmt_pct, "Margem EBITDA": fmt_pct, "Margem Líquida": fmt_pct,
            "Equity Multiplier": fmt_multiplo, "Spread Alavancagem": fmt_pct,
            "Marketing/Receita": fmt_pct,
            "Dív.Líq/EBITDA": fmt_multiplo, "Dív.Bruta/EBITDA": fmt_multiplo,
            "Dív.Líq/FCO": fmt_multiplo,
            "EBITDA/Desp.Fin (LTM)": fmt_multiplo, "EBITDA/Desp.Fin (5A)": fmt_multiplo,
            "Dív.Total/PL": fmt_multiplo, "Equity-to-Assets": fmt_pct,
            "Estab. Receita (Moody's)": fmt_multiplo,
            "Payout (LTM)": fmt_pct, "Cresc. Sustentável": fmt_pct,
            "FCO/Lucro (LTM)": fmt_multiplo, "Fair P/BV Teórico": fmt_multiplo,
            "Retorno ao Acionista/PL": fmt_pct,
        }
        for k, fn in formato_mult.items():
            if k in display_mult.index:
                display_mult.loc[k] = display_mult.loc[k].apply(fn)
        display_mult = _limpar_tabela(display_mult)
        st.dataframe(display_mult, use_container_width=True, height=min(450, 40 + len(display_mult) * 35))

        if setor in ("Card / Outros", "Banco"):
            col_m1, col_m2 = st.columns(2)
            with col_m1:
                fig = grafico_linhas(df, ["divida_liq_ebitda", "divida_total_pl"],
                                     ["DL/EBITDA", "Dív.Total/PL"],
                                     [CORES["roxo"], CORES["vermelho"]], "Alavancagem")
                st.plotly_chart(fig, use_container_width=True)
            with col_m2:
                fig = grafico_linhas(df, ["payout", "total_shareholder_return_pl"],
                                     ["Payout (LTM)", "Retorno ao Acionista/PL"],
                                     [CORES["azul"], CORES["verde"]], "Retorno ao Acionista")
                fig.update_layout(yaxis=dict(tickformat=".0%"))
                st.plotly_chart(fig, use_container_width=True)

        st.markdown("---")

    # --- 6. Cronograma ---
    st.header("Cronograma de Vencimento da Divida")
    _render_cronograma(df_completo, pasta, ticker, setor, is_admin, n_periodos)

    st.markdown("---")

    # --- 6b. Parecer Tecnico ---
    _render_parecer(pasta, ticker, setor, df_completo, dados_am=dados_am)

    st.markdown("---")

    # --- 7. Glossario ---
    with st.expander("Metodologia e Glossario", expanded=False):
        from src.dashboard.glossario_fin import GLOSSARIO_METODOLOGIA
        st.markdown(GLOSSARIO_METODOLOGIA)


# =========================================================================
# MAIN
# =========================================================================
def main():
    is_admin = st.session_state.get("user_role") == "admin"

    # --- Sidebar ---
    with st.sidebar:
        st.title("Dashboard de Credito Global")
        st.markdown("---")

        ticker_input = st.text_input("Buscar empresa (ticker)", placeholder="ex: OXY, JPM, AXP, BX", key="ticker_input")
        btn_carregar = st.button("Carregar", key="btn_carregar")

        # List companies from both directories
        empresas_lista = _listar_empresas()
        empresas_display = [f"{t} — {nome}" if nome != t else t for t, nome in empresas_lista]
        empresas_tickers = [t for t, _ in empresas_lista]

        ticker_selecionado = ""
        if empresas_lista:
            st.markdown("---")
            sel = st.selectbox("Empresas carregadas", [""] + empresas_display, index=0, key="ticker_select")
            if sel:
                # Extract ticker from display string (format: "TICKER — Nome")
                ticker_selecionado = sel.split(" — ")[0].strip()

            if is_admin:
                with st.expander("Excluir empresa", expanded=False):
                    ticker_excluir = st.selectbox("Selecione", [""] + empresas_tickers, index=0, key="ticker_excluir")
                    if ticker_excluir:
                        st.warning(f"Removera todos os dados de **{ticker_excluir}**.")
                        if st.button("Confirmar exclusao", key="btn_excluir"):
                            import shutil
                            for base in [LOCAL_DATA_BASE_NF, LOCAL_DATA_BASE_FIN, DEPLOY_DATA_DIR]:
                                p = os.path.join(base, ticker_excluir)
                                if os.path.isdir(p):
                                    shutil.rmtree(p)
                            st.success(f"**{ticker_excluir}** excluida.")
                            st.rerun()

        st.markdown("---")
        visao = st.radio("Visao", ["Trimestral", "Anual"], index=0)

        growth_mode = st.radio("Comparacao de crescimento", ["QoQ (sequencial)", "YoY (mesmo trimestre)"], index=0)

        n_periodos = st.slider("Per\u00edodos exibidos", 4, 20, 12)

        st.markdown("---")

        # Auto-detect sector
        _input_upper = ticker_input.strip().upper() if ticker_input else ""
        _select_upper = ticker_selecionado.upper() if ticker_selecionado else ""
        _active_ticker = _input_upper or _select_upper
        _auto_idx = _detectar_setor(_active_ticker) if _active_ticker else 0

        setor = st.radio("Setor", SETORES, index=_auto_idx)

        st.markdown("---")
        st.caption("Fonte: SEC EDGAR + Earnings Release")

    # Determine ticker
    ticker = ""
    if btn_carregar and ticker_input.strip():
        ticker = ticker_input.strip().upper()
    elif ticker_selecionado:
        ticker = ticker_selecionado

    if not ticker:
        st.markdown("# Dashboard de Credito Global")
        st.info(
            "Digite um ticker na barra lateral e clique em **Carregar** para comecar. "
            "O sistema busca automaticamente os dados no SEC EDGAR caso nao estejam disponiveis."
        )
        return

    # Data path based on sector
    pasta = _pasta_empresa(ticker, setor)
    caminho_json = os.path.join(pasta, "Dados_EDGAR", "contas_chave.json")

    if not os.path.exists(caminho_json):
        st.info(f"Dados nao encontrados para **{ticker}**. Buscando no SEC EDGAR...")
        with st.spinner(f"Coletando dados para {ticker}..."):
            try:
                from src.coleta.api_edgar import ColetorEDGAR
                coletor = ColetorEDGAR()
                resultado = coletor.coletar(query=ticker, ano_inicio=2019, pasta_destino=pasta)
                if resultado["n_registros"] > 0:
                    st.success(f"Dados coletados: {resultado['empresa']['title']} ({resultado['n_registros']} registros)")
                    # Download earnings releases
                    try:
                        from src.coleta.downloader_docs import baixar_documentos
                        baixar_documentos(ticker, pasta, desde="2023-01-01")
                    except Exception:
                        pass
                    st.rerun()
                else:
                    st.error(f"Nenhum dado encontrado para **{ticker}**.")
                    return
            except Exception as e:
                st.error(f"Erro: {e}")
                return

    # Calculate indicators based on sector
    caminho_cron = os.path.join(pasta, "Dados_EDGAR", "cronogramas.json")
    cron_path = caminho_cron if os.path.exists(caminho_cron) else None
    caminho_sup = os.path.join(pasta, "Dados_EDGAR", "supplement_data.json")
    sup_path = caminho_sup if os.path.exists(caminho_sup) else None

    if _is_financeira(setor):
        df, alertas_dados = calcular_indicadores_fin(caminho_json, caminho_cronogramas=cron_path, caminho_supplement=sup_path)
    else:
        df, alertas_dados = calcular_indicadores_nf(caminho_json)

    # Reconcile with earnings release
    dados_earnings = carregar_dados_earnings(pasta)
    if dados_earnings is None:
        pasta_docs = os.path.join(pasta, "Documentos")
        if os.path.isdir(pasta_docs) and any(
            f.lower().endswith((".pdf", ".htm", ".html")) and any(kw in f.lower() for kw in ["earning", "press", "release", "ex99", "exhibit99"])
            for f in os.listdir(pasta_docs)
        ):
            st.warning(f"⚠️ **GEMINI EM USO** — {ticker}: Extraindo dados do Earnings Release via Gemini AI. Considere usar Financial Supplements oficiais para dados mais robustos.", icon="🤖")
            with st.spinner("Extraindo dados do Earnings Release via Gemini..."):
                dados_earnings = extrair_e_salvar(pasta, ticker)
            if dados_earnings:
                st.success(f"✅ Gemini extraiu earnings de {ticker} com sucesso. Dados salvos em Dados_Extraidos/dados_earnings.json")
    if dados_earnings:
        if _is_financeira(setor):
            df = reconciliar_fin(df, dados_earnings, alertas_dados)
        else:
            df = reconciliar(df, dados_earnings, alertas_dados)

    # Ratings and RI
    ratings = buscar_ratings(ticker, pasta)
    ri_data = buscar_ri_website(ticker, pasta)

    # Filter by view
    if visao == "Anual":
        df = df[df["trimestre"] == 4].copy()
    df_completo = df.copy()
    df = df.tail(n_periodos)

    if df.empty:
        st.error(f"Nenhum dado disponivel para **{ticker}**.")
        return

    # Company name
    nome_empresa = ""
    try:
        from src.coleta.api_edgar import ColetorEDGAR
        nome_empresa = ColetorEDGAR().buscar_empresa(ticker).get("title", "")
    except Exception:
        pass

    st.markdown(f"# {ticker} — {nome_empresa}" if nome_empresa else f"# {ticker}")
    st.caption(f"Setor: **{setor}**")

    # Data quality alerts (admin only)
    if is_admin and alertas_dados:
        with st.expander(f"Alertas de dados ({len(alertas_dados)})", expanded=False):
            for a in alertas_dados:
                if a["tipo"] in ("inconsistente", "ausente"):
                    st.error(f"**{a['indicador']}**: {a['mensagem']}")
                elif a["tipo"] == "proxy":
                    st.warning(f"**{a['indicador']}**: {a['mensagem']}")
                else:
                    st.info(f"**{a['indicador']}**: {a['mensagem']}")

    # --- KPIs ---
    ultimo = df.iloc[-1]
    if setor == "Nao-Financeira":
        penultimo = df.iloc[-2] if len(df) > 1 else pd.Series()
        is_qoq = growth_mode.startswith("QoQ")
        growth_suffix = "qoq" if is_qoq else "yoy"

        col1, col2, col3, col4, col5, col6, col7 = st.columns(7)
        with col1:
            st.metric("Receita", fmt_bilhoes(ultimo.get("receita_liquida")),
                       fmt_pct(ultimo.get(f"receita_{growth_suffix}")) if not pd.isna(ultimo.get(f"receita_{growth_suffix}")) else None)
        with col2:
            st.metric("EBITDA", fmt_bilhoes(ultimo.get("ebitda")),
                       fmt_pct(ultimo.get("margem_ebitda")) if not pd.isna(ultimo.get("margem_ebitda")) else None)
        with col3:
            st.metric("Lucro Líquido", fmt_bilhoes(ultimo.get("lucro_liquido")))
        with col4:
            st.metric("Dívida Líquida", fmt_bilhoes(ultimo.get("divida_liquida")))
        with col5:
            st.metric("DL/EBITDA", fmt_multiplo(ultimo.get("divida_liq_ebitda")))
        with col6:
            st.metric("Liquidez Corrente", fmt_multiplo(ultimo.get("liquidez_corrente")))
        with col7:
            nota_fl = ultimo.get("fleuriet_nota")
            tipo_fl = ultimo.get("fleuriet_tipo", "")
            st.metric("Nota Fleuriet", f"{nota_fl:.0f}/10" if not pd.isna(nota_fl) else "-")
            if tipo_fl:
                st.caption(f"**{tipo_fl}**")

    elif setor == "Banco":
        col1, col2, col3, col4, col5, col6 = st.columns(6)
        with col1: st.metric("RoTCE", fmt_pct(ultimo.get("rotce")))
        with col2: st.metric("Tier 1", fmt_pct(ultimo.get("tier1_ratio")))
        with col3: st.metric("SLR", fmt_pct(ultimo.get("slr")))
        with col4: st.metric("Efficiency", fmt_pct(ultimo.get("efficiency_ratio")))
        with col5: st.metric("CASA", fmt_pct(ultimo.get("casa_ratio")))
        with col6: st.metric("Coverage", fmt_multiplo(ultimo.get("coverage_ratio")) if not pd.isna(ultimo.get("coverage_ratio")) else "-")

    elif setor == "Card / Outros":
        col1, col2, col3, col4, col5, col6 = st.columns(6)
        with col1: st.metric("Receita", fmt_bilhoes(ultimo.get("receita_liquida")))
        with col2: st.metric("Lucro Líquido", fmt_bilhoes(ultimo.get("lucro_liquido")))
        with col3: st.metric("ROE", fmt_pct(ultimo.get("roe")))
        with col4: st.metric("Efficiency Ratio", fmt_pct(ultimo.get("efficiency_ratio")))
        with col5: st.metric("Provision Ratio", fmt_pct(ultimo.get("provision_ratio")))
        with col6: st.metric("Dívida Líquida", fmt_bilhoes(ultimo.get("divida_liquida")))

    else:  # Asset Manager
        col1, col2, col3, col4, col5, col6 = st.columns(6)
        with col1: st.metric("Receita", fmt_bilhoes(ultimo.get("receita_liquida")))
        with col2: st.metric("EBITDA", fmt_bilhoes(ultimo.get("ebitda")))
        with col3: st.metric("Lucro Líquido", fmt_bilhoes(ultimo.get("lucro_liquido")))
        with col4: st.metric("ROE", fmt_pct(ultimo.get("roe")))
        with col5: st.metric("Margem EBIT", fmt_pct(ultimo.get("margem_ebit")))
        with col6: st.metric("Dívida Líquida", fmt_bilhoes(ultimo.get("divida_liquida")))

    # Ratings
    col_r1, col_r2, col_r3 = st.columns(3)
    with col_r1: st.metric("Moody's", ratings.get("moodys") or "-")
    with col_r2: st.metric("S&P", ratings.get("sp") or "-")
    with col_r3: st.metric("Fitch", ratings.get("fitch") or "-")

    # RI
    ri_url = ri_data.get("ri_url")
    if ri_url:
        st.markdown(f"**Investor Relations:** [{ri_url}]({ri_url})")
    else:
        st.caption("Site de RI nao encontrado.")

    # Edit ratings/RI (admin)
    if is_admin:
        with st.expander("Editar ratings e site de RI", expanded=False):
            col_rm, col_rs, col_rf = st.columns(3)
            with col_rm: input_m = st.text_input("Moody's", value=ratings.get("moodys") or "", key="input_m")
            with col_rs: input_s = st.text_input("S&P", value=ratings.get("sp") or "", key="input_s")
            with col_rf: input_f = st.text_input("Fitch", value=ratings.get("fitch") or "", key="input_f")
            st.markdown("---")
            input_ri = st.text_input("Site de RI", value=ri_data.get("ri_url") or "", key="input_ri")
            if st.button("Salvar", key="btn_salvar"):
                r = {"moodys": input_m.strip() or None, "sp": input_s.strip() or None,
                     "fitch": input_f.strip() or None, "ticker": ticker,
                     "data_consulta": datetime.now().isoformat(), "fonte": "Insercao manual"}
                os.makedirs(pasta, exist_ok=True)
                with open(os.path.join(pasta, "ratings.json"), "w", encoding="utf-8") as f:
                    json.dump(r, f, ensure_ascii=False, indent=2)
                if input_ri.strip():
                    ri = {"ri_url": input_ri.strip(), "ticker": ticker,
                          "data_consulta": datetime.now().isoformat(), "fonte": "manual"}
                    with open(os.path.join(pasta, "ri_website.json"), "w", encoding="utf-8") as f:
                        json.dump(ri, f, ensure_ascii=False, indent=2)
                st.success("Salvo!")
                st.rerun()

    st.markdown("---")

    # --- TABS ---
    tab_quant, tab_quali, tab_atualiz = st.tabs(["Analise Quantitativa", "Analise Qualitativa", "Atualizacoes"])

    with tab_quant:
        if setor == "Nao-Financeira":
            _layout_nao_financeira(df, df_completo, pasta, ticker, setor, is_admin, n_periodos, growth_mode)
        else:
            _layout_financeira(df, df_completo, pasta, ticker, setor, is_admin, n_periodos, visao)

    with tab_quali:
        _render_tab_qualitativa(pasta, ticker, setor, is_admin)

    with tab_atualiz:
        _render_tab_atualizacoes(pasta, ticker, setor, is_admin)


# =========================================================================
# AUTH WRAPPER
# =========================================================================
def app():
    """Entry point with authentication."""
    if st.session_state.get("authenticated", False):
        show_logout()
        if st.session_state.get("user_role") == "admin":
            show_admin_panel()
        main()
        return

    tab_login, tab_register = st.tabs(["Entrar", "Criar Conta"])
    with tab_login:
        authenticated, username, role = show_login()
        if authenticated:
            st.rerun()
    with tab_register:
        show_registration_form()


if __name__ == "__main__":
    app()
