from fastapi import APIRouter, Depends, HTTPException, Request

from app.core.security import require_api_token
from app.meshcore.models import DeviceSettingsPatch

router = APIRouter(dependencies=[Depends(require_api_token)])


@router.get("/info")
async def get_device_info(request: Request):
    return await request.app.state.meshcore_manager.get_device_info()


@router.get("/settings")
async def get_device_settings(request: Request, refresh: bool = False):
    try:
        return await request.app.state.meshcore_manager.get_settings(refresh=refresh)
    except (RuntimeError, TimeoutError):
        return []


@router.patch("/settings")
async def patch_device_settings(request: Request, payload: DeviceSettingsPatch):
    try:
        return await request.app.state.meshcore_manager.update_settings(payload.values)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/advert")
async def send_device_advert(request: Request):
    try:
        return await request.app.state.meshcore_manager.send_advert()
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/settings/history")
async def get_device_settings_history():
    return []
