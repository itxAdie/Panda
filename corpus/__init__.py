"""Milestone 1 — deterministic corpus foundation.

The resolver is the load-bearing component. Its safety guarantees are enforced by
stage order, not by convention: see corpus.resolver.

Stage order is MANDATORY. Drops run BEFORE canonical matching. Violating this
silently resolves ambiguous forms to the wrong place — demonstrated in
data/normalization/rerun-results.md, worth 7.6 points of false resolution.
"""

# Resolution outcomes. Ordered by severity so callers cannot miss a Drop.
UNRESOLVED = "unresolved"          # genuine miss — safe, logged
DROPPED = "dropped"                # refused by policy — safe, must be auditable
MEASUREMENT = "measurement"        # size/currency/category — NOT a place
RESOLVED = "resolved"              # bound to a canonical entity

OUTCOMES = (RESOLVED, DROPPED, MEASUREMENT, UNRESOLVED)