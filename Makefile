COMPOSE ?= docker compose

.PHONY: dev dev-infra down logs api web lint fmt test ci smoke schemas

dev: ## 构建并启动全套本地栈（API/Web/Postgres/Redis/MinIO/Temporal）
	$(COMPOSE) up -d --build

dev-infra: ## 只启动基础设施容器；API/Web 用 make api / make web 在本机跑
	$(COMPOSE) up -d postgres redis minio temporal temporal-ui

down: ## 停止并移除容器（保留数据卷）
	$(COMPOSE) down

logs:
	$(COMPOSE) logs -f

api: ## 本机热重载运行 API（先 uv sync）
	uv run uvicorn videoforge_api.main:app --reload --port 8000

web: ## 本机运行 Web dev server（先 pnpm install）
	pnpm --filter @videoforge/web dev

lint:
	uv run ruff check .
	uv run ruff format --check .
	pnpm -r typecheck

fmt:
	uv run ruff format .
	uv run ruff check --fix .

schemas: ## 从 Pydantic 真值再生成 schemas/ 与 contracts-ts 类型
	uv run python -m videoforge_contracts.export
	pnpm --filter @videoforge/contracts generate

test:
	uv run pytest
	pnpm -r test

ci: lint test

smoke: ## 对运行中的栈做健康检查
	curl -fsS http://localhost:$${API_PORT:-8000}/healthz
	@echo ""
	@curl -fsS -o /dev/null http://localhost:$${WEB_PORT:-5173} && echo "web: ok"
	@curl -fsS -o /dev/null http://localhost:$${TEMPORAL_UI_PORT:-8233}/api/v1/namespaces && echo "temporal: ok"
