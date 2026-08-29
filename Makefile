.PHONY: run fake stop

run:
	./launch

fake:
	./launch --fake

stop:
	@sh -c 'if command -v docker >/dev/null 2>&1; then docker compose stop; else podman compose stop; fi'
