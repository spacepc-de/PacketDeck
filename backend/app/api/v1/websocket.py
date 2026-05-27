from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.event_bus import event_bus

router = APIRouter()


@router.websocket("/ws/events")
async def websocket_events(websocket: WebSocket):
    await websocket.accept()
    try:
        async for event in event_bus.subscribe():
            await websocket.send_json(
                {
                    "type": event.type,
                    "source": event.source,
                    "severity": event.severity,
                    "payload": event.payload,
                    "created_at": event.created_at.isoformat(),
                }
            )
    except WebSocketDisconnect:
        return
