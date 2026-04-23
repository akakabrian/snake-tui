.PHONY: all venv run test test-only perf clean

# Pure-Python engine — no bootstrap / SWIG step needed. `make all` still
# installs deps so a fresh clone reaches "ready to play" in one command.
all: venv

venv: .venv/bin/python
.venv/bin/python:
	python3 -m venv .venv
	.venv/bin/pip install -e .

run: venv
	.venv/bin/python play.py

# Full QA suite.
test: venv
	.venv/bin/python -m tests.qa

# Subset. Usage: make test-only PAT=collide
test-only: venv
	.venv/bin/python -m tests.qa $(PAT)

# Perf baseline.
perf: venv
	.venv/bin/python -m tests.perf

clean:
	rm -rf .venv *.egg-info tests/out/*.svg tests/out/*.png
