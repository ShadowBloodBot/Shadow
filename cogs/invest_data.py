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
STRATEGIES_WEEK = "2026-W33"
STRATEGIES_COUNT = 7

STRATEGIES = [
    {
        "title": 'Section 100A Trust Distribution Drag',
        "hook": (
            'Family trust distributions can lower tax on paper while leaving the lender and ATO reading '
            'two different cash-flow stories.'
        ),
        "mechanic": (
            'Section 100A risk appears when trust income is distributed to a lower-tax beneficiary but '
            'the economic benefit circles back to the controller. Credit then has the opposite problem: '
            'the borrower wants income counted personally while the tax file says the trust paid someone '
            'else. Clean execution needs beneficiary resolutions, payment trails, UPE handling, and loan '
            'application income mapping to match the actual cash benefit, not just the tax minute.'
        ),
        "retail_trap": (
            'The retail file uploads trust returns and beneficiary notices without proving who retained '
            'the cash. The ATO sees reimbursement agreement risk; the lender sees income that may not be '
            'available to the applicant. A tax-effective distribution can become a servicing add-back '
            'refusal when the funds never landed with the borrower.'
        ),
        "execution": [
            '**Distribution cash trail** — beneficiary resolution, bank transfer, UPE ledger, and tax return all show the same economic recipient before credit submission.',
            '**Servicing bridge** — classify trust profit as retained, distributed, or paid wages before choosing the lender policy that will count it.',
        ],
        "drop": 'Trust income only works when the tax recipient and the credit recipient are the same economic person.',
    },
    {
        "title": 'SMSF LRBA Contribution Cap Squeeze',
        "hook": (
            'An SMSF property can pass LVR and still fail when contribution caps are the only thing '
            'standing behind the loan.'
        ),
        "mechanic": (
            'LRBA servicing is not just rent minus repayments. The lender tests member contributions, '
            'employer SG cadence, concessional and non-concessional cap room, fund expenses, insurance, '
            'and pension phase obligations inside a vehicle that cannot be casually topped up. A '
            'related-party loan may solve rate or LVR friction, but its terms still need arm's-length '
            'support and fund liquidity after the property settles.'
        ),
        "retail_trap": (
            'The retail broker treats the SMSF as a deposit-rich borrower and leaves the contribution '
            'buffer for the accountant. Credit then asks for deed powers, investment strategy minutes, '
            'bare trust documents, contribution history, and liquidity evidence after the contract is '
            'unconditional. Super cash is locked; missed buffers cannot be fixed with a redraw transfer.'
        ),
        "execution": [
            '**Cap-room stress test** — model rent shade, SG, salary sacrifice, concessional caps, admin costs, insurance, and minimum liquidity inside the fund.',
            '**LRBA document stack** — deed, bare trust, investment strategy, related-party terms, lease evidence, and contribution ledger ready before valuation.',
        ],
        "drop": 'SMSF leverage is constrained by trapped liquidity, not the member\'s personal appetite for debt.',
    },
    {
        "title": 'Div 7A Deposit Poisoning',
        "hook": (
            'Company cash used as a property deposit can turn into assessable income, a deemed loan, and '
            'a credit liability in the same file.'
        ),
        "mechanic": (
            'Division 7A treats private use of company funds by shareholders or associates as a loan or '
            'deemed dividend unless documented and repaid under compliant terms. In credit, the same '
            'movement must be explained as genuine savings, gift, loan, dividend, or business drawing. '
            'Each label changes servicing, tax, and source-of-funds treatment. A deposit funded by '
            'company cash needs the tax ledger built before the bank statements expose it.'
        ),
        "retail_trap": (
            'The retail move is transfer surplus company cash to the personal account, call it savings, '
            'and lodge. The assessor requests company financials, the accountant books a shareholder '
            'loan after the fact, and repayments reduce NDI. If booked as a dividend, top-up tax and '
            'income consistency become the next problem.'
        ),
        "execution": [
            '**Source-of-funds classification** — decide dividend, wage, complying Div 7A loan, or retained company cash before any deposit transfer leaves the company.',
            '**Credit liability mapping** — if it is a loan, include minimum yearly repayments, interest, and company capacity in servicing from day one.',
        ],
        "drop": 'Company cash is not personal deposit money until tax law and lender policy both say it is.',
    },
    {
        "title": 'DTI Ceiling With Hidden HEM Burn',
        "hook": (
            'A borrower can sit under the headline DTI cap and still fail because HEM, buffers, and '
            'shaded rent consume the real NDI.'
        ),
        "mechanic": (
            'APRA DTI is a blunt exposure ratio; lender servicing calculators still decide the file. '
            'Existing IO debt may be assessed on P&I residual term, new debt receives a buffer, rent is '
            'shaded, bonuses are capped, HECS is loaded, and living expenses are benchmarked against HEM '
            'or declared spend. A 6x DTI exception means nothing if NDI is negative after policy loading.'
        ),
        "retail_trap": (
            'Retail structuring chases the lender with the highest DTI appetite and ignores the expense '
            'model. Credit then clips bonus income, refuses overtime, loads HELP, and converts IO to P&I '
            'assessment. The borrower was never short on gross income; the file was short on policy NDI.'
        ),
        "execution": [
            '**Calculator-first lender order** — rank lenders by NDI output after rent shade, HELP, bonus policy, IO loading, and living expense treatment.',
            '**Debt-shape clean-up** — close unused cards, split OO/invest debt, and refinance IO cliffs before chasing a DTI exception.',
        ],
        "drop": 'DTI is the gate label; NDI is the gate lock.',
    },
    {
        "title": 'Fixed Split Break-Cost Trap',
        "hook": (
            'Fixing the whole loan can buy rate certainty while selling the investor\'s ability to '
            'release equity, recycle debt, or sell cleanly.'
        ),
        "mechanic": (
            'Fixed rates restrict redraw, extra repayments, offset access, cash-out, and discharge '
            'timing depending on lender terms. A portfolio investor needs variable capacity for active '
            'capital movements: equity release, debt recycling, construction invoices, tax instalments, '
            'or sale timing. The correct split is not rate prediction; it is matching fixed debt to '
            'stable holding debt and variable debt to tactical capital.'
        ),
        "retail_trap": (
            'The retail broker fixes the full balance because the rate is cheaper on the day. Six months '
            'later the client needs cash-out for stamp duty, wants to sell, or must restructure for tax. '
            'Break costs, missing offset, and redraw restrictions turn a pricing decision into a '
            'portfolio control problem.'
        ),
        "execution": [
            '**Purpose-based split map** — fixed portion covers stable deductible holding debt; variable/offset portion holds capital scheduled for redraw, deposits, or tax.',
            '**Break-cost scenario file** — model sale, refinance, cash-out, and IO expiry before accepting the fixed-rate discount.',
        ],
        "drop": 'A cheap fixed rate is expensive when it blocks the next capital movement.',
    },
    {
        "title": 'Alt-Doc GST Turnover Mirage',
        "hook": (
            'Low-doc income built from BAS turnover collapses when GST, margin, ATO debt, and seasonal '
            'spikes are not stripped out.'
        ),
        "mechanic": (
            'Alt-doc policy can use BAS, business bank statements, accountant declarations, or interim '
            'financials, but each document translates turnover differently. GST-inclusive receipts are '
            'not profit. Inventory buys, director wages, asset finance, tax arrears, one-off contracts, '
            'and merchant timing all change assessable income. The arbitrage is picking the document '
            'set that reflects current cash flow without overstating capacity.'
        ),
        "retail_trap": (
            'The borrower says revenue doubled, the broker annualises the last two BAS, and credit finds '
            'GST counted as income, ATO arrears, irregular deposits, and a margin that cannot support '
            'the declared figure. The file dies on reconciliation, not on appetite for self-employed '
            'risk.'
        ),
        "execution": [
            '**BAS-to-bank reconciliation** — strip GST, normalise margin, isolate one-offs, map ATO liabilities, and tie turnover to deposits before lodgement.',
            '**Policy document selection** — choose BAS, accountant declaration, or bank-stat method by usable net income, not the largest gross revenue number.',
        ],
        "drop": 'Alt-doc is not loose-doc; it is a different proof standard with the same servicing maths.',
    },
    {
        "title": 'Equity Release Buffer Leakage',
        "hook": (
            'Cash-out approved today can be dead capital tomorrow if the lender parks it in the wrong '
            'facility or the purpose trail is vague.'
        ),
        "mechanic": (
            'Equity release should be a purpose-built split with funds parked in offset until the next '
            'investment use. If released into redraw, mixed with salary, or crossed against multiple '
            'securities, deductibility and portability suffer. Lenders also shade cash-out purpose: '
            'future investment, renovations, business use, and debt consolidation each receive different '
            'evidence requests and LVR limits.'
        ),
        "retail_trap": (
            'Retail execution tops up the existing loan, crosses securities for convenience, and lets '
            'cash sit in redraw until a purchase appears. The investor then cannot trace interest, '
            'cannot refinance one property cleanly, and cannot prove the release was for the asset now '
            'being bought.'
        ),
        "execution": [
            '**Standalone release split** — cash-out sits in a separate variable split with offset, direct settlement trail, and no salary or private spending contamination.',
            '**Security isolation** — avoid cross-collateralising unless the valuation and exit maths beat the future refinance restriction.',
        ],
        "drop": 'Equity is useful only when the facility preserves traceability and exit control.',
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
