"""
Coletor de dados financeiros via SEC EDGAR.

Usa a API XBRL Company Facts para obter dados estruturados
de empresas com filings nos EUA (10-K, 10-Q).

Uso:
    from src.coleta.api_edgar import ColetorEDGAR
    c = ColetorEDGAR()
    c.coletar("AAPL", ano_inicio=2021)
"""

import os
import json
import time
import requests
from datetime import datetime, timedelta
from .tag_mapping import (
    DRE_TAGS, BPA_TAGS, BPP_TAGS, DFC_TAGS, resolve_tag
)


USER_AGENT = "DashboardCredito/1.0 (contact: flpbuchmann@gmail.com)"
EDGAR_BASE = "https://data.sec.gov"
TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"

# Cache de 7 dias para company facts
CACHE_MAX_AGE = 7 * 24 * 3600


class ColetorEDGAR:
    """Coletor de dados financeiros via SEC EDGAR XBRL API."""

    def __init__(self, cache_dir: str = "data/raw/edgar_api"):
        self.cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})
        self._last_request = 0
        self._tickers_cache = None

    def _log(self, msg: str):
        print(f"[EDGAR] {msg}")

    def _rate_limit(self):
        """SEC requires max 10 req/s."""
        elapsed = time.time() - self._last_request
        if elapsed < 0.12:
            time.sleep(0.12 - elapsed)
        self._last_request = time.time()

    # ------------------------------------------------------------------
    # Company Search
    # ------------------------------------------------------------------

    def _carregar_tickers(self) -> dict:
        """Carrega lista de tickers da SEC (cache em memória)."""
        if self._tickers_cache:
            return self._tickers_cache

        cache_path = os.path.join(self.cache_dir, "company_tickers.json")
        if os.path.exists(cache_path):
            age = time.time() - os.path.getmtime(cache_path)
            if age < CACHE_MAX_AGE:
                with open(cache_path, "r") as f:
                    self._tickers_cache = json.load(f)
                return self._tickers_cache

        self._rate_limit()
        resp = self.session.get(TICKERS_URL, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        with open(cache_path, "w") as f:
            json.dump(data, f)
        self._tickers_cache = data
        return data

    def buscar_empresa(self, query: str) -> dict:
        """
        Busca empresa por ticker ou nome.

        Returns:
            {"cik": "0001318605", "ticker": "TSLA", "title": "Tesla, Inc."}
        """
        tickers = self._carregar_tickers()
        query_upper = query.upper().strip()

        # Busca por ticker exato
        for entry in tickers.values():
            if entry.get("ticker", "").upper() == query_upper:
                cik = str(entry["cik_str"]).zfill(10)
                return {
                    "cik": cik,
                    "ticker": entry["ticker"],
                    "title": entry["title"],
                }

        # Busca por nome (parcial)
        for entry in tickers.values():
            if query_upper in entry.get("title", "").upper():
                cik = str(entry["cik_str"]).zfill(10)
                return {
                    "cik": cik,
                    "ticker": entry["ticker"],
                    "title": entry["title"],
                }

        raise ValueError(f"Empresa não encontrada: {query}")

    # ------------------------------------------------------------------
    # Company Facts (XBRL)
    # ------------------------------------------------------------------

    def obter_company_facts(self, cik: str) -> dict:
        """Obtém todos os fatos XBRL de uma empresa (com cache)."""
        cache_path = os.path.join(self.cache_dir, f"CIK{cik}.json")

        if os.path.exists(cache_path):
            age = time.time() - os.path.getmtime(cache_path)
            if age < CACHE_MAX_AGE:
                self._log(f"Usando cache: {os.path.basename(cache_path)}")
                with open(cache_path, "r") as f:
                    return json.load(f)

        url = f"{EDGAR_BASE}/api/xbrl/companyfacts/CIK{cik}.json"
        self._log(f"Baixando company facts: {url}")
        self._rate_limit()
        resp = self.session.get(url, timeout=60)
        resp.raise_for_status()
        data = resp.json()

        with open(cache_path, "w") as f:
            json.dump(data, f)

        return data

    # ------------------------------------------------------------------
    # Submissions (filing history)
    # ------------------------------------------------------------------

    def obter_submissions(self, cik: str) -> dict:
        """Obtém histórico de filings."""
        url = f"{EDGAR_BASE}/submissions/CIK{cik}.json"
        self._rate_limit()
        resp = self.session.get(url, timeout=30)
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # Extract contas_chave
    # ------------------------------------------------------------------

    def _descobrir_periodos(self, facts: dict, ano_inicio: int) -> list[dict]:
        """
        Descobre os períodos disponíveis a partir dos facts.

        Returns:
            Lista de {"end": "2023-12-31", "form": "10-K", "fp": "FY", "fy": 2023}
        """
        usgaap = facts.get("facts", {}).get("us-gaap", {})

        # Usar Assets (quase sempre presente) para descobrir períodos
        periodos = set()
        for tag in ["Assets", "Revenues", "NetIncomeLoss", "CashAndCashEquivalentsAtCarryingValue"]:
            tag_data = usgaap.get(tag, {})
            for unit_data in tag_data.get("units", {}).values():
                for entry in unit_data:
                    fy = entry.get("fy", 0)
                    if fy < ano_inicio:
                        continue
                    form = entry.get("form", "")
                    if form not in ("10-K", "10-Q", "10-K/A", "10-Q/A"):
                        continue
                    fp = entry.get("fp", "")
                    end = entry.get("end", "")
                    start = entry.get("start", "")
                    if end:
                        periodos.add((end, form.replace("/A", ""), fp, fy, start))

        # Deduplicate: para cada (end, form), pegar o mais completo
        por_end_form = {}
        for end, form, fp, fy, start in periodos:
            key = (end, form)
            if key not in por_end_form:
                por_end_form[key] = {"end": end, "form": form, "fp": fp, "fy": fy, "start": start}

        resultado = sorted(por_end_form.values(), key=lambda x: x["end"])
        return resultado

    def extrair_contas_chave(self, facts: dict, ano_inicio: int = 2021) -> list[dict]:
        """
        Transforma XBRL company facts em contas_chave.json.

        Returns:
            Lista de dicts no formato {"periodo", "tipo", "ano", "contas"}
        """
        usgaap = facts.get("facts", {}).get("us-gaap", {})
        periodos = self._descobrir_periodos(facts, ano_inicio)

        entries = []

        for p in periodos:
            end = p["end"]
            form = p["form"]
            fp = p["fp"]
            fy = p["fy"]
            start = p.get("start", "")
            ano = int(end[:4])

            # Determinar tipo (equivalente ao CVM ITR/DFP)
            if form == "10-K":
                prefix = "DFP"
            else:
                prefix = "ITR"

            # ---- DRE ----
            dre = {}
            for conta, tags in DRE_TAGS.items():
                val = resolve_tag(usgaap, tags, form, end, start)
                dre[conta] = val * 1.0 if val is not None else 0.0

            # Calcular resultado_bruto se não disponível
            if dre.get("resultado_bruto", 0) == 0 and dre.get("receita_liquida", 0) != 0:
                dre["resultado_bruto"] = dre["receita_liquida"] + dre.get("custo", 0)

            # Calcular despesas_operacionais
            dre["despesas_operacionais"] = (
                dre.get("despesas_vendas", 0) + dre.get("despesas_ga", 0)
            )
            dre["resultado_equivalencia"] = 0.0

            if dre.get("receita_liquida", 0) != 0:
                entries.append({
                    "periodo": end,
                    "tipo": f"{prefix}_dre",
                    "ano": ano,
                    "contas": dre,
                })

            # ---- BPA (Assets) ----
            bpa = {}
            for conta, tags in BPA_TAGS.items():
                val = resolve_tag(usgaap, tags, form, end)
                bpa[conta] = val * 1.0 if val is not None else 0.0

            # Se ativo_nao_circulante = 0, calcular como ativo_total - ativo_circulante
            if bpa.get("ativo_nao_circulante", 0) == 0 and bpa.get("ativo_total", 0) > 0:
                bpa["ativo_nao_circulante"] = bpa["ativo_total"] - bpa.get("ativo_circulante", 0)

            if bpa.get("ativo_total", 0) != 0:
                entries.append({
                    "periodo": end,
                    "tipo": f"{prefix}_bpa",
                    "ano": ano,
                    "contas": bpa,
                })

            # ---- BPP (Liabilities + Equity) ----
            bpp = {}
            for conta, tags in BPP_TAGS.items():
                val = resolve_tag(usgaap, tags, form, end)
                bpp[conta] = val * 1.0 if val is not None else 0.0

            # passivo_total = ativo_total (balanço fecha)
            bpp["passivo_total"] = bpa.get("ativo_total", 0)

            # Se passivo_nao_circulante = 0, calcular
            if bpp.get("passivo_nao_circulante", 0) == 0 and bpp["passivo_total"] > 0:
                bpp["passivo_nao_circulante"] = (
                    bpp["passivo_total"]
                    - bpp.get("passivo_circulante", 0)
                    - bpp.get("patrimonio_liquido", 0)
                )

            bpp["outras_obrigacoes_cp"] = 0.0
            bpp["provisoes_cp"] = 0.0
            bpp["outras_obrigacoes_lp"] = 0.0
            bpp["provisoes_lp"] = 0.0

            if bpp.get("passivo_circulante", 0) != 0 or bpp.get("patrimonio_liquido", 0) != 0:
                entries.append({
                    "periodo": end,
                    "tipo": f"{prefix}_bpp",
                    "ano": ano,
                    "contas": bpp,
                })

            # ---- DFC (Cash Flow) ----
            dfc = {}
            for conta, tags in DFC_TAGS.items():
                val = resolve_tag(usgaap, tags, form, end, start)
                dfc[conta] = val * 1.0 if val is not None else 0.0

            dfc["caixa_gerado_operacoes"] = dfc.get("fco", 0)
            dfc["var_ativos_passivos"] = 0.0
            dfc["juros_emprestimos_dfc"] = abs(dfc.get("juros_pagos", 0))

            if dfc.get("fco", 0) != 0:
                entries.append({
                    "periodo": end,
                    "tipo": f"{prefix}_dfc",
                    "ano": ano,
                    "contas": dfc,
                })

        self._log(f"Extraídos {len(entries)} registros de contas")
        return entries

    # ------------------------------------------------------------------
    # Main orchestration
    # ------------------------------------------------------------------

    def coletar(self, query: str, ano_inicio: int = 2021,
                pasta_destino: str | None = None) -> dict:
        """
        Coleta completa de dados financeiros de uma empresa.

        Args:
            query: ticker ou nome da empresa
            ano_inicio: ano inicial para buscar dados
            pasta_destino: pasta onde salvar os resultados

        Returns:
            {"empresa": {...}, "contas": [...], "n_registros": int}
        """
        self._log(f"=== Coleta: {query} ===")

        # 1. Buscar empresa
        empresa = self.buscar_empresa(query)
        self._log(f"Empresa: {empresa['title']} (CIK: {empresa['cik']}, Ticker: {empresa['ticker']})")

        # 2. Obter company facts
        facts = self.obter_company_facts(empresa["cik"])

        # 3. Extrair contas
        contas = self.extrair_contas_chave(facts, ano_inicio)

        # 4. Salvar
        if pasta_destino:
            dados_dir = os.path.join(pasta_destino, "Dados_EDGAR")
            os.makedirs(dados_dir, exist_ok=True)
            caminho = os.path.join(dados_dir, "contas_chave.json")
            with open(caminho, "w", encoding="utf-8") as f:
                json.dump(contas, f, ensure_ascii=False, indent=2, default=str)
            self._log(f"Contas salvas em {caminho}")

        self._log(f"=== Concluído: {len(contas)} registros ===")

        return {
            "empresa": empresa,
            "contas": contas,
            "n_registros": len(contas),
        }
