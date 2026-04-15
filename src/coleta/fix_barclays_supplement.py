"""
Fix Barclays PLC supplement_data.json:
1. Field mapping fixes (avg_total_deposits, avg_loans, loan_to_deposit, nco_ratio)
2. Extract credit quality data from FY Results Announcement PDFs (Stage 3, ECL, total capital ratio)
3. Extract wholesale funding maturity (cronograma) from FY-2025 PDF
4. Convert all GBP values to USD using fx_rate

All credit risk data comes from year-end FY PDFs only (most detailed).
Quarterly data that isn't year-end gets year-end values carried (point-in-time balances).
"""

import json
import os
import re
import pdfplumber

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
SUPPLEMENT_PATH = r"G:\Meu Drive\Análise de Crédito Financeiras\BCS\Dados_EDGAR\supplement_data.json"
DOCS_PATH = r"G:\Meu Drive\Análise de Crédito Financeiras\BCS\Documentos"

# ---------------------------------------------------------------------------
# Hard-coded annual credit risk data extracted from FY PDFs
# (year-end point-in-time balances, in GBP millions)
# Source: "Loans and advances at amortised cost by geography" tables
# ---------------------------------------------------------------------------
# Format: {year_end_date: {gross_loans, stage3, ecl, total_cap_ratio}}
# gross_loans = Total loans and advances at amortised cost (excl debt securities)
# stage3 = Stage 3 excluding POCI (= NPL equivalent under IFRS)
# ecl = Total impairment allowance on loans
# total_cap_ratio = Total regulatory capital ratio (%)

ANNUAL_CREDIT_DATA = {
    "2021-12-31": {
        "gross_loans_gbp_m": 367193,  # FY-2022 PDF p31 comparative
        "stage3_gbp_m": 7235,
        "ecl_gbp_m": 5742,
        "total_cap_ratio": 0.223,     # FY-2021 PDF p50
        "deposits_gbp_bn": 519,       # FY-2021 PDF p47
        "loans_bs_gbp_bn": 361,       # FY-2021 PDF p47 (balance sheet loans)
        "loan_deposit_ratio": 0.70,    # From deposit page
    },
    "2022-12-31": {
        "gross_loans_gbp_m": 358842,  # FY-2023 PDF p33 comparative
        "stage3_gbp_m": 7086,
        "ecl_gbp_m": 5550,
        "total_cap_ratio": 0.208,     # FY-2022 PDF p57
        "deposits_gbp_bn": 546,
        "loans_bs_gbp_bn": 399,
        "loan_deposit_ratio": 0.73,
    },
    "2023-12-31": {
        "gross_loans_gbp_m": 348468,  # FY-2024 PDF p36 comparative
        "stage3_gbp_m": 7191,
        "ecl_gbp_m": 5721,
        "total_cap_ratio": 0.201,     # FY-2023 PDF p57
        "deposits_gbp_bn": 539,
        "loans_bs_gbp_bn": 399,
        "loan_deposit_ratio": 0.74,
    },
    "2024-12-31": {
        "gross_loans_gbp_m": 351343,  # FY-2025 PDF p33 (as at 31.12.24)
        "stage3_gbp_m": 7359,
        "ecl_gbp_m": 5070,
        "total_cap_ratio": 0.196,     # FY-2024 PDF p62
        "deposits_gbp_bn": 561,
        "loans_bs_gbp_bn": 414,
        "loan_deposit_ratio": 0.74,
    },
    "2025-12-31": {
        "gross_loans_gbp_m": 366812,  # FY-2025 PDF p32
        "stage3_gbp_m": 7530,
        "ecl_gbp_m": 5289,
        "total_cap_ratio": 0.204,     # FY-2025 PDF p59
        "deposits_gbp_bn": 586,
        "loans_bs_gbp_bn": 430,
        "loan_deposit_ratio": 0.73,
    },
}

# Wholesale funding maturity from FY-2025 PDF p57 (as at 31.12.25, in GBP bn)
WHOLESALE_FUNDING_FY2025 = {
    "as_at": "2025-12-31",
    "currency": "GBP",
    "buckets": [
        {"label": "<1 month", "gbp_bn": 10.4},
        {"label": "1-3 months", "gbp_bn": 17.0},
        {"label": "3-6 months", "gbp_bn": 31.5},
        {"label": "6-12 months", "gbp_bn": 25.0},
        {"label": "1-2 years", "gbp_bn": 21.2},
        {"label": "2-3 years", "gbp_bn": 22.7},
        {"label": "3-4 years", "gbp_bn": 19.3},
        {"label": "4-5 years", "gbp_bn": 13.8},
        {"label": ">5 years", "gbp_bn": 59.2},
    ],
    "total_gbp_bn": 220.1,
}


def get_year_end(periodo: str) -> str:
    """Return the year-end date for a given period (e.g. 2025-03-31 -> 2024-12-31)."""
    yr = int(periodo[:4])
    month = int(periodo[5:7])
    if month == 12:
        return f"{yr}-12-31"
    else:
        return f"{yr - 1}-12-31"


def get_most_recent_year_end(periodo: str) -> str:
    """Return the most recent year-end at or before the period."""
    yr = int(periodo[:4])
    month = int(periodo[5:7])
    if month == 12:
        return f"{yr}-12-31"
    return f"{yr - 1}-12-31"


def fix_supplement():
    # Load existing data
    with open(SUPPLEMENT_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    print(f"Loaded {len(data)} quarters from supplement_data.json")

    for q in data:
        periodo = q["periodo"]
        fx = q["fx_rate"]
        trimestre = q["trimestre"]

        # -------------------------------------------------------------------
        # 1. Field mapping fixes
        # -------------------------------------------------------------------
        avg = q.get("avg_balances", {})

        # Copy avg_customer_deposits -> avg_total_deposits
        if "avg_customer_deposits" in avg:
            avg["avg_total_deposits"] = avg["avg_customer_deposits"]

        # Copy avg_customer_loans -> avg_loans
        if "avg_customer_loans" in avg:
            avg["avg_loans"] = avg["avg_customer_loans"]

        # Calculate loan_to_deposit ratio
        if avg.get("avg_customer_loans") and avg.get("avg_customer_deposits"):
            avg["loan_to_deposit"] = round(
                avg["avg_customer_loans"] / avg["avg_customer_deposits"], 4
            )

        q["avg_balances"] = avg

        # Copy loan_loss_rate -> nco_ratio (annualized loan loss rate)
        yr = q.get("yields_rates", {})
        if "loan_loss_rate" in yr and yr["loan_loss_rate"] is not None:
            yr["nco_ratio"] = yr["loan_loss_rate"]

        q["yields_rates"] = yr

        # -------------------------------------------------------------------
        # 2. Add credit quality data from FY PDFs (year-end point-in-time)
        # -------------------------------------------------------------------
        # Use the most recent year-end data available
        ye = get_most_recent_year_end(periodo)
        annual = ANNUAL_CREDIT_DATA.get(ye)

        cq = q.get("credit_quality", {})

        if annual:
            # Convert GBP m to USD m
            ye_fx = q["fx_rate"]  # Use quarter's own fx rate for conversion

            # Gross loans (carteira_credito_bruta)
            cq["carteira_credito_bruta"] = round(annual["gross_loans_gbp_m"] * ye_fx, 1)

            # Impairment allowance (provisao_acumulada)
            cq["provisao_acumulada"] = round(annual["ecl_gbp_m"] * ye_fx, 1)

            # Stage 3 = NPL
            cq["npl"] = round(annual["stage3_gbp_m"] * ye_fx, 1)

            # NPL ratio
            if annual["gross_loans_gbp_m"] > 0:
                cq["npl_ratio"] = round(
                    annual["stage3_gbp_m"] / annual["gross_loans_gbp_m"], 4
                )

            # Coverage ratio (ECL / Stage 3)
            if annual["stage3_gbp_m"] > 0:
                cq["coverage_ratio"] = round(
                    annual["ecl_gbp_m"] / annual["stage3_gbp_m"], 4
                )

            # Reserve ratio (ECL / gross loans)
            if annual["gross_loans_gbp_m"] > 0:
                cq["reserve_ratio"] = round(
                    annual["ecl_gbp_m"] / annual["gross_loans_gbp_m"], 4
                )

        q["credit_quality"] = cq

        # -------------------------------------------------------------------
        # 3. Add total capital ratio to capital section
        # -------------------------------------------------------------------
        cap = q.get("capital", {})

        if annual and "total_cap_ratio" in annual:
            # For year-end quarters, use the exact ratio
            if periodo.endswith("12-31"):
                cap["total_capital_ratio"] = annual["total_cap_ratio"]
            else:
                # For non-year-end, use the most recent year-end value
                cap["total_capital_ratio"] = annual["total_cap_ratio"]

        q["capital"] = cap

    # -----------------------------------------------------------------------
    # 4. Add wholesale funding cronograma to the most recent quarter (4Q25)
    # -----------------------------------------------------------------------
    last_q = data[-1]
    if last_q["periodo"] == "2025-12-31":
        fx_4q25 = last_q["fx_rate"]
        cronograma = []
        for bucket in WHOLESALE_FUNDING_FY2025["buckets"]:
            cronograma.append({
                "faixa": bucket["label"],
                "valor_usd_m": round(bucket["gbp_bn"] * fx_4q25 * 1000, 1),
                "valor_gbp_bn": bucket["gbp_bn"],
            })
        last_q["cronograma_divida"] = {
            "as_at": WHOLESALE_FUNDING_FY2025["as_at"],
            "total_usd_m": round(WHOLESALE_FUNDING_FY2025["total_gbp_bn"] * fx_4q25 * 1000, 1),
            "total_gbp_bn": WHOLESALE_FUNDING_FY2025["total_gbp_bn"],
            "faixas": cronograma,
        }

    # -----------------------------------------------------------------------
    # Save
    # -----------------------------------------------------------------------
    with open(SUPPLEMENT_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"\nSaved updated supplement_data.json with {len(data)} quarters")

    # Print last 2 quarters for verification
    print("\n" + "=" * 80)
    print("VERIFICATION: Last 2 quarters")
    print("=" * 80)
    for q in data[-2:]:
        print(f"\n--- {q['trimestre']} ({q['periodo']}) ---")
        print(f"  fx_rate: {q['fx_rate']}")

        avg = q.get("avg_balances", {})
        print(f"  avg_balances:")
        print(f"    avg_customer_deposits: {avg.get('avg_customer_deposits'):,.0f}")
        print(f"    avg_total_deposits:    {avg.get('avg_total_deposits'):,.0f}")
        print(f"    avg_customer_loans:    {avg.get('avg_customer_loans'):,.0f}")
        print(f"    avg_loans:             {avg.get('avg_loans'):,.0f}")
        print(f"    loan_to_deposit:       {avg.get('loan_to_deposit')}")

        yr = q.get("yields_rates", {})
        print(f"  yields_rates:")
        print(f"    nim:            {yr.get('nim')}")
        print(f"    loan_loss_rate: {yr.get('loan_loss_rate')}")
        print(f"    nco_ratio:      {yr.get('nco_ratio')}")

        cap = q.get("capital", {})
        print(f"  capital:")
        print(f"    cet1_ratio:          {cap.get('cet1_ratio')}")
        print(f"    total_capital_ratio:  {cap.get('total_capital_ratio')}")

        cq = q.get("credit_quality", {})
        print(f"  credit_quality:")
        print(f"    loan_loss_rate_bps:    {cq.get('loan_loss_rate_bps')}")
        print(f"    carteira_credito_bruta: {cq.get('carteira_credito_bruta'):,.1f}" if cq.get('carteira_credito_bruta') else "    carteira_credito_bruta: N/A")
        print(f"    provisao_acumulada:     {cq.get('provisao_acumulada'):,.1f}" if cq.get('provisao_acumulada') else "    provisao_acumulada: N/A")
        print(f"    npl:                    {cq.get('npl'):,.1f}" if cq.get('npl') else "    npl: N/A")
        print(f"    npl_ratio:              {cq.get('npl_ratio')}")
        print(f"    coverage_ratio:         {cq.get('coverage_ratio')}")
        print(f"    reserve_ratio:          {cq.get('reserve_ratio')}")

        if "cronograma_divida" in q:
            cr = q["cronograma_divida"]
            print(f"  cronograma_divida:")
            print(f"    total_usd_m: {cr['total_usd_m']:,.1f}")
            for f_item in cr["faixas"]:
                print(f"      {f_item['faixa']:>15}: ${f_item['valor_usd_m']:,.1f}m (GBP {f_item['valor_gbp_bn']}bn)")


if __name__ == "__main__":
    fix_supplement()
