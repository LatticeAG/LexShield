.PHONY: test acceptance build sync install

# LexShield v0.1 development targets (see CONTRIBUTING.md)

sync:
	uv sync
	pnpm install

install: sync

test:
	uv run pytest
	pnpm test
	pnpm test:golden

acceptance:
	uv run python scripts/acceptance_v01.py

build:
	pnpm --filter @latticeag/lexshield build
