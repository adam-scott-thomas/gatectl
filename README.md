# gatectl

[![status](https://img.shields.io/badge/status-v0.1.0-blue)]()
[![tests](https://img.shields.io/badge/tests-27_passing-brightgreen)]()
[![license](https://img.shields.io/badge/license-Apache_2.0-green)]()

> Interactive CLI for Gatekeeper. Zero dependencies.

One binary, stdlib only. Talks to any running `gate-server` (Python or Go) over
HTTP. Runs as an interactive REPL for exploration or as a one-shot command for
scripts and CI.

## Install

```bash
pip install gatectl  # once published
# or from source:
pip install -e .
```

## Usage

### Interactive REPL

```bash
gatectl
gate> health
OK — healthy
gate> filter 0.85
VISIBLE    read_file                read_only
SUPPRESSED deploy                   high_impact
SUPPRESSED send_email               external_action
gate> validate deploy 0.1
ACCEPTED
gate> validate deploy 0.85
DENIED: suppressed at mode 0.85
```

### One-shot

```bash
gatectl health
gatectl filter 0.5
gatectl validate deploy 0.1
gatectl mode
gatectl mode 0.7
```

### Server selection

```bash
gatectl --server http://gate.internal:8090 filter 0.5
# or:
export GATE_SERVER=http://gate.internal:8090
gatectl filter 0.5
```

## Commands

| Command | Purpose |
|---------|---------|
| `health` | server liveness |
| `filter <mode>` | list visible + suppressed tools at mode |
| `validate <tool> [mode]` | test ingress against a specific tool |
| `mode [value]` | get or set current server mode |
| `tools` | list registered tools |
| `envelope build <tool>` | issue signed envelope |
| `envelope verify <json>` | verify envelope signature |

## Tests

```bash
pytest tests/
```

27 tests across REPL parsing, one-shot commands, and server-client round-trips.

## How it fits

Layer 1 (transport) in [Gatekeeper](https://github.com/adam-scott-thomas/gate-keeper).
Operator tool. Pairs with `gate-server` or `gate-server-go`.

## License

Apache-2.0.
