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
STRATEGIES_WEEK = "2026-W38"
STRATEGIES_COUNT = 7

STRATEGIES = [
    {
        "title": "Trust Vesting Date Serviceability Cliff",
        "hook": (
            "A family trust can hold the asset neatly while the vesting date quietly ruins the refinance lane."
        ),
        "mechanic": (
            "The trust deed is credit evidence, not paperwork garnish. Vesting date, appointor powers, "
            "trustee replacement, borrowing powers, beneficiary classes, and distribution mechanics all "
            "tell credit whether the borrower can hold and refinance the asset for the loan term. If the "
            "vesting date sits inside the proposed facility horizon, the file can trigger legal review, "
            "deed variation, resettlement risk, CGT risk, and stamp duty questions before NDI is even tested."
        ),
        "retail_trap": (
            "Retail handling sends the trust deed after approval-in-principle and assumes the solicitor "
            "will tidy it up. Credit then sees a short vesting runway, unclear appointor succession, or "
            "missing borrowing powers. The tax structure might be fine on day one and still fail the "
            "bank's security and continuity test for year twenty-five."
        ),
        "execution": [
            "**Deed runway audit** - vesting date, variation powers, appointor succession, and trustee authority are cleared before valuation spend.",
            "**Loan-term alignment** - match lender, term, guarantors, and legal review to the trust's actual control and continuity profile.",
        ],
        "drop": "A trust with a short legal runway is not an asset wrapper; it is a refinance defect.",
    },
    {
        "title": "SMSF Pension-Phase LRBA Compression",
        "hook": (
            "An SMSF LRBA can clear at acquisition and still jam when member cash flow shifts into pension phase."
        ),
        "mechanic": (
            "LRBA assessment is a cash-flow stack inside a compliance box. Rent, fund expenses, liquidity, "
            "minimum pension payments, contribution caps, related-party terms, insurance, and arm's-length "
            "interest all need to survive the fund's actual phase. Once members draw pensions, the fund may "
            "have less surplus cash to absorb vacancies, repairs, rate rises, and limited recourse debt."
        ),
        "retail_trap": (
            "Retail packaging treats SMSF borrowing like a standard investment loan with a bare trust "
            "bolted on. The file ignores member age, pension drawdowns, contribution restrictions, liquidity "
            "covenants, and lease concentration. The loan approves on an accumulation-phase snapshot and "
            "struggles when the fund's mandated cash outflow changes."
        ),
        "execution": [
            "**Fund cash-flow map** - rent, pensions, contributions, expenses, and LRBA repayments are modelled inside the SMSF, not the member's household budget.",
            "**Liquidity covenant buffer** - preserve cash for vacancy, repairs, insurance, and minimum pension payments before sizing the limited recourse loan.",
        ],
        "drop": "An LRBA fails when the fund can own the asset but cannot fund the law around it.",
    },
    {
        "title": "PAYG Bonus Shading Income Split",
        "hook": (
            "A high PAYG package can be cut in half by credit policy when bonus income is parked in the wrong lane."
        ),
        "mechanic": (
            "Base salary, overtime, commission, car allowance, RSUs, sign-on bonus, annual bonus, and salary "
            "sacrifice are not assessed the same way. Some lenders take two-year average bonus, some shade "
            "to 80 percent, some need YTD confirmation, and some ignore one-off payments. HECS then loads "
            "against gross taxable income even when the usable bonus is shaded."
        ),
        "retail_trap": (
            "Retail servicing enters the applicant's package total and waits for credit to accept it. The "
            "assessor strips the sign-on, averages the annual bonus, discounts commission, loads HECS, and "
            "treats the car allowance as taxable income with a matching expense. The gross package never "
            "turns into usable NDI."
        ),
        "execution": [
            "**Income component grid** - split base, bonus, commission, allowance, RSU, and sacrifice before lender selection.",
            "**HECS policy overlay** - test each lender on shaded income after compulsory repayment load, not headline remuneration.",
        ],
        "drop": "Income is not borrowing power until the policy calculator counts it after every shade.",
    },
    {
        "title": "NPR Add-Back Director Wage Loop",
        "hook": (
            "A company can show low taxable profit while the director's real servicing income sits in add-back mechanics."
        ),
        "mechanic": (
            "Self-employed servicing starts with taxable profit and rebuilds capacity through normalised "
            "profit reconciliation. Director wages, super, depreciation, interest, one-off legal costs, "
            "NPR, motor vehicle add-backs, and non-cash expenses need to reconcile across tax returns, "
            "financials, BAS, and bank conduct. The same dollar cannot be counted as company profit and "
            "director income twice."
        ),
        "retail_trap": (
            "Retail handling sends accountant financials and hopes credit finds the income. The assessor "
            "sees director wages added back inside company profit while also used as personal PAYG income, "
            "or sees NPR claimed without loan statements proving the interest purpose. The add-back becomes "
            "double-counting or unsupported noise."
        ),
        "execution": [
            "**Normalised profit bridge** - reconcile taxable profit to servicing income line-by-line with source documents.",
            "**Double-count block** - quarantine director wages, related-party rent, and NPR so each dollar appears once in the borrower group.",
        ],
        "drop": "An add-back is credit income only when the file proves it is not counted somewhere else.",
    },
    {
        "title": "Bucket Company UPE Div 7A Spill",
        "hook": (
            "A bucket company can cap tax and still create a private-company debt that leaks into Div 7A."
        ),
        "mechanic": (
            "Trust income appointed to a bucket company can hold tax at the company rate, but the unpaid "
            "present entitlement is not magic cash. Sub-trust treatment, complying loan terms, benchmark "
            "interest, minimum yearly repayments, franked dividends, working capital needs, and cash "
            "movement decide whether the UPE remains commercial or mutates into Div 7A exposure."
        ),
        "retail_trap": (
            "Retail structuring celebrates the lower trust distribution tax and ignores who actually holds "
            "the cash. The family uses company-retained funds for deposits, renovations, or private offsets "
            "without a complying agreement. The accountant later has a deemed dividend problem and the "
            "lender has an undisclosed related-party liability."
        ),
        "execution": [
            "**UPE ledger control** - distribution minute, company entitlement, cash movement, sub-trust, and loan agreement agree before funds move.",
            "**Repayment servicing load** - Div 7A minimum yearly repayments and benchmark interest are treated as real cash-flow drains.",
        ],
        "drop": "Bucket-company tax deferral becomes debt the moment the cash is used like private money.",
    },
    {
        "title": "APRA DTI Card Limit Guillotine",
        "hook": (
            "A clean income file can lose the approval because unused credit limits inflate APRA debt metrics."
        ),
        "mechanic": (
            "DTI is built from total debt against gross income, while NDI still loads repayments at assessed "
            "rates. Credit cards, overdrafts, BNPL limits, car loans, HECS, margin loans, and guarantees "
            "can push a borrower over lender appetite before LVR matters. A $30k unused card can be "
            "serviced as a real limit and counted inside total debt even when the balance is nil."
        ),
        "retail_trap": (
            "Retail broking checks repayment conduct and leaves every card open for convenience. Credit "
            "then applies a percentage-of-limit repayment, loads the full facility into liabilities, and "
            "tags the file as high DTI. The borrower had deposit and income but carried lazy limits into "
            "the calculator."
        ),
        "execution": [
            "**Limit purge sequence** - close or reduce cards, overdrafts, BNPL, and dormant facilities before application data is captured.",
            "**DTI pre-score** - test total debt, guarantees, HECS, and assessed repayments against lender appetite before ordering valuation.",
        ],
        "drop": "Unused limits are still debt when APRA maths is measuring capacity.",
    },
    {
        "title": "Land Tax Entity Threshold Mismatch",
        "hook": (
            "The same property can carry a different annual drag once the buyer name changes."
        ),
        "mechanic": (
            "Land tax is state law, entity law, and threshold law stacked together. Individuals, joint "
            "owners, discretionary trusts, fixed trusts, companies, absentees, and surcharge purchasers "
            "can sit in different annual-cost lanes. Stamp duty is the entry hit; land tax is the recurring "
            "drag. The purchase structure must model both before deciding whether tax control, asset "
            "protection, or borrowing simplicity wins."
        ),
        "retail_trap": (
            "Retail advice compares loan products and leaves ownership to a last-minute conveyancer chat. "
            "The trust buys with no threshold, the company triggers a surcharge lane, or the individual "
            "tips over a state threshold across the portfolio. Cash flow then misses a statutory cost that "
            "was baked in from contract exchange."
        ),
        "execution": [
            "**Entity-cost matrix** - model duty, annual land tax, surcharge exposure, thresholds, and portfolio aggregation by buyer type.",
            "**After-tax hold test** - size debt and offset buffer after the statutory drag, not off gross rent and purchase price.",
        ],
        "drop": "Ownership name is a cash-flow variable before it is an asset-protection choice.",
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
