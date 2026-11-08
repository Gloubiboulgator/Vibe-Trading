"""PEA mode: a per-session switch for users who invest through a French PEA.

The PEA (plan d'épargne en actions) only holds shares of companies whose
registered office is in the EU or the EEA, and funds that keep at least 75 %
of their assets in such shares. A user who turns the mode on states that once,
instead of repeating "éligible PEA" in every message (see the 2026-11-08 trace
where the agent proposed Vertiv, nVent and Modine to a PEA investor).

The mode does two things:

* :data:`PEA_MODE_BLOCK` rides in the current user message, like the goal
  context, so the system prompt stays byte-stable for the prefix cache.
* :data:`PEA_STANDING_MARKET` seeds a standing, non-explicit "eu" preference in
  the resolution context, so "Sanofi" resolves to SAN.PA without the user
  having to write "PEA" first.
"""

from __future__ import annotations

PEA_STANDING_MARKET = "eu"
PEA_SOURCE_ID = "session:pea_mode"

# EU member states plus the three EEA states outside the EU. The UK (since
# 2021) and Switzerland are not eligible.
PEA_ELIGIBLE_COUNTRIES = (
    "Austria, Belgium, Bulgaria, Croatia, Cyprus, Czech Republic, Denmark, "
    "Estonia, Finland, France, Germany, Greece, Hungary, Ireland, Italy, "
    "Latvia, Lithuania, Luxembourg, Malta, Netherlands, Poland, Portugal, "
    "Romania, Slovakia, Slovenia, Spain, Sweden, Iceland, Liechtenstein, Norway"
)

PEA_MODE_BLOCK = f"""<pea-mode>
The user invests through a French PEA (plan d'épargne en actions). This holds for the whole conversation, even when a message does not repeat it.
- Eligible: shares of companies whose registered office is in the EU or the EEA ({PEA_ELIGIBLE_COUNTRIES}), and funds or ETFs labelled PEA-eligible (they keep at least 75 % in such shares; many synthetic ETFs give world or US exposure this way).
- Not eligible: companies headquartered elsewhere (United States, United Kingdom, Switzerland, Asia...), even when they also trade in Paris or Frankfurt, and ADRs. Eligibility follows the registered office, not the listing.
- When you screen or propose securities, propose only eligible ones. Prefer the euro-area listing (SAN.PA, not SNY.US) and quote prices in EUR.
- Before you call a company eligible, check its country with get_stock_profile. If the country is unknown, say eligibility is not verified.
- When the user names an ineligible security, still answer the question, state plainly that it cannot be held in a PEA, and when useful name an eligible alternative (a European peer or a PEA-eligible ETF).
- Do not state PEA ceilings, holding periods or tax rates as figures unless a tool result in this run supports them.
</pea-mode>"""


def wrap_user_message(user_message: str) -> str:
    """Return the message the model sees for one PEA-mode turn."""
    return f"{PEA_MODE_BLOCK}\n\n{user_message}"
