"""
Mapeamento de tags US GAAP XBRL → contas internas do dashboard.

Cada conta interna mapeia para uma lista de tags candidatas em ordem de prioridade.
O sistema tenta cada tag até encontrar uma com dados para a empresa.
"""

# ---- Income Statement (DRE) ----
DRE_TAGS = {
    "receita_liquida": [
        "Revenues",
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "RevenueFromContractWithCustomerIncludingAssessedTax",
        "SalesRevenueNet",
        "SalesRevenueGoodsNet",
        "RevenueFromRelatedParties",
    ],
    "custo": [
        "CostOfRevenue",
        "CostOfGoodsAndServicesSold",
        "CostOfGoodsSold",
        "CostOfGoodsAndServiceExcludingDepreciationDepletionAndAmortization",
    ],
    "resultado_bruto": [
        "GrossProfit",
    ],
    "despesas_vendas": [
        "SellingAndMarketingExpense",
        "SellingExpense",
        "SellingGeneralAndAdministrativeExpense",
    ],
    "despesas_ga": [
        "GeneralAndAdministrativeExpense",
    ],
    "ebit": [
        "OperatingIncomeLoss",
    ],
    "resultado_financeiro": [
        "NonoperatingIncomeExpense",
    ],
    "receitas_financeiras": [
        "InvestmentIncomeInterest",
        "InterestIncomeOther",
        "InvestmentIncomeInterestAndDividend",
        "OtherNonoperatingIncome",
    ],
    "despesas_financeiras": [
        "InterestExpense",
        "InterestExpenseDebt",
        "InterestAndDebtExpense",
        "InterestExpenseBorrowings",
        "InterestIncomeExpenseNet",
    ],
    "lucro_antes_ir": [
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments",
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesDomestic",
    ],
    "ir_csll": [
        "IncomeTaxExpenseBenefit",
    ],
    "lucro_liquido": [
        "NetIncomeLoss",
        "ProfitLoss",
        "NetIncomeLossAvailableToCommonStockholdersBasic",
    ],
}

# ---- Balance Sheet - Assets (BPA) ----
BPA_TAGS = {
    "ativo_total": [
        "Assets",
    ],
    "ativo_circulante": [
        "AssetsCurrent",
    ],
    "caixa": [
        "CashCashEquivalentsAndShortTermInvestments",
        "CashAndCashEquivalentsAtCarryingValue",
        "CashAndCashEquivalentsAtCarryingValueIncludingDiscontinuedOperations",
        "Cash",
    ],
    "aplicacoes_financeiras_cp": [
        "ShortTermInvestments",
        "MarketableSecuritiesCurrent",
        "AvailableForSaleSecuritiesCurrent",
    ],
    "contas_a_receber": [
        "AccountsReceivableNetCurrent",
        "ReceivablesNetCurrent",
        "AccountsReceivableNet",
        "AccountsNotesAndLoansReceivableNetCurrent",
    ],
    "estoques_cp": [
        "InventoryNet",
        "InventoryFinishedGoodsAndWorkInProcess",
    ],
    "ativo_nao_circulante": [
        "AssetsNoncurrent",
    ],
    "investimentos": [
        "LongTermInvestments",
        "Investments",
        "InvestmentsInAffiliatesSubsidiariesAssociatesAndJointVentures",
    ],
    "imobilizado": [
        "PropertyPlantAndEquipmentNet",
    ],
    "intangivel": [
        "IntangibleAssetsNetExcludingGoodwill",
        "IntangibleAssetsNetIncludingGoodwill",
        "Goodwill",
    ],
}

# ---- Balance Sheet - Liabilities (BPP) ----
BPP_TAGS = {
    "passivo_circulante": [
        "LiabilitiesCurrent",
    ],
    "fornecedores": [
        "AccountsPayableCurrent",
        "AccountsPayableAndAccruedLiabilitiesCurrent",
    ],
    "obrigacoes_fiscais_cp": [
        "TaxesPayableCurrent",
        "AccruedIncomeTaxesCurrent",
    ],
    "emprestimos_cp": [
        "DebtCurrent",
        "LongTermDebtCurrent",
        "LongTermDebtAndCapitalLeaseObligationsCurrent",
        "ShortTermBorrowings",
        "CommercialPaper",
        "LinesOfCreditCurrent",
    ],
    "passivo_nao_circulante": [
        "LiabilitiesNoncurrent",
    ],
    "emprestimos_lp": [
        "LongTermDebtNoncurrent",
        "LongTermDebt",
        "LongTermDebtAndCapitalLeaseObligations",
    ],
    "patrimonio_liquido": [
        "StockholdersEquity",
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
    ],
    "capital_social": [
        "CommonStockValue",
        "CommonStocksIncludingAdditionalPaidInCapital",
    ],
}

# ---- Cash Flow Statement (DFC) ----
DFC_TAGS = {
    "fco": [
        "NetCashProvidedByUsedInOperatingActivities",
        "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
    ],
    "depreciacao_amortizacao": [
        "DepreciationDepletionAndAmortization",
        "DepreciationAndAmortization",
        "Depreciation",
    ],
    "fci": [
        "NetCashProvidedByUsedInInvestingActivities",
        "NetCashProvidedByUsedInInvestingActivitiesContinuingOperations",
    ],
    "capex": [
        "PaymentsToAcquirePropertyPlantAndEquipment",
        "PaymentsToAcquireProductiveAssets",
    ],
    "fcf": [
        "NetCashProvidedByUsedInFinancingActivities",
        "NetCashProvidedByUsedInFinancingActivitiesContinuingOperations",
    ],
    "amortizacao_divida": [
        "RepaymentsOfLongTermDebt",
        "RepaymentsOfDebt",
        "RepaymentsOfLongTermCapitalLeaseObligations",
    ],
    "captacao_divida": [
        "ProceedsFromIssuanceOfLongTermDebt",
        "ProceedsFromDebtNetOfIssuanceCosts",
        "ProceedsFromIssuanceOfDebt",
    ],
    "dividendos_pagos": [
        "PaymentsOfDividends",
        "PaymentsOfDividendsCommonStock",
        "PaymentsOfOrdinaryDividends",
    ],
    "juros_pagos": [
        "InterestPaidNet",
        "InterestPaid",
    ],
}

# ---- Debt Maturity Schedule (Cronograma) ----
# Tags XBRL que muitas empresas preenchem diretamente
MATURITY_TAGS = {
    "next_12_months": [
        "LongTermDebtMaturitiesRepaymentsOfPrincipalInNextTwelveMonths",
    ],
    "year_two": [
        "LongTermDebtMaturitiesRepaymentsOfPrincipalInYearTwo",
    ],
    "year_three": [
        "LongTermDebtMaturitiesRepaymentsOfPrincipalInYearThree",
    ],
    "year_four": [
        "LongTermDebtMaturitiesRepaymentsOfPrincipalInYearFour",
    ],
    "year_five": [
        "LongTermDebtMaturitiesRepaymentsOfPrincipalInYearFive",
    ],
    "thereafter": [
        "LongTermDebtMaturitiesRepaymentsOfPrincipalAfterYearFive",
        "LongTermDebtMaturitiesRepaymentsOfPrincipalRemainderOfFiscalYear",
    ],
}


def resolve_tag(facts_usgaap: dict, candidates: list[str],
                form: str, period_end: str,
                period_start: str | None = None,
                prefer_quarterly: bool = False) -> float | None:
    """
    Dado o dicionário us-gaap dos company facts, tenta resolver
    o valor para uma lista de tags candidatas.

    Args:
        facts_usgaap: facts["us-gaap"] do JSON da SEC
        candidates: lista de tags XBRL em ordem de prioridade
        form: "10-K" ou "10-Q"
        period_end: data fim do período (YYYY-MM-DD)
        period_start: data início (opcional, para filtrar duration items)
        prefer_quarterly: se True, prefere dados trimestrais vs YTD

    Returns:
        valor em USD ou None se não encontrado
    """
    for tag in candidates:
        tag_data = facts_usgaap.get(tag)
        if not tag_data:
            continue

        units = tag_data.get("units", {})
        usd_data = units.get("USD") or units.get("USD/shares")
        if not usd_data:
            continue

        # Filtrar por período e form type
        matches = []
        for entry in usd_data:
            if entry.get("end") != period_end:
                continue
            entry_form = entry.get("form", "")
            if form == "10-K" and entry_form not in ("10-K", "10-K/A"):
                continue
            if form == "10-Q" and entry_form not in ("10-Q", "10-Q/A"):
                continue

            # Para itens de duration (DRE, DFC), verificar start date
            if period_start and "start" in entry:
                if prefer_quarterly:
                    # Preferir dados trimestrais (start próximo do end)
                    entry_start = entry.get("start", "")
                    if entry_start == period_start:
                        matches.insert(0, entry)  # Prioridade
                    else:
                        matches.append(entry)
                else:
                    if entry.get("start") == period_start:
                        matches.append(entry)
            else:
                matches.append(entry)

        if matches:
            return matches[0]["val"]

    return None
