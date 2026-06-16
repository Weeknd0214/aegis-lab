.PHONY: up down dev logs build ps health push

up:
	bash scripts/dev_up.sh

down:
	docker compose down

dev:
	docker compose --profile dev up -d --build web-dev
	@echo "Vite: http://127.0.0.1:5173"

logs:
	docker compose logs -f platform worker cvat_server

ps:
	docker compose ps

build:
	docker compose build

push:
	bash scripts/docker_push.sh

health:
	@curl -s http://127.0.0.1:8788/api/v1/health 2>/dev/null | python3 -m json.tool || echo "平台未启动"
