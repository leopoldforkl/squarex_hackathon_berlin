export UID := $(shell id -u)

.PHONY: build up down logs cli

build:
	docker compose build

up:
	mkdir -p logs runtime
	docker compose up -d

down:
	docker compose down

logs:
	docker compose logs -f

# make cli ARGS='status'   make cli ARGS='start "pick up the can" --seconds 90'
cli:
	docker compose run --rm ui python -m squarex $(ARGS)
