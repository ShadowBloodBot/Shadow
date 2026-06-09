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

STRATEGIES = [
    {
        "title": "Fixed vs Variable in the Current RBA Cycle",
        "body": (
            "When rates are shifting, split your loan strategy: fix what you cannot afford "
            "to rise (living costs buffer), keep flexibility on the portion you may repay early. "
            "Brokers model 2–3 scenarios across 24 months, not just today's rate."
        ),
        "source": "RBA cash rate decisions + lender pricing sheets",
        "link": "https://www.rba.gov.au/statistics/cash-rate/",
    },
    {
        "title": "How Offset Accounts Actually Save You Money",
        "body": (
            "A 100% offset reduces interest charged on your loan balance dollar-for-dollar. "
            "For investors, offsets can preserve loan deductibility compared with parking cash "
            "in the loan directly. Structure offsets per loan segment with your broker."
        ),
        "source": "ASIC Moneysmart — home loans",
        "link": "https://moneysmart.gov.au/home-loans",
    },
    {
        "title": "First Home Guarantee — Who It Helps in 2026",
        "body": (
            "Low-deposit pathways can cut years off your purchase timeline, but LMI risk, "
            "serviceability buffers, and postcode caps still apply. Pre-approval first, "
            "then confirm scheme eligibility with your broker and conveyancer."
        ),
        "source": "Housing Australia — Home Guarantee Scheme",
        "link": "https://www.housingaustralia.gov.au/",
    },
    {
        "title": "LVR, LMI and the 80% Threshold",
        "body": (
            "Crossing 80% LVR usually triggers LMI — sometimes worth it to enter the market, "
            "sometimes not. Compare: LMI premium vs 12–24 months of rent + price movement. "
            "Your broker can run break-even on keep renting vs buy now."
        ),
        "source": "APRA lending guidance / lender LMI schedules",
        "link": "https://www.apra.gov.au/",
    },
    {
        "title": "Serviceability Buffers Brokers Use",
        "body": (
            "Lenders stress-test repayments above your actual rate (often +2.5% to +3%). "
            "That is why pre-approval amounts differ from online calculators. Bring payslips, "
            "HECS, limits on cards — brokers clean up file before lodgement."
        ),
        "source": "APRA serviceability guidance",
        "link": "https://www.apra.gov.au/",
    },
    {
        "title": "When Refinancing Is Worth the Break Cost",
        "body": (
            "Refinance when NPV is positive: monthly saving × hold period > switching costs + break fees. "
            "Also refinance for structure (split loans, offset, cash-out for investment deposit) "
            "not rate alone."
        ),
        "source": "MFAA broker best-practice frameworks",
        "link": "https://www.mfaa.com.au/",
    },
    {
        "title": "Investment Loans — IO vs P&I",
        "body": (
            "Interest-only can improve cash flow early; P&I builds equity and can improve "
            "serviceability on next purchase. Many investors use IO with offset, then switch "
            "before expiry. Plan the expiry date at settlement, not five years later."
        ),
        "source": "ATO rental property / loan purpose guidance",
        "link": "https://www.ato.gov.au/individuals-and-families/investments-and-assets",
    },
    {
        "title": "Equity Release for Property #2",
        "body": (
            "Usable equity = (value × max LVR) − loan balance. Banks order fresh valuations — "
            "do not assume Domain estimate is bank value. Cross-collateral vs standalone "
            "security is a major broker decision with real exit-cost implications."
        ),
        "source": "CoreLogic / lender valuation practice",
        "link": "https://www.corelogic.com.au/",
    },
    {
        "title": "Broker vs Going Direct to a Bank",
        "body": (
            "Brokers access multiple lenders, compare policy (not just rate), and manage "
            "credit assessment. Direct can work if your file is simple and you know the policy. "
            "For investors, policy nuance usually favours a broker."
        ),
        "source": "MFAA — why use a broker",
        "link": "https://www.mfaa.com.au/why-use-a-broker",
    },
    {
        "title": "Pre-Approval — What to Prepare",
        "body": (
            "3–6 months transactions, payslips, liabilities, rental income evidence, "
            "and realistic purchase range. Conditional pre-approval is not unconditional — "
            "do not exchange until finance clause is cleared on the actual property."
        ),
        "source": "ASIC Moneysmart — buying a home checklist",
        "link": "https://moneysmart.gov.au/buying-a-home",
    },
    {
        "title": "Stamp Duty and Concessions by State",
        "body": (
            "NSW, VIC, QLD, WA all differ on FHB thresholds and investment surcharges. "
            "Foreign purchaser surcharges and land tax exposure matter for investors. "
            "Model total purchase cost, not just loan repayments."
        ),
        "source": "State revenue office guides",
        "link": "https://www.revenue.nsw.gov.au/",
    },
    {
        "title": "Rate Lock Tactics Before Settlement",
        "body": (
            "If rates are rising into settlement, ask about rate lock and fee. If falling, "
            "float. Locks are usually 60–90 days — align with your conveyancer's settlement date, "
            "not contract date."
        ),
        "source": "Lender product disclosure statements",
        "link": "https://moneysmart.gov.au/home-loans/choosing-a-home-loan",
    },
]

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
