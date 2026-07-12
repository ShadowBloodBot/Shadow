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
STRATEGIES_WEEK = "2026-W29"
STRATEGIES_COUNT = 7

STRATEGIES = [
    {
        "title": 'SMSF LRBA Liquidity Covenant',
        "hook": (
            'SMSF trustees buying property on LRBA terms are confusing concessional leverage with '
            'ordinary investor debt and ignoring the cash-flow lock inside the fund.'
        ),
        "mechanic": (
            'An LRBA quarantines recourse to the single acquirable asset, but the assessor still wants '
            'fund liquidity, contribution history, rent shading, insurance premiums, and pension-phase '
            'obligations tested together. Rental income is not free cash flow when the fund must '
            'preserve minimum liquidity and cannot patch deficits with casual member redraws. '
            'Contribution caps and preservation rules make a servicing miss structurally different from '
            'a personal investment loan.'
        ),
        "retail_trap": (
            'Retail lending treats the SMSF like a high-deposit borrower and models rent against '
            'repayments only. The deed, bare trust, related-party loan terms, liquidity buffer, and '
            'investment strategy minutes arrive after credit review. A bare trust defect or undocumented '
            'related-party rate can stall settlement while the fund is already exposed to duty and '
            'contract dates.'
        ),
        "execution": [
            '**LRBA pre-credit pack** — deed, bare trust, investment strategy, liquidity minute, rent lease, and member contribution trail before valuation order.',
            '**Fund cash-flow stress** — model rent at lender shade plus insurance, admin, pension minimums, and buffer inside the SMSF, not in personal offset.',
        ],
        "drop": 'SMSF leverage is not personal leverage in a super wrapper; the cash is trapped where the covenant sits.',
    },
    {
        "title": 'Bucket Company Franking Drag',
        "hook": (
            'Bucket companies cap tax leakage at 30%, then quietly strand borrowing power when franked '
            'dividends are not engineered back to the human borrower.'
        ),
        "mechanic": (
            'A discretionary trust distributing to a corporate beneficiary can defer top-up tax, but the '
            'retained cash belongs to the company. If the individual borrower needs servicing income, a '
            'later dividend must carry franking credits, fit Division 7A records, and appear '
            'consistently enough for lender policy. A one-off franked dividend may solve tax '
            'reconciliation and still fail income regularity if the assessor wants a two-year pattern.'
        ),
        "retail_trap": (
            'The accountant parks surplus in the bucket company for tax control; the broker lodges PAYG '
            'plus rental schedules and leaves company cash invisible. Then the client extracts funds '
            'through a shareholder loan, missing Div 7A compliance, contaminating deposit funds, and '
            'creating a liability the lender shades harder than the tax saved.'
        ),
        "execution": [
            '**Dividend cadence map** — set franked dividend timing across two financial years when personal servicing will need the company profit.',
            '**Div 7A ledger control** — separate complying loan agreements, repayments, and UPE evidence from deposit cash so credit and ATO traces do not collide.',
        ],
        "drop": 'A bucket company is a tax valve; without dividend architecture it is also an income lockbox.',
    },
    {
        "title": 'Part IVA Redraw Contamination',
        "hook": (
            'Debt recycling fails when the tax story says investment purpose but the bank trail says '
            'lifestyle redraw and recycled private cash.'
        ),
        "mechanic": (
            'Deductibility follows use of borrowed funds, not the property securing the loan. Redraw '
            'from a mixed PPOR facility creates apportionment; offset cash does not. Part IVA risk '
            'increases when circular flows pay down private debt, redraw immediately, and claim interest '
            'without a commercial investment sequence. Clean recycling uses new splits, direct '
            'settlement flow to income-producing assets, and accountant workpapers that match bank '
            'statements line by line.'
        ),
        "retail_trap": (
            'The retail play is pay wages into the home loan, redraw for shares or deposit, and call the '
            'new interest deductible. The lender sees owner-occupied purpose, the ATO sees mixed account '
            'history, and the investor discovers the security split never fixed the purpose split.'
        ),
        "execution": [
            '**New split before movement** — principal reduction occurs in the PPOR loan; investment borrowing starts from a separate facility with direct trace to the asset.',
            '**Contemporaneous purpose file** — bank statements, settlement authority, brokerage contract, and interest schedule stored before the first deduction is claimed.',
        ],
        "drop": 'Security does not create deductibility; fund use creates deductibility and mixed redraw destroys the evidence.',
    },
    {
        "title": 'Guarantor DTI Shadow Liability',
        "hook": (
            'Family guarantees look like free equity until APRA DTI policy counts the contingent '
            'exposure against the guarantor at the wrong moment.'
        ),
        "mechanic": (
            'A limited guarantee can avoid cash deposit drag and LMI, but the guarantor may carry the '
            'guaranteed portion as a contingent liability in future servicing. Some lenders ignore it '
            'with release conditions and clear repayment conduct; others load the exposure against NDI. '
            'The borrower also needs an exit valuation pathway, because a guarantee without scheduled '
            'release can trap the parent security beyond the original 80% LVR target.'
        ),
        "retail_trap": (
            'Retail structure takes the fastest no-LMI approval and leaves the guarantee open-ended '
            'across the parent PPOR. The child refinances late, valuation misses, rates are higher, and '
            'the parent then cannot borrow because their own lender treats the guarantee as shadow debt.'
        ),
        "execution": [
            '**Limited guarantee cap** — guarantee only the top-up portion required to reach target LVR, with no all-monies wording across unrelated facilities.',
            '**Release trigger diary** — valuation, repayment conduct, and refinance policy checked at 70-75% LVR before the guarantor applies for their own credit.',
        ],
        "drop": 'A guarantee is not invisible equity; it is dormant debt until the lender agrees to release it.',
    },
    {
        "title": 'Alt-Doc BAS Income Gap',
        "hook": (
            'Low-doc approvals are not loose credit; they are document-policy arbitrage where BAS '
            'turnover must reconcile to usable taxable cash flow.'
        ),
        "mechanic": (
            'Alt-doc lenders may accept accountant declarations, BAS, business bank statements, or '
            'interim financials when full tax returns lag the real business. The spread is in income '
            'translation: GST-inclusive turnover, cost of goods, director wages, one-off equipment buys, '
            'and retained earnings all need adjustment before the lender sets assessable income. A clean '
            'BAS run can beat a stale full-doc return, but only when ATO portals, ABN age, and account '
            'conduct line up.'
        ),
        "retail_trap": (
            'The borrower says revenue is up; the broker uploads four BAS and lets credit infer margin. '
            'GST is counted wrong, seasonal spikes are annualised, tax debt is undisclosed, and the file '
            'dies on conduct rather than income. Low-doc pricing then gets blamed for a documentation '
            'failure.'
        ),
        "execution": [
            '**BAS-to-income bridge** — strip GST, normalise margins, isolate one-offs, and reconcile tax debt before selecting alt-doc policy.',
            '**Conduct clean-up window** — three to six months of business statements without dishonours, ATO arrears drift, or unexplained transfers before lodgement.',
        ],
        "drop": 'Alt-doc is still full scrutiny; the difference is which documents carry the income proof.',
    },
    {
        "title": 'LMI Arbitrage at 88 LVR',
        "hook": (
            'Avoiding LMI at all costs can waste deployable capital when the portfolio constraint is '
            'deposit velocity, not headline insurance premium.'
        ),
        "mechanic": (
            'At 80% LVR, capital is trapped as equity buffer. At 85-88% LVR, the one-off LMI premium may '
            'preserve cash for stamp duty, buffers, or the next deposit. The arbitrage works only when '
            'the property yield, rate loading, insurer premium tier, and lender capitalisation rules '
            'leave NDI intact. Above certain bands, premium jumps and servicing shade can erase the '
            'benefit, especially with investor IO debt.'
        ),
        "retail_trap": (
            'Retail advice treats LMI as dead money and forces a larger deposit into the first deal. The '
            'investor saves a premium, loses the next acquisition window, and then releases equity later '
            'at higher valuation risk, higher rates, and another full credit assessment.'
        ),
        "execution": [
            '**Premium tier modelling** — compare 80, 85, 88, and 90% LVR on total cash retained, NDI, and next-deal deposit capacity.',
            '**Capitalised LMI boundary** — keep the loan under the insurer jump point; do not let a rounded cash-out request push the file into the next premium band.',
        ],
        "drop": 'LMI is expensive only when it buys nothing; when it preserves scarce capital, it is a leverage cost.',
    },
    {
        "title": 'Land Tax Stamp Duty Stack',
        "hook": (
            'Investors modelling yield without acquisition duty and annual land tax are quoting fake '
            'cash flow before the first tenant pays rent.'
        ),
        "mechanic": (
            'Stamp duty is an upfront capital drag; land tax is a recurring state-based drag that '
            'changes by ownership name, threshold, aggregation, absentee status, and trust surcharge. A '
            'trust may solve asset control and estate planning while triggering surcharge land tax. A '
            'company may cap tax but fail main-residence concessions. The correct structure is '
            'jurisdiction-specific because NSW, VIC, QLD, SA, WA, TAS, ACT, and NT do not tax the same '
            'ownership stack the same way.'
        ),
        "retail_trap": (
            'The spreadsheet uses purchase price, rent, and interest only. Duty is funded from buffer, '
            'land tax arrives after settlement, and trust surcharge turns a marginal yield into a '
            'cash-flow bleed. Then the investor refinances to patch holding costs and pollutes the next '
            'deposit plan.'
        ),
        "execution": [
            '**State-by-state holding model** — duty, land tax, surcharge, aggregation, council, insurance, and vacancy before unconditional exchange.',
            '**Owner-name selection** — individual, trust, company, or SMSF chosen against land tax and lending policy together, not after the contract is signed.',
        ],
        "drop": 'Yield starts after duty and land tax; anything before that is brochure arithmetic.',
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
