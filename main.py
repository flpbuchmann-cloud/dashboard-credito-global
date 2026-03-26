"""
Dashboard de Crédito Global - Script principal de coleta.

Orquestra a coleta de dados financeiros de empresas listadas nos EUA:
  1. EDGAR XBRL → Dados estruturados (Income Statement, Balance Sheet, Cash Flow)
  2. EDGAR Filings → Cronograma de amortização de dívida (HTML parsing)

Uso:
    python main.py --empresa "TSLA" --ano-inicio 2021

    # Apenas dados XBRL:
    python main.py --empresa "AAPL" --apenas-xbrl

    # Apenas cronograma:
    python main.py --empresa "TSLA" --apenas-cronograma

    # Listar empresas cadastradas:
    python main.py --listar
"""

import os
import sys
import json
import argparse
import yaml
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.coleta.api_edgar import ColetorEDGAR
from src.coleta.filing_parser import extrair_cronograma_edgar, salvar_cronogramas


# Caminho do cadastro
CADASTRO_PATH = os.path.join(os.path.dirname(__file__), "empresas_cadastro.yaml")

# Pasta base para dados
DATA_BASE = "G:/Meu Drive/Análise de Crédito Global"


def carregar_cadastro() -> dict:
    """Carrega cadastro de empresas do YAML."""
    if not os.path.exists(CADASTRO_PATH):
        return {}
    with open(CADASTRO_PATH, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    empresas = {}
    for emp in data.get("empresas", []):
        if isinstance(emp, dict):
            nome = emp.get("nome", "")
            empresas[nome] = emp
    return empresas


def listar_empresas():
    """Lista empresas cadastradas."""
    empresas = carregar_cadastro()
    if not empresas:
        print("Nenhuma empresa cadastrada.")
        return

    print("\nEmpresas cadastradas:")
    print("-" * 60)
    for nome, config in empresas.items():
        ticker = config.get("ticker", "?")
        cik = config.get("cik", "?")
        setor = config.get("setor", "?")
        status = config.get("status", "?")
        print(f"  {nome} ({ticker}) | CIK: {cik} | {setor} | {status}")


def coletar_xbrl(empresa: str, config: dict, ano_inicio: int):
    """Coleta dados XBRL do EDGAR."""
    print("\n" + "=" * 60)
    print("ETAPA 1: Coleta de Dados XBRL via EDGAR")
    print("=" * 60)

    coletor = ColetorEDGAR()
    ticker = config.get("ticker", empresa)
    pasta = config.get("pasta", os.path.join(DATA_BASE, empresa))

    resultado = coletor.coletar(
        query=ticker,
        ano_inicio=ano_inicio,
        pasta_destino=pasta,
    )

    # Resumo
    print(f"\n--- Resumo EDGAR ---")
    print(f"Empresa: {resultado['empresa']['title']}")
    print(f"CIK: {resultado['empresa']['cik']}")
    print(f"Ticker: {resultado['empresa']['ticker']}")
    print(f"Registros: {resultado['n_registros']}")

    return resultado


def coletar_cronograma(empresa: str, config: dict):
    """Coleta cronograma de amortização dos filings."""
    print("\n" + "=" * 60)
    print("ETAPA 2: Extração de Cronograma de Amortização")
    print("=" * 60)

    cik = config.get("cik", "")
    if not cik:
        # Buscar CIK pelo ticker
        coletor = ColetorEDGAR()
        info = coletor.buscar_empresa(config.get("ticker", empresa))
        cik = info["cik"]

    pasta = config.get("pasta", os.path.join(DATA_BASE, empresa))
    saida = os.path.join(pasta, "Dados_EDGAR", "cronogramas.json")

    cronogramas = extrair_cronograma_edgar(cik, n_recentes=3)

    if cronogramas:
        salvar_cronogramas(cronogramas, saida)
        print(f"\n{len(cronogramas)} cronogramas extraídos.")
    else:
        print("\nNenhum cronograma extraído.")

    return cronogramas


def main():
    parser = argparse.ArgumentParser(description="Dashboard de Crédito Global - Coleta de Dados")
    parser.add_argument("--empresa", type=str, help="Nome ou ticker da empresa")
    parser.add_argument("--ano-inicio", type=int, default=2021, help="Ano inicial (default: 2021)")
    parser.add_argument("--apenas-xbrl", action="store_true", help="Apenas dados XBRL")
    parser.add_argument("--apenas-cronograma", action="store_true", help="Apenas cronograma")
    parser.add_argument("--listar", action="store_true", help="Listar empresas cadastradas")
    args = parser.parse_args()

    if args.listar:
        listar_empresas()
        return

    if not args.empresa:
        parser.print_help()
        return

    # Carregar configuração
    empresas = carregar_cadastro()
    config = empresas.get(args.empresa, {})

    if not config:
        # Empresa não cadastrada — usar ticker diretamente
        config = {
            "ticker": args.empresa,
            "pasta": os.path.join(DATA_BASE, args.empresa),
        }

    print(f"Dashboard de Crédito Global - Coleta de Dados")
    print(f"Empresa: {args.empresa}")
    print(f"Período: {args.ano_inicio} até atual")

    if not args.apenas_cronograma:
        coletar_xbrl(args.empresa, config, args.ano_inicio)

    if not args.apenas_xbrl:
        coletar_cronograma(args.empresa, config)

    print("\n" + "=" * 60)
    print("COLETA CONCLUÍDA")
    print("=" * 60)


if __name__ == "__main__":
    main()
