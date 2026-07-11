# Changelog

All notable changes to LexShield are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-07-11

First open-source release. Local-first policy firewall for agent tool calls — deterministic evaluation works with no API keys.

### Added

- **Python engine** (`lexshield` on PyPI): policy engine, deterministic classifier, optional LLM classifier, redaction, trace sinks, FastAPI server, `Shield` SDK with `@shield.guard`
- **CLI** (`lexshield-cli`): `init`, `check`, `evaluate`, `run`, `challenge` commands; `lexshield-check-packs` for CI
- **TypeScript SDK** (`@latticeag/lexshield` on npm): `evaluate`, `guard`, policy loader, golden-parity engine
- **Policy packs**: `baseline-deny`, `pii-guard`, `change-window`
- **Built-in intent taxonomy**: 24 frozen intents with severity ranks ([Appendix B](./SPEC.md#appendix-b--built-in-intent-catalog-v01)); exported in [`taxonomy/builtin.yaml`](./taxonomy/builtin.yaml)
- **Golden fixtures**: cross-engine regression suite under `fixtures/golden/`
- **Examples**: `python-block-exfil`, `python-challenge-delete`, `ts-evaluate`
- **Documentation**: policy, intents, SDK guides, CLI reference, security model
- **CI**: Python pytest, TypeScript vitest, golden parity, pack validation

### Security

- Default-deny policy packs block unknown tools
- Deterministic secret patterns map to `security.secret_exposure` → BLOCK
- Redaction applied to LLM payloads and NDJSON traces
- API server refuses `0.0.0.0` bind without `--i-understand-bind-all`

### Notes

- LLM classification is optional and probabilistic; deterministic path is the v0.1 default
- See [docs/security.md](./docs/security.md) for threat model and honest limits
- Full specification: [SPEC.md](./SPEC.md)

[0.1.0]: https://github.com/latticeag/lexshield/releases/tag/v0.1.0
