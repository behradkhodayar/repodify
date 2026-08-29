.PHONY: run fake stop

run:
	./launch

fake:
	./launch --fake

stop:
	docker compose stop
