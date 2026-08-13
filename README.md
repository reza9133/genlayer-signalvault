# SignalVault

**A conservative multi-channel signal-triggered vault primitive for GenLayer.**

SignalVault is a reusable Intelligent Contract that locks assets and releases them only after independent multi-validator consensus confirms a specific public signal across 3–5 external channels.

It is designed as a high-quality primitive for milestone-based grants, parametric releases, crowdfunding success conditions, and event-conditioned escrow — not as a thin LLM wrapper or demo.

## Key Features

- **Multi-channel public signal detection** (3–5 HTTPS sources)
- **Independent re-execution by validators** (not format-only checks)
- **Closed-schema LLM analysis** with strict relevance + confirmation levels
- **Exact canonical string consensus** via custom `run_nondet_unsafe`
- **Conservative state machine**: `ACTIVE → PENDING → CONFIRMED → RELEASED`
- **Mandatory owner veto** + challenge window before release
- **Pull-based claim** for beneficiaries
- Clear separation between non-deterministic analysis and deterministic state updates

## How Consensus Works

1. Anyone can call `open_check()` when the vault is `ACTIVE`.
2. `adjudicate()` triggers the non-deterministic block:
   - Every validator independently fetches each channel with `gl.nondet.web.render`
   - Runs the same closed-schema LLM prompt
   - Builds a canonical reading vector (`C0:F0:RHIGH:CSTRONG:X0|...`)
   - Derives a final decision (`CONFIRMED` or `ACTIVE`)
3. Validators accept **only** if they produce the exact same canonical string (decision + evidence counts + vector).
4. Only after consensus succeeds is the contract state updated.

This design ensures validators bind the **substantive outcome**, not merely JSON shape.

## State Machine

| State       | Description                                      |
|-------------|--------------------------------------------------|
| ACTIVE      | Waiting for signal check                         |
| PENDING     | Check opened, waiting for adjudication           |
| CONFIRMED   | Signal confirmed, challenge window running       |
| RELEASED    | Challenge window passed, funds claimable         |

Owner can always `veto()` while in `CONFIRMED` and return the vault to `ACTIVE`.

## Core Methods

| Method            | Type     | Description                                      |
|-------------------|----------|--------------------------------------------------|
| `create_vault`    | payable  | Initialize vault with signal, channels, beneficiaries |
| `open_check`      | write    | Move from ACTIVE → PENDING                       |
| `adjudicate`      | write    | Run multi-validator signal consensus             |
| `veto`            | write    | Owner cancels a confirmation                     |
| `release`         | write    | Finalize after challenge window                  |
| `claim`           | write    | Beneficiary pulls their share                    |
| `get_full_info`   | view     | Human-readable status summary                    |

## Why This Is Not a Thin Wrapper

- Validators independently re-fetch live web pages and re-run the LLM analysis
- Consensus requires exact match on a canonical decision string derived from evidence counts
- Multiple independent public sources are required
- Full lifecycle with owner controls and time-locked release
- Designed as a reusable primitive, not a one-off demo

## Deployment

- Network: GenLayer Bradbury Testnet
- Contract address: `0x7ba069b6224fF48CBa3490fBa9B0399520efE383`
- Explorer: https://explorer-bradbury.genlayer.com/address/0x7ba069b6224fF48CBa3490fBa9B0399520efE383

## Source

The exact source deployed on-chain is in `contracts/signalvault.py`.
