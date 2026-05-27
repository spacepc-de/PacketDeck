import asyncio
import time

from meshcore import MeshCore
from meshcore.events import EventType


async def main():
    client = await MeshCore.create_tcp("192.168.2.118", 5000, auto_reconnect=False)
    print("connected", flush=True)

    async def on_any(event):
        event_type = getattr(event.type, "value", str(event.type))
        payload = getattr(event, "payload", None)
        attrs = getattr(event, "attributes", None)
        print("event", event_type, "payload=", payload, "attrs=", attrs, flush=True)
        if event.type == EventType.MESSAGES_WAITING:
            for _ in range(5):
                msg = await client.commands.get_msg(timeout=8)
                msg_type = getattr(msg.type, "value", str(msg.type))
                print("get_msg", msg_type, "payload=", getattr(msg, "payload", None), "attrs=", getattr(msg, "attributes", None), flush=True)
                if msg.type in {EventType.NO_MORE_MSGS, EventType.ERROR}:
                    break

    sub = client.subscribe(None, on_any)
    print("listening 90s - send private and channel now", flush=True)
    start = time.monotonic()
    try:
        while time.monotonic() - start < 90:
            await asyncio.sleep(0.5)
    finally:
        sub.unsubscribe()
        await client.disconnect()
        print("done", flush=True)


asyncio.run(main())
