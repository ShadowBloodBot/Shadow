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
STRATEGIES_WEEK = "2026-W41"
STRATEGIES_COUNT = 7

STRATEGIES = [
    {
        "title": "SMSF LRBA Liquidity Haircut",
        "hook": (
            "SMSF buyers treating the deposit as the only hurdle are missing the liquidity test "
            "that kills the LRBA before the valuer even becomes relevant."
        ),
        "mechanic": (
            "An LRBA sits inside the SMSF, but the lender still stress-tests rent, concessional "
            "contributions, admin costs, insurance premiums, and minimum liquidity after settlement. "
            "A 70% LVR deal can fail if the fund is left with no cash buffer or if members are near "
            "retirement and contribution flow is uncertain. The bare trust isolates title; it does "
            "not make the repayment invisible."
        ),
        "retail_trap": (
            "Retail execution prices the loan off LVR and ignores the fund deed, investment strategy, "
            "member age, contribution history, and post-settlement cash. Decline arrives as a "
            "liquidity failure, not a rate issue."
        ),
        "execution": [
            "**Pre-contract SMSF liquidity map** — model rent, contributions, pension phase risk, and "
            "12 months of fund expenses after stamp duty and legal costs.",
            "**Bare trust document audit** — confirm trustee names, holding trustee, and contract party "
            "before signing; post-contract fixes create lender and stamp duty friction.",
        ],
        "drop": (
            "LRBA leverage is approved against fund liquidity, not the investor's appetite for debt."
        ),
    },
    {
        "title": "Bucket Company Servicing Mirage",
        "hook": (
            "Bucket company profits look like clean tax control until the assessor treats them as "
            "trapped company capital instead of personal servicing income."
        ),
        "mechanic": (
            "A bucket company caps tax at the company rate, but retained earnings do not automatically "
            "service a personal investment loan. Extracting cash can create dividends, franking credit "
            "timing, or Div 7A loan consequences. Lenders want recurring salary, dividends, or trust "
            "distributions with evidence. A balance sheet full of retained profit is not the same as "
            "verified borrower income."
        ),
        "retail_trap": (
            "The broker uploads company financials and assumes retained profit carries through to "
            "NDI. Credit shades it to nil, then Div 7A questions start when drawings appear in the "
            "ledger without complying loan terms."
        ),
        "execution": [
            "**Income extraction calendar** — align salary, franked dividends, and trust distributions "
            "to the next 24-month borrowing window before 30 June resolutions are locked.",
            "**Div 7A ledger quarantine** — separate shareholder loans, UPEs, and genuine wages so "
            "credit and tax treatment do not contaminate each other.",
        ],
        "drop": (
            "Company profit that cannot be paid, evidenced, or serviced is not borrowing capacity."
        ),
    },
    {
        "title": "Section 100A Distribution Fallout",
        "hook": (
            "Trust distributions built for low tax can poison the next loan when Section 100A risk "
            "makes the income pattern look engineered instead of commercial."
        ),
        "mechanic": (
            "Assessors rely on taxable distributions because they are visible on returns and notices "
            "of assessment. The ATO tests whether a beneficiary distribution is part of a reimbursement "
            "agreement where someone else enjoys the cash. Adult-child allocations, circular payments, "
            "and unpaid present entitlements can turn an income solution into an audit flag and a "
            "credit weakness."
        ),
        "retail_trap": (
            "The file shows two years of distributions to beneficiaries who never received or controlled "
            "the money. Retail packaging calls it income; credit asks for bank evidence and the tax "
            "position starts to unravel."
        ),
        "execution": [
            "**Distribution evidence pack** — trustee resolution, beneficiary statement, bank movement, "
            "and commercial rationale matched before lodging with any lender.",
            "**Borrowing-year tax alignment** — do not manufacture one-off distributions purely to pass "
            "servicing; unstable income gets shaded and audited.",
        ],
        "drop": (
            "A trust distribution only works when the tax trail and the cash trail tell the same story."
        ),
    },
    {
        "title": "LMI Premium Equity Arbitrage",
        "hook": (
            "Avoiding LMI at all costs can be the expensive move when the preserved cash is the only "
            "thing keeping the next acquisition alive."
        ),
        "mechanic": (
            "At 80% LVR the borrower avoids LMI but burns deposit and stamp duty liquidity. At 85-88% "
            "LVR, capitalised LMI can preserve six figures of cash for buffers, repairs, or the next "
            "deposit. The trade is not rate versus fee; it is portfolio velocity versus equity drag, "
            "subject to NDI still clearing after the higher repayment."
        ),
        "retail_trap": (
            "Retail advice treats LMI as dead money without modelling the opportunity cost of trapped "
            "cash. Borrower pays 20% deposit, then cannot fund repairs or the second contract without "
            "a cash-out refinance at tighter policy."
        ),
        "execution": [
            "**LVR sensitivity table** — compare 80%, 85%, and 88% using capitalised LMI, post-settlement "
            "cash, and stressed repayment impact.",
            "**Cash buffer hierarchy** — preserve funds for stamp duty, vacancy, works, and next-deal "
            "deposit before chasing a clean 80% headline.",
        ],
        "drop": (
            "LMI is expensive only when the preserved equity has no higher use."
        ),
    },
    {
        "title": "Alt-Doc BAS Income Mismatch",
        "hook": (
            "Low-doc approvals fail when BAS turnover, business bank credits, and declared income "
            "tell three different stories."
        ),
        "mechanic": (
            "Alt-doc policy replaces full tax returns with BAS, accountant declarations, bank statements, "
            "or interim financials. The lender reverse-engineers sustainable income from turnover, GST "
            "patterns, margins, and account conduct. High revenue with heavy subcontractor payments "
            "does not become borrower income just because the BAS is large."
        ),
        "retail_trap": (
            "Broker submits six months of credits and an accountant letter that contradicts BAS figures. "
            "Credit applies industry margin haircuts, asks for ATO portal debt, then declines on "
            "inconsistent income evidence."
        ),
        "execution": [
            "**Triangulate income evidence** — BAS, trading account credits, and accountant declaration "
            "must reconcile before the lender applies margin shading.",
            "**ATO debt and conduct check** — clear payment plans, overdishonours, and director loan "
            "noise before alt-doc lodgement.",
        ],
        "drop": (
            "Alt-doc is not no-doc; it is forensic income reconstruction with fewer excuses."
        ),
    },
    {
        "title": "Land Tax Stamp Duty Stack",
        "hook": (
            "The deal that works at purchase price fails after state taxes, transfer duty, and land "
            "tax thresholds are stacked into the actual cash requirement."
        ),
        "mechanic": (
            "Acquisition cost is price plus duty, legal, buyer's agent fee, lender fees, and immediate "
            "holding costs. Land tax then depends on state, ownership entity, threshold, absentee "
            "status, and aggregation rules. Trust ownership can lose thresholds in some states while "
            "personal ownership can aggregate faster. The assessor sees the debt; the cashflow model "
            "must carry the tax leakage."
        ),
        "retail_trap": (
            "Retail calculators model deposit and loan only. Settlement arrives short, land tax notice "
            "lands later, and the investor funds statutory leakage from credit cards or redraw, "
            "wrecking clean deductibility."
        ),
        "execution": [
            "**State-by-state ownership map** — compare personal, trust, and company land tax outcomes "
            "before contract, not after settlement.",
            "**Settlement cash stack** — ring-fence duty, legal, first-year land tax, vacancy, and repairs "
            "outside the loan approval number.",
        ],
        "drop": (
            "Purchase price is marketing; after-tax acquisition cost is the real entry number."
        ),
    },
    {
        "title": "Guarantor Release LVR Snare",
        "hook": (
            "Family guarantees solve the first purchase and create the next bottleneck when release "
            "depends on valuation, not goodwill."
        ),
        "mechanic": (
            "A limited guarantee can avoid LMI or bridge a deposit gap, but release usually requires "
            "the secured loan to fall below the lender's target LVR using a fresh valuation. If the "
            "market is flat or the loan capitalised fees, the guarantor remains tied up. Their security "
            "can also block their own refinance or equity release."
        ),
        "retail_trap": (
            "The guarantee is sold as temporary without a release model. No valuation trigger, no "
            "principal reduction schedule, no second-lender exit check, and the family home stays "
            "encumbered through the next credit cycle."
        ),
        "execution": [
            "**Release pathway at approval** — document required valuation, target balance, repayment "
            "pace, and fallback refinance policy before the guarantee is signed.",
            "**Limit guarantee exposure** — cap the guarantee to the minimum shortfall and avoid global "
            "security language that drags unrelated family assets into the deal.",
        ],
        "drop": (
            "A guarantor loan is not released by time; it is released by LVR mathematics."
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
