# PacketDeck

PacketDeck is a self-hosted web UI for MeshCore companion devices. The current implementation provides a SvelteKit frontend, a Python FastAPI backend, PostgreSQL persistence, WebSocket updates, MQTT integration endpoints, and automation foundations.

This repository is currently focused on MeshCore WiFi/TCP companion connections. Serial USB and BLE remain part of the project goal, but they are not the active runtime path in the current codebase.

## Current Status

Implemented project areas:

- FastAPI backend with `/api/v1` REST routes and `/health`.
- Long-lived MeshCore manager using the official `meshcore` Python package.
- WiFi/TCP MeshCore transport via `MeshCore.create_tcp`.
- PostgreSQL models and Alembic migrations.
- Gateway telemetry normalization and history storage.
- Node/contact state, telemetry, events, favorites, repeater/admin fields, and raw payload preservation.
- Message send/history APIs and chat-style frontend page.
- Device info/settings APIs with capability-style setting metadata.
- MQTT broker configuration/status/test endpoints.
- Automation rule and run APIs with service-layer tests.
- WebSocket event stream for frontend updates.
- SvelteKit dashboard pages for Dashboard, Messages, Nodes, Map, Device Settings, Automations, MQTT, and System.
- Docker Compose stack for backend, frontend, PostgreSQL, and Mosquitto.

Not currently implemented as active runtime features:

- Serial USB transport.
- BLE transport.
- Connection profile CRUD.
- First-run setup wizard.
- Authentication UI.

## Stack

Backend:

- Python 3.12+
- FastAPI
- Uvicorn
- SQLAlchemy 2.x async
- Alembic
- PostgreSQL
- Pydantic v2
- `meshcore`
- `aiomqtt`

Frontend:

- SvelteKit
- Svelte 5
- TypeScript
- Vite
- Node adapter

Infrastructure:

- Docker Compose
- PostgreSQL 16
- Eclipse Mosquitto 2

## Repository Layout

```text
.
├── AGENTS.md
├── README.md
├── docker-compose.yml
├── .env.example
├── backend/
│   ├── app/
│   │   ├── api/v1/          REST and WebSocket routes
│   │   ├── core/            config, logging, event bus, security
│   │   ├── db/              SQLAlchemy models and session setup
│   │   ├── meshcore/        manager, transport abstraction, TCP transport
│   │   ├── services/        telemetry, nodes, messages, automations, MQTT
│   │   └── tests/
│   ├── alembic/
│   ├── pyproject.toml
│   └── Dockerfile
├── frontend/
│   ├── src/lib/
│   ├── src/routes/
│   ├── package.json
│   └── Dockerfile
└── infra/
    └── mosquitto/
```

## Quick Start

Create an environment file:

```sh
cp .env.example .env
```

For the current TCP runtime, set the MeshCore companion address in `.env` or directly through Compose:

```env
MESHCORE_CONNECTION_TYPE=tcp
MESHCORE_TCP_HOST=127.0.0.1
MESHCORE_TCP_PORT=5000
```

Start the stack:

```sh
docker compose up -d --build
```

Run database migrations:

```sh
docker compose exec backend alembic upgrade head
```

Open PacketDeck:

```text
http://localhost:8080
```

Default service URLs:

- Frontend: `http://localhost:8080`
- Backend API: `http://localhost:8000/api/v1`
- Backend health check: `http://localhost:8000/health`
- PostgreSQL: `localhost:5432`
- MQTT broker: `localhost:1883`

## Configuration

The backend reads settings from environment variables. Important current variables:

```env
DATABASE_URL=postgresql+asyncpg://meshcore:meshcore@postgres:5432/meshcore
MQTT_URL=mqtt://mqtt:1883
MQTT_TOPIC_PREFIX=meshcore-webgui
MESHCORE_CONNECTION_TYPE=tcp
MESHCORE_TCP_HOST=127.0.0.1
MESHCORE_TCP_PORT=5000
MESHCORE_AUTO_RECONNECT=true
MESHCORE_MESSAGE_MAX_CHARS=180
CORS_ORIGINS=http://localhost:8080,http://localhost:5173
AUTH_ENABLED=false
API_TOKEN=
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4.1-mini
```

Notes:

- `MESHCORE_CONNECTION_TYPE` must currently be `tcp`.
- `MESHCORE_TCP_HOST` and `MESHCORE_TCP_PORT` must point to a reachable MeshCore WiFi/TCP companion.
- Keep `.env` and secrets out of Git.
- If the frontend is opened through a LAN hostname or Raspberry Pi address, add that origin to `CORS_ORIGINS`.
- `OPENAI_API_KEY` is optional and only needed for automation features that call the OpenAI-backed weather/service path.

## Docker Compose

The default Compose stack builds:

- `backend` on port `8000`.
- `frontend` on port `8080`.
- `postgres` on port `5432`.
- `mqtt` on port `1883`.

The checked-in `docker-compose.yml` currently defaults to:

```yaml
MESHCORE_CONNECTION_TYPE: tcp
MESHCORE_TCP_HOST: ${MESHCORE_TCP_HOST:-127.0.0.1}
MESHCORE_TCP_PORT: ${MESHCORE_TCP_PORT:-5000}
```

Override the companion host without editing the file:

```sh
MESHCORE_TCP_HOST=meshcore-companion.local MESHCORE_TCP_PORT=5000 docker compose up -d --build
```

## API

All application API endpoints are under:

```text
/api/v1
```

Current route groups:

- `/connection`
- `/device`
- `/telemetry`
- `/nodes`
- `/messages`
- `/automations`
- `/mqtt`
- `/system`

WebSocket event stream:

```text
ws://localhost:8000/api/v1/ws/events
```

Health check:

```text
GET /health
```

Useful connection calls:

```sh
curl http://localhost:8000/api/v1/connection/status
curl -X POST http://localhost:8000/api/v1/connection/connect
curl -X POST http://localhost:8000/api/v1/connection/disconnect
```

## Frontend

The UI is English-only and currently includes:

- Dashboard
- Messages
- Nodes
- Map
- Device Settings
- Automations
- MQTT
- System

The root route redirects to `/dashboard`.

For local frontend development:

```sh
cd frontend
npm install
npm run dev
```

Frontend checks:

```sh
cd frontend
npm run check
```

Production build:

```sh
cd frontend
npm run build
```

## Backend Development

Create a local environment:

```sh
cd backend
python -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
```

Run migrations:

```sh
alembic upgrade head
```

Run the backend:

```sh
uvicorn app.main:app --reload
```

Run tests:

```sh
pytest
```

## Database Migrations

PacketDeck uses Alembic migrations:

```sh
docker compose exec backend alembic upgrade head
```

For local backend development:

```sh
cd backend
alembic upgrade head
```

PostgreSQL is the runtime database. SQLite is not accepted by the production settings validator and should only be used for isolated tests or fixtures.

## MQTT

MQTT is an integration surface for systems such as Home Assistant, Node-RED, scripts, and automation workflows. The frontend uses REST and WebSocket as its primary transports.

Current MQTT-related features include:

- Broker configuration API and UI.
- Broker status API.
- Test publish endpoint.
- Automation service support for MQTT publish actions.

Broker passwords and tokens must be treated as secrets and must not be logged or committed.

## Serial USB and BLE Roadmap

The project contract still targets serial USB and BLE support, but the current code only builds a TCP transport. The existing `.env.example` contains older serial/BLE variables; treat those as future-facing placeholders until serial and BLE transports are added back to the runtime.

Planned transport work:

- Serial transport implementation and serial scan endpoint.
- BLE transport implementation and BLE scan endpoint.
- Docker deployment notes for stable `/dev/serial/by-id/...` mappings.
- Linux BLE container profile with DBus/BlueZ documentation.
- Connection profile management if reusable profiles are reintroduced.

## Troubleshooting

### Backend is reachable, but the device stays disconnected

Check the configured TCP companion:

```sh
curl http://localhost:8000/api/v1/connection/status
```

Verify:

- `MESHCORE_CONNECTION_TYPE=tcp`.
- `MESHCORE_TCP_HOST` is reachable from the backend container.
- `MESHCORE_TCP_PORT` matches the MeshCore companion TCP port.
- The MeshCore companion is powered on and connected to the same network.

### Dashboard stays on loading

Check whether the browser can reach the backend:

```sh
curl http://localhost:8000/api/v1/connection/status
curl http://localhost:8000/api/v1/telemetry/gateway/latest
```

If these fail, verify:

- Backend container is running.
- Port `8000` is reachable from the browser.
- `PUBLIC_API_BASE_URL` points to a browser-reachable backend address.
- `CORS_ORIGINS` includes the frontend origin.

### Database errors after a fresh start

Run migrations:

```sh
docker compose exec backend alembic upgrade head
```

### Frontend cannot connect to the WebSocket

Check that `PUBLIC_WS_URL` points to the backend address the browser can reach:

```env
PUBLIC_WS_URL=ws://localhost:8000/api/v1/ws/events
```

For LAN deployments, use the LAN hostname or IP address instead of `localhost`.

## Security Notes

PacketDeck is designed for local self-hosting. Do not expose it publicly without authentication and HTTPS.

Recommended baseline:

- Keep `.env` private.
- Rotate secrets if they were pasted into chat or logs.
- Use API tokens when enabling remote integrations.
- Restrict CORS to known frontend origins.
- Do not log MQTT passwords, BLE PINs, API tokens, OpenAI keys, or webhook secrets.

## License

PacketDeck is released under the MIT License. See [LICENSE](./LICENSE).
