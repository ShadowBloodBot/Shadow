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
STRATEGIES_WEEK = "2026-W37"
STRATEGIES_COUNT = 7

STRATEGIES = [
    {
        "title": "Unit Trust Debt Capacity Mismatch",
        "hook": (
            "A unit trust can split ownership neatly while giving the lender no clean borrower to assess."
        ),
        "mechanic": (
            "Unit trusts work when entitlement, control, cash flow, and guarantees are engineered before "
            "the loan. The lender wants the borrowing entity, unit holders, trustee, deed powers, and "
            "beneficial ownership to line up. Income may sit in the trust, debt may sit with the trustee, "
            "and serviceability may sit with the individuals. The file needs unit register, distribution "
            "history, interposed entity map, and guarantee logic tied to the actual cash waterfall."
        ),
        "retail_trap": (
            "Retail packaging treats the trust as a fancy ownership wrapper and lodges personal payslips "
            "beside a trust deed. Credit then asks who controls the asset, who receives income, who is "
            "liable for debt, and whether minority unit holders can block decisions. A clean tax split can "
            "become a serviceability void."
        ),
        "execution": [
            "**Unit register proof** - deed, trustee powers, unit holder ledger, guarantees, and distribution minutes sit in one assessor pack.",
            "**Servicing borrower match** - select the lender by whether it counts trust income, beneficiary income, or guarantor support without double-counting debt.",
        ],
        "drop": "A trust structure has no credit value until the assessor can follow control, income, and liability.",
    },
    {
        "title": "Alt-Doc BAS Add-Back Ladder",
        "hook": (
            "A self-employed borrower can show weak taxable income and still carry the deal if the add-back ladder is built cleanly."
        ),
        "mechanic": (
            "Alt-doc and low-doc servicing is not guesswork; it is a policy ladder. BAS turnover, accountant "
            "letter, business bank credits, GST registration, ABN age, NPR, depreciation, interest add-backs, "
            "one-off expenses, and director wages all need the same story. The lender is chosen by the "
            "highest defensible income it will accept, not by rate card. Tax minimisation only survives "
            "credit when the adjustments are documented."
        ),
        "retail_trap": (
            "The retail broker grabs the latest tax return, sees low net profit, and declares the client "
            "unserviceable. The sloppy version swings the other way and invents income from gross BAS "
            "receipts without cost proof. Credit either ignores the business strength or kills the file for "
            "unsupported income inflation."
        ),
        "execution": [
            "**Income ladder file** - BAS, bank statements, accountant letter, ABN/GST proof, and add-back schedule reconcile to one usable income figure.",
            "**NPR quarantine** - split normalised profit from depreciation, interest, one-offs, and owner wages before the lender calculator sees it.",
        ],
        "drop": "Alt-doc works only when every dollar of adjusted income has a policy-backed source.",
    },
    {
        "title": "Div 7A Loan Repayment Squeeze",
        "hook": (
            "Company cash can fund the deposit and still poison the borrower when Div 7A repayments hit serviceability."
        ),
        "mechanic": (
            "A private company loan to a shareholder or associate is not free equity. If it is not repaid, "
            "declared as a dividend, or put under a complying Div 7A agreement, it can become deemed income. "
            "For credit, the minimum yearly repayment is a real cash-flow drag. For tax, the loan agreement, "
            "benchmark interest, term, security, and repayment date drive whether the structure holds."
        ),
        "retail_trap": (
            "Retail handling calls the company transfer savings and lodges the deposit trail. The assessor "
            "spots a director loan account, the accountant warns on deemed dividends, and the repayment "
            "schedule lands after servicing was already modelled. The borrower borrowed from their own "
            "company and forgot the company wants it back."
        ),
        "execution": [
            "**Div 7A servicing load** - include benchmark interest, minimum yearly repayment, loan term, and security status in the lender calculator.",
            "**Cash-source labelling** - separate wage, franked dividend, complying loan, and genuine savings before deposit evidence is supplied.",
        ],
        "drop": "Company money used privately is either income, debt, or a tax problem.",
    },
    {
        "title": "Section 100A Family Split Audit",
        "hook": (
            "Family trust distributions can reduce tax and still fail when the benefit never reaches the beneficiary."
        ),
        "mechanic": (
            "Section 100A risk lives in reimbursement agreements: trust income appointed to a lower-tax "
            "beneficiary while another person enjoys the cash. Adult children, parents, bucket entities, "
            "UPEs, journal entries, and circular family transfers need commercial substance and actual "
            "benefit. Credit also needs to know whether that beneficiary income is recurring, controlled, "
            "and available for debt servicing."
        ),
        "retail_trap": (
            "Retail advice points at the distribution statement and ignores who banked the money. The ATO "
            "sees a tax outcome with the economic benefit redirected. Credit sees income allocated to "
            "someone outside the borrower group. The same split can be useless for servicing and exposed "
            "for tax."
        ),
        "execution": [
            "**Benefit tracing** - distribution minute, bank transfer, beneficiary loan account, and use of funds match the person taxed on the income.",
            "**Borrower-group test** - count trust distributions only where lender policy accepts control, recurrence, and actual cash availability.",
        ],
        "drop": "A trust distribution is weak when tax follows one person and cash follows another.",
    },
    {
        "title": "DTI Cap Equity Release Gridlock",
        "hook": (
            "Equity can be real on valuation and still unusable when DTI and APRA buffers lock the release."
        ),
        "mechanic": (
            "Cash-out is assessed on proposed debt, sensitised repayments, existing liabilities, living "
            "expenses, rental shading, and lender DTI caps. A low LVR does not override NDI. Some lenders "
            "treat equity release for investment as acceptable with evidence; others cap it, require "
            "contracts, or shade the purpose. The usable number is the lesser of valuation equity, servicing "
            "capacity, purpose policy, and post-release buffer."
        ),
        "retail_trap": (
            "The retail broker says there is $300k equity at 80 percent LVR and orders a top-up. Credit "
            "then loads the new debt at assessment rate, counts every card limit, shades rent, and applies "
            "DTI appetite. The paper equity never becomes settlement cash."
        ),
        "execution": [
            "**Four-cap model** - valuation LVR, NDI, DTI, and cash-out purpose policy are calculated before refinance structure is chosen.",
            "**Liability compression** - close unused cards, sequence deductible splits, and stage equity releases where one full cash-out breaks servicing.",
        ],
        "drop": "Equity is not borrowing power until APRA maths lets it leave the property.",
    },
    {
        "title": "Fixed Split Refix Shock",
        "hook": (
            "A cheap fixed rate can hide the refinance failure waiting at IO expiry and refix date."
        ),
        "mechanic": (
            "Fixed and variable splits need exit maths, not rate nostalgia. IO expiry converts cash flow, "
            "remaining term compresses principal repayments, fixed breaks limit restructure timing, and "
            "offset cash may only sit against the variable split. The next approval uses current assessment "
            "rates and actual residual term. A portfolio can be profitable and still fail refinance when "
            "old cheap debt matures into amortising debt."
        ),
        "retail_trap": (
            "Retail structuring fixes everything for certainty, ignores offset placement, and sets IO "
            "expiry across multiple loans in the same quarter. When the cliff arrives, servicing is tested "
            "on higher rates, shorter terms, and P&I repayments. The borrower has cash-flow shock and no "
            "clean refinance lane."
        ),
        "execution": [
            "**Expiry ladder** - stagger IO expiries, fixed maturities, and refinance reviews so all debt does not reprice under one policy window.",
            "**Offset-to-split map** - park cash against non-deductible or variable debt where it preserves liquidity and future restructure control.",
        ],
        "drop": "Rate certainty is worthless if the maturity date destroys refinance capacity.",
    },
    {
        "title": "Land Tax Stamp Duty Stack",
        "hook": (
            "The purchase price is not the capital requirement when stamp duty and land tax hit the same stack."
        ),
        "mechanic": (
            "Acquisition cash must model duty, transfer fees, legal, lender fees, land tax adjustment, "
            "vacancy, repairs, strata levies, insurance, and state-by-state thresholds. Trusts and companies "
            "can trigger different land tax treatment, surcharge exposure, and no threshold in some lanes. "
            "The debt structure must leave liquidity after settlement instead of treating statutory costs "
            "as loose change."
        ),
        "retail_trap": (
            "Retail modelling says deposit plus loan equals purchase. Then duty lands, land tax is adjusted, "
            "repairs are immediate, and the borrower empties the offset before the first tenant payment. "
            "The deal technically settles and financially limps from day one."
        ),
        "execution": [
            "**State-cost stack** - duty, land tax threshold, surcharge risk, entity type, and settlement adjustments are modelled before LVR is chosen.",
            "**Liquidity floor** - preserve post-settlement offset for vacancy, repairs, rates, and insurance before chasing a cleaner deposit percentage.",
        ],
        "drop": "A property is not affordable because the loan approves; it is affordable when statutory friction is funded.",
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
