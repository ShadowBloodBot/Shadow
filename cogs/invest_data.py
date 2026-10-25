"""Curated AU property picks and mortgage strategy content for invest_bot."""

DISCLAIMER = (
    "Educational discussion only — not personal financial advice. "
    "Talk to a licensed Australian mortgage broker for your situation."
)

DISCLAIMER_SHORT = "Educational discussion only — not personal financial advice."

# type: rental = yield-focused, growth = capital-growth-focused
PROPERTIES = [
    {"id": "parra-2br-unit", "type": "rental", "suburb": "Parramatta", "state": "NSW",
     "price": 620000, "beds": 2, "ptype": "Unit", "rent_wk": 580, "yield": 4.9,
     "hook": "Strong tenant demand near transport and university corridor."},
    {"id": "merrylands-3br-house", "type": "rental", "suburb": "Merrylands", "state": "NSW",
     "price": 980000, "beds": 3, "ptype": "House", "rent_wk": 750, "yield": 4.0,
     "hook": "Family rental stock with consistent enquiry in Greater Western Sydney."},
    {"id": "geelong-2br-unit", "type": "rental", "suburb": "Geelong", "state": "VIC",
     "price": 480000, "beds": 2, "ptype": "Unit", "rent_wk": 480, "yield": 5.2,
     "hook": "Affordable entry with solid yield outside Melbourne CBD."},
    {"id": "logan-4br-house", "type": "rental", "suburb": "Logan Central", "state": "QLD",
     "price": 650000, "beds": 4, "ptype": "House", "rent_wk": 620, "yield": 5.0,
     "hook": "Large-format housing popular with multi-income tenant profiles."},
    {"id": "salisbury-3br-house", "type": "rental", "suburb": "Salisbury", "state": "SA",
     "price": 580000, "beds": 3, "ptype": "House", "rent_wk": 520, "yield": 4.7,
     "hook": "Northern Adelaide pocket with improving rental tightness."},
    {"id": "braddon-1br-unit", "type": "rental", "suburb": "Braddon", "state": "ACT",
     "price": 520000, "beds": 1, "ptype": "Unit", "rent_wk": 550, "yield": 5.5,
     "hook": "Inner-city unit market with high occupancy near civic employment."},
    {"id": "maylands-2br-unit", "type": "growth", "suburb": "Maylands", "state": "WA",
     "price": 550000, "beds": 2, "ptype": "Unit", "growth_5y": 6.8,
     "hook": "Rail-linked infill suburb with lifestyle-led buyer demand."},
    {"id": "mooloolaba-2br-unit", "type": "growth", "suburb": "Mooloolaba", "state": "QLD",
     "price": 890000, "beds": 2, "ptype": "Unit", "growth_5y": 7.2,
     "hook": "Coastal corridor with interstate migration tailwinds."},
    {"id": "footscray-2br-unit", "type": "growth", "suburb": "Footscray", "state": "VIC",
     "price": 580000, "beds": 2, "ptype": "Unit", "growth_5y": 5.9,
     "hook": "Inner-west gentrification and transport upgrades support values."},
    {"id": "newcastle-3br-house", "type": "growth", "suburb": "Newcastle", "state": "NSW",
     "price": 920000, "beds": 3, "ptype": "House", "growth_5y": 6.1,
     "hook": "Regional city re-rate story with infrastructure and employment depth."},
    {"id": "north-hobart-3br-house", "type": "growth", "suburb": "North Hobart", "state": "TAS",
     "price": 780000, "beds": 3, "ptype": "House", "growth_5y": 5.4,
     "hook": "Tight listing supply in character suburbs near CBD."},
    {"id": "belconnen-2br-unit", "type": "growth", "suburb": "Belconnen", "state": "ACT",
     "price": 490000, "beds": 2, "ptype": "Unit", "growth_5y": 5.0,
     "hook": "Government-adjacent employment base supports resale liquidity."},
]

# Mb daily strategy posts — 7 entries per ISO week (Mon=index 0 … Sun=index 6).
# Replaced weekly by Cursor Automation — see .cursor/rules/mb-daily-strategy-post.mdc
STRATEGIES_WEEK = "2026-W44"
STRATEGIES_COUNT = 7

STRATEGIES = [
    {
        "title": "Trust UPE Servicing Contamination",
        "hook": (
            "Trust income only helps credit when the unpaid present entitlement and the cash trail "
            "survive both lender scrutiny and Section 100A pressure."
        ),
        "mechanic": (
            "A family trust can distribute profit to beneficiaries or a bucket company, but an unpaid "
            "present entitlement is not automatically usable servicing income. Credit wants tax returns, "
            "NOAs, trustee resolutions, and bank movement showing who actually controlled the money. "
            "Where the distribution sits unpaid while another party enjoys the cash, Section 100A risk "
            "and lender income shading arrive in the same file."
        ),
        "retail_trap": (
            "Retail packaging uploads the trust return and treats every distribution as borrower income. "
            "The assessor asks for beneficiary statements and bank credits, finds circular movements or "
            "stale UPEs, then shades the income while the accountant has to explain the reimbursement risk."
        ),
        "execution": [
            "**UPE ageing schedule** — separate paid distributions, unpaid entitlements, beneficiary loans, "
            "and bucket company balances before the loan file is touched.",
            "**Cash-control evidence** — match trustee minutes, NOAs, and bank transfers so servicing income "
            "does not contradict the tax position.",
        ],
        "drop": (
            "A trust distribution that never moves cash is tax theatre, not borrowing power."
        ),
    },
    {
        "title": "SMSF Related-Party Lease Dead Zone",
        "hook": (
            "The SMSF property deal dies when the asset use, tenant, and lease terms breach the rulebook "
            "before the LRBA policy even starts."
        ),
        "mechanic": (
            "An SMSF can borrow under an LRBA for a single acquirable asset, but residential property cannot "
            "be acquired from or leased to related parties. Business real property has a different lane, with "
            "commercial lease terms, market rent, and clean payment conduct. The lender overlays liquidity, "
            "member contributions, fund expenses, bare trust documents, and post-settlement cash."
        ),
        "retail_trap": (
            "The broker treats SMSF as a deposit-and-LVR exercise and misses the related-party use problem. "
            "Credit asks for the lease, fund deed, investment strategy, and bare trustee documents; the file "
            "collapses because the tenant or vendor relationship was wrong from contract day."
        ),
        "execution": [
            "**Related-party map** — identify vendor, tenant, guarantor, trustee, and member links before "
            "contract exchange.",
            "**LRBA document stack** — align bare trust, fund deed, investment strategy, lease, and liquidity "
            "buffer before valuation spend.",
        ],
        "drop": (
            "SMSF leverage is useless when the asset fails the super law entry test."
        ),
    },
    {
        "title": "Redraw Debt Recycling Pollution",
        "hook": (
            "Debt recycling fails when clean investment debt is mixed with private redraw movements and the "
            "interest trail loses deductibility."
        ),
        "mechanic": (
            "The tax outcome follows use of borrowed funds, not the label on the loan. A split used to buy "
            "income-producing assets can produce deductible interest; the same split polluted by holidays, "
            "cars, school fees, or PPOR renovations becomes apportioned. Offset preserves loan purpose; redraw "
            "can create a fresh borrowing purpose each time funds are pulled back out."
        ),
        "retail_trap": (
            "Retail advice says 'use the redraw' because the rate is low. Six months later the loan account has "
            "dividends, groceries, renovations, and ETF purchases through one split, leaving the accountant to "
            "reconstruct deductibility line by line."
        ),
        "execution": [
            "**Purpose-isolated splits** — create separate loan splits for each investment use and do not run "
            "private expenses through them.",
            "**Offset-only cash parking** — store surplus cash in offset, not redraw, when the original debt "
            "purpose must stay clean.",
        ],
        "drop": (
            "Deductibility is traced by money movement, not by intent after the account is polluted."
        ),
    },
    {
        "title": "Div 7A Minimum Repayment Drag",
        "hook": (
            "Div 7A does not just create tax friction; it can consume NDI through compulsory repayments that "
            "credit policy will not ignore."
        ),
        "mechanic": (
            "Shareholder loans and UPEs to a company need complying terms or they risk deemed dividends. Once "
            "a Div 7A loan exists, minimum yearly repayments become a real cashflow obligation. Lenders can treat "
            "those repayments as commitments, shade company income extraction, and question drawings that look "
            "like living expenses funded by the company balance sheet."
        ),
        "retail_trap": (
            "The file is packaged off taxable income while the balance sheet shows director loans moving the "
            "other way. Credit asks for loan agreements and repayments, then loads the obligation into servicing "
            "or removes the income that was meant to carry the deal."
        ),
        "execution": [
            "**Div 7A servicing schedule** — model principal-and-interest minimum repayments beside mortgage "
            "commitments before applying.",
            "**Drawing discipline** — separate wages, dividends, reimbursements, and shareholder loans so credit "
            "does not recast lifestyle spend as unstable income.",
        ],
        "drop": (
            "Company cash borrowed personally is still debt when the assessor reads the ledger."
        ),
    },
    {
        "title": "Part IVA Round-Robin Refinance",
        "hook": (
            "Circular refinance steps built only to manufacture deductions can trigger anti-avoidance risk and "
            "still fail lender common sense."
        ),
        "mechanic": (
            "Refinancing can preserve or reset loan purpose depending on what debt is repaid and what asset the "
            "borrowed funds support. Part IVA pressure appears when the dominant purpose is tax benefit rather "
            "than commercial funding. Round-robin repayments, related-party loans, back-to-back redraws, and "
            "paper-only interest flows give the ATO and credit assessor the same problem: form without substance."
        ),
        "retail_trap": (
            "The broker chases a cash-out approval and ignores why the funds move through three related accounts. "
            "Credit asks for statements and purpose evidence; the tax adviser sees a scheme narrative forming "
            "around the deduction."
        ),
        "execution": [
            "**Purpose ledger before refinance** — document original debt, payout destination, new funds use, "
            "and commercial reason for each step.",
            "**Related-party substance test** — support every internal loan with terms, repayments, security, "
            "and bank movement that would exist without the tax result.",
        ],
        "drop": (
            "A refinance step with no commercial job is just evidence for the denial file."
        ),
    },
    {
        "title": "HECS Bonus Shading Split",
        "hook": (
            "A high PAYG package can still miss serviceability when HECS and bonus shading hit the same income "
            "line from opposite sides."
        ),
        "mechanic": (
            "HECS is assessed as a repayment drag against gross income, while bonus, overtime, commission, RSUs, "
            "and allowances are treated differently across lenders. Some use two-year averages, some shade to "
            "80%, some exclude irregular income, and some will consider current-year evidence. APRA buffer and "
            "DTI controls then compress the approved loan even when payslips look strong."
        ),
        "retail_trap": (
            "Retail submission uses total remuneration from the employment contract and forgets HECS, probation, "
            "variable bonus history, and policy caps. The pre-approval shrinks when credit rebuilds income from "
            "YTD payslips and prior payment summaries."
        ),
        "execution": [
            "**Income component matrix** — split base, bonus, overtime, allowances, RSUs, and HECS across lender "
            "policy before ordering valuations.",
            "**Evidence timing control** — lodge after bonus payment, YTD consistency, or probation expiry when "
            "policy requires it.",
        ],
        "drop": (
            "Gross salary is not capacity when policy taxes the deductions and discounts the upside."
        ),
    },
    {
        "title": "Fixed-Variable IO Cliff",
        "hook": (
            "The fixed-rate IO loan that looked safe at settlement becomes a servicing cliff when expiry, revert "
            "rate, and principal reset land together."
        ),
        "mechanic": (
            "Fixed and variable splits manage rate risk, but interest-only expiry changes the repayment basis. "
            "When the IO term ends, remaining principal is amortised over the shortened residual term, often at "
            "a higher revert rate. Lenders assess the proposed and existing debts under buffered repayments, so "
            "an investor can be trapped with equity but no NDI to refinance."
        ),
        "retail_trap": (
            "Retail structuring celebrates the cheap IO payment and sets no expiry ladder. Three splits roll off "
            "inside one quarter, rent is shaded, living expenses are updated, and the refinance fails despite a "
            "healthy valuation."
        ),
        "execution": [
            "**Expiry ladder** — stagger fixed and IO maturities so no single quarter carries the whole repayment "
            "reset.",
            "**Residual-term stress test** — calculate repayments on the remaining P&I term at buffered rates, "
            "not the current IO payment.",
        ],
        "drop": (
            "Equity does not refinance a portfolio when the IO cliff has already destroyed NDI."
        ),
    },
]


def strategy_index_for_weekday(weekday: int | None = None) -> int:
    """Map Australia/Sydney weekday to STRATEGIES index (Mon=0 … Sun=6)."""
    if weekday is None:
        from zoneinfo import ZoneInfo
        from datetime import datetime
        weekday = datetime.now(ZoneInfo("Australia/Sydney")).weekday()
    return weekday % STRATEGIES_COUNT


def strategy_for_today() -> dict:
    if len(STRATEGIES) != STRATEGIES_COUNT:
        raise ValueError(
            f"STRATEGIES must contain exactly {STRATEGIES_COUNT} entries for weekday mapping; "
            f"got {len(STRATEGIES)} (week {STRATEGIES_WEEK})"
        )
    return STRATEGIES[strategy_index_for_weekday()]


def _clip(text: str, limit: int = 1024) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def strategy_embed_parts(item: dict) -> dict:
    """Build title, description, and field list for Mb daily strategy Discord embed."""
    if "hook" in item:
        title = f"📋 Daily Strategy — {item['title']}"
        description = _clip(f"**The Hook**\n{item['hook']}", 4096)
        fields = [
            ("The Mechanic", _clip(item["mechanic"])),
            ("The Retail Trap", _clip(item["retail_trap"])),
            ("The Execution", _clip("\n".join(f"• {line}" for line in item["execution"]))),
            ("The Drop", _clip(item["drop"])),
        ]
        if item.get("source"):
            ref = item["source"]
            if item.get("link"):
                ref = f"{ref}\n{item['link']}"
            fields.append(("Reference", _clip(ref)))
        return {"title": title, "description": description, "fields": fields}

    # Legacy weekly format fallback
    return {
        "title": f"📋 Daily Strategy — {item['title']}",
        "description": item.get("body", ""),
        "fields": [
            ("Source", item["source"]),
            ("Read more", item.get("link", "—")),
        ] if item.get("source") else [],
    }

# Top Sydney suburbs for curated daily rotation (Week 1–4 engagement loop)
SYDNEY_DAILY_ROTATION = [
    "Parramatta", "Croydon Park", "Merrylands", "Blacktown", "Liverpool",
    "Auburn", "Bankstown", "Penrith", "Ryde", "Hurstville",
]

WEEKLY_DIGEST_LINES = [
    "RBA cash rate — check latest decision at rba.gov.au/statistics/cash-rate/",
    "Domain weekly market wrap — indicative clearance and listing trends nationally.",
    "Investor focus: compare gross yield vs 12m growth in corridors you are researching.",
    "Broker discussion point: stress-test at +3% above your quoted rate before committing.",
]
