import asyncio

from fastapi import APIRouter, Depends, Request

from app.core.security import require_api_token

router = APIRouter(dependencies=[Depends(require_api_token)])


@router.get("/status")
async def get_connection_status(request: Request):
    return await request.app.state.meshcore_manager.get_state()


@router.post("/connect")
async def connect(request: Request):
    manager = request.app.state.meshcore_manager
    try:
        return await asyncio.wait_for(manager.connect(), timeout=8)
    except asyncio.TimeoutError:
        await manager.disconnect(manual=False)
        manager.state.last_error = "MeshCore WiFi TCP connection timed out. Check host, port, and WiFi reachability."
        manager.state.state = "error"
        return manager.state


@router.post("/disconnect")
async def disconnect(request: Request):
    return await request.app.state.meshcore_manager.disconnect()
