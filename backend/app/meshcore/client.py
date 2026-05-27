from app.core.config import Settings
from app.meshcore.transports import MeshCoreTransport
from app.meshcore.wifi_transport import WifiTcpMeshCoreTransport


def build_transport(settings: Settings) -> MeshCoreTransport:
    if settings.meshcore_connection_type != "tcp":
        raise RuntimeError("PacketDeck is configured for WiFi TCP MeshCore connections only")
    return WifiTcpMeshCoreTransport(settings.meshcore_tcp_host, settings.meshcore_tcp_port)
