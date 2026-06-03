# Porta de verificació del projecte (backend + frontend).
# Ús: `make verifica`  ·  `make backend-test`  ·  `make frontend-check`
.PHONY: verifica backend-test frontend-check frontend-build

verifica: backend-test frontend-check ## Executa tota la bateria de verificació

backend-test: ## Tests del backend (pytest)
	cd backend && python -m pytest -q

frontend-check: ## type-check + lint + build del frontend
	cd frontend && npm run type-check && npm run lint && npm run build
