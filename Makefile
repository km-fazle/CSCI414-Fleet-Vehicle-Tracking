COMPOSE = docker compose

.PHONY: up down test lab shell teardown ui

up:
	$(COMPOSE) up -d --build

down:
	$(COMPOSE) down

test:
	$(COMPOSE) exec -T lab pytest tests/unit -q

lab:
	$(COMPOSE) up -d --build
	$(COMPOSE) exec -T lab bash scripts/run-lab.sh

shell:
	$(COMPOSE) exec lab bash

ui:
	$(COMPOSE) up -d
	$(COMPOSE) exec -T lab bash scripts/start-dashboard.sh
	@echo "Dispatch board: http://127.0.0.1:8787"

teardown:
	$(COMPOSE) exec -T lab bash scripts/teardown.sh
