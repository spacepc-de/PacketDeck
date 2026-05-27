from fastapi import APIRouter

from app.api.v1 import automations, connection, device, messages, mqtt, nodes, system, telemetry, websocket

api_router = APIRouter()
api_router.include_router(connection.router, prefix="/connection", tags=["connection"])
api_router.include_router(device.router, prefix="/device", tags=["device"])
api_router.include_router(telemetry.router, prefix="/telemetry", tags=["telemetry"])
api_router.include_router(nodes.router, prefix="/nodes", tags=["nodes"])
api_router.include_router(messages.router, prefix="/messages", tags=["messages"])
api_router.include_router(automations.router, prefix="/automations", tags=["automations"])
api_router.include_router(mqtt.router, prefix="/mqtt", tags=["mqtt"])
api_router.include_router(system.router, prefix="/system", tags=["system"])
api_router.include_router(websocket.router, tags=["websocket"])
