.PHONY: install install-hooks run run-paranoid models download lint fmt check test \
        build publish publish-test tool-install tool-uninstall \
        tag release clean

# ── setup ────────────────────────────────────────────────────────────────────

install:
	uv sync

install-hooks:
	git config core.hooksPath .githooks
	@echo "Configured git hooks from .githooks/"

# ── run ──────────────────────────────────────────────────────────────────────

run:
	uv run gterm

run-paranoid:
	uv run gterm --paranoid

# ── model management ─────────────────────────────────────────────────────────

models:
	uv run gterm models

download:
	uv run gterm download

# ── dev ──────────────────────────────────────────────────────────────────────

lint:
	uv run ruff check gterm/

fmt:
	uv run ruff format gterm/

check: lint
	uv run ruff check --select I gterm/

test:
	uv run pytest

# ── packaging ────────────────────────────────────────────────────────────────

build:
	uv build

# Install as a global CLI tool on this machine (survives outside the project dir)
tool-install:
	uv tool install . --reinstall

tool-uninstall:
	uv tool uninstall gterm

# Publish to PyPI (requires PYPI_TOKEN or `uv publish --token`)
publish: build
	uv publish

# Publish to TestPyPI first to verify
publish-test: build
	uv publish --publish-url https://test.pypi.org/legacy/ --token $(TESTPYPI_TOKEN)

# Tag a release — usage: make tag VERSION=0.2.0
tag:
	@test -n "$(VERSION)" || (echo "usage: make tag VERSION=x.y.z" && exit 1)
	git tag -s v$(VERSION) -m "release v$(VERSION)"
	@echo "Tagged v$(VERSION). Push with: git push origin v$(VERSION)"

# Full release: tag + push (triggers CI release workflow)
release:
	@test -n "$(VERSION)" || (echo "usage: make release VERSION=x.y.z" && exit 1)
	$(MAKE) tag VERSION=$(VERSION)
	git push origin v$(VERSION)

# ── clean ────────────────────────────────────────────────────────────────────

clean:
	rm -rf .venv __pycache__ gterm/__pycache__ dist .pytest_cache
	find . -name "*.pyc" -delete
