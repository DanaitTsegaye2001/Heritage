# The Heritage Short — one command: `make film`
PYTHON  ?= python3
VENV    := .venv
PY      := $(VENV)/bin/python
STAMP   := $(VENV)/.installed
RUN     := $(PY) -m pipeline.run
SHOTS   ?=
SHOTARG := $(if $(SHOTS),--shots $(SHOTS),)

.PHONY: film film-offline setup validate script keyframes shots narration music assemble reroll costs test clean-outputs help

help:            ## list targets
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  make %-14s %s\n", $$1, $$2}'

film: $(STAMP)   ## validate + run every stage -> outputs/final/heritage_16x9.mp4 and heritage_9x16.mp4
	$(RUN)

film-offline: $(STAMP) ## same film with stub providers only: no API keys, no network, $0
	$(RUN) --offline

$(STAMP): requirements.txt
	$(PYTHON) -m venv $(VENV)
	$(PY) -m pip install --quiet --upgrade pip
	$(PY) -m pip install --quiet -r requirements.txt
	@touch $@

setup: $(STAMP)  ## create .venv and install dependencies

validate: $(STAMP) ## check storyboard.json against the schema + semantic rules
	$(RUN) script

script keyframes shots narration music assemble: $(STAMP) ## run one stage (SHOTS=s03,s07 to limit)
	$(RUN) $@ $(SHOTARG)

reroll: $(STAMP) ## force-regenerate per-shot artifacts for SHOTS=..., then reassemble
	@test -n "$(SHOTS)" || (echo "usage: make reroll SHOTS=s03" && exit 2)
	$(RUN) keyframes shots narration --shots $(SHOTS) --force
	$(RUN) music assemble

costs: $(STAMP)  ## summarise runs.jsonl (latency / GPU minutes / list-price cost)
	$(PY) -m pipeline.costs

test: $(STAMP)   ## schema tests + selective-regeneration end-to-end test (stub providers)
	$(PY) -m unittest discover -s tests -v

clean-outputs:   ## delete generated media (keeps runs.jsonl)
	find outputs -mindepth 1 ! -name .gitkeep ! -name README.md -delete
