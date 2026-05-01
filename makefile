ub:
	docker compose -f docker-compose.yml -f docker-compose.net.yml up --build

u:
	docker compose -f docker-compose.yml -f docker-compose.net.yml up

d:
	docker compose down

dv:
	docker compose down -v

