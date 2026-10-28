# 13: Review screener v2 candidates for gate 7

**Role:** strategist

**Status:** ready-for-agent

**Blocked by:** 12

**What to build:** A gate-7 recommendation the Owner can act on in one command: which markets from the screener v2 run to approve into the first dataset, with the chart evidence for each, and a verdict on whether the v2 gates need a v3 change (base-activity gate for gap markets) before the Owner relies on them.

Spec: [../spec.md](../spec.md)

- [ ] Each of the v2 top-10 charts (`reports/screens/20261028-113941/charts/`) reviewed and classified: sweep-and-return / gap market / trend / chop, with one line of reasoning each
- [ ] Recommended approve list (markets + the exact `ttp dataset approve 20261028-113941 <markets...> --name <name>` command) and a reject list, written to `.scratch/initial-infrastructure/gate-7-recommendation.md`
- [ ] Verdict on ticket 12's three observations (vacuous calm-base gate, `base_range = 0` markets, `retrace_median > 1`): keep v2 as is, or specify the v3 rule precisely for a follow-up ticket
- [ ] STRATEGY.md screening section updated if the rule changes; status line stays "awaiting Owner approval (gate 2)"
