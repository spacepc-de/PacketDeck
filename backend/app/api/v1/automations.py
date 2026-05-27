import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import require_api_token
from app.db.models import AutomationRule, AutomationRun
from app.db.session import get_db_session
from app.services.automation_service import test_automation_rule

router = APIRouter(dependencies=[Depends(require_api_token)])


class AutomationRuleIn(BaseModel):
    name: str
    enabled: bool = True
    trigger_type: str
    trigger_config: dict = Field(default_factory=dict)
    conditions: list[dict] = Field(default_factory=list)
    actions: list[dict] = Field(default_factory=list)
    cooldown_seconds: int = Field(default=0, ge=0)


@router.get("")
async def list_automations(session: AsyncSession = Depends(get_db_session)):
    result = await session.execute(select(AutomationRule).order_by(AutomationRule.created_at.desc()))
    return result.scalars().all()


@router.post("", status_code=201)
async def create_automation(payload: AutomationRuleIn, session: AsyncSession = Depends(get_db_session)):
    rule = AutomationRule(**payload.model_dump())
    session.add(rule)
    await session.commit()
    await session.refresh(rule)
    return rule


@router.get("/{rule_id}")
async def get_automation(rule_id: uuid.UUID, session: AsyncSession = Depends(get_db_session)):
    rule = await session.get(AutomationRule, rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Automation rule not found")
    return rule


@router.put("/{rule_id}")
async def update_automation(rule_id: uuid.UUID, payload: AutomationRuleIn, session: AsyncSession = Depends(get_db_session)):
    rule = await session.get(AutomationRule, rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Automation rule not found")
    for key, value in payload.model_dump().items():
        setattr(rule, key, value)
    await session.commit()
    await session.refresh(rule)
    return rule


@router.delete("/{rule_id}", status_code=204)
async def delete_automation(rule_id: uuid.UUID, session: AsyncSession = Depends(get_db_session)):
    rule = await session.get(AutomationRule, rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Automation rule not found")
    await session.delete(rule)
    await session.commit()


@router.post("/{rule_id}/enable")
async def enable_automation(rule_id: uuid.UUID, session: AsyncSession = Depends(get_db_session)):
    return await _set_enabled(rule_id, True, session)


@router.post("/{rule_id}/disable")
async def disable_automation(rule_id: uuid.UUID, session: AsyncSession = Depends(get_db_session)):
    return await _set_enabled(rule_id, False, session)


@router.post("/{rule_id}/test")
async def test_automation(rule_id: uuid.UUID, request: Request, session: AsyncSession = Depends(get_db_session)):
    rule = await session.get(AutomationRule, rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Automation rule not found")
    manager = request.app.state.meshcore_manager
    return await test_automation_rule(session, manager.settings, rule, manager=manager)


@router.get("/{rule_id}/runs")
async def get_automation_runs(rule_id: uuid.UUID, session: AsyncSession = Depends(get_db_session)):
    result = await session.execute(select(AutomationRun).where(AutomationRun.rule_id == rule_id).order_by(AutomationRun.started_at.desc()))
    return result.scalars().all()


async def _set_enabled(rule_id: uuid.UUID, enabled: bool, session: AsyncSession):
    rule = await session.get(AutomationRule, rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Automation rule not found")
    rule.enabled = enabled
    await session.commit()
    await session.refresh(rule)
    return rule
