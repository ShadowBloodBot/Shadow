"""Mortgage discussion calculators — educational models only, not advice."""

from dataclasses import dataclass


@dataclass
class NegGearResult:
    loan_amount: float
    annual_rent: float
    annual_interest: float
    annual_holding_costs: float
    annual_depreciation: float
    pre_tax_cashflow: float
    taxable_loss: float
    tax_benefit: float
    after_tax_cashflow: float
    marginal_rate_pct: float


def calc_negative_gearing(
    property_price: float,
    rent_weekly: float,
    mortgage_rate_pct: float,
    *,
    deposit_pct: float = 20.0,
    marginal_tax_rate_pct: float = 37.0,
    holding_cost_pct: float = 1.5,
    depreciation_pct: float = 2.0,
) -> NegGearResult:
    """Simplified IO investor model for discussion purposes."""
    loan = property_price * (1 - deposit_pct / 100)
    annual_rent = rent_weekly * 52
    annual_interest = loan * (mortgage_rate_pct / 100)
    annual_holding = property_price * (holding_cost_pct / 100)
    annual_depreciation = property_price * 0.75 * (depreciation_pct / 100)
    expenses = annual_interest + annual_holding + annual_depreciation
    pre_tax = annual_rent - expenses
    taxable_loss = max(-pre_tax, 0)
    tax_benefit = taxable_loss * (marginal_tax_rate_pct / 100)
    after_tax = pre_tax + tax_benefit
    return NegGearResult(
        loan_amount=loan,
        annual_rent=annual_rent,
        annual_interest=annual_interest,
        annual_holding_costs=annual_holding,
        annual_depreciation=annual_depreciation,
        pre_tax_cashflow=pre_tax,
        taxable_loss=taxable_loss,
        tax_benefit=tax_benefit,
        after_tax_cashflow=after_tax,
        marginal_rate_pct=marginal_tax_rate_pct,
    )


@dataclass
class RefiCheckResult:
    loan_balance: float
    current_monthly: float
    market_monthly: float
    monthly_saving: float
    annual_saving: float
    break_even_months: float | None
    indicative_new_rate_pct: float
    serviceability_pass: bool | None
    serviceability_note: str


def calc_refinance_check(
    current_rate_pct: float,
    equity_pct: float,
    income_annual: float,
    *,
    property_value: float = 800_000,
    switch_cost: float = 1_500,
    market_rate_pct: float | None = None,
    stress_buffer_pct: float = 3.0,
) -> RefiCheckResult:
    """Educational refi comparison — not a lender assessment."""
    loan = property_value * (1 - equity_pct / 100)
    if market_rate_pct is None:
        # Rough discount if strong equity
        market_rate_pct = max(current_rate_pct - (1.2 if equity_pct >= 30 else 0.6), 5.5)

    def monthly_payment(principal: float, rate_pct: float) -> float:
        r = rate_pct / 100 / 12
        n = 360
        if r == 0:
            return principal / n
        return principal * (r * (1 + r) ** n) / ((1 + r) ** n - 1)

    cur_m = monthly_payment(loan, current_rate_pct)
    mkt_m = monthly_payment(loan, market_rate_pct)
    saving = cur_m - mkt_m
    annual = saving * 12
    break_even = (switch_cost / saving) if saving > 0 else None

    stress_rate = market_rate_pct + stress_buffer_pct
    stress_m = monthly_payment(loan, stress_rate)
    # Very rough APRA-style heuristic: gross income / 12 * 0.30 vs stress repayment
    max_repay = (income_annual / 12) * 0.30
    svc_pass = stress_m <= max_repay if income_annual > 0 else None
    if income_annual <= 0:
        svc_note = "Income not provided — serviceability not assessed."
    elif svc_pass:
        svc_note = (
            f"Indicative stress repayment ${stress_m:,.0f}/mo vs ~30% gross ${max_repay:,.0f}/mo — "
            "may pass discussion-level serviceability (lender policy varies)."
        )
    else:
        svc_note = (
            f"Indicative stress repayment ${stress_m:,.0f}/mo exceeds ~30% gross ${max_repay:,.0f}/mo — "
            "worth discussing structure with a licensed broker."
        )

    return RefiCheckResult(
        loan_balance=loan,
        current_monthly=cur_m,
        market_monthly=mkt_m,
        monthly_saving=saving,
        annual_saving=annual,
        break_even_months=break_even,
        indicative_new_rate_pct=market_rate_pct,
        serviceability_pass=svc_pass,
        serviceability_note=svc_note,
    )


def fmt_currency(amount: float) -> str:
    return f"${amount:,.0f}"
