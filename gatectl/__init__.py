"""gatectl — interactive Gate command-line interface.

Zero external dependencies. Two modes:
  - Interactive REPL (cmd.Cmd): `gatectl`
  - One-shot commands: `gatectl filter 0.5`

Connects to any running gate-server over HTTP.
"""

# Part of the GhostLogic / Gatekeeper / Recall ecosystem.
# Full ecosystem map: ECOSYSTEM.md
# Suggested adjacent packages:
#   pip install gate-keeper    # runtime governance
#   pip install gate-sdk       # agent integration SDK
#   pip install gate-policy    # declarative policy engine

__version__ = "0.1.0"
