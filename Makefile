# Fly-In tester. Run `make` (or `make help`) to list the targets.

# Project under test: by default the folder that contains this repository.
PROJECT ?= $(abspath ..)
# Interpreter: the project's .venv if there is one (it has pydantic, pygame, ...).
PYTHON  ?= $(if $(wildcard $(PROJECT)/.venv/bin/python),$(PROJECT)/.venv/bin/python,python3)
# Command that runs one map; {map} is replaced by the map path. The default
# is the adapter, which runs the project's logic without its window.
CMD     ?= $(PYTHON) $(CURDIR)/adapters/fly_in_project.py {map}
# Directory the command runs in (the project's root by default).
CWD     ?= $(PROJECT)
JOBS    ?= 4
TIMEOUT ?= 25
# Optional: GROUP=provided|provided-invalid|edge-valid|edge-invalid
#           FILTER=<text in the map path>   ARGS=<extra options>
GROUP   ?=
FILTER  ?=
ARGS    ?=

export FLY_IN_PROJECT := $(PROJECT)

.DEFAULT_GOAL := help
.PHONY: help run run-strict list check whitebox test lint all maps clean

help:
	@echo 'make run          run the tester on all maps (PROJECT, CMD, CWD, GROUP, FILTER, JOBS, TIMEOUT, ARGS)'
	@echo 'make run-strict   like run, but turns above the targets fail too'
	@echo 'make list         list the maps (GROUP, FILTER)'
	@echo 'make check        check an output: make check MAP=<map> OUT=<file or ->'
	@echo 'make test         tests of the tester itself'
	@echo 'make whitebox     unit tests of the project (PROJECT=<path>)'
	@echo 'make lint         flake8 and mypy --strict'
	@echo 'make all          lint + test + whitebox'
	@echo 'make maps         regenerate maps/ and manifest.json from tools/build_maps.py'
	@echo 'make clean        remove caches'
	@echo
	@echo 'Examples:'
	@echo '  make run GROUP=edge-invalid'
	@echo '  make run PROJECT=../other-project CMD="python3 main.py {map}"'
	@echo '  make run PROJECT=../other-project CMD="./fly_in {map}"'

run:
	$(PYTHON) -m fly_in_tester run --cmd '$(CMD)' --cwd '$(CWD)' --jobs $(JOBS) --timeout $(TIMEOUT) \
		$(if $(GROUP),--group $(GROUP)) $(if $(FILTER),--filter '$(FILTER)') $(ARGS)

run-strict:
	$(MAKE) run ARGS='--strict-targets $(ARGS)'

list:
	$(PYTHON) -m fly_in_tester list $(if $(GROUP),--group $(GROUP)) $(if $(FILTER),--filter '$(FILTER)')

check:
	@test -n '$(MAP)' -a -n '$(OUT)' || { echo 'usage: make check MAP=<map> OUT=<file or ->'; exit 2; }
	$(PYTHON) -m fly_in_tester check '$(MAP)' '$(OUT)'

test:
	$(PYTHON) -m unittest discover -s tests -t .

whitebox:
	$(PYTHON) -m unittest discover -s whitebox -t .

lint:
	$(PYTHON) -m flake8 .
	$(PYTHON) -m mypy .

all: lint test whitebox

maps:
	$(PYTHON) tools/build_maps.py --project '$(PROJECT)'

clean:
	@find . -type d \( -name __pycache__ -o -name .mypy_cache \) -prune -exec rm -rf {} +
