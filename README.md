# PlayWorld project page

Promotional research website for PlayWorld, a player-guided benchmark for
evaluating geometry consistency, interaction fidelity, and state evolution in
long-horizon interactive world models.

The curated demo carousel contains one 30+ second rollout for each of nine
evaluated models.

## Development

```bash
npm install
npm run dev
```

## Validation

```bash
npm run build
npm test
```

## Benchmark and agent code

The publishable Python implementation is in [`playworld_code/`](playworld_code/).
It contains the Gemini dual-sampling metrics, Fail=1 OE-split aggregation,
`PlayWorldEngine`, HappyOyster/Genie3 adapters, the fault-tolerant Agent harness,
CLI commands, configuration examples, and tests. The external datasuite is
distributed separately and is intentionally not committed to this repository.

See [`playworld_code/README.md`](playworld_code/README.md) for installation,
credentials, evaluation, aggregation, and Agent-control usage.
