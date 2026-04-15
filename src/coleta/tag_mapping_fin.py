"""
Mapeamento de tags US GAAP XBRL para empresas financeiras e asset managers.

Inclui tags específicas de bancos (NIM, provisions, deposits) e
gestoras de ativos (management fees, AUM, FRE).
"""

# ---- Income Statement (DRE) - Financial Companies ----
DRE_TAGS = {
    # Receita total (para financeiras: total revenues net of interest expense)
    # NÃO incluir InterestAndDividendIncomeOperating (gross interest income) nem
    # NoninterestIncome (apenas fee income) — ambos são componentes, não total.
    # Se nenhuma tag direta existir, o parser calcula: NII + NoninterestIncome.
    "receita_liquida": [
        "RevenuesNetOfInterestExpense",
        "Revenues",
        "RevenueFromContractWithCustomerExcludingAssessedTax",
    ],
    # Receita de juros (banks)
    "receita_juros": [
        "InterestAndDividendIncomeOperating",
        "InterestIncomeExpenseNet",
        "InterestAndFeeIncomeLoansAndLeases",
        "InterestIncomeOperating",
    ],
    # Despesa de juros (banks - custo de funding)
    "despesa_juros": [
        "InterestExpense",
        "InterestExpenseDeposits",
        "InterestAndDebtExpense",
        "InterestExpenseBorrowings",
    ],
    # Net Interest Income (NII)
    "nii": [
        "InterestIncomeExpenseNet",
        "NetInterestIncome",
    ],
    # Receita não-juros (fees, commissions)
    "receita_nao_juros": [
        "NoninterestIncome",
        "RevenueFromContractWithCustomerExcludingAssessedTax",
    ],
    # Provisão para perdas de crédito
    "provisao_credito": [
        "ProvisionForLoanLossesExpensed",
        "ProvisionForLoanLeaseAndOtherLosses",
        "ProvisionForCreditLosses",
    ],
    # Despesas operacionais totais (non-interest expense)
    "despesas_operacionais": [
        "NoninterestExpense",
        "OperatingExpenses",
        "CostsAndExpenses",
    ],
    # Compensation (importante para asset managers)
    "compensacao": [
        "LaborAndRelatedExpense",
        "EmployeeBenefitsAndShareBasedCompensation",
        "CompensationAndBenefitsTrustAndOtherExpense",
    ],
    # Marketing / Card member rewards (AXP)
    "marketing": [
        "MarketingExpense",
    ],
    # EBIT / Operating Income
    "ebit": [
        "OperatingIncomeLoss",
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
    ],
    # Lucro antes IR
    "lucro_antes_ir": [
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments",
    ],
    # IR
    "ir_csll": [
        "IncomeTaxExpenseBenefit",
    ],
    # Lucro líquido
    "lucro_liquido": [
        "NetIncomeLossAvailableToCommonStockholdersBasic",
        "NetIncomeLoss",
        "ProfitLoss",
    ],
    # D&A
    "depreciacao_amortizacao": [
        "DepreciationDepletionAndAmortization",
        "DepreciationAndAmortization",
        "Depreciation",
    ],
}

# ---- Balance Sheet - Assets ----
BPA_TAGS = {
    "ativo_total": [
        "Assets",
    ],
    "caixa": [
        "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
        "CashAndCashEquivalentsAtCarryingValue",
        "CashAndDueFromBanks",
        "Cash",
    ],
    "investimentos_titulos": [
        "DebtSecuritiesAvailableForSaleAndHeldToMaturity",
        "InvestmentSecurities",
        "AvailableForSaleSecuritiesDebtSecurities",
        "HeldToMaturitySecurities",
        "MarketableSecurities",
    ],
    # Depósitos remunerados em bancos/Fed (ativo — componente HQLA)
    "depositos_em_bancos": [
        "InterestBearingDepositsInBanks",
    ],
    "emprestimos_concedidos": [
        "FinancingReceivableExcludingAccruedInterestAfterAllowanceForCreditLoss",
        "LoansAndLeasesReceivableNetReportedAmount",
        "NotesReceivableNet",
        "FinancingReceivableAfterAllowanceForCreditLossExcludingAccruedInterest",
    ],
    "contas_a_receber": [
        "AccountsReceivableNet",
        "AccountsReceivableNetCurrent",
        "ReceivablesNetCurrent",
    ],
    "imobilizado": [
        "PropertyPlantAndEquipmentNet",
    ],
    "intangivel": [
        "IntangibleAssetsNetExcludingGoodwill",
        "Goodwill",
        "GoodwillAndIntangibleAssetsNet",
    ],
    "ativo_circulante": [
        "AssetsCurrent",
    ],
    "ativo_nao_circulante": [
        "AssetsNoncurrent",
    ],
    # Carteira de crédito bruta (antes da provisão)
    "carteira_credito_bruta": [
        "FinancingReceivableExcludingAccruedInterestBeforeAllowanceForCreditLoss",
        "LoansAndLeasesReceivableGrossCarryingAmount",
        "NotesReceivableGross",
    ],
    # Provisão acumulada (allowance for credit losses - stock)
    "provisao_acumulada": [
        "FinancingReceivableAllowanceForCreditLosses",
        "FinancingReceivableAllowanceForCreditLoss",
        "FinancingReceivableAllowanceForCreditLossExcludingAccruedInterest",
        "AllowanceForLoanAndLeaseLosses",
        "LoansAndLeasesReceivableAllowance",
    ],
    # Lucros retidos
    "lucros_retidos": [
        "RetainedEarningsAccumulatedDeficit",
    ],
    # Earning assets (ativos rendosos — proxy para NIM denominador)
    "earning_assets": [
        "InterestBearingAssetsAverage",
    ],
    # NPL (nonaccrual / nonperforming loans)
    "npl": [
        "FinancingReceivableExcludingAccruedInterestNonaccrual",
        "FinancingReceivableRecordedInvestmentNonaccrualStatus",
        "FinancingReceivableNonaccrualStatus",
    ],
}

# ---- Balance Sheet - Liabilities & Equity ----
BPP_TAGS = {
    "passivo_total": [
        "Liabilities",
    ],
    "depositos": [
        "Deposits",
        "DepositsSavingsDeposits",
    ],
    # Depósitos não-remunerados (demand/checking — custo zero)
    "depositos_noninterest_bearing": [
        "NoninterestBearingDomesticDepositDemand",
        "NoninterestBearingDepositLiabilities",
        "DepositsNoninterestBearing",
    ],
    # Depósitos remunerados (interest-bearing)
    "depositos_interest_bearing_domestic": [
        "InterestBearingDepositLiabilitiesDomestic",
        "InterestBearingDomesticDepositDemand",
    ],
    "depositos_interest_bearing_foreign": [
        "InterestBearingDepositLiabilitiesForeign",
    ],
    "emprestimos_cp": [
        "LongTermDebtCurrent",
        "DebtCurrent",
        "ShortTermBorrowings",
        "CommercialPaper",
    ],
    "short_term_borrowings": [
        "ShortTermBorrowings",
        "CommercialPaper",
    ],
    "emprestimos_lp": [
        "LongTermDebtNoncurrent",
        "LongTermDebt",
        "LongTermDebtAndCapitalLeaseObligations",
    ],
    "passivo_circulante": [
        "LiabilitiesCurrent",
    ],
    "passivo_nao_circulante": [
        "LiabilitiesNoncurrent",
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

# ---- Cash Flow Statement ----
DFC_TAGS = {
    "fco": [
        "NetCashProvidedByUsedInOperatingActivities",
        "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
    ],
    "depreciacao_amortizacao": [
        "DepreciationDepletionAndAmortization",
        "DepreciationAndAmortization",
    ],
    "fci": [
        "NetCashProvidedByUsedInInvestingActivities",
    ],
    "capex": [
        "PaymentsToAcquirePropertyPlantAndEquipment",
        "PaymentsToAcquireProductiveAssets",
    ],
    "fcf": [
        "NetCashProvidedByUsedInFinancingActivities",
    ],
    "amortizacao_divida": [
        "RepaymentsOfLongTermDebt",
        "RepaymentsOfDebt",
    ],
    "captacao_divida": [
        "ProceedsFromIssuanceOfLongTermDebt",
        "ProceedsFromIssuanceOfDebt",
    ],
    "dividendos_pagos": [
        "PaymentsOfOrdinaryDividends",
        "PaymentsOfDividends",
        "PaymentsOfDividendsCommonStock",
    ],
    "juros_pagos": [
        "InterestPaidNet",
        "InterestPaid",
    ],
    "recompra_acoes": [
        "PaymentsForRepurchaseOfCommonStock",
        "PaymentsForRepurchaseOfEquity",
    ],
}

# ---- Debt Maturity Schedule ----
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
    ],
}


# ---- Per-Share / Shares Tags (unidades especiais) ----
PER_SHARE_TAGS = {
    "lpa_diluido": [
        "EarningsPerShareDiluted",
        "EarningsPerShareBasic",
    ],
    "dividendo_por_acao": [
        "CommonStockDividendsPerShareDeclared",
        "CommonStockDividendsPerShareCashPaid",
    ],
}

SHARES_TAGS = {
    "acoes_diluidas": [
        "WeightedAverageNumberOfDilutedSharesOutstanding",
        "WeightedAverageNumberOfSharesOutstandingBasic",
    ],
    "acoes_outstanding": [
        "CommonStockSharesOutstanding",
    ],
}


# ---- Regulatory Capital Ratios (unidade "pure", não USD) ----
REGULATORY_TAGS = {
    "tier1_ratio": [
        "TierOneRiskBasedCapitalToRiskWeightedAssets",
        "CapitalAdequacyTier1RiskWeightedAssets",
    ],
    "total_capital_ratio": [
        "CapitalToRiskWeightedAssets",
    ],
    "slr": [
        "SupplementaryLeverageRatio",
    ],
    "cet1_ratio": [
        "CommonEquityTier1CapitalRatio",
        "CommonEquityTier1CapitalRequiredUnderBaselIIIToRiskWeightedAssets",
    ],
}


def resolve_tag_pure(facts_usgaap: dict, candidates: list[str],
                     form: str, period_end: str) -> float | None:
    """Resolve valor XBRL para tags com unidade 'pure' (ratios regulatórios)."""
    for tag in candidates:
        tag_data = facts_usgaap.get(tag)
        if not tag_data:
            continue
        units = tag_data.get("units", {})
        pure_data = units.get("pure")
        if not pure_data:
            continue
        matches = []
        for entry in pure_data:
            if entry.get("end") != period_end:
                continue
            entry_form = entry.get("form", "")
            if form == "10-K" and entry_form not in ("10-K", "10-K/A"):
                continue
            if form == "10-Q" and entry_form not in ("10-Q", "10-Q/A"):
                continue
            matches.append(entry)
        if matches:
            return matches[0]["val"]
    return None


def resolve_tag(facts_usgaap: dict, candidates: list[str],
                form: str, period_end: str,
                period_start: str | None = None,
                prefer_quarterly: bool = False) -> float | None:
    """Resolve valor XBRL para uma lista de tags candidatas."""
    for tag in candidates:
        tag_data = facts_usgaap.get(tag)
        if not tag_data:
            continue
        units = tag_data.get("units", {})
        usd_data = units.get("USD") or units.get("USD/shares")
        if not usd_data:
            continue
        matches = []
        for entry in usd_data:
            if entry.get("end") != period_end:
                continue
            entry_form = entry.get("form", "")
            if form == "10-K" and entry_form not in ("10-K", "10-K/A"):
                continue
            if form == "10-Q" and entry_form not in ("10-Q", "10-Q/A"):
                continue
            if period_start and "start" in entry:
                if entry.get("start") == period_start:
                    matches.append(entry)
            else:
                matches.append(entry)
        if matches:
            return matches[0]["val"]
    return None


def resolve_tag_any_unit(facts_usgaap: dict, candidates: list[str],
                         form: str, period_end: str) -> float | None:
    """Resolve valor XBRL para tags com qualquer unidade (USD/shares, shares, etc.)."""
    for tag in candidates:
        tag_data = facts_usgaap.get(tag)
        if not tag_data:
            continue
        units = tag_data.get("units", {})
        for unit_type, unit_entries in units.items():
            matches = []
            for entry in unit_entries:
                if entry.get("end") != period_end:
                    continue
                entry_form = entry.get("form", "")
                if form == "10-K" and entry_form not in ("10-K", "10-K/A"):
                    continue
                if form == "10-Q" and entry_form not in ("10-Q", "10-Q/A"):
                    continue
                matches.append(entry)
            if matches:
                return matches[0]["val"]
    return None
