.PHONY: up down dev logs build ps health

up:
	bash scripts/dev_up.sh

dev:
	docker compose --profile dev up -d --build web-dev
	@echo "Vite: http://127.0.0.1:5173"

down:
	docker compose -f docker-compose.yml -f docker-compose.cvat.yml --profile dev down

logs:
	docker compose logs -f platform worker

ps:
	docker compose ps

build:
	docker compose build

health:
	@curl -s http://127.0.0.1:8787/api/v1/health 2>/dev/null | python3 -m json.tool || echo "平台未启动"
