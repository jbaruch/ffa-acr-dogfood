# jbaruch/ffa-acr-dogfood

Write professional, persuasive complaint letters to US airlines on behalf of passengers — grounded in the airline's own published policies, federal DOT regulations, and the passenger's loyalty status, not generic grievances.

## Installation

This is the ACR dogfood copy of [upstream frequent-flyer-advocate](https://github.com/jbaruch/frequent-flyer-advocate).

Version 0.9.39 is being prepared. Before publishing or installing it, release and install the corrected [ACR CLI](https://github.com/jbaruch/agentic-context-registry) with `source.tesslIdentity` support. ACR 0.1.3 and earlier reject that field. The candidate CLI is not release-approved.

Once that CLI and this package's v0.9.39 release are available, run these commands from your project directory. Select the agents you use in `acr init`:

```shell
acr init --agent claude-code --agent codex --agent cursor --non-interactive
acr install github:jbaruch/ffa-acr-dogfood@v0.9.39 --non-interactive
acr realize
acr check
```

Tessl is optional. The SessionStart hook skips its update with a notice when Tessl is absent. When present, it runs `tessl update --yes` in the project directory and reports any failure.

This copy is not published to Tessl. Repository Actions, including the inherited Tessl publication workflow, are disabled. Manual ACR publication does not require the inherited workflow secrets listed in `.env.example`.

## What's Included

### Skills

| Skill | Description |
|-------|-------------|
| [frequent-flyer-advocate](skills/frequent-flyer-advocate/SKILL.md) | Intake → flight verification → policy research → letter construction for airline service failures (delays, cancellations, baggage, downgrades, denied boarding). Fits the letter to the airline's submission channel and its character limit. Tracks compensation credits and prior complaints across a shared inventory. |
| [using-travel-credits](skills/using-travel-credits/SKILL.md) | Action router over the shared travel-credits inventory at `~/.claude/travel-credits/`: check store readiness, list, show expiring, match credits to a booking scenario, add, mark used. The invocation surface other plugins call instead of shipping their own copy of the tracker. |

### Rules

| Rule | Summary |
|------|---------|
| [boundaries](rules/boundaries.md) | Never fabricate regulations, docket numbers, citations, or policy quotes — cite only verifiable sources. |
| [letter-quality](rules/letter-quality.md) | The mandatory requirements every complaint letter must satisfy, plus what the web-form variant may drop and what survives compression. |
| [escalation-output](rules/escalation-output.md) | Required contents for every escalation guide / next-steps document. |
| [complaint-patterns](rules/complaint-patterns.md) | How to use prior-complaint history (from the complaint bank) as escalation leverage. |

See [CHANGELOG.md](CHANGELOG.md) for version history.
