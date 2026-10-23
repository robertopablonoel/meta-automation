"""Weekly Meta ads review pipeline for Spicy Cubes (deterministic core).

Stages: pull (read-only Graph API) -> join (name/transcript joins) ->
compute (tiers, signal paths, rollups) -> publish (stub).

READ-ONLY against Meta. Never POST. See DESIGN.md and CLAUDE.md Rule 0.
"""
