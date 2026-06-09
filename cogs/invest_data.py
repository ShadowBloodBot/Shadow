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
STRATEGIES_WEEK = "2026-W24"
STRATEGIES_COUNT = 7

STRATEGIES = [
    {
        "title": "Negative Gearing vs NDI Destruction",
        "hook": (
            "Investors obsessed with negative gearing tax refunds are systematically compressing "
            "their NDI and capping portfolio growth at two properties before APRA DTI gates engage."
        ),
        "mechanic": (
            "Each additional negatively geared asset increases assessable liabilities and reduces "
            "surplus income under the lender's HEM model. The ATO rewards the taxable loss via your "
            "marginal rate; the assessor penalises the same loss as reduced repayment capacity at "
            "+3% stress. Div 40/43 depreciation amplifies the paradox — zero cash outflow, maximum "
            "servicing drag unless add-backs are lender-accepted."
        ),
        "retail_trap": (
            "Retail brokers lodge the tax return loss position without a servicing add-back schedule. "
            "Major banks hair-cut depreciation 50–100%. No Tier-2 pivot to lenders that accept "
            "full Div 40 add-backs on IO investor facilities."
        ),
        "execution": [
            "**Pre-lodge servicing matrix** — model each property's after-tax cashflow against assessor "
            "income at +3% before contract; kill deals that breach DTI at property three.",
            "**Split IO with offset quarantine** — park surplus in offset against PPOR non-deductible "
            "debt first; never cross-collateralise investment debt with owner-occupied security.",
        ],
        "drop": (
            "The tax refund is a lagging reimbursement; the servicing decline is a forward constraint. "
            "Elite portfolios optimise the assessor first, the ATO second."
        ),
    },
    {
        "title": "Trust Retained Earnings vs Borrowing Power",
        "hook": (
            "Discretionary trust beneficiaries leaving profits undistributed to minimise personal "
            "tax are unknowingly erasing the income stream assessors require for the next purchase."
        ),
        "mechanic": (
            "Assessors want consistent, attributable personal income — distributions declared on "
            "trust tax returns with matching beneficiary notices. Retained trust profits sit in "
            "the entity; they do not service personal debt unless the lender accepts company/trust "
            "servicing (rare on residential). Section 100A scrutiny intensifies when distributions "
            "are reversed or selectively allocated to low-tax beneficiaries without commercial logic."
        ),
        "retail_trap": (
            "Accountant minimises tax via undistributed trust income; broker submits personal "
            "PAYG only. Application fails NDI. No Part IVA/100A review before year-end distribution "
            "decisions are locked."
        ),
        "execution": [
            "**Align 30 June distribution to 24-month borrowing plan** — distribute minimum assessable "
            "income required for pre-approval, document trustee resolution before 30 June.",
            "**Tier-2 policy scan** — Pepper, Liberty, and selected non-banks assess trust distributions "
            "with 2-year averaging; match lender before trust deed is amended.",
        ],
        "drop": (
            "Undistributed trust profits are invisible to the assessor and radioactive to the ATO "
            "if distribution patterns lack commercial substance."
        ),
    },
    {
        "title": "Debt Recycling & Div 7A Quarantine",
        "hook": (
            "Paying down PPOR principal without a debt-recycling architecture permanently destroys "
            "deductible capacity that cannot be reconstructed at the same LVR."
        ),
        "mechanic": (
            "Non-deductible PPOR debt converts to deductible investment debt only when borrowed "
            "funds trace to an income-producing asset — not via redraw on a mixed-purpose loan. "
            "Split facilities: PPOR P&I segregated from investment IO. Surplus cash flows through "
            "offset against PPOR, then equity release via standalone investment split with clean "
            "bank tracing. Div 7A complicates bucket-company extraction — UPEs must be managed on "
            "complying loan terms or franked dividends."
        ),
        "retail_trap": (
            "Client redraws $200k from PPOR to fund deposit; single loan account, mixed purpose. "
            "ATO apportions interest; assessor treats entire facility as owner-occupied. "
            "No split, no accountant tracing memo, audit exposure on full interest claim."
        ),
        "execution": [
            "**Isolate non-deductible P&R debt** in split IO facilities before drawing Div 7A or "
            "equity release, quarantining cash flow for aggressive debt recycling.",
            "**Document fund flow** — settlement statement, loan purpose letter, and accountant "
            "interest apportionment schedule at drawdown, not at audit.",
        ],
        "drop": (
            "The ATO traces dollars; the assessor traces repayment capacity. Mixed-purpose loans fail both."
        ),
    },
    {
        "title": "HECS & Bonus Income — Lender Arbitrage",
        "hook": (
            "PAYG investors on HECS with performance bonuses are failing serviceability at majors "
            "while Tier-1 alternate policies would have cleared the same file at identical LVR."
        ),
        "mechanic": (
            "CBA and Westpac typically shade bonus income to 80% and apply HECS repayment as a "
            "liability in the serviceability calculator. NAB and Macquarie policy varies by channel "
            "and employment tenure. Non-banks may exclude HECS where PAYG tenure exceeds 12 months "
            "and bonus is contractual. The spread on borrowing power can exceed $150k on a $200k "
            "bonus component — pure policy arbitrage, not rate shopping."
        ),
        "retail_trap": (
            "Borrower applies direct to their transaction bank; HECS indexed at 4.7% shades serviceability. "
            "Bonus treated as occasional. No liability optimisation — credit card limits not reduced "
            "pre-lodgement."
        ),
        "execution": [
            "**Liability strip 90 days pre-lodgement** — close unused facilities, reduce limits, "
            "confirm HECS balance for lender-specific treatment.",
            "**Lender matrix on bonus + HECS** before rate comparison — policy beats basis points on "
            "high-income PAYG files.",
        ],
        "drop": (
            "The cheapest rate is irrelevant when the policy rejects the income you actually earn."
        ),
    },
    {
        "title": "Self-Employed NPR & Add-Back Architecture",
        "hook": (
            "Self-employed borrowers presenting accountant-prepared financials without an NPR "
            "add-back schedule are being assessed on taxable profit — not cash flow — and declined "
            "at lenders that would accept the same file with correct presentation."
        ),
        "mechanic": (
            "Net Profit Before Tax in company/trust returns understates servicing capacity. Lenders "
            "allow add-backs: depreciation (Div 40/43), one-off expenses, director salaries above "
            "market, interest on business debt. Tier-2 lenders often accept 100% depreciation add-back; "
            "majors hair-cut. BAS quarterly revenue can support alt-doc pathways where full-doc "
            "tax returns show suppressed profit via legitimate deductions."
        ),
        "retail_trap": (
            "Broker submits company tax return net profit as assessable income. No add-back table. "
            "No director dividend/distribution history. Decline. Client told they cannot borrow "
            "when alternate lender policy accepts $180k add-backs on a $90k taxable profit."
        ),
        "execution": [
            "**Build add-back schedule** — line-item depreciation, amortisation, non-recurring expenses "
            "with accountant sign-off before credit submission.",
            "**Match entity structure to lender** — company vs trust vs sole trader changes which "
            "add-backs are accepted; restructure before lodgement, not after decline.",
        ],
        "drop": (
            "Taxable profit is an ATO construct; assessable income is a lender negotiation. "
            "They are not the same number."
        ),
    },
    {
        "title": "Cross-Collateralisation Exit Trap",
        "hook": (
            "Investors accepting cross-collateralised security across PPOR and investment properties "
            "are locking exit costs that exceed years of rental yield on a single asset."
        ),
        "mechanic": (
            "Cross-collateral links valuations — releasing one property triggers revaluation of all. "
            "Selling an investment can force PPOR LVR breach, triggering margin call or forced sale. "
            "Standalone security per asset: separate lenders or separate splits with no-all-monies "
            "clause review. Exit cost = break fees × linked facilities + revaluation shortfall + "
            "LMI re-trigger if LVR resets above 80%."
        ),
        "retail_trap": (
            "Bank offers rate discount for bundling PPOR + inv #1 + inv #2. Client signs global "
            "security. Sells inv #1 in downturn; bank revalues portfolio, PPOR now 85% LVR, "
            "PIF or LMI top-up required at worst liquidity moment."
        ),
        "execution": [
            "**Standalone security per asset** — separate loan splits, no cross-collateral deed; "
            "accept marginal rate premium for exit optionality.",
            "**Equity release via cash-out on standalone inv split** — not top-up on PPOR linked to portfolio.",
        ],
        "drop": (
            "Bundled security is a lender liquidity preference masquerading as a client rate benefit."
        ),
    },
    {
        "title": "IO Expiry Without Servicing Bridge",
        "hook": (
            "Investors on five-year IO terms treating expiry as a distant admin task are facing "
            "forced P&I conversion that will breach DTI on their next purchase — or at renewal."
        ),
        "mechanic": (
            "IO expiry converts to P&I at remaining term (often 20–25 years), spiking monthly "
            "commitments by 40–60%. Assessors model the post-IO repayment now on new applications. "
            "Refinance to new IO requires full re-serviceability at current rates + buffer. "
            "Portfolio investors hit stacking effect: three IO expiries in 18 months = triple "
            "commitment spike unless staggered at origination."
        ),
        "retail_trap": (
            "Broker sets IO because payment fits; no diary on expiry, no stagger plan, no "
            "refinance pathway. Client returns at month 57; rates higher, DTI tighter, trapped."
        ),
        "execution": [
            "**Stagger IO terms at settlement** — 3yr / 5yr / 5yr across portfolio, not identical expiry.",
            "**Model post-IO P&I at application** — if surplus goes negative at conversion, fix structure now.",
        ],
        "drop": (
            "IO is a servicing deferral, not a repayment elimination. The assessor always counts the cliff."
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
