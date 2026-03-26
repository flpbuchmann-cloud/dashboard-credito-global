"""
Dashboard de Crédito Global - Financial Analysis for US-Listed Companies.

Streamlit app that displays financial indicators, multiples, and charts
from data collected via SEC EDGAR API.

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
from src.calculo.indicadores import (
    calcular_indicadores,
    formatar_tabela_dre,
    formatar_tabela_fluxo_caixa,
    formatar_tabela_estrutura_capital,
    formatar_tabela_capital_giro,
    formatar_tabela_multiplos,
    formatar_tabela_fleuriet,
)
from src.dashboard.auth import (
    show_login,
    show_registration_form,
    show_admin_panel,
    show_logout,
)

# Detect deploy vs local
# Deploy: data/empresas/ exists inside repo and local drive doesn't
DEPLOY_DATA_DIR = os.path.join(PROJECT_ROOT, "data", "empresas")
LOCAL_DATA_BASE = "G:/Meu Drive/Análise de Crédito Global"
IS_DEPLOYED = os.path.exists(DEPLOY_DATA_DIR) and not os.path.exists(LOCAL_DATA_BASE)


def _pasta_empresa(ticker: str) -> str:
    """Returns the correct path for the company's data folder (local or deploy)."""
    if IS_DEPLOYED:
        return os.path.join(DEPLOY_DATA_DIR, ticker)
    return os.path.join(LOCAL_DATA_BASE, ticker)


def _listar_empresas_disponiveis() -> list[str]:
    """Lists tickers with data already collected."""
    tickers = set()
    # Check deploy dir
    if os.path.isdir(DEPLOY_DATA_DIR):
        for d in os.listdir(DEPLOY_DATA_DIR):
            contas = os.path.join(DEPLOY_DATA_DIR, d, "Dados_EDGAR", "contas_chave.json")
            if os.path.exists(contas):
                tickers.add(d)
    # Check local dir
    if os.path.isdir(LOCAL_DATA_BASE):
        for d in os.listdir(LOCAL_DATA_BASE):
            contas = os.path.join(LOCAL_DATA_BASE, d, "Dados_EDGAR", "contas_chave.json")
            if os.path.exists(contas):
                tickers.add(d)
    return sorted(tickers)


def _sync_para_deploy(caminho_local: str, ticker: str):
    """
    Copies a locally saved file to the deploy directory (data/empresas/)
    and auto-commits + pushes for the hosted dashboard.
    """
    if IS_DEPLOYED:
        return

    pasta_local = os.path.join(LOCAL_DATA_BASE, ticker)
    try:
        rel = os.path.relpath(caminho_local, pasta_local)
    except ValueError:
        return

    destino = os.path.join(DEPLOY_DATA_DIR, ticker, rel)
    os.makedirs(os.path.dirname(destino), exist_ok=True)

    import shutil
    shutil.copy2(caminho_local, destino)

    # Auto commit + push
    try:
        import subprocess
        subprocess.run(
            ["git", "add", destino],
            cwd=PROJECT_ROOT, capture_output=True, timeout=10,
        )
        subprocess.run(
            ["git", "commit", "-m", f"Sync {ticker}/{rel} from localhost"],
            cwd=PROJECT_ROOT, capture_output=True, timeout=10,
        )
        subprocess.run(
            ["git", "push"],
            cwd=PROJECT_ROOT, capture_output=True, timeout=30,
        )
    except Exception:
        pass


# =========================================================================
# CONFIGURATION
# =========================================================================
st.set_page_config(
    page_title="Dashboard de Crédito Global",
    page_icon="📊",
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
# FORMATTING FUNCTIONS (USD)
# =========================================================================
def fmt_bilhoes(valor):
    """Format value in USD billions."""
    if pd.isna(valor):
        return "-"
    v = valor / 1e9
    if abs(v) >= 1:
        return f"${v:.2f}B"
    return f"${valor / 1e6:.0f}M"


def fmt_milhoes(valor):
    """Format value in USD millions."""
    if pd.isna(valor):
        return "-"
    return f"${valor / 1e6:.0f}M"


def fmt_pct(valor):
    """Format percentage."""
    if pd.isna(valor):
        return "-"
    return f"{valor:.1%}"


def fmt_multiplo(valor):
    """Format multiple (e.g. 2.5x)."""
    if pd.isna(valor):
        return "-"
    return f"{valor:.2f}x"


def estilo_valor(valor, inverter=False):
    """Returns color based on value (positive=green, negative=red)."""
    if pd.isna(valor):
        return ""
    positivo = valor > 0
    if inverter:
        positivo = not positivo
    return "color: #2ca02c" if positivo else "color: #d62728"


def criar_tabela_formatada(df, formato_colunas, titulo=""):
    """Creates table with conditional formatting."""
    display_df = df.copy().reset_index(drop=True)
    if "Período" in display_df.columns:
        display_df = display_df.set_index("Período").T
    elif "label" in display_df.columns:
        display_df = display_df.set_index("label").T
    return display_df


# =========================================================================
# CHARTS
# =========================================================================
def grafico_barras_evolucao(df, colunas, nomes, cores, titulo, formato="bilhoes"):
    """Bar chart with time evolution."""
    fig = go.Figure()
    labels = df["label"].tolist()

    for col, nome, cor in zip(colunas, nomes, cores):
        valores = df[col].tolist()
        if formato == "bilhoes":
            texto = [
                f"${v/1e9:.1f}B" if not pd.isna(v) and abs(v) >= 1e9
                else (f"${v/1e6:.0f}M" if not pd.isna(v) else "")
                for v in valores
            ]
        else:
            texto = [f"{v:.1%}" if not pd.isna(v) else "" for v in valores]

        fig.add_trace(go.Bar(
            name=nome,
            x=labels,
            y=valores,
            marker_color=cor,
            text=texto,
            textposition="outside",
            textfont=dict(size=9),
        ))

    fig.update_layout(
        title=dict(text=titulo, font=dict(size=16)),
        barmode="group",
        height=400,
        margin=dict(t=50, b=30, l=50, r=20),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        yaxis=dict(gridcolor="#eee"),
        plot_bgcolor="white",
    )
    return fig


def grafico_linhas_multiplos(df, colunas, nomes, cores, titulo):
    """Line chart for multiples."""
    fig = go.Figure()
    labels = df["label"].tolist()

    for col, nome, cor in zip(colunas, nomes, cores):
        fig.add_trace(go.Scatter(
            name=nome,
            x=labels,
            y=df[col].tolist(),
            mode="lines+markers",
            line=dict(color=cor, width=2),
            marker=dict(size=6),
        ))

    fig.update_layout(
        title=dict(text=titulo, font=dict(size=16)),
        height=350,
        margin=dict(t=50, b=30, l=50, r=20),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        yaxis=dict(gridcolor="#eee"),
        plot_bgcolor="white",
    )
    return fig


def grafico_margens(df, titulo="Margin Evolution"):
    """Margin line chart."""
    fig = go.Figure()
    labels = df["label"].tolist()

    margens = [
        ("margem_bruta", "Gross Margin", CORES["azul"]),
        ("margem_ebitda", "EBITDA Margin", CORES["verde"]),
        ("margem_liquida", "Net Margin", CORES["laranja"]),
    ]

    for col, nome, cor in margens:
        if col in df.columns:
            fig.add_trace(go.Scatter(
                name=nome,
                x=labels,
                y=df[col].tolist(),
                mode="lines+markers",
                line=dict(color=cor, width=2),
                marker=dict(size=6),
            ))

    fig.update_layout(
        title=dict(text=titulo, font=dict(size=16)),
        height=350,
        margin=dict(t=50, b=30, l=50, r=20),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        yaxis=dict(tickformat=".0%", gridcolor="#eee"),
        plot_bgcolor="white",
    )
    return fig


def grafico_divida_alavancagem(df, titulo="Net Debt vs Leverage"):
    """Combo chart: bars (net debt) + line (ND/EBITDA)."""
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    labels = df["label"].tolist()

    fig.add_trace(
        go.Bar(
            name="Net Debt",
            x=labels,
            y=df["divida_liquida"].tolist(),
            marker_color=[
                CORES["vermelho"] if v > 0 else CORES["verde"]
                for v in df["divida_liquida"].fillna(0)
            ],
            opacity=0.7,
        ),
        secondary_y=False,
    )

    fig.add_trace(
        go.Scatter(
            name="Net Debt/EBITDA (LTM)",
            x=labels,
            y=df["divida_liq_ebitda"].tolist(),
            mode="lines+markers",
            line=dict(color=CORES["roxo"], width=3),
            marker=dict(size=8),
        ),
        secondary_y=True,
    )

    fig.update_layout(
        title=dict(text=titulo, font=dict(size=16)),
        height=400,
        margin=dict(t=50, b=30, l=50, r=50),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        plot_bgcolor="white",
    )
    fig.update_yaxes(title_text="USD", gridcolor="#eee", secondary_y=False)
    fig.update_yaxes(title_text="x EBITDA", gridcolor="#eee", secondary_y=True)
    return fig


def _label_vencimento(k: str) -> str:
    """Converts maturity key to readable label."""
    faixas = {
        "ate_1_ano": "< 1 year", "1_a_2_anos": "1-2 years",
        "2_a_5_anos": "2-5 years", "3_a_5_anos": "3-5 years",
        "acima_5_anos": "> 5 years",
    }
    if k == "longo_prazo":
        return "Long Term"
    return faixas.get(k, k)


def _fmt_valor_barra(v: float) -> str:
    """Format value for bar label."""
    if v >= 1000:
        return f"${v/1000:.1f}B"
    return f"${v:,.0f}M"


def _label_periodo(cronograma: dict) -> str:
    """E.g. 'Q3/24' from data_referencia '2024-09-30'."""
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


def grafico_fluxo_caixa(df, titulo="CFO vs Capex vs FCF"):
    """Bar chart: CFO, Capex, FCF."""
    return grafico_barras_evolucao(
        df,
        colunas=["fco", "capex", "fcl"],
        nomes=["CFO", "Capex", "FCF"],
        cores=[CORES["azul"], CORES["vermelho"], CORES["verde"]],
        titulo=titulo,
    )


# =========================================================================
# DASHBOARD LAYOUT
# =========================================================================
def main():
    # --- Sidebar ---
    with st.sidebar:
        st.title("Dashboard de Crédito Global")
        st.markdown("---")

        # Ticker input for auto-loading
        ticker_input = st.text_input(
            "Search company (ticker)",
            placeholder="e.g. OXY, AAPL, MSFT",
            key="ticker_input",
        )

        col_load, col_status = st.columns([1, 1])
        with col_load:
            btn_carregar = st.button("Load", key="btn_carregar")

        # Previously loaded companies dropdown
        empresas_disponiveis = _listar_empresas_disponiveis()

        if empresas_disponiveis:
            st.markdown("---")
            ticker_selecionado = st.selectbox(
                "Previously loaded",
                options=[""] + empresas_disponiveis,
                index=0,
                key="ticker_select",
            )
        else:
            ticker_selecionado = ""

        st.markdown("---")

        visao = st.radio("View", ["Quarterly", "Annual"], index=0)

        n_periodos = st.slider(
            "Periods to display",
            min_value=4,
            max_value=20,
            value=12,
        )

        st.markdown("---")
        st.caption("Source: SEC EDGAR (XBRL + Filings)")

    # Determine which ticker to use
    ticker = ""
    if btn_carregar and ticker_input.strip():
        ticker = ticker_input.strip().upper()
    elif ticker_selecionado:
        ticker = ticker_selecionado

    if not ticker:
        st.markdown("# Dashboard de Crédito Global")
        st.info(
            "Enter a ticker in the sidebar and click **Load** to start. "
            "The system will automatically fetch data from SEC EDGAR if not already available."
        )
        return

    # Check if data exists, auto-collect if not
    pasta = _pasta_empresa(ticker)
    caminho_json = os.path.join(pasta, "Dados_EDGAR", "contas_chave.json")

    if not os.path.exists(caminho_json):
        # Auto-collect data from SEC EDGAR (works both locally and deployed)
        st.info(f"Data not found for **{ticker}**. Fetching from SEC EDGAR...")
        with st.spinner(f"Collecting data for {ticker}..."):
            try:
                from src.coleta.api_edgar import ColetorEDGAR
                coletor = ColetorEDGAR()
                resultado = coletor.coletar(
                    query=ticker,
                    ano_inicio=2019,
                    pasta_destino=pasta,
                )
                if resultado["n_registros"] > 0:
                    st.success(
                        f"Data collected: {resultado['empresa']['title']} "
                        f"({resultado['n_registros']} records)"
                    )
                    st.rerun()
                else:
                    st.error(f"No data found for ticker **{ticker}**.")
                    return
            except Exception as e:
                st.error(f"Error collecting data: {e}")
                return

    # Load and calculate indicators
    df = calcular_indicadores(caminho_json)

    # Filter by view
    if visao == "Annual":
        df = df[df["trimestre"] == 4].copy()

    # Limit periods
    df = df.tail(n_periodos)

    if df.empty:
        st.error(f"No data available for **{ticker}** with the selected filters.")
        return

    # --- Header ---
    st.markdown(f"# {ticker}")

    # KPIs at top
    ultimo = df.iloc[-1] if not df.empty else pd.Series()
    penultimo = df.iloc[-2] if len(df) > 1 else pd.Series()

    col1, col2, col3, col4, col5, col6, col7 = st.columns(7)
    with col1:
        st.metric(
            "Revenue",
            fmt_bilhoes(ultimo.get("receita_liquida")),
            fmt_pct(ultimo.get("receita_yoy")) if not pd.isna(ultimo.get("receita_yoy")) else None,
        )
    with col2:
        st.metric(
            "EBITDA",
            fmt_bilhoes(ultimo.get("ebitda")),
            fmt_pct(ultimo.get("margem_ebitda")) if not pd.isna(ultimo.get("margem_ebitda")) else None,
        )
    with col3:
        st.metric("Net Income", fmt_bilhoes(ultimo.get("lucro_liquido")))
    with col4:
        st.metric("Net Debt", fmt_bilhoes(ultimo.get("divida_liquida")))
    with col5:
        st.metric("ND/EBITDA", fmt_multiplo(ultimo.get("divida_liq_ebitda")))
    with col6:
        st.metric("Current Ratio", fmt_multiplo(ultimo.get("liquidez_corrente")))
    with col7:
        nota_fl = ultimo.get("fleuriet_nota")
        tipo_fl = ultimo.get("fleuriet_tipo", "")
        st.metric("Fleuriet Score", f"{nota_fl:.0f}/10" if not pd.isna(nota_fl) else "-")
        if tipo_fl:
            st.caption(f"**{tipo_fl}**")

    st.markdown("---")

    # =====================================================================
    # TABS
    # =====================================================================
    tab_quant, tab_quali, tab_atualiz = st.tabs([
        "Quantitative Analysis",
        "Qualitative Analysis",
        "Updates",
    ])

    # --- File paths ---
    pasta_empresa = _pasta_empresa(ticker)
    caminho_quali = os.path.join(pasta_empresa, "analise_qualitativa.md")
    caminho_atualiz = os.path.join(pasta_empresa, "atualizacoes.json")

    # =================================================================
    # TAB: QUALITATIVE ANALYSIS (Markdown editor)
    # =================================================================
    def _slug(texto: str) -> str:
        import re
        slug = texto.lower().strip()
        slug = re.sub(r'[^\w\s-]', '', slug)
        slug = re.sub(r'[\s]+', '-', slug)
        return slug

    def _extrair_titulos(conteudo: str) -> list[tuple[str, str, str]]:
        titulos = []
        for linha in conteudo.split("\n"):
            stripped = linha.strip()
            if stripped.startswith("## "):
                texto = stripped[3:].strip()
                titulos.append(("h2", texto, _slug(texto)))
            elif stripped.startswith("# "):
                texto = stripped[2:].strip()
                titulos.append(("h1", texto, _slug(texto)))
        return titulos

    with tab_quali:
        st.subheader("Qualitative Analysis")

        conteudo_quali = ""
        if os.path.exists(caminho_quali):
            with open(caminho_quali, "r", encoding="utf-8") as f:
                conteudo_quali = f.read()

        is_admin = st.session_state.get("user_role") == "admin"
        if is_admin and not IS_DEPLOYED:
            modo_quali = st.radio(
                "Mode", ["View", "Edit"], horizontal=True, key="modo_quali",
            )
        else:
            modo_quali = "View"

        if modo_quali == "Edit":
            novo_conteudo = st.text_area(
                "Content (Markdown)", value=conteudo_quali, height=500, key="editor_quali",
            )
            if st.button("Save", key="salvar_quali"):
                os.makedirs(os.path.dirname(caminho_quali), exist_ok=True)
                with open(caminho_quali, "w", encoding="utf-8") as f:
                    f.write(novo_conteudo)
                _sync_para_deploy(caminho_quali, ticker)
                st.success("Qualitative analysis saved and synced!")
                st.rerun()
        elif conteudo_quali.strip():
            titulos = _extrair_titulos(conteudo_quali)

            if titulos:
                import json as _json
                titulos_js = _json.dumps([
                    {"nivel": n, "texto": t}
                    for n, t, s in titulos
                ], ensure_ascii=False)

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
                <div id="toc">
                    <p class="title">Table of Contents</p>
                </div>
                <script>
                (function() {{
                    var titulos = {titulos_js};
                    var toc = document.getElementById('toc');

                    function getMainDoc() {{
                        try {{ return window.parent.document; }} catch(e) {{ return null; }}
                    }}

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
            st.info("No qualitative analysis recorded.")

    # =================================================================
    # TAB: UPDATES
    # =================================================================
    with tab_atualiz:
        st.subheader("Updates Log")
        st.caption(
            "Record relevant events: quarterly results, regulatory changes, "
            "guidance, M&A, etc."
        )

        atualizacoes = []
        if os.path.exists(caminho_atualiz):
            with open(caminho_atualiz, "r", encoding="utf-8") as f:
                atualizacoes = json.load(f)

        if not IS_DEPLOYED:
            with st.expander("Add new update", expanded=False):
                with st.form("form_atualizacao", clear_on_submit=True):
                    col_data, col_cat = st.columns([1, 1])
                    with col_data:
                        data_atualiz = st.date_input("Date", value=datetime.now().date())
                    with col_cat:
                        categoria = st.selectbox(
                            "Category",
                            ["Quarterly Results", "Guidance", "Sector / Market",
                             "Regulatory", "M&A", "Rating / Credit", "Other"],
                        )
                    titulo_atualiz = st.text_input("Title")
                    corpo_atualiz = st.text_area(
                        "Description (Markdown)", height=150,
                        placeholder="Describe the event, expected impact, sources...",
                    )
                    submitted = st.form_submit_button("Save update")
                    if submitted and titulo_atualiz.strip():
                        nova = {
                            "data": str(data_atualiz),
                            "categoria": categoria,
                            "titulo": titulo_atualiz.strip(),
                            "corpo": corpo_atualiz.strip(),
                            "criado_em": datetime.now().isoformat(),
                        }
                        atualizacoes.insert(0, nova)
                        os.makedirs(os.path.dirname(caminho_atualiz), exist_ok=True)
                        with open(caminho_atualiz, "w", encoding="utf-8") as f:
                            json.dump(atualizacoes, f, ensure_ascii=False, indent=2)
                        _sync_para_deploy(caminho_atualiz, ticker)
                        st.success("Update recorded and synced!")
                        st.rerun()

        if atualizacoes:
            categorias_existentes = sorted(set(a["categoria"] for a in atualizacoes))
            filtro_cat = st.multiselect(
                "Filter by category", categorias_existentes, default=categorias_existentes,
            )

            for idx, atualiz in enumerate(atualizacoes):
                if atualiz["categoria"] not in filtro_cat:
                    continue

                st.markdown(
                    f"### {atualiz['titulo']}\n"
                    f"**{atualiz['data']}** | {atualiz['categoria']}"
                )
                if atualiz.get("corpo"):
                    st.markdown(atualiz["corpo"])

                if not IS_DEPLOYED:
                    if st.button("Remove", key=f"del_atualiz_{idx}"):
                        atualizacoes.pop(idx)
                        with open(caminho_atualiz, "w", encoding="utf-8") as f:
                            json.dump(atualizacoes, f, ensure_ascii=False, indent=2)
                        _sync_para_deploy(caminho_atualiz, ticker)
                        st.rerun()

                st.markdown("---")
        else:
            st.info("No updates recorded. Use the form above to add one.")

    # =================================================================
    # TAB: QUANTITATIVE ANALYSIS
    # =================================================================
    with tab_quant:

        # =====================================================================
        # 1. INCOME STATEMENT
        # =====================================================================
        st.header("Income Statement")

        tab_dre = formatar_tabela_dre(df)
        display_dre = tab_dre.set_index("Período").T

        formato_rows = {
            "Receita Líquida": fmt_bilhoes,
            "CPV": fmt_bilhoes,
            "Resultado Bruto": fmt_bilhoes,
            "Despesas com Vendas": fmt_bilhoes,
            "Despesas G&A": fmt_bilhoes,
            "EBIT": fmt_bilhoes,
            "D&A": fmt_bilhoes,
            "EBITDA": fmt_bilhoes,
            "Resultado Financeiro": fmt_bilhoes,
            "Receitas Financeiras": fmt_bilhoes,
            "Despesas Financeiras": fmt_bilhoes,
            "Lucro Antes IR": fmt_bilhoes,
            "IR/CSLL": fmt_bilhoes,
            "Lucro Líquido": fmt_bilhoes,
            "Growth YoY": fmt_pct,
            "EBITDA YoY": fmt_pct,
            "Margem Bruta": fmt_pct,
            "Margem EBIT": fmt_pct,
            "Margem EBITDA": fmt_pct,
            "Margem Líquida": fmt_pct,
        }

        for row_name, fmt_fn in formato_rows.items():
            if row_name in display_dre.index:
                display_dre.loc[row_name] = display_dre.loc[row_name].apply(fmt_fn)

        ocultar_dre = [
            "CPV", "Resultado Bruto", "Despesas com Vendas", "Despesas G&A",
            "D&A", "Lucro Antes IR", "IR/CSLL",
        ]
        display_dre = display_dre.drop(
            [r for r in ocultar_dre if r in display_dre.index], axis=0
        )

        st.dataframe(display_dre, use_container_width=True, height=500)

        col_g1, col_g2 = st.columns(2)
        with col_g1:
            fig_receita = grafico_barras_evolucao(
                df,
                ["receita_liquida", "ebitda", "lucro_liquido"],
                ["Revenue", "EBITDA", "Net Income"],
                [CORES["azul"], CORES["verde"], CORES["laranja"]],
                "Revenue, EBITDA & Net Income",
            )
            st.plotly_chart(fig_receita, use_container_width=True)

        with col_g2:
            fig_margens = grafico_margens(df)
            st.plotly_chart(fig_margens, use_container_width=True)

        st.markdown("---")

        # =====================================================================
        # 2. CASH FLOW
        # =====================================================================
        st.header("Cash Flow")

        tab_fc = formatar_tabela_fluxo_caixa(df)
        display_fc = tab_fc.set_index("Período").T

        formato_fc = {
            "FCO": fmt_bilhoes,
            "FCO/EBITDA": fmt_pct,
            "FCO/Receita": fmt_pct,
            "Capex": fmt_bilhoes,
            "Capex/Receita": fmt_pct,
            "FCL": fmt_bilhoes,
            "FCL/Receita": fmt_pct,
            "Juros Pagos": fmt_bilhoes,
            "Amortiz. Dívida": fmt_bilhoes,
            "Captação": fmt_bilhoes,
            "Dividendos Pagos": fmt_bilhoes,
            "FC Financiamento": fmt_bilhoes,
        }
        for row_name, fmt_fn in formato_fc.items():
            if row_name in display_fc.index:
                display_fc.loc[row_name] = display_fc.loc[row_name].apply(fmt_fn)

        st.dataframe(display_fc, use_container_width=True, height=420)

        col_fc1, col_fc2 = st.columns(2)
        with col_fc1:
            fig_fc = grafico_fluxo_caixa(df)
            st.plotly_chart(fig_fc, use_container_width=True)

        with col_fc2:
            fig_fc_pct = grafico_linhas_multiplos(
                df,
                ["fco_receita", "capex_receita", "fcl_receita"],
                ["CFO/Revenue", "Capex/Revenue", "FCF/Revenue"],
                [CORES["azul"], CORES["vermelho"], CORES["verde"]],
                "CFO, Capex & FCF as % of Revenue",
            )
            fig_fc_pct.update_layout(yaxis=dict(tickformat=".0%"))
            st.plotly_chart(fig_fc_pct, use_container_width=True)

        st.markdown("---")

        # =====================================================================
        # 3. CAPITAL STRUCTURE
        # =====================================================================
        st.header("Capital Structure")

        tab_ec = formatar_tabela_estrutura_capital(df)
        display_ec = tab_ec.set_index("Período").T

        formato_ec = {
            "Caixa": fmt_bilhoes,
            "Aplicações Fin. CP": fmt_bilhoes,
            "Liquidez Total": fmt_bilhoes,
            "Dívida CP": fmt_bilhoes,
            "Dívida LP": fmt_bilhoes,
            "Dívida Bruta": fmt_bilhoes,
            "Dívida Líquida": fmt_bilhoes,
            "Patrimônio Líquido": fmt_bilhoes,
            "Dív.Líq/EBITDA": fmt_multiplo,
            "Dív.Líq/FCO": fmt_multiplo,
        }
        for row_name, fmt_fn in formato_ec.items():
            if row_name in display_ec.index:
                display_ec.loc[row_name] = display_ec.loc[row_name].apply(fmt_fn)

        st.dataframe(display_ec, use_container_width=True, height=340)

        fig_divida = grafico_divida_alavancagem(df)
        st.plotly_chart(fig_divida, use_container_width=True)

        st.markdown("---")

        # =====================================================================
        # 4. WORKING CAPITAL
        # =====================================================================
        st.header("Working Capital")

        tab_cg = formatar_tabela_capital_giro(df)
        display_cg = tab_cg.set_index("Período").T

        formato_cg = {
            "Contas a Receber": fmt_bilhoes,
            "Estoques": fmt_bilhoes,
            "Fornecedores": fmt_bilhoes,
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
            fig_cg = grafico_barras_evolucao(
                df,
                ["contas_a_receber", "estoques", "fornecedores"],
                ["Accounts Receivable", "Inventory", "Accounts Payable"],
                [CORES["azul"], CORES["laranja"], CORES["vermelho"]],
                "Working Capital Components",
            )
            st.plotly_chart(fig_cg, use_container_width=True)

        with col_cg2:
            if "ciclo_caixa" in df.columns:
                fig_ciclo = grafico_linhas_multiplos(
                    df,
                    ["dso", "dio", "dpo", "ciclo_caixa"],
                    ["DSO", "DIO", "DPO", "Cash Conversion Cycle"],
                    [CORES["azul"], CORES["laranja"], CORES["vermelho"], CORES["roxo"]],
                    "Cash Conversion Cycle (days)",
                )
                fig_ciclo.update_layout(yaxis=dict(tickformat=".0f"))
                st.plotly_chart(fig_ciclo, use_container_width=True)

        st.markdown("---")

        # =====================================================================
        # 5. LEVERAGE & LIQUIDITY MULTIPLES
        # =====================================================================
        st.header("Leverage & Liquidity Multiples")

        tab_mult = formatar_tabela_multiplos(df)
        display_mult = tab_mult.set_index("Período").T

        formato_mult = {
            "Dív.Líq/EBITDA": fmt_multiplo,
            "Dív.Líq/FCO": fmt_multiplo,
            "EBITDA/Desp.Fin (LTM)": fmt_multiplo,
            "EBIT/Desp.Fin (LTM)": fmt_multiplo,
            "DSCR": fmt_multiplo,
            "Equity Multiplier": fmt_multiplo,
            "Debt-to-Assets": fmt_pct,
            "Dív.CP / Dív.Total": fmt_pct,
            "Liquidez Corrente": fmt_multiplo,
            "Liquidez Seca": fmt_multiplo,
            "Cash Ratio": fmt_multiplo,
            "Solvência Geral": fmt_multiplo,
            "Dív.Total / PL": fmt_multiplo,
            "Custo da Dívida": fmt_pct,
            "Capex/EBITDA (LTM)": fmt_pct,
            "Payout (LTM)": fmt_pct,
        }
        for row_name, fmt_fn in formato_mult.items():
            if row_name in display_mult.index:
                display_mult.loc[row_name] = display_mult.loc[row_name].apply(fmt_fn)

        st.dataframe(display_mult, use_container_width=True, height=500)

        col_m1, col_m2 = st.columns(2)
        with col_m1:
            fig_liq = grafico_linhas_multiplos(
                df,
                ["liquidez_corrente", "liquidez_seca", "cash_ratio"],
                ["Current Ratio", "Quick Ratio", "Cash Ratio"],
                [CORES["azul"], CORES["laranja"], CORES["verde"]],
                "Liquidity",
            )
            st.plotly_chart(fig_liq, use_container_width=True)

        with col_m2:
            fig_alav = grafico_linhas_multiplos(
                df,
                ["divida_liq_ebitda", "divida_total_pl", "interest_coverage_ebitda"],
                ["ND/EBITDA", "Total Debt/Equity", "EBITDA/Interest"],
                [CORES["roxo"], CORES["vermelho"], CORES["azul"]],
                "Leverage & Interest Coverage",
            )
            st.plotly_chart(fig_alav, use_container_width=True)

        col_m3, col_m4 = st.columns(2)
        with col_m3:
            fig_solv = grafico_linhas_multiplos(
                df,
                ["solvencia"],
                ["Solvency (Total Assets / Total Liabilities)"],
                [CORES["azul"]],
                "Solvency Evolution",
            )
            st.plotly_chart(fig_solv, use_container_width=True)

        with col_m4:
            fig_custo = grafico_linhas_multiplos(
                df,
                ["custo_divida"],
                ["Cost of Debt (|Interest Exp.| LTM / Gross Debt)"],
                [CORES["vermelho"]],
                "Cost of Debt Evolution",
            )
            fig_custo.update_layout(yaxis=dict(tickformat=".1%"))
            st.plotly_chart(fig_custo, use_container_width=True)

        st.markdown("---")

        # =====================================================================
        # 5b. FLEURIET MODEL (Dynamic Working Capital Analysis)
        # =====================================================================
        st.header("Fleuriet Model - Dynamic Analysis")

        tab_fleuriet = formatar_tabela_fleuriet(df)
        display_fl = tab_fleuriet.set_index("Período").T

        formato_fl = {
            "CDG (Capital de Giro)": fmt_bilhoes,
            "NCG (Nec. Capital de Giro)": fmt_bilhoes,
            "Saldo de Tesouraria (T)": fmt_bilhoes,
            "CDG / NCG": fmt_multiplo,
            "T / Receita": fmt_pct,
            "Nota Fleuriet": lambda v: f"{v:.0f}/10" if not pd.isna(v) else "-",
        }
        for row_name, fmt_fn in formato_fl.items():
            if row_name in display_fl.index:
                display_fl.loc[row_name] = display_fl.loc[row_name].apply(fmt_fn)

        st.dataframe(display_fl, use_container_width=True, height=320)

        col_fl_g1, col_fl_g2 = st.columns(2)
        with col_fl_g1:
            fig_fleuriet = grafico_barras_evolucao(
                df,
                ["fleuriet_cdg", "fleuriet_ncg", "fleuriet_t"],
                ["CDG (Working Capital)", "NCG (WC Requirement)", "Treasury Balance (T)"],
                [CORES["azul"], CORES["laranja"], CORES["verde"]],
                "CDG, NCG & Treasury Balance",
            )
            st.plotly_chart(fig_fleuriet, use_container_width=True)

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
                x=labels,
                y=notas,
                marker_color=cores_nota,
                text=[f"{n:.0f} - {t}" if not pd.isna(n) else "" for n, t in zip(notas, tipos)],
                textposition="outside",
                textfont=dict(size=9),
            ))
            fig_nota.update_layout(
                title=dict(text="Fleuriet Score Evolution (1-10)", font=dict(size=16)),
                height=400,
                margin=dict(t=50, b=30, l=50, r=20),
                yaxis=dict(range=[0, 11], dtick=1, gridcolor="#eee"),
                plot_bgcolor="white",
                showlegend=False,
            )
            fig_nota.add_hrect(y0=7.5, y1=10.5, fillcolor="green", opacity=0.05, line_width=0)
            fig_nota.add_hrect(y0=5.5, y1=7.5, fillcolor="blue", opacity=0.05, line_width=0)
            fig_nota.add_hrect(y0=3.5, y1=5.5, fillcolor="orange", opacity=0.05, line_width=0)
            fig_nota.add_hrect(y0=0, y1=3.5, fillcolor="red", opacity=0.05, line_width=0)
            st.plotly_chart(fig_nota, use_container_width=True)

        st.markdown("---")

        # =====================================================================
        # 6. DEBT MATURITY SCHEDULE
        # =====================================================================
        st.header("Debt Maturity Schedule")

        caminho_cronogramas = os.path.join(pasta_empresa, "Dados_EDGAR", "cronogramas.json")

        cronogramas = []
        if os.path.exists(caminho_cronogramas):
            with open(caminho_cronogramas, "r", encoding="utf-8") as f:
                cronogramas = json.load(f)

        # Manual cronograma input (admin, localhost only)
        is_admin_cron = st.session_state.get("user_role") == "admin"

        if is_admin_cron and not IS_DEPLOYED:
            with st.expander("Insert/Edit maturity schedule manually", expanded=False):
                st.caption(
                    "Use when the schedule cannot be extracted automatically. "
                    "Values in **USD millions**."
                )
                col_ref, col_caixa = st.columns(2)
                with col_ref:
                    data_ref_input = st.text_input(
                        "Reference date (YYYY-MM-DD)",
                        value="2025-12-31",
                        key="cron_data_ref",
                    )
                with col_caixa:
                    caixa_input = st.number_input(
                        "Cash ($M)", value=0.0, step=100.0, key="cron_caixa"
                    )

                st.markdown("**Maturities by year** (fill in relevant years):")
                ano_base = int(data_ref_input[:4]) + 1 if len(data_ref_input) >= 4 else 2026
                cols_anos = st.columns(5)
                venc_inputs = {}
                for j in range(10):
                    ano = ano_base + j
                    with cols_anos[j % 5]:
                        val = st.number_input(
                            f"{ano}", value=0.0, step=100.0,
                            key=f"cron_{ano}", min_value=0.0,
                        )
                        if val > 0:
                            venc_inputs[str(ano)] = val

                arquivo_input = st.text_input(
                    "Source (e.g. 10-K 2024 p.27)",
                    value="Manual input",
                    key="cron_arquivo",
                )

                if st.button("Save schedule", key="btn_salvar_cron"):
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
                        os.makedirs(os.path.dirname(caminho_cronogramas), exist_ok=True)
                        with open(caminho_cronogramas, "w", encoding="utf-8") as f:
                            json.dump(cronogramas, f, ensure_ascii=False, indent=2, default=str)
                        _sync_para_deploy(caminho_cronogramas, ticker)
                        st.success(f"Schedule {data_ref_input} saved and synced!")
                        st.rerun()
                    else:
                        st.warning("Fill in at least one maturity year.")

        if cronogramas:
            recentes = sorted(cronogramas, key=lambda c: c.get("data_referencia", ""), reverse=True)[:3]

            # Override cash from PDF with API value (more reliable)
            for cronograma in recentes:
                dr = cronograma.get("data_referencia", "")
                if dr and "caixa" in df.columns:
                    match = df[df.index == pd.Timestamp(dr)]
                    if not match.empty and not pd.isna(match["caixa"].iloc[0]):
                        cronograma["caixa"] = match["caixa"].iloc[0]

            cor_caixa = "#5b9bd5"
            cor_vencimento = "#c0504d"
            N_ANOS = 5

            for idx, cronograma in enumerate(recentes):
                label = _label_periodo(cronograma)
                sufixo = " (Most Recent)" if idx == 0 else ""
                vencimentos = cronograma.get("vencimentos", {})
                caixa = cronograma.get("caixa") or 0

                dr = cronograma.get("data_referencia", "")
                if dr:
                    ano_ref = int(dr.split("-")[0])
                else:
                    ano_ref = 2025
                primeiro_ano = ano_ref + 1

                anos_numericos = {}
                valor_lp = 0
                tem_faixas = False
                for k, v in vencimentos.items():
                    if k in ("longo_prazo", "acima_5_anos"):
                        valor_lp += v
                    elif k.startswith("ate_") or k.endswith("_anos"):
                        tem_faixas = True
                    else:
                        try:
                            ano = int(k)
                            if ano >= primeiro_ano:
                                anos_numericos[ano] = v
                        except ValueError:
                            pass

                if tem_faixas:
                    chaves_faixa = []
                    for k in ["ate_1_ano", "1_a_2_anos", "2_a_5_anos", "3_a_5_anos", "acima_5_anos"]:
                        if k in vencimentos:
                            chaves_faixa.append(k)
                    bar_labels = ["Cash"] + [_label_vencimento(k) for k in chaves_faixa]
                    bar_valores = [caixa / 1e6] + [vencimentos[k] / 1e6 for k in chaves_faixa]
                else:
                    anos_futuros = sorted(anos_numericos.keys())
                    anos_individuais = anos_futuros[:N_ANOS - 1]
                    anos_acumulados = anos_futuros[N_ANOS - 1:]

                    bar_labels = ["Cash"]
                    bar_valores = [caixa / 1e6]

                    for ano in anos_individuais:
                        bar_labels.append(str(ano))
                        bar_valores.append(anos_numericos[ano] / 1e6)

                    if anos_acumulados or valor_lp > 0:
                        acum = sum(anos_numericos[a] for a in anos_acumulados) + valor_lp
                        ultimo_ano_ind = anos_acumulados[0] if anos_acumulados else (anos_individuais[-1] + 1 if anos_individuais else primeiro_ano)
                        bar_labels.append(f"{ultimo_ano_ind}+")
                        bar_valores.append(acum / 1e6)

                cores = [cor_caixa] + [cor_vencimento] * (len(bar_labels) - 1)

                textos = []
                for v in bar_valores:
                    if v >= 1000:
                        textos.append(f"${v/1000:.1f}B")
                    else:
                        textos.append(f"${v:,.0f}M")

                fig = go.Figure(go.Bar(
                    x=bar_labels,
                    y=bar_valores,
                    marker_color=cores,
                    text=textos,
                    textposition="outside",
                    textfont=dict(size=12),
                    width=0.6,
                ))

                max_val = max(bar_valores) if bar_valores else 0
                fig.update_layout(
                    title=dict(text=f"Position at {label}{sufixo}", font=dict(size=15)),
                    height=350,
                    margin=dict(t=50, b=30, l=60, r=20),
                    plot_bgcolor="white",
                    xaxis=dict(type="category"),
                    yaxis=dict(title="USD Millions", gridcolor="#eee", range=[0, max_val * 1.3]),
                    showlegend=False,
                )

                st.plotly_chart(fig, use_container_width=True, key=f"amort_{idx}")

        else:
            st.info(
                "No maturity schedule available. Use the manual input form above "
                "or run the collector with `--apenas-cronograma`."
            )

        st.markdown("---")

        # =====================================================================
        # 7. METHODOLOGY
        # =====================================================================
        with st.expander("Methodology & Glossary", expanded=False):

            st.markdown("""
### How to Read This Dashboard

This dashboard shows a company's financial health from a **credit** perspective --
i.e., whether the company can service its debts. Data comes from SEC EDGAR
(official financial statements via XBRL API).

All values are **quarterly** (isolated, not cumulative) unless marked "LTM"
(Last Twelve Months = sum of last 4 quarters).

---

### 1. Income Statement

| Indicator | What it is | Why it matters |
|---|---|---|
| **Revenue** | Total sales, net of returns and discounts. | Starting point -- if revenue falls, everything else tends to worsen. |
| **Gross Profit** | Revenue minus COGS. | Shows if the core business is profitable. |
| **EBIT** | Operating income -- before interest and taxes. | Measures pure operational efficiency. |
| **EBITDA** | EBIT + D&A. "Cash" operating profit. | Primary metric used by creditors. |
| **Net Income** | Bottom line after all expenses. | Final result for shareholders. |

**Margins** = indicators above divided by revenue (as %).

**Growth YoY** = change vs same quarter prior year.

---

### 2. Cash Flow

| Indicator | What it is | Why it matters |
|---|---|---|
| **CFO** | Cash from operations. | Positive and consistent = self-sustaining business. |
| **Capex** | Capital expenditures (negative). | Investment in growth or maintenance. |
| **FCF** | CFO + Capex. Free cash flow. | Positive = cash available for debt service and dividends. |
| **CFO/EBITDA** | Cash conversion. | Near 100% = EBITDA is turning into real cash. |

---

### 3. Capital Structure

| Indicator | What it is | Reference |
|---|---|---|
| **Net Debt/EBITDA** | Years of EBITDA to pay off debt. | < 2x: comfortable. > 3.5x: high risk. |
| **Interest Coverage** | EBITDA / Interest Expense. | > 3x: healthy. < 1.5x: distressed. |
| **Current Ratio** | Current Assets / Current Liabilities. | > 1x: can cover short-term obligations. |
| **Cash Ratio** | Cash / Current Liabilities. | Conservative liquidity measure. |

---

### 4. Fleuriet Model (1-10 Score)

Dynamic working capital analysis. Combines CDG (Working Capital), NCG (WC Requirement)
and T (Treasury Balance) signals and magnitudes into a 1-10 score.

| Score | Classification | Meaning |
|:---:|:---|:---|
| **10** | Excellent | CDG+, NCG-, T+ strong. Ideal structure with ample buffer. |
| **8-9** | Solid | CDG+, NCG+, T+ with good coverage. |
| **6-7** | Adequate | CDG+, NCG+, T+ with fair coverage. |
| **4-5** | Unsatisfactory | Treasury deficit or unstable structure. |
| **1-3** | Critical | Severe structural deficit. Insolvency risk. |

---

### Data Source

- **Structured data (IS, BS, CF):** SEC EDGAR XBRL Company Facts API
- **Maturity schedule:** Extracted from 10-K/10-Q filings
- **Periodicity:** Annual (10-K) mapped as DFP
- **Currency:** USD
            """)


def app():
    """Entry point with authentication."""
    if st.session_state.get("authenticated", False):
        show_logout()
        if st.session_state.get("user_role") == "admin":
            show_admin_panel()
        main()
        return

    tab_login, tab_register = st.tabs(["Sign In", "Create Account"])
    with tab_login:
        authenticated, username, role = show_login()
        if authenticated:
            st.rerun()
    with tab_register:
        show_registration_form()


if __name__ == "__main__":
    app()
