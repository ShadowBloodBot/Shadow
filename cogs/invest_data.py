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
STRATEGIES_WEEK = "2026-W40"
STRATEGIES_COUNT = 7

STRATEGIES = [
    {
        "title": "Trust Loss Quarantine and Servicing",
        "hook": (
            "Trust investors burying losses inside the entity are building neat tax files that "
            "do not convert into assessable servicing income."
        ),
        "mechanic": (
            "Residential lenders assess the person first and the trust second. A discretionary "
            "trust loss does not magically become beneficiary income because the asset is family "
            "controlled. Loss quarantine, unpaid present entitlements, and beneficiary loan accounts "
            "need to reconcile to the tax return, balance sheet, and distribution minute. Section "
            "100A risk rises when distributions are papered to low-rate beneficiaries while cash "
            "stays with the controller."
        ),
        "retail_trap": (
            "Retail submission uses the trust tax return as if all net income belongs to the "
            "borrower. The assessor strips retained income, questions UPEs, and ignores paper "
            "distributions without matching bank flow. The accountant saved marginal tax; the "
            "broker lost the next approval."
        ),
        "execution": [
            "**Pre-30 June distribution map** — set trustee minutes against the next two borrowing "
            "events, not just the lowest tax outcome.",
            "**Cashflow evidence pack** — reconcile UPEs, beneficiary loans, and actual bank transfers "
            "before the credit assessor asks for them.",
        ],
        "drop": (
            "A trust distribution that cannot be traced is not income; it is a servicing ghost."
        ),
    },
    {
        "title": "SMSF LRBA Liquidity Wall",
        "hook": (
            "SMSF property buyers treating an LRBA like ordinary investor debt are missing the "
            "liquidity wall that decides whether the fund can settle and survive."
        ),
        "mechanic": (
            "An LRBA is assessed inside the super environment: member balances, contribution "
            "capacity, rental income, fund expenses, insurance, and buffer policy all matter. "
            "The bare trust must hold the single acquirable asset, improvements cannot breach "
            "replacement rules, and related-party loans need commercial terms. High personal "
            "income does not repair a fund that cannot demonstrate post-settlement liquidity."
        ),
        "retail_trap": (
            "Retail advice starts with the property contract and only later checks the SMSF deed, "
            "bare trust, contribution caps, and liquidity reserve. The lender sees stamp duty, "
            "legals, adviser fees, and vacancy risk draining the fund below policy before rent "
            "even lands."
        ),
        "execution": [
            "**Fund-level servicing model** — test rent, concessional contributions, and fund expenses "
            "inside LRBA policy before contract.",
            "**Liquidity buffer quarantine** — keep cash outside deposit and duty calculations; the "
            "reserve is approval capital, not lazy capital.",
        ],
        "drop": (
            "In an LRBA, the asset is inside super, but the failure point is almost always cash."
        ),
    },
    {
        "title": "Part IVA Debt Recycling Boundary",
        "hook": (
            "Debt recycling fails when the structure is built to manufacture a deduction instead "
            "of tracing borrowed money into an income-producing use."
        ),
        "mechanic": (
            "Deductibility follows use of funds, not marketing language. Recycling works when "
            "non-deductible PPOR debt is reduced from surplus cash and a clean split is redrawn "
            "for shares, units, or investment property costs. Part IVA pressure appears when the "
            "dominant purpose looks like deduction creation with circular cash, related-party "
            "wash loans, or no real investment exposure."
        ),
        "retail_trap": (
            "Broker refinances one blended PPOR facility and calls the redraw investment debt. "
            "ATO tracing collapses because wages, rent, private spending, and investment transfers "
            "all hit the same account. The lender records cash-out purpose; the tax file records "
            "a guess."
        ),
        "execution": [
            "**One split per purpose** — PPOR P&I, investment IO, and cash-out facilities must be "
            "separate before funds move.",
            "**Audit trail at drawdown** — loan purpose letter, bank transfer, CHESS or settlement "
            "evidence, and accountant apportionment filed on day one.",
        ],
        "drop": (
            "Debt recycling is tracing discipline; without it, the deduction is just noise."
        ),
    },
    {
        "title": "Bucket Company Franking Drag",
        "hook": (
            "Bucket companies cap tax leakage only until trapped cash, Div 7A, and franking timing "
            "start choking the next lending move."
        ),
        "mechanic": (
            "A bucket company receives trust distributions at the company tax rate, but extraction "
            "is never free. Cash lent back to the family group can trigger Div 7A unless documented "
            "under complying terms. Franked dividends move cash to shareholders but can lift personal "
            "taxable income, affect Medicare levy surcharge, and change serviceability in the same "
            "year the borrower is trying to look clean to credit."
        ),
        "retail_trap": (
            "Retail structure parks every surplus dollar in the bucket, then raids it for deposits "
            "without Div 7A minutes, loan agreements, or repayment capacity. The accountant repairs "
            "the tax file later; the lender has already seen unexplained related-party liabilities."
        ),
        "execution": [
            "**Div 7A ledger before deposit release** — document terms, benchmark interest, minimum "
            "yearly repayments, and security before cash leaves the company.",
            "**Franking timing model** — test dividend extraction against the exact credit year, not "
            "the accountant's preferred tax year.",
        ],
        "drop": (
            "A bucket company stores tax friction; it does not delete it."
        ),
    },
    {
        "title": "NPR Add-Back Without Audit Noise",
        "hook": (
            "Self-employed borrowers lose six figures of capacity when Net Profit is lodged naked "
            "instead of rebuilt into lender-recognised cash flow."
        ),
        "mechanic": (
            "NPR is only the base. Depreciation, amortisation, one-off legal costs, interest on "
            "business debt being refinanced, non-recurring repairs, and director wages above market "
            "can be added back where policy allows. The issue is evidence: every adjustment needs "
            "tax return line reference, accountant explanation, and business bank support. Aggressive "
            "add-backs without proof become audit noise and credit decline material."
        ),
        "retail_trap": (
            "Retail broker keys taxable profit into the calculator and stops. Or worse, adds back "
            "everything in the P&L without separating private add-backs from policy add-backs. "
            "The credit assessor sees inflated servicing and asks for full financials."
        ),
        "execution": [
            "**Line-item add-back schedule** — map each adjustment to return label, ledger account, "
            "and lender policy treatment.",
            "**Two-year income bridge** — explain variance between FY25 and FY26 before the assessor "
            "turns it into a risk note.",
        ],
        "drop": (
            "An add-back is credit evidence, not a sales pitch."
        ),
    },
    {
        "title": "LMI Arbitrage Without Cross-Security",
        "hook": (
            "Avoiding LMI at all costs can be more expensive than paying it once to keep security "
            "clean and future equity releasable."
        ),
        "mechanic": (
            "LMI is a once-off capital cost priced against LVR; cross-security is a control cost "
            "priced every time the portfolio changes. A 90% standalone investment loan with LMI can "
            "leave the PPOR unencumbered, preserve lender choice, and avoid global revaluation risk. "
            "Family guarantee structures can reduce LMI, but they import another balance sheet and "
            "can trap the guarantor until valuation uplift or principal reduction releases them."
        ),
        "retail_trap": (
            "Banker offers an 80% lend by taking the PPOR, the new purchase, and sometimes a parent "
            "guarantee. No LMI is paid, but every sale, refinance, or equity release now needs the "
            "same lender's permission and fresh valuations across linked security."
        ),
        "execution": [
            "**Compare LMI to control loss** — price premium, exit fees, and revaluation risk before "
            "accepting cross-security.",
            "**Guarantee release trigger** — document the LVR, valuation date, and debt reduction path "
            "before guarantor paperwork is signed.",
        ],
        "drop": (
            "Cheap entry that surrenders exit control is not cheap debt."
        ),
    },
    {
        "title": "Alt-Doc BAS vs DTI Ceiling",
        "hook": (
            "Alt-doc lending solves missing tax returns, but it does not solve a DTI ceiling built "
            "from real liabilities."
        ),
        "mechanic": (
            "Low-doc and alt-doc policies can use BAS turnover, accountant declarations, or business "
            "bank statements where full financials lag. The lender still shades income, applies "
            "GST logic, loads existing debts at assessment rates, and watches APRA-style DTI even "
            "outside the majors. BAS evidence proves revenue; it does not prove disposable income "
            "after tax, wages, rent, supplier float, and ATO payment plans."
        ),
        "retail_trap": (
            "Retail file grabs the latest BAS and ignores seasonality, ATO arrears, credit cards, "
            "and equipment finance. The rate looks tolerable until DTI and NDI fail under shaded "
            "income and loaded commitments."
        ),
        "execution": [
            "**BAS normalisation schedule** — remove GST, isolate one-off spikes, and reconcile bank "
            "credits to declared turnover.",
            "**Liability compression first** — close unused limits, restructure equipment debt, and "
            "clear ATO plans before alt-doc lodgement.",
        ],
        "drop": (
            "Alt-doc changes the income document; it does not change the maths."
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
