import uuid
from datetime import datetime
import json
import ssl

import aiomqtt
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, SecretStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import require_api_token
from app.db.models import MqttBroker
from app.db.session import get_db_session

router = APIRouter(dependencies=[Depends(require_api_token)])


class MqttBrokerIn(BaseModel):
    name: str
    host: str
    port: int = Field(default=1883, ge=1, le=65535)
    username: str | None = None
    password: SecretStr | None = None
    tls_enabled: bool = False
    client_id: str | None = None
    topic_prefix: str = "meshcore-webgui"
    retain_settings: dict = Field(default_factory=dict)


class MqttBrokerOut(BaseModel):
    id: uuid.UUID
    name: str
    host: str
    port: int
    username: str | None
    has_password: bool
    tls_enabled: bool
    client_id: str | None
    topic_prefix: str
    retain_settings: dict
    created_at: datetime
    updated_at: datetime


class MqttTestIn(BaseModel):
    broker_id: uuid.UUID | None = None
    topic: str = "packetdeck/test"
    payload: dict | str = Field(default_factory=lambda: {"message": "PacketDeck test publish"})
    qos: int = Field(default=0, ge=0, le=2)
    retain: bool = False


def broker_out(broker: MqttBroker) -> MqttBrokerOut:
    return MqttBrokerOut(
        id=broker.id,
        name=broker.name,
        host=broker.host,
        port=broker.port,
        username=broker.username,
        has_password=bool(broker.password_secret_ref),
        tls_enabled=broker.tls_enabled,
        client_id=broker.client_id,
        topic_prefix=broker.topic_prefix,
        retain_settings=broker.retain_settings,
        created_at=broker.created_at,
        updated_at=broker.updated_at,
    )


@router.get("/status")
async def get_mqtt_status():
    return {"connected": False, "last_error": None}


@router.get("/brokers", response_model=list[MqttBrokerOut])
async def list_brokers(session: AsyncSession = Depends(get_db_session)):
    result = await session.execute(select(MqttBroker).order_by(MqttBroker.created_at.desc()))
    return [broker_out(broker) for broker in result.scalars().all()]


@router.post("/brokers", status_code=201, response_model=MqttBrokerOut)
async def create_broker(payload: MqttBrokerIn, session: AsyncSession = Depends(get_db_session)):
    broker = MqttBroker(
        **payload.model_dump(exclude={"password"}),
        password_secret_ref=payload.password.get_secret_value() if payload.password else None,
    )
    session.add(broker)
    await session.commit()
    await session.refresh(broker)
    return broker_out(broker)


@router.put("/brokers/{broker_id}", response_model=MqttBrokerOut)
async def update_broker(broker_id: uuid.UUID, payload: MqttBrokerIn, session: AsyncSession = Depends(get_db_session)):
    broker = await session.get(MqttBroker, broker_id)
    if not broker:
        raise HTTPException(status_code=404, detail="MQTT broker not found")
    for key, value in payload.model_dump(exclude={"password"}).items():
        setattr(broker, key, value)
    if payload.password:
        broker.password_secret_ref = payload.password.get_secret_value()
    await session.commit()
    await session.refresh(broker)
    return broker_out(broker)


@router.delete("/brokers/{broker_id}", status_code=204)
async def delete_broker(broker_id: uuid.UUID, session: AsyncSession = Depends(get_db_session)):
    broker = await session.get(MqttBroker, broker_id)
    if not broker:
        raise HTTPException(status_code=404, detail="MQTT broker not found")
    await session.delete(broker)
    await session.commit()


@router.post("/test")
async def test_mqtt_publish(payload: MqttTestIn, session: AsyncSession = Depends(get_db_session)):
    broker = None
    if payload.broker_id:
        broker = await session.get(MqttBroker, payload.broker_id)
        if not broker:
            raise HTTPException(status_code=404, detail="MQTT broker not found")
    else:
        result = await session.execute(select(MqttBroker).order_by(MqttBroker.created_at.desc()).limit(1))
        broker = result.scalar_one_or_none()
    if not broker:
        raise HTTPException(status_code=400, detail="No MQTT broker configured")
    message = payload.payload if isinstance(payload.payload, str) else json.dumps(payload.payload)
    try:
        async with aiomqtt.Client(
            hostname=broker.host,
            port=broker.port,
            username=broker.username,
            password=broker.password_secret_ref,
            identifier=broker.client_id,
            tls_context=ssl.create_default_context() if broker.tls_enabled else None,
            timeout=10,
        ) as client:
            await client.publish(payload.topic, payload=message, qos=payload.qos, retain=payload.retain)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"MQTT test publish failed: {exc}") from exc
    return {"status": "published", "broker_id": str(broker.id), "topic": payload.topic}
