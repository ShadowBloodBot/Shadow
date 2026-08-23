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
STRATEGIES_WEEK = "2026-W35"
STRATEGIES_COUNT = 7

STRATEGIES = [
    {
        "title": 'Bucket Company Franking Trap',
        "hook": (
            'A bucket company can cap tax leakage while quietly starving the personal borrower of usable '
            'servicing income.'
        ),
        "mechanic": (
            'Trust profit distributed to a corporate beneficiary can park income at the company tax rate, '
            'but credit treats that cash as company retained earnings unless it is paid out as wages, '
            'dividends, or a documented loan. Franking credits only matter when dividends are declared '
            'and assessed against the shareholder profile. The structure needs a tax ledger, UPE position, '
            'cash movement, and servicing treatment aligned before the borrower claims the profit supports '
            'personal debt.'
        ),
        "retail_trap": (
            'The retail broker uploads trust and company returns, points at the profit, and expects an '
            'add-back. The assessor sees income quarantined in a separate taxpayer, franking trapped until '
            'dividend declaration, and UPE or Div 7A exposure if the cash moved privately. Tax efficiency '
            'created a credit dead zone.'
        ),
        "execution": [
            '**Corporate beneficiary map** - show trust minute, company ledger, UPE balance, franking account, and actual cash location as one file.',
            '**Income extraction choice** - decide wage, dividend, complying loan, or retained profit before selecting the lender policy that will count it.',
        ],
        "drop": 'Bucket companies reduce tax friction only when the credit file can prove who controls the cash.',
    },
    {
        "title": 'SMSF LRBA Bare Trust Choke Point',
        "hook": (
            'An SMSF purchase can have enough deposit and still fail because the bare trust and liquidity '
            'stack were built after the contract.'
        ),
        "mechanic": (
            'LRBA credit sits on a limited recourse loan, a bare trustee, fund deed powers, investment '
            'strategy minutes, rent assumptions, SG cadence, contribution caps, and post-settlement cash. '
            'The fund cannot repair a weak buffer with personal redraw after settlement. The lender needs '
            'the custodian structure and liquidity proof before valuation because the asset, borrower, '
            'trustee, and security are not the same legal pocket.'
        ),
        "retail_trap": (
            'Retail execution orders the contract in the fund name, asks the accountant for documents '
            'later, and discovers the bare trustee, deed variation, related-party lease issue, or minimum '
            'liquidity requirement after the cooling-off window. Super law does not bend because credit '
            'was lodged in the wrong order.'
        ),
        "execution": [
            '**Pre-contract LRBA stack** - deed power, bare trustee, custodian deed, investment strategy, contribution ledger, and liquidity buffer cleared first.',
            '**Fund cash stress** - model rent shade, SG timing, concessional cap room, insurance, land tax, rates, and minimum balance inside the SMSF.',
        ],
        "drop": 'SMSF leverage fails where the fund structure cannot legally carry the property.',
    },
    {
        "title": 'Debt Recycling Purpose Contamination',
        "hook": (
            'Debt recycling only works while every dollar keeps its deductible purpose and private cash '
            'stays out of the investment split.'
        ),
        "mechanic": (
            'The deductible character of interest follows use of borrowed funds, not the property label. '
            'A clean recycle pays down non-deductible PPOR debt, redraws or re-borrows into a separate '
            'split, and sends those borrowed funds directly to income-producing assets. Salary, groceries, '
            'school fees, offset sweeps, and mixed redraws contaminate tracing. Credit then assesses the '
            'new split while the ATO tests the purpose trail.'
        ),
        "retail_trap": (
            'The retail file tops up the home loan, leaves one blended facility, and calls the investment '
            'portion deductible because the property is an investment. Later, repayments, redraws, and '
            'offset movements are mixed. The accountant cannot reconstruct clean interest deductibility '
            'from a transaction account full of private spending.'
        ),
        "execution": [
            '**Split-level tracing** - each recycle drawdown sits in its own loan split with direct transfer to brokerage, managed fund, or investment settlement.',
            '**Offset quarantine** - private cash remains in the non-deductible offset; investment borrowings never share a redraw pool with living expenses.',
        ],
        "drop": 'Debt recycling dies the moment purpose tracing becomes a reconstruction exercise.',
    },
    {
        "title": 'Part IVA Cash-Out Circularity',
        "hook": (
            'A refinance can manufacture deductible debt on paper and still look circular when the cash '
            'ends up back with the borrower.'
        ),
        "mechanic": (
            'Part IVA risk appears when a dominant tax benefit is engineered without commercial substance. '
            'Cash-out against one property, circular repayments through related parties, back-to-back '
            'loans, or same-day trust movements can create an interest deduction narrative that does not '
            'match economic reality. Credit wants purpose; the ATO wants purpose plus substance. The file '
            'needs arm\'s-length documents, actual investment use, and no round-trip of funds.'
        ),
        "retail_trap": (
            'The retail broker calls it cash-out for investment and stops at the lender letter. Bank '
            'statements then show funds moving to a spouse, company, trust, or offset before returning '
            'to reduce private debt. The deduction was never supported by a durable income-producing use.'
        ),
        "execution": [
            '**Commercial-use file** - loan purpose, investment contract, related-party terms, bank trail, and income expectation line up before interest is claimed.',
            '**No round-trip funds** - borrowed money lands in the asset or entity using it, not a private offset, family account, or circular repayment chain.',
        ],
        "drop": 'A deduction built on circular cash flow is tax engineering without a spine.',
    },
    {
        "title": 'HECS Bonus Policy Servicing Split',
        "hook": (
            'A PAYG applicant can have strong gross income and still lose borrowing power when HELP and '
            'bonus shading hit the wrong lender calculator.'
        ),
        "mechanic": (
            'HECS/HELP is assessed differently across lenders: some load the repayment scale against '
            'gross taxable income, some use payslip deductions, and some model the debt separately. Bonus, '
            'commission, RSUs, overtime, and allowances are also shaded by tenure, consistency, and policy '
            'caps. The correct lender is the one that preserves NDI after HELP and variable income rules, '
            'not the one with the lowest advertised rate.'
        ),
        "retail_trap": (
            'Retail packaging annualises the last payslip bonus, ignores HELP, and lodges with a bank '
            'that only accepts 80 percent or a two-year average. Credit strips the income, loads the HELP '
            'repayment, and the deal misses NDI while the borrower still appears high income on paper.'
        ),
        "execution": [
            '**Income-policy matrix** - compare HELP treatment, bonus percentage, tenure rule, and payslip/YTD evidence across lenders before ordering credit.',
            '**NDI-first sequencing** - clear small HELP only when the repayment saving beats the cash lost for deposit, LMI, and buffers.',
        ],
        "drop": 'High PAYG income is weak credit income when policy shades the moving parts.',
    },
    {
        "title": 'LMI Arbitrage vs Stamp Duty Drag',
        "hook": (
            'Avoiding LMI can cost more than paying it when stamp duty, land tax, and dead equity are '
            'stacked into the same purchase plan.'
        ),
        "mechanic": (
            'LMI is a leverage cost, not automatically a mistake. A lower deposit can preserve cash for '
            'stamp duty, land tax adjustment, repairs, buffers, and the next acquisition. The comparison '
            'is not 80 percent LVR versus 88 percent LVR in isolation; it is after-tax holding cost, '
            'opportunity cost of trapped equity, deductible interest treatment, premium capitalisation, '
            'and portfolio velocity under APRA servicing.'
        ),
        "retail_trap": (
            'The retail answer is save until 20 percent because LMI feels dirty. By settlement, stamp '
            'duty, buyers agent fees, repairs, and land tax apportionments have drained the buffer and '
            'the investor has one cleaner loan with no capacity for the next move.'
        ),
        "execution": [
            '**Capital-stack comparison** - model LMI premium, deposit retained, stamp duty, land tax, repairs, offset buffer, and next-purchase deposit as one table.',
            '**LVR policy lane** - pick the highest LVR that preserves servicing, valuation tolerance, and cash buffer without forcing cross-security.',
        ],
        "drop": 'LMI is expensive only when it buys no extra usable capital.',
    },
    {
        "title": 'Guarantor Exit and Cross-Security Lock',
        "hook": (
            'A guarantor loan can solve the deposit gap and still trap the family balance sheet when the '
            'exit pathway is not engineered.'
        ),
        "mechanic": (
            'Family guarantee structures use limited security support to replace cash deposit or avoid '
            'LMI, but the guarantee must be capped, isolated, and releasable. Cross-collateralising the '
            'parent home, borrower property, and future investment debt gives the lender control over '
            'valuations, discharges, and refinance timing. The exit is driven by LVR reduction, valuation '
            'uplift, principal paydown, and servicing at release date.'
        ),
        "retail_trap": (
            'The retail broker sells no-deposit convenience and leaves the guarantee open-ended. Years '
            'later the parents want to downsize, the borrower wants to refinance, and one low-equity '
            'property blocks every discharge because the securities were welded together.'
        ),
        "execution": [
            '**Limited guarantee cap** - guarantee only the shortfall amount, document release triggers, and keep parent debt outside the investment security pool.',
            '**Exit valuation schedule** - track LVR, paydown, market uplift, and refinance servicing from settlement rather than waiting for family pressure.',
        ],
        "drop": 'A guarantor structure without an exit is borrowed equity with family collateral attached.',
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
