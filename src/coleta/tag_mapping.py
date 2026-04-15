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
        # E&P / Oil & Gas specific cost tags
        "ExplorationExpense",
        "ProductionRelatedExpenses",
        "OilAndGasProductionExpense",
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
        "InterestExpenseNonoperating",
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
        "NetIncomeLossAvailableToCommonStockholdersBasic",
        "NetIncomeLoss",
        "ProfitLoss",
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
        "PropertyPlantAndEquipmentAndFinanceLeaseRightOfUseAssetAfterAccumulatedDepreciationAndAmortization",
        "PropertyPlantAndEquipmentAndFinanceLeaseRightOfUseAssetNet",
        "OilAndGasPropertyFullCostMethodNet",
    ],
    "intangivel": [
        "IntangibleAssetsNetExcludingGoodwill",
        "IntangibleAssetsNetIncludingGoodwill",
        "Goodwill",
        "GoodwillAndIntangibleAssetsNet",
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
        # Porção corrente de dívida de longo prazo
        "LongTermDebtAndCapitalLeaseObligationsCurrent",
        "LongTermDebtCurrent",
        "DebtCurrent",
    ],
    "short_term_borrowings": [
        # Empréstimos de curto prazo separados (commercial paper, linhas de crédito)
        "ShortTermBorrowings",
        "CommercialPaper",
        "LinesOfCreditCurrent",
    ],
    "passivo_nao_circulante": [
        "LiabilitiesNoncurrent",
    ],
    "emprestimos_lp": [
        # Prefer tags that include finance/capital leases
        "LongTermDebtAndCapitalLeaseObligations",
        "LongTermDebtAndFinanceLeaseLiabilityNoncurrent",
        "LongTermDebtNoncurrent",
        "LongTermDebt",
    ],
    # Tags adicionais para cálculo de dívida total (finance leases LP)
    "finance_lease_lp": [
        "FinanceLeaseLiabilityNoncurrent",
        "CapitalLeaseObligationsNoncurrent",
    ],
    "finance_lease_cp": [
        "FinanceLeaseLiabilityCurrent",
        "CapitalLeaseObligationsCurrent",
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
        "PaymentsOfOrdinaryDividends",
        "PaymentsOfDividends",
        "PaymentsOfDividendsCommonStock",
        "PaymentsOfDividendsPreferredStockAndPreferenceStock",
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
        "LongTermDebtMaturitiesRepaymentsOfPrincipalInNextRollingTwelveMonths",
        "FinanceLeaseLiabilityPaymentsDueNextTwelveMonths",
    ],
    "year_two": [
        "LongTermDebtMaturitiesRepaymentsOfPrincipalInYearTwo",
        "LongTermDebtMaturitiesRepaymentsOfPrincipalInRollingYearTwo",
        "FinanceLeaseLiabilityPaymentsDueInTwoYears",
    ],
    "year_three": [
        "LongTermDebtMaturitiesRepaymentsOfPrincipalInYearThree",
        "LongTermDebtMaturitiesRepaymentsOfPrincipalInRollingYearThree",
        "FinanceLeaseLiabilityPaymentsDueInThreeYears",
    ],
    "year_four": [
        "LongTermDebtMaturitiesRepaymentsOfPrincipalInYearFour",
        "LongTermDebtMaturitiesRepaymentsOfPrincipalInRollingYearFour",
        "FinanceLeaseLiabilityPaymentsDueInFourYears",
    ],
    "year_five": [
        "LongTermDebtMaturitiesRepaymentsOfPrincipalInYearFive",
        "LongTermDebtMaturitiesRepaymentsOfPrincipalInRollingYearFive",
        "FinanceLeaseLiabilityPaymentsDueInFiveYears",
    ],
    "thereafter": [
        "LongTermDebtMaturitiesRepaymentsOfPrincipalAfterYearFive",
        "LongTermDebtMaturitiesRepaymentsOfPrincipalInRollingAfterYearFive",
        "FinanceLeaseLiabilityPaymentsDueAfterYearFive",
        "LongTermDebtMaturitiesRepaymentsOfPrincipalRemainderOfFiscalYear",
    ],
}


def _pick_best_entry(matches: list[dict]) -> dict | None:
    """
    Desambigua múltiplos entries XBRL para o mesmo período.

    Prefere entries do filing original (fy == ano do end) sobre
    comparativos de filings futuros (restatements).
    Em empate, prefere entry com 'frame' (canônico EDGAR).
    """
    if not matches:
        return None
    if len(matches) == 1:
        return matches[0]

    end_year = int(matches[0]["end"][:4])
    original = [m for m in matches if m.get("fy", 0) == end_year]
    restated = [m for m in matches if m.get("fy", 0) != end_year]

    pool = original if original else restated
    with_frame = [m for m in pool if m.get("frame")]
    if with_frame:
        return with_frame[0]
    return pool[0]


def resolve_tag(facts_usgaap: dict, candidates: list[str],
                form: str, period_end: str,
                period_start: str | None = None,
                prefer_quarterly: bool = False) -> float | None:
    """
    Dado o dicionário us-gaap dos company facts, tenta resolver
    o valor para uma lista de tags candidatas.

    Desambigua filings duplicados (original vs restatement) preferindo
    entries do filing original do período.

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
                    entry_start = entry.get("start", "")
                    if entry_start == period_start:
                        matches.insert(0, entry)
                    else:
                        matches.append(entry)
                else:
                    if entry.get("start") == period_start:
                        matches.append(entry)
            else:
                matches.append(entry)

        if matches:
            best = _pick_best_entry(matches)
            if best:
                return best["val"]

    return None
