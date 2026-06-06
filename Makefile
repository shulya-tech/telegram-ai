.PHONY: up down build rebuild logs train list-admins add-admin remove-admin

## Run without recompiling (quickly)
up:
	docker compose up

## Rebuild only the changed images and run
build:
	DOCKER_BUILDKIT=1 docker compose up --build

## Complete rebuild from scratch (without cache)
rebuild:
	DOCKER_BUILDKIT=1 docker compose build --no-cache && docker compose up

down:
	docker compose down

logs:
	docker compose logs -f

## Run fine-tuning. Set USE_GPU=true in .env to enable GPU.
train:
	$(eval USE_GPU ?= false)
	@if [ "$$(grep -s '^USE_GPU=true' .env)" ]; then \
		echo "Training with GPU..."; \
		DOCKER_BUILDKIT=1 docker compose -f docker-compose.yml -f docker-compose.gpu.yml run --rm train python train.py; \
	else \
		echo "Training with CPU..."; \
		DOCKER_BUILDKIT=1 docker compose run --rm train python train.py; \
	fi

list-admins:
	docker compose exec -w /app/bot bot python3 admin_cli.py list

add-admin:
	@if [ -z "$(ID)" ]; then \
		echo "Usage: make add-admin ID=<telegram_user_id>"; \
		exit 1; \
	fi
	docker compose exec -w /app/bot bot python3 admin_cli.py add $(ID)

remove-admin:
	@if [ -z "$(ID)" ]; then \
		echo "Usage: make remove-admin ID=<telegram_user_id>"; \
		exit 1; \
	fi
	docker compose exec -w /app/bot bot python3 admin_cli.py remove $(ID)
