# gatectl Integration

## Architecture

```
User  →  gatectl (REPL or one-shot)  →  gate-server (:8090 or :8900)
              ↓                                ↓
         cmd.Cmd shell                    gate-core (in-process)
         session state                    tool filtering
         (mode, envelope)                 envelope signing
```

gatectl is a **pure client**. It talks to gate-server over HTTP and
maintains local session state (current mode, last envelope).

## Two Modes

### Interactive REPL
```bash
$ gatectl --server http://localhost:8090
gatectl [0.10 normal]> demo
Registered 5 demo tools.
gatectl [0.10 normal]> mode 0.5
Mode set to 0.50 (elevated)
gatectl [0.50 elevated]> filter
Mode: 0.50 (elevated)
VISIBLE (4):
  read_file                read_only
  analyze                  advisory
  send_email               external_action
  write_db                 state_mutation
SUPPRESSED (1):
  deploy                   high_impact [SUPPRESSED]
gatectl [0.50 elevated]> validate deploy
DENIED — execution_class_suppressed
gatectl [0.50 elevated]> envelope read_file
Envelope built for read_file at mode 0.50
  execution_mode: cautious
  max_tool_calls: 10
  branching:      deny
gatectl [0.50 elevated]> verify
VALID — signature verified
gatectl [0.50 elevated]> tamper
TAMPER DETECTED — signature mismatch (max_tool_calls changed to 9999)
```

### One-Shot Commands
```bash
$ gatectl health
OK — ok

$ gatectl filter 0.5
VISIBLE    read_file                read_only
VISIBLE    analyze                  advisory
VISIBLE    send_email               external_action
VISIBLE    write_db                 state_mutation
SUPPRESSED deploy                   high_impact

$ gatectl validate deploy 0.5
DENIED: execution_class_suppressed
```

## Differentiation vs gate-cli (Creator 2)

| Dimension | gate-cli | gatectl |
|-----------|----------|---------|
| Dependencies | click, httpx, rich, pyyaml, maelstrom-gate | None (stdlib) |
| Framework | Click (batch-only) | cmd.Cmd (interactive REPL) |
| Session state | None | Mode, last envelope persist between commands |
| Prompt | Static | Dynamic: shows mode + zone |
| Tab completion | Click built-in | cmd.Cmd built-in (execution classes) |
| Output | Rich tables, JSON, YAML | Plain text (pipe-friendly) |
| One-shot | Yes | Yes |
| Interactive | No | Yes (REPL) |
| Install | pip install (5 deps) | Just run (0 deps) |

**gatectl trades rich formatting for interactivity.** The REPL lets operators
explore gate-server state conversationally, keeping context between commands.
gate-cli is better for scripting; gatectl is better for exploration and demos.

## Connections

- **gate-server** (Layer 1): primary dependency, all 8 endpoints proxied
- **gate-sdk**: could embed gatectl as a debugging tool in SDK projects
- **gate-dashboard/gate-dash**: complementary — dashboard for visual, CLI for terminal
