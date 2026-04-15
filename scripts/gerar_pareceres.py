"""Gera pareceres tecnicos para todas as empresas cadastradas."""
from __future__ import annotations

import os
import sys
import json
import warnings

warnings.filterwarnings("ignore")
sys.stdout.reconfigure(encoding="utf-8")

# bootstrap path
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

from src.analise.parecer import salvar_parecer
from src.calculo.indicadores import calcular_indicadores
try:
    from src.calculo.indicadores_fin import calcular_indicadores as calcular_indicadores_fin
except ImportError:
    calcular_indicadores_fin = None

BANCOS = {"BK","JPM","BAC","C","WFC","GS","MS","USB","PNC","TFC","SCHW","STT",
          "NTRS","FITB","CFG","KEY","RF","HBAN","ZION","MTB","BCS","HSBC","CS",
          "DB","UBS","BBVA","SAN","ING","BNP"}
ASSET_MANAGERS = {"APO","BX","KKR","ARES","OWL","BAM","CG","TPG","BN","FIG"}
CARDS = {"AXP","V","MA","DFS","COF","SYF"}

LOCAL_NF = "G:/Meu Drive/Análise de Crédito Global"
LOCAL_FIN = "G:/Meu Drive/Análise de Crédito Financeiras"


def _setor(ticker: str) -> str:
    t = ticker.upper()
    if t in BANCOS: return "Banco"
    if t in CARDS: return "Card / Outros"
    if t in ASSET_MANAGERS: return "Asset Manager"
    return "Nao-Financeira"


def _carregar_ratings(pasta: str) -> dict:
    p = os.path.join(pasta, "Dados_EDGAR", "ratings.json")
    if not os.path.exists(p):
        return {}
    try:
        d = json.load(open(p, encoding="utf-8"))
        ra = d.get("ratings_atuais", {})
        return {
            "moodys": (ra.get("Moodys") or {}).get("rating"),
            "sp": (ra.get("SP") or {}).get("rating"),
            "fitch": (ra.get("Fitch") or {}).get("rating"),
        }
    except Exception:
        return {}


def main():
    n_ok = n_fail = 0
    for base in (LOCAL_NF, LOCAL_FIN):
        if not os.path.isdir(base):
            continue
        for ticker in sorted(os.listdir(base)):
            pasta = os.path.join(base, ticker)
            cc = os.path.join(pasta, "Dados_EDGAR", "contas_chave.json")
            if not os.path.exists(cc):
                continue
            setor = _setor(ticker)
            try:
                if setor != "Nao-Financeira" and calcular_indicadores_fin:
                    cron = os.path.join(pasta, "Dados_EDGAR", "cronogramas.json")
                    sup = os.path.join(pasta, "Dados_EDGAR", "supplement_data.json")
                    df, _ = calcular_indicadores_fin(
                        cc,
                        caminho_cronogramas=cron if os.path.exists(cron) else None,
                        caminho_supplement=sup if os.path.exists(sup) else None,
                    )
                else:
                    df, _ = calcular_indicadores(cc)
                ratings = _carregar_ratings(pasta)
                out = salvar_parecer(ticker, setor, df, ratings,
                                     os.path.join(pasta, "Dados_EDGAR"))
                n_ok += 1
                print(f"OK  {ticker:6s} ({setor:15s}) -> {out}")
            except Exception as e:
                n_fail += 1
                print(f"ERR {ticker:6s} ({setor:15s}): {e}")
    print(f"\nTotal OK={n_ok}  FAIL={n_fail}")


if __name__ == "__main__":
    main()
