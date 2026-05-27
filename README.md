# PacketDeck

PacketDeck is a self-hosted web client for MeshCore companion devices. It provides a modern SvelteKit frontend and a Python FastAPI backend for managing MeshCore gateways over serial USB or Bluetooth LE, storing telemetry in PostgreSQL, and exposing integration surfaces for MQTT, automations, and HTTP APIs.

PacketDeck is an independent web client compatible with MeshCore. It is designed for local, self-hosted deployments such as Raspberry Pi gateways, home labs, and Home Assistant adjacent installations.

## Highlights

- MeshCore connection management over serial USB and BLE.
- First-run setup wizard for hardware discovery, connection testing, and profile creation.
- Connection profiles with default profile selection.
- Live connection state, diagnostics, and reconnect-safe status handling.
- Gateway telemetry storage with PostgreSQL and historical API endpoints.
- Dashboard with connection, radio, battery, node, message, and activity views.
- Node and contact tracking with raw MeshCore payload preservation.
- Message API and frontend message views.
- MQTT broker configuration and integration endpoints.
- Automation rule foundation for message, telemetry, node, MQTT, webhook, and schedule driven workflows.
- WebSocket event stream for real-time frontend updates.
- Docker Compose based local deployment.

## Stack

### Backend

- Python 3.12+
- FastAPI
- Uvicorn
- SQLAlchemy 2.x async
- Alembic
- PostgreSQL
- Pydantic v2
- `meshcore`
- `bleak`
- `aiomqtt`

### Frontend

- SvelteKit
- Svelte 5
- TypeScript
- Vite
- Node adapter

### Infrastructure

- Docker Compose
- PostgreSQL 16
- Optional local Mosquitto or external MQTT broker

## Repository Layout

```text
.
├── backend/              FastAPI backend, MeshCore manager, transports, API routes
├── frontend/             SvelteKit frontend
├── infra/mosquitto/      Local Mosquitto config
├── docker-compose.yml    Default local Docker Compose stack
├── .env.example          Environment template
├── LICENSE
└── README.md
```

## Quick Start

Clone the repository:

```sh
git clone https://github.com/spacepc-de/PacketDeck.git
cd PacketDeck
```

Create an environment file:

```sh
cp .env.example .env
```

Start the default stack:

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

On a fresh database without connection profiles, opening `/` routes to the Setup Wizard. After a default connection profile exists, `/` routes to the Dashboard.

## First-Run Setup Wizard

The Setup Wizard is the recommended way to initialize a new PacketDeck installation.

It guides you through:

1. Selecting serial USB or BLE.
2. Scanning for available devices.
3. Testing the MeshCore connection.
4. Saving a reusable default connection profile.
5. Optionally connecting immediately after saving.

After initial setup, the wizard is available from the System page.

## Serial USB Setup

For real hardware on Linux, prefer stable `/dev/serial/by-id/...` paths instead of volatile `/dev/ttyACM0` or `/dev/ttyUSB0` names.

List available serial devices on the host:

```sh
ls -l /dev/serial/by-id/
```

Use the `linux-serial` Compose profile when you want Docker to map a specific host serial device into the backend container:

```sh
MESHCORE_HOST_SERIAL_PORT=/dev/serial/by-id/YOUR_DEVICE_ID \
docker compose --profile linux-serial up -d --build
```

The default `backend` service is intended for general development. The `backend-linux-serial` service maps the selected host serial device to `/dev/meshcore` inside the container and exposes the backend on port `8001`.

For Raspberry Pi or host-network deployments, a small deployment-specific Compose file is often more practical because serial devices, DBus, and network access are host-specific.

## BLE Notes

BLE in containers is host dependent. Linux hosts usually need BlueZ, DBus access, host networking, and additional capabilities. The included `ble-linux` profile is a starting point, not a universal guarantee.

Start the BLE profile:

```sh
docker compose --profile ble-linux up -d --build
```

If BLE scanning fails in Docker, verify:

- Bluetooth is enabled on the host.
- BlueZ is running.
- DBus is available.
- The container can access `/var/run/dbus`.
- Host networking and required capabilities are available.

Serial USB is usually the more predictable deployment mode for a fixed gateway.

## Configuration

Copy `.env.example` to `.env` and adjust values for your environment.

Important variables:

```env
DATABASE_URL=postgresql+asyncpg://meshcore:meshcore@postgres:5432/meshcore
MESHCORE_CONNECTION_TYPE=serial
MESHCORE_HOST_SERIAL_PORT=/dev/serial/by-id/REPLACE_WITH_DEVICE
MESHCORE_SERIAL_PORT=/dev/meshcore
MESHCORE_SERIAL_BAUD=115200
MESHCORE_BLE_ADDRESS=
MESHCORE_BLE_PIN=
MESHCORE_AUTO_RECONNECT=true
CORS_ORIGINS=http://localhost:8080,http://localhost:5173
AUTH_ENABLED=false
API_TOKEN=
OPENAI_API_KEY=
```

Notes:

- Keep secrets out of Git.
- Do not commit `.env`.
- If you use a Raspberry Pi or LAN hostname, add the frontend origin to `CORS_ORIGINS`.
- `OPENAI_API_KEY` is optional and should only be set when features need it.

## MQTT

PacketDeck supports MQTT as an integration surface for systems such as Home Assistant, Node-RED, scripts, and automation engines.

MQTT is not the primary frontend transport. The frontend uses REST and WebSocket. MQTT is intended for external integrations and command topics.

Typical use cases:

- Publish gateway status and telemetry.
- Publish node and message events.
- Subscribe to command topics for external control.
- Use MQTT actions from automations.

Configure brokers from the MQTT page in the frontend. Passwords and tokens should be treated as secrets and must not be logged or committed.

## API

All application API endpoints are under:

```text
/api/v1
```

Core endpoint groups:

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

## Development

Install and run frontend locally:

```sh
cd frontend
npm install
npm run dev
```

Run the frontend production build:

```sh
cd frontend
npm run build
```

Run backend locally:

```sh
cd backend
python -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
alembic upgrade head
uvicorn app.main:app --reload
```

Run backend tests:

```sh
cd backend
pytest
```

Run frontend checks:

```sh
cd frontend
npm run check
```

## Database Migrations

PacketDeck uses Alembic migrations. After creating a fresh database, run:

```sh
docker compose exec backend alembic upgrade head
```

For local backend development:

```sh
cd backend
alembic upgrade head
```

PostgreSQL is the production database. SQLite is not intended as the primary production database.

## Raspberry Pi Deployment Notes

A Raspberry Pi deployment usually needs host-specific Compose settings:

- LAN frontend URL, for example `http://192.168.2.49:8090`.
- Backend API URL visible to the browser, for example `http://192.168.2.49:8000/api/v1`.
- Serial access via `/dev/serial/by-id/...`.
- Optional `/dev` and DBus mounts for scanning and BLE access.
- `CORS_ORIGINS` including the Pi frontend URL.

Example values:

```env
CORS_ORIGINS=http://192.168.2.49:8090,http://localhost:8090,http://localhost:5173
PUBLIC_API_BASE_URL=http://192.168.2.49:8000/api/v1
PUBLIC_WS_URL=ws://192.168.2.49:8000/api/v1/ws/events
```

For first-run testing, disabling auto reconnect can be useful:

```env
MESHCORE_AUTO_RECONNECT=false
```

That lets the Setup Wizard be the first connection flow instead of having the backend attempt a connection before a profile exists.

## Troubleshooting

### The dashboard stays on loading

Check whether the browser can reach the backend:

```sh
curl http://YOUR_HOST:8000/api/v1/connection/status
curl http://YOUR_HOST:8000/api/v1/telemetry/gateway/latest
```

If these fail from your workstation, verify:

- Backend container is running.
- Port `8000` is reachable from your browser.
- `PUBLIC_API_BASE_URL` points to the backend address your browser can access.
- `CORS_ORIGINS` includes your frontend origin.

### Serial device is not found

Check host devices:

```sh
ls -l /dev/serial/by-id/
ls -l /dev/ttyACM* /dev/ttyUSB*
```

Then verify the backend can see them:

```sh
curl http://YOUR_HOST:8000/api/v1/connection/scan/serial
```

Use stable `/dev/serial/by-id/...` paths for profiles whenever possible.

### Connection test hangs or fails

Make sure the selected serial device is the MeshCore companion and not another adapter such as a Zigbee dongle. Also check that no other process is using the serial port.

### BLE scan fails

BLE support in containers depends heavily on host Bluetooth setup. Prefer serial for fixed gateways unless BLE is required.

### Database errors after a fresh start

Run migrations:

```sh
docker compose exec backend alembic upgrade head
```

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
