.PHONY: up down build rebuild logs train list-admins add-admin remove-admin deploy

## Run without recompiling (quickly)
up:
	@GEMINI_VAL=$$(grep -E '^GEMINI_API_KEY[[:space:]]*=' .env 2>/dev/null | cut -d= -f2- | tr -d '"'\'' '); \
	if [ -n "$$GEMINI_VAL" ]; then \
		echo "Starting only Bot service (using Gemini API)..."; \
		docker compose up --no-deps bot; \
	else \
		echo "Starting Bot and AI Service (using local models)..."; \
		docker compose up bot ai_service; \
	fi

## Rebuild only the changed images and run
build:
	@GEMINI_VAL=$$(grep -E '^GEMINI_API_KEY[[:space:]]*=' .env 2>/dev/null | cut -d= -f2- | tr -d '"'\'' '); \
	if [ -n "$$GEMINI_VAL" ]; then \
		echo "Building and starting only Bot service (using Gemini API)..."; \
		DOCKER_BUILDKIT=1 docker compose up --build --no-deps bot; \
	else \
		echo "Building and starting Bot and AI Service (using local models)..."; \
		DOCKER_BUILDKIT=1 docker compose up --build bot ai_service; \
	fi

## Complete rebuild from scratch (without cache)
rebuild:
	@GEMINI_VAL=$$(grep -E '^GEMINI_API_KEY[[:space:]]*=' .env 2>/dev/null | cut -d= -f2- | tr -d '"'\'' '); \
	if [ -n "$$GEMINI_VAL" ]; then \
		echo "Complete rebuild from scratch (using Gemini API)..."; \
		DOCKER_BUILDKIT=1 docker compose build --no-cache bot && docker compose up --no-deps bot; \
	else \
		echo "Complete rebuild from scratch (using local models)..."; \
		DOCKER_BUILDKIT=1 docker compose build --no-cache bot ai_service && docker compose up bot ai_service; \
	fi

## Deploy in background (daemon mode)
deploy:
	@GEMINI_VAL=$$(grep -E '^GEMINI_API_KEY[[:space:]]*=' .env 2>/dev/null | cut -d= -f2- | tr -d '"'\'' '); \
	if [ -n "$$GEMINI_VAL" ]; then \
		echo "Deploying only Bot service in background (using Gemini API)..."; \
		DOCKER_BUILDKIT=1 docker compose up --build -d --no-deps bot && docker compose stop ai_service 2>/dev/null || true; \
	else \
		echo "Deploying Bot and AI Service in background (using local models)..."; \
		DOCKER_BUILDKIT=1 docker compose up --build -d bot ai_service; \
	fi

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
