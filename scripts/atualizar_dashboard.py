"""
Orquestrador de atualizacao do dashboard.

Uso:
  python scripts/atualizar_dashboard.py                # tudo
  python scripts/atualizar_dashboard.py CI MT JPM      # apenas tickers especificos
  python scripts/atualizar_dashboard.py --skip-edgar   # pula coleta EDGAR (mais rapido)
  python scripts/atualizar_dashboard.py --so-pareceres # so regenera pareceres

Pipeline por empresa:
  1. EDGAR XBRL via ColetorEDGAR (US companies)
  2. Extractor especifico (XLSM > supplements PDF > earnings releases)
  3. Reconciliacao (se aplicavel)
  4. Regenerar parecer.md

Convencoes:
  - XLSM em Documentos/ tem prioridade sobre PDFs
  - Se ha extrator dedicado para o ticker, eh usado
  - Caso contrario, ColetorEDGAR (XBRL) eh fallback
"""
from __future__ import annotations

import os
import sys
import json
import time
import warnings
import argparse
from pathlib import Path

warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

LOCAL_NF = "G:/Meu Drive/Análise de Crédito Global"
LOCAL_FIN = "G:/Meu Drive/Análise de Crédito Financeiras"

BANCOS = {"BK","JPM","BAC","C","WFC","GS","MS","USB","BCS","HSBC","UBS","DB"}
ASSET_MANAGERS = {"APO","BX","KKR","ARES","OWL","BAM","CG","TPG","BN","FIG"}
CARDS = {"AXP","V","MA","DFS","COF","SYF"}


def _setor(ticker: str) -> str:
    t = ticker.upper()
    if t in BANCOS: return "Banco"
    if t in CARDS: return "Card / Outros"
    if t in ASSET_MANAGERS: return "Asset Manager"
    return "Nao-Financeira"


def _pasta(ticker: str, setor: str) -> str:
    base = LOCAL_FIN if setor != "Nao-Financeira" else LOCAL_NF
    return os.path.join(base, ticker)


# ===========================================================================
# REGISTRY: ticker -> updater function
# Cada updater retorna (ok: bool, msg: str)
# ===========================================================================
def _try_xlsm(ticker: str, pasta: str, xlsm_glob: str, extrair_func, *args) -> tuple[bool, str]:
    """Helper: encontra XLSM na pasta Documentos e roda o extrator."""
    docs = os.path.join(pasta, "Documentos")
    if not os.path.isdir(docs):
        return False, f"sem pasta Documentos"
    candidates = [f for f in os.listdir(docs) if f.lower().endswith((".xlsm", ".xlsx"))
                  and xlsm_glob.lower() in f.lower()]
    if not candidates:
        return False, f"sem XLSM ({xlsm_glob})"
    xlsm = os.path.join(docs, candidates[0])
    dest = os.path.join(pasta, "Dados_EDGAR")
    extrair_func(xlsm, dest, *args)
    return True, f"XLSM {candidates[0]}"


def _updater_mt(pasta: str) -> tuple[bool, str]:
    from src.coleta.extrator_xlsm_mt import extrair_xlsm_mt
    return _try_xlsm("MT", pasta, "mt.as", extrair_xlsm_mt, 2018)


def _updater_ci(pasta: str) -> tuple[bool, str]:
    from src.coleta.extrator_xlsm_research import extrair, CONFIG_CI
    docs = os.path.join(pasta, "Documentos")
    if not os.path.isdir(docs):
        return False, "sem pasta Documentos"
    cand = [f for f in os.listdir(docs) if f.lower().endswith((".xlsx", ".xlsm")) and "ci" in f.lower()]
    if not cand:
        return False, "sem XLSM CI"
    extrair(CONFIG_CI, os.path.join(docs, cand[0]),
            os.path.join(pasta, "Dados_EDGAR"), ano_inicio=2018)
    return True, f"XLSM {cand[0]}"


def _updater_vwagy(pasta: str) -> tuple[bool, str]:
    from src.coleta.extrator_supplement_vw import extrair_supplement_vw
    docs = os.path.join(pasta, "Documentos")
    extrair_supplement_vw(docs, os.path.join(pasta, "Dados_EDGAR"))
    return True, "PDFs interim/annual VW"


def _updater_mbg(pasta: str) -> tuple[bool, str]:
    from src.coleta.extrator_supplement_mbg import extrair_supplement_mbg
    docs = os.path.join(pasta, "Documentos")
    extrair_supplement_mbg(docs, os.path.join(pasta, "Dados_EDGAR"))
    return True, "fact sheets MBG"


def _updater_jpm(pasta: str) -> tuple[bool, str]:
    from src.coleta.extrator_supplement_jpm import extrair_supplement_jpm
    extrair_supplement_jpm(os.path.join(pasta, "Documentos"),
                            os.path.join(pasta, "Dados_EDGAR"))
    return True, "supplement JPM"


def _updater_bac(pasta: str) -> tuple[bool, str]:
    from src.coleta.extrator_supplement_bac import extrair_supplement_bac
    extrair_supplement_bac(os.path.join(pasta, "Documentos"),
                            os.path.join(pasta, "Dados_EDGAR"))
    return True, "supplement BAC"


def _updater_citi(pasta: str) -> tuple[bool, str]:
    from src.coleta.extrator_supplement_citi import extrair_supplement_citi
    extrair_supplement_citi(os.path.join(pasta, "Documentos"),
                             os.path.join(pasta, "Dados_EDGAR"))
    return True, "supplement Citi"


def _updater_bk(pasta: str) -> tuple[bool, str]:
    from src.coleta.extrator_supplement import extrair_supplement
    extrair_supplement(os.path.join(pasta, "Documentos"),
                        os.path.join(pasta, "Dados_EDGAR"))
    return True, "supplement BK"


def _updater_bcs(pasta: str) -> tuple[bool, str]:
    from src.coleta.extrator_supplement_barclays import extrair_supplement_barclays
    extrair_supplement_barclays(os.path.join(pasta, "Documentos"),
                                 os.path.join(pasta, "Dados_EDGAR"))
    return True, "Barclays results pack"


def _updater_hsbc(pasta: str) -> tuple[bool, str]:
    from src.coleta.extrator_supplement_hsbc import extrair_supplement_hsbc
    extrair_supplement_hsbc(os.path.join(pasta, "Documentos"),
                             os.path.join(pasta, "Dados_EDGAR"))
    return True, "HSBC results"


def _updater_ubs(pasta: str) -> tuple[bool, str]:
    from src.coleta.extrator_supplement_ubs import extrair_supplement_ubs
    extrair_supplement_ubs(os.path.join(pasta, "Documentos"),
                            os.path.join(pasta, "Dados_EDGAR"))
    return True, "UBS results"


def _updater_apo(pasta: str) -> tuple[bool, str]:
    from src.coleta.extrator_supplement_apollo import extrair_supplement_apollo
    extrair_supplement_apollo(os.path.join(pasta, "Documentos"),
                               os.path.join(pasta, "Dados_EDGAR"))
    return True, "Apollo supplement"


def _updater_edgar(pasta: str, ticker: str) -> tuple[bool, str]:
    """Fallback generico: ColetorEDGAR para empresas com XBRL US."""
    from src.coleta.api_edgar import ColetorEDGAR
    try:
        coletor = ColetorEDGAR()
        res = coletor.coletar(query=ticker, ano_inicio=2019, pasta_destino=pasta)
        return res["n_registros"] > 0, f"EDGAR XBRL ({res['n_registros']} registros)"
    except Exception as e:
        return False, f"EDGAR falhou: {e}"


REGISTRY = {
    # Non-financeiras com extrator dedicado
    "MT":     _updater_mt,
    "CI":     _updater_ci,
    "VWAGY":  _updater_vwagy,
    "MBG":    _updater_mbg,
    # Bancos com supplement parser
    "JPM":    _updater_jpm,
    "BAC":    _updater_bac,
    "C":      _updater_citi,
    "BK":     _updater_bk,
    "BCS":    _updater_bcs,
    "HSBC":   _updater_hsbc,
    "UBS":    _updater_ubs,
    # Asset managers
    "APO":    _updater_apo,
    # Demais (AA, OXY, CVS, PFE, PSX, AXP, V, BX) caem no _updater_edgar
}


# ===========================================================================
# RECONCILIACAO POS-COLETA
# ===========================================================================
def _aplicar_reconciliacao(ticker: str, pasta: str, setor: str):
    """Roda reconciliador se houver dados_earnings.json."""
    cc = os.path.join(pasta, "Dados_EDGAR", "contas_chave.json")
    de_path = os.path.join(pasta, "Dados_Extraidos", "dados_earnings.json")
    if not os.path.exists(cc) or not os.path.exists(de_path):
        return
    # apenas para nao-fin onde reconciliador eh aplicavel
    if setor != "Nao-Financeira":
        return
    try:
        from src.calculo.indicadores import calcular_indicadores
        from src.calculo.reconciliador import reconciliar
        df, alertas = calcular_indicadores(cc)
        with open(de_path, encoding="utf-8") as f:
            de = json.load(f)
        # filtrar entradas com receita > 4x do XBRL (lixo do Gemini anual)
        if isinstance(de, dict) and de.get("periodos"):
            limpos = []
            for p in de["periodos"]:
                periodo = p.get("periodo")
                rec_de = (p.get("dre") or {}).get("receita_liquida")
                if periodo and rec_de:
                    import pandas as pd
                    dt = pd.Timestamp(periodo)
                    if dt in df.index:
                        rec_xbrl = df.loc[dt, "receita_liquida"]
                        if rec_xbrl and rec_de / rec_xbrl > 3:
                            continue  # descarta lixo
                limpos.append(p)
            if len(limpos) != len(de["periodos"]):
                de["periodos"] = limpos
                with open(de_path, "w", encoding="utf-8") as f:
                    json.dump(de, f, indent=2, ensure_ascii=False)
    except Exception:
        pass


# ===========================================================================
# MAIN
# ===========================================================================
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("tickers", nargs="*", help="Tickers especificos (vazio=todos)")
    ap.add_argument("--skip-edgar", action="store_true",
                    help="Pula coleta EDGAR (mais rapido p/ revalidar XLSM/PDFs)")
    ap.add_argument("--so-pareceres", action="store_true",
                    help="Apenas regenera os pareceres .md (sem recoletar dados)")
    args = ap.parse_args()

    # Listar empresas existentes
    todas: list[tuple[str, str, str]] = []
    for base in (LOCAL_NF, LOCAL_FIN):
        if not os.path.isdir(base):
            continue
        for d in sorted(os.listdir(base)):
            if not os.path.isdir(os.path.join(base, d)):
                continue
            cc = os.path.join(base, d, "Dados_EDGAR", "contas_chave.json")
            if os.path.exists(cc) or d in REGISTRY:
                setor = _setor(d)
                todas.append((d, setor, os.path.join(base, d)))

    if args.tickers:
        wanted = {t.upper() for t in args.tickers}
        todas = [t for t in todas if t[0].upper() in wanted]

    print(f"\n{'='*70}")
    print(f"  ATUALIZACAO DASHBOARD — {len(todas)} empresas")
    print(f"{'='*70}\n")

    if not args.so_pareceres:
        for ticker, setor, pasta in todas:
            t0 = time.time()
            print(f"[{ticker:6s}] {setor:15s} ", end="", flush=True)

            updater = REGISTRY.get(ticker)
            try:
                if updater:
                    ok, msg = updater(pasta)
                elif args.skip_edgar:
                    ok, msg = True, "skip-edgar (mantem dados existentes)"
                else:
                    ok, msg = _updater_edgar(pasta, ticker)

                _aplicar_reconciliacao(ticker, pasta, setor)

                dt = time.time() - t0
                status = "OK " if ok else "WRN"
                print(f"{status} {msg}  ({dt:.1f}s)")
            except Exception as e:
                print(f"ERR {type(e).__name__}: {str(e)[:60]}")

    # Regenerar pareceres
    print(f"\n{'-'*70}")
    print("  Regenerando pareceres tecnicos...")
    print(f"{'-'*70}")
    try:
        from src.analise.parecer import salvar_parecer
        from src.calculo.indicadores import calcular_indicadores
        try:
            from src.calculo.indicadores_fin import calcular_indicadores as calc_fin
        except ImportError:
            calc_fin = None

        for ticker, setor, pasta in todas:
            try:
                cc = os.path.join(pasta, "Dados_EDGAR", "contas_chave.json")
                if not os.path.exists(cc):
                    continue
                if setor != "Nao-Financeira" and calc_fin:
                    cron = os.path.join(pasta, "Dados_EDGAR", "cronogramas.json")
                    sup = os.path.join(pasta, "Dados_EDGAR", "supplement_data.json")
                    df, _ = calc_fin(cc,
                                     caminho_cronogramas=cron if os.path.exists(cron) else None,
                                     caminho_supplement=sup if os.path.exists(sup) else None)
                else:
                    df, _ = calcular_indicadores(cc)
                # Carregar ratings
                rp = os.path.join(pasta, "Dados_EDGAR", "ratings.json")
                ratings = {}
                if os.path.exists(rp):
                    rd = json.load(open(rp, encoding="utf-8"))
                    ra = rd.get("ratings_atuais", {})
                    ratings = {
                        "moodys": (ra.get("Moodys") or {}).get("rating"),
                        "sp": (ra.get("SP") or {}).get("rating"),
                        "fitch": (ra.get("Fitch") or {}).get("rating"),
                    }
                salvar_parecer(ticker, setor, df, ratings,
                                os.path.join(pasta, "Dados_EDGAR"))
                print(f"  parecer {ticker}: ok")
            except Exception as e:
                print(f"  parecer {ticker}: ERR {str(e)[:60]}")
    except Exception as e:
        print(f"Falha ao regenerar pareceres: {e}")

    print(f"\n{'='*70}")
    print("  CONCLUIDO. Reinicie o dashboard (Ctrl+C + streamlit run) ou")
    print("  pressione 'C' no app para limpar cache do Streamlit.")
    print(f"{'='*70}\n")


if __name__ == "__main__":
    main()
