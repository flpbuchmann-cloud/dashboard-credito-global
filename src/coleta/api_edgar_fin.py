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
from .tag_mapping_fin import (
    DRE_TAGS, BPA_TAGS, BPP_TAGS, DFC_TAGS, MATURITY_TAGS,
    PER_SHARE_TAGS, SHARES_TAGS, REGULATORY_TAGS,
    resolve_tag, resolve_tag_any_unit, resolve_tag_pure,
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

    @staticmethod
    def _pick_best_entry(matches: list[dict]) -> dict | None:
        """
        Desambigua múltiplos entries para o mesmo período.

        Regra: entries do filing original do período (fy == ano do end) têm
        prioridade sobre comparativos de filings futuros (restatements).
        Em caso de empate, prefere entry com 'frame' (canônico EDGAR).
        """
        if not matches:
            return None
        if len(matches) == 1:
            return matches[0]

        # Separar: entries cujo fy corresponde ao ano do período
        end_year = int(matches[0]["end"][:4])
        original = [m for m in matches if m.get("fy", 0) == end_year]
        restated = [m for m in matches if m.get("fy", 0) != end_year]

        # Preferir originais do período
        pool = original if original else restated

        # Dentro do pool, preferir entry com frame (canônico)
        with_frame = [m for m in pool if m.get("frame")]
        if with_frame:
            return with_frame[0]
        return pool[0]

    def _resolve_flow_item(self, usgaap: dict, candidates: list[str],
                           form: str, period_end: str, fp: str) -> float | None:
        """
        Resolve um item de fluxo (DRE ou DFC) preferindo dados do filing original.

        Para 10-Q: prefere o entry YTD (maior duração) para consistência
        com a desacumulação do indicadores.py.
        Para 10-K: pega o entry anual completo.
        Desambigua filings duplicados (original vs restatement) via _pick_best_entry.
        """
        for tag in candidates:
            tag_data = usgaap.get(tag)
            if not tag_data:
                continue

            units = tag_data.get("units", {})
            usd_data = units.get("USD")
            if not usd_data:
                continue

            # Filtrar por end date e form type
            matches = []
            for entry in usd_data:
                if entry.get("end") != period_end:
                    continue
                entry_form = entry.get("form", "")
                if form == "10-K" and entry_form not in ("10-K", "10-K/A"):
                    continue
                if form == "10-Q" and entry_form not in ("10-Q", "10-Q/A"):
                    continue
                if "start" in entry:
                    matches.append(entry)

            if not matches:
                continue

            if len(matches) > 1:
                # Filtrar por maior duração (YTD para 10-Q, full year para 10-K)
                # Evita pegar entries de Q4 isolado quando existe o acumulado anual
                from datetime import datetime
                for m in matches:
                    try:
                        start_dt = datetime.strptime(m["start"], "%Y-%m-%d")
                        end_dt = datetime.strptime(m["end"], "%Y-%m-%d")
                        m["_duration"] = (end_dt - start_dt).days
                    except (ValueError, KeyError):
                        m["_duration"] = 0

                max_dur = max(m.get("_duration", 0) for m in matches)
                longest_matches = [m for m in matches if m.get("_duration", 0) == max_dur]
                best = self._pick_best_entry(longest_matches)
                return best["val"] if best else matches[0]["val"]
            else:
                best = self._pick_best_entry(matches)
                return best["val"] if best else None

        return None

    def _descobrir_periodos(self, facts: dict, ano_inicio: int) -> list[dict]:
        """
        Descobre os períodos disponíveis a partir dos facts.

        Para 10-K: período anual (FY)
        Para 10-Q: período trimestral (Q1, Q2, Q3) — prefere dados
        trimestrais (start próximo do end) vs YTD.
        """
        usgaap = facts.get("facts", {}).get("us-gaap", {})

        # Usar Assets (balance sheet, point-in-time) para descobrir end dates
        end_dates = {}
        for tag in ["Assets", "CashAndCashEquivalentsAtCarryingValue",
                     "StockholdersEquity", "LiabilitiesCurrent"]:
            tag_data = usgaap.get(tag, {})
            for unit_data in tag_data.get("units", {}).values():
                for entry in unit_data:
                    fy = entry.get("fy") or 0
                    if fy < ano_inicio:
                        continue
                    form = entry.get("form", "")
                    if form not in ("10-K", "10-Q", "10-K/A", "10-Q/A"):
                        continue
                    end = entry.get("end", "")
                    fp = entry.get("fp", "")
                    form_clean = form.replace("/A", "")
                    end_year = int(end[:4]) if end else 0

                    if end:
                        key = (end, form_clean)
                        # Preferir entry do filing original (fy == ano do end)
                        # sobre comparativos de filings futuros
                        existing = end_dates.get(key)
                        is_original = (fy == end_year)
                        if existing is None:
                            end_dates[key] = {
                                "end": end, "form": form_clean,
                                "fp": fp, "fy": fy,
                            }
                        elif is_original and existing.get("fy", 0) != end_year:
                            # Substituir restatement pelo original
                            end_dates[key] = {
                                "end": end, "form": form_clean,
                                "fp": fp, "fy": fy,
                            }

        resultado = sorted(end_dates.values(), key=lambda x: x["end"])
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
            # Para 10-Q, buscar dados trimestrais (não YTD)
            dre = {}
            for conta, tags in DRE_TAGS.items():
                val = self._resolve_flow_item(usgaap, tags, form, end, fp)
                dre[conta] = val * 1.0 if val is not None else 0.0

            # Receita fallback: se nenhuma tag direta (Revenues, RevenuesNetOfInterestExpense)
            # existir, calcular como NII + NoninterestIncome (consistente entre 10-K e 10-Q)
            if dre.get("receita_liquida", 0) == 0:
                nii_val = dre.get("nii", 0)
                rnj_val = dre.get("receita_nao_juros", 0)
                if nii_val != 0 and rnj_val != 0:
                    dre["receita_liquida"] = nii_val + rnj_val
                    self._log(f"  Receita via NII+NonInterest: {dre['receita_liquida']/1e6:,.0f}M ({end})")

            # Garantir custo negativo (XBRL CostOfRevenue vem positivo)
            if "custo" in dre and dre.get("custo", 0) > 0:
                dre["custo"] = -abs(dre["custo"])

            # COGS fallback (apenas se tag "custo" existe no mapping)
            if "custo" in DRE_TAGS:
                if dre.get("custo", 0) == 0 and dre.get("receita_liquida", 0) != 0 and form == "10-K":
                    for cogs_tag in DRE_TAGS["custo"]:
                        val_10q = self._resolve_flow_item(
                            usgaap, [cogs_tag], "10-Q", end, fp
                        )
                        if val_10q is not None and val_10q != 0:
                            dre["custo"] = -abs(val_10q)
                            self._log(f"  COGS via 10-Q fallback: {cogs_tag} = {val_10q/1e6:,.0f}M ({end})")
                            break

            # Calcular resultado_bruto se não disponível
            if "resultado_bruto" in DRE_TAGS:
                if dre.get("resultado_bruto", 0) == 0 and dre.get("receita_liquida", 0) != 0:
                    dre["resultado_bruto"] = dre["receita_liquida"] + dre.get("custo", 0)

            # EBIT fallback: some 10-K filings omit OperatingIncomeLoss
            if dre.get("ebit", 0) == 0 and form == "10-K":
                # Try 10-Q tags for same end date
                val_10q = self._resolve_flow_item(
                    usgaap, DRE_TAGS["ebit"], "10-Q", end, fp
                )
                if val_10q is not None and val_10q != 0:
                    dre["ebit"] = val_10q
                    self._log(f"  EBIT via 10-Q fallback: {val_10q/1e6:,.0f}M ({end})")

            # Calcular EBIT se ainda não disponível
            if dre.get("ebit", 0) == 0 and dre.get("lucro_antes_ir", 0) != 0:
                # EBIT = Lucro antes IR + Despesas financeiras
                desp_fin = abs(dre.get("despesas_financeiras", 0))
                rec_fin = dre.get("receitas_financeiras", 0)
                dre["ebit"] = dre["lucro_antes_ir"] + desp_fin - rec_fin

            # Calcular despesas_operacionais (apenas se XBRL não retornou valor)
            if dre.get("despesas_operacionais", 0) == 0:
                fallback = dre.get("despesas_vendas", 0) + dre.get("despesas_ga", 0)
                if fallback != 0:
                    dre["despesas_operacionais"] = fallback
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
            # Resolve core BPP tags (skip finance_lease_* which are supplementary)
            core_bpp_keys = [k for k in BPP_TAGS if not k.startswith("finance_lease_")]
            for conta in core_bpp_keys:
                tags = BPP_TAGS[conta]
                val = resolve_tag(usgaap, tags, form, end)
                bpp[conta] = val * 1.0 if val is not None else 0.0

            # Add finance leases to debt if not already included
            # Check if emprestimos_lp came from a tag that includes leases
            emp_lp_tag_used = None
            for tag in BPP_TAGS["emprestimos_lp"]:
                if resolve_tag(usgaap, [tag], form, end) is not None:
                    emp_lp_tag_used = tag
                    break

            lease_included = emp_lp_tag_used and ("Lease" in emp_lp_tag_used or "lease" in emp_lp_tag_used)
            if not lease_included:
                # Add finance lease LP separately
                fl_lp = resolve_tag(usgaap, BPP_TAGS.get("finance_lease_lp", []), form, end)
                if fl_lp and fl_lp > 0:
                    bpp["emprestimos_lp"] += fl_lp
                    self._log(f"  +Finance Lease LP: {fl_lp/1e6:,.0f}M ({end})")

                # Add finance lease CP if not in emprestimos_cp
                emp_cp_tag_used = None
                for tag in BPP_TAGS["emprestimos_cp"]:
                    if resolve_tag(usgaap, [tag], form, end) is not None:
                        emp_cp_tag_used = tag
                        break
                cp_lease_included = emp_cp_tag_used and ("Lease" in emp_cp_tag_used or "lease" in emp_cp_tag_used)
                if not cp_lease_included:
                    fl_cp = resolve_tag(usgaap, BPP_TAGS.get("finance_lease_cp", []), form, end)
                    if fl_cp and fl_cp > 0:
                        bpp["emprestimos_cp"] += fl_cp

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

            if bpp.get("passivo_circulante", 0) != 0 or bpp.get("patrimonio_liquido", 0) != 0 or bpp.get("emprestimos_lp", 0) != 0:
                entries.append({
                    "periodo": end,
                    "tipo": f"{prefix}_bpp",
                    "ano": ano,
                    "contas": bpp,
                })

            # ---- DFC (Cash Flow) ----
            dfc = {}
            for conta, tags in DFC_TAGS.items():
                val = self._resolve_flow_item(usgaap, tags, form, end, fp)
                dfc[conta] = val * 1.0 if val is not None else 0.0

            # Normalizar sinais: XBRL Payments*/Repayments* vêm positivos,
            # mas representam saídas de caixa — converter para negativos
            for campo_saida in ["capex", "amortizacao_divida", "dividendos_pagos", "juros_pagos"]:
                if dfc.get(campo_saida, 0) > 0:
                    dfc[campo_saida] = -abs(dfc[campo_saida])

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

            # ---- Per-Share & Shares Data ----
            psd = {}
            for conta, tags in PER_SHARE_TAGS.items():
                val = resolve_tag_any_unit(usgaap, tags, form, end)
                if val is not None:
                    psd[conta] = val
            for conta, tags in SHARES_TAGS.items():
                val = resolve_tag_any_unit(usgaap, tags, form, end)
                if val is not None:
                    psd[conta] = val
            if psd:
                entries.append({
                    "periodo": end,
                    "tipo": f"{prefix}_psd",
                    "ano": ano,
                    "contas": psd,
                })

            # ---- Regulatory Capital Ratios (pure units) ----
            reg = {}
            for conta, tags in REGULATORY_TAGS.items():
                val = resolve_tag_pure(usgaap, tags, form, end)
                if val is not None:
                    reg[conta] = val
            if reg:
                entries.append({
                    "periodo": end,
                    "tipo": f"{prefix}_reg",
                    "ano": ano,
                    "contas": reg,
                })

        self._log(f"Extraídos {len(entries)} registros de contas")
        return entries

    # ------------------------------------------------------------------
    # Debt Maturity Schedule (Cronograma via XBRL)
    # ------------------------------------------------------------------

    def _extrair_cronograma_periodo(self, usgaap: dict, end_date: str,
                                     form_types: tuple, form_label: str) -> dict | None:
        """Extrai um cronograma de maturidade para um período/form específico."""
        vencimentos = {}
        ano_base = int(end_date[:4])

        for label, tags in MATURITY_TAGS.items():
            for tag in tags:
                tag_data = usgaap.get(tag, {})
                entries = tag_data.get("units", {}).get("USD", [])
                match = [e for e in entries if e.get("end") == end_date
                         and e.get("form") in form_types]
                if match:
                    # Preferir entry do filing original (fy == ano do end)
                    end_year = int(end_date[:4])
                    original = [m for m in match if m.get("fy", 0) == end_year]
                    best = original[-1] if original else match[-1]
                    val = best["val"]
                    if label == "next_12_months":
                        vencimentos[str(ano_base + 1)] = val
                    elif label == "year_two":
                        vencimentos[str(ano_base + 2)] = val
                    elif label == "year_three":
                        vencimentos[str(ano_base + 3)] = val
                    elif label == "year_four":
                        vencimentos[str(ano_base + 4)] = val
                    elif label == "year_five":
                        vencimentos[str(ano_base + 5)] = val
                    elif label == "thereafter":
                        vencimentos["longo_prazo"] = val
                    break

        if len(vencimentos) < 3:
            return None

        divida_total_xbrl = sum(vencimentos.values())

        # Calcular "thereafter" implícito se faltam buckets
        for debt_tag in ["LongTermDebt", "LongTermDebtNoncurrent",
                         "LongTermDebtAndCapitalLeaseObligations"]:
            tag_data = usgaap.get(debt_tag, {})
            entries = tag_data.get("units", {}).get("USD", [])
            debt_match = [e for e in entries if e.get("end") == end_date
                          and e.get("form") in form_types
                          and "start" not in e]
            if debt_match:
                total_debt = debt_match[-1]["val"]
                residual = total_debt - divida_total_xbrl
                if residual > 100_000_000:
                    vencimentos["longo_prazo"] = vencimentos.get("longo_prazo", 0) + residual
                    divida_total_xbrl = sum(vencimentos.values())
                    self._log(f"  Adicionado thereafter implícito: {residual/1e6:,.0f}M (Total debt: {total_debt/1e6:,.0f}M)")
                break

        return {
            "data_referencia": end_date,
            "caixa": None,
            "vencimentos": vencimentos,
            "divida_total": divida_total_xbrl,
            "arquivo": f"XBRL {form_label} ({end_date})",
        }

    def extrair_cronograma_xbrl(self, facts: dict) -> list[dict]:
        """
        Extrai cronograma de amortização diretamente das tags XBRL.

        Busca tanto em 10-K (anual) quanto 10-Q (trimestral) para
        fornecer cronogramas mais recentes e comparações entre períodos.
        """
        usgaap = facts.get("facts", {}).get("us-gaap", {})
        cronogramas = []

        tag_test = "LongTermDebtMaturitiesRepaymentsOfPrincipalInNextTwelveMonths"
        if tag_test not in usgaap:
            return []

        test_entries = usgaap[tag_test].get("units", {}).get("USD", [])

        # Coletar todos os períodos com dados de maturidade (10-K e 10-Q)
        periodos = {}
        for e in test_entries:
            form = e.get("form", "")
            end = e["end"]
            if form in ("10-K", "10-K/A"):
                periodos[end] = ("10-K", "10-K/A")
            elif form in ("10-Q", "10-Q/A"):
                periodos[end] = ("10-Q", "10-Q/A")

        # Processar os 6 mais recentes (mix de 10-K e 10-Q)
        for end_date in sorted(periodos.keys(), reverse=True)[:6]:
            form_types = periodos[end_date]
            form_label = "10-K" if "10-K" in form_types else "10-Q"

            resultado = self._extrair_cronograma_periodo(
                usgaap, end_date, form_types, form_label
            )
            if resultado:
                cronogramas.append(resultado)
                self._log(f"Cronograma XBRL {end_date} ({form_label}): {len(resultado['vencimentos'])} buckets")

        return cronogramas

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

        # 4. Extrair cronograma via XBRL (com fallback para HTML parsing)
        cronogramas = self.extrair_cronograma_xbrl(facts)
        if cronogramas:
            self._log(f"{len(cronogramas)} cronogramas extraídos via XBRL")

        # Check if we have quarterly (10-Q) cronogramas from XBRL
        xbrl_has_10q = any(
            "10-Q" in c.get("arquivo", "") for c in cronogramas
        )

        # Fallback: HTML parsing when XBRL is incomplete or missing 10-Q data
        xbrl_incompleto = any(
            len(c.get("vencimentos", {})) < 5 for c in cronogramas
        ) if cronogramas else True
        needs_html = xbrl_incompleto or not xbrl_has_10q

        if needs_html:
            try:
                from .filing_parser import extrair_cronograma_edgar
                self._log("Extraindo cronogramas via HTML filing (inclui 10-Q)...")
                html_cronogramas = extrair_cronograma_edgar(
                    empresa["cik"], n_recentes=6, incluir_10q=True
                )
                if html_cronogramas:
                    # Substituir cronogramas XBRL incompletos por HTML mais ricos
                    for hc in html_cronogramas:
                        dr = hc.get("data_referencia", "")
                        xbrl_match = [c for c in cronogramas if c.get("data_referencia") == dr]
                        if xbrl_match:
                            xbrl_buckets = len(xbrl_match[0].get("vencimentos", {}))
                            html_buckets = len(hc.get("vencimentos", {}))
                            if html_buckets > xbrl_buckets:
                                cronogramas = [c for c in cronogramas if c.get("data_referencia") != dr]
                                cronogramas.append(hc)
                                self._log(f"  HTML ({html_buckets} buckets) substituiu XBRL ({xbrl_buckets} buckets) para {dr}")
                        else:
                            cronogramas.append(hc)
                            self._log(f"  HTML adicionou cronograma para {dr}")
            except Exception as e:
                self._log(f"Fallback HTML falhou: {e}")

        # 5. Salvar
        if pasta_destino:
            dados_dir = os.path.join(pasta_destino, "Dados_EDGAR")
            os.makedirs(dados_dir, exist_ok=True)
            caminho = os.path.join(dados_dir, "contas_chave.json")
            with open(caminho, "w", encoding="utf-8") as f:
                json.dump(contas, f, ensure_ascii=False, indent=2, default=str)
            self._log(f"Contas salvas em {caminho}")

            if cronogramas:
                caminho_cron = os.path.join(dados_dir, "cronogramas.json")
                with open(caminho_cron, "w", encoding="utf-8") as f:
                    json.dump(cronogramas, f, ensure_ascii=False, indent=2, default=str)
                self._log(f"Cronogramas salvos em {caminho_cron}")

        self._log(f"=== Concluído: {len(contas)} registros ===")

        return {
            "empresa": empresa,
            "contas": contas,
            "cronogramas": cronogramas,
            "n_registros": len(contas),
        }
