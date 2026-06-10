import re
import socket

from app.core.config import get_settings
from app.schemas.tools import WakePcResponse


MAC_RE = re.compile(r"^[0-9A-Fa-f]{2}([-:]?)[0-9A-Fa-f]{2}(\1[0-9A-Fa-f]{2}){4}$")


def _normalize_mac(mac: str) -> str:
    compact = re.sub(r"[-:]", "", mac).upper()
    if not MAC_RE.match(mac) or len(compact) != 12:
        raise ValueError("MAC address invalido para Wake-on-LAN.")
    return compact


def send_wake_on_lan_packet() -> WakePcResponse:
    settings = get_settings()
    if not settings.wake_on_lan_enabled:
        return WakePcResponse(
            ok=False,
            message="Wake-on-LAN esta desativado. Configure WAKE_ON_LAN_ENABLED=true.",
        )
    if not settings.wake_target_mac:
        return WakePcResponse(
            ok=False,
            message="MAC do PC nao configurado. Configure WAKE_TARGET_MAC no .env.",
        )

    compact_mac = _normalize_mac(settings.wake_target_mac)
    magic_packet = bytes.fromhex("FF" * 6 + compact_mac * 16)

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.sendto(magic_packet, (settings.wake_broadcast_ip, settings.wake_port))

    return WakePcResponse(
        ok=True,
        message="Magic packet Wake-on-LAN enviado para ligar o PC.",
        target_mac=settings.wake_target_mac,
        broadcast_ip=settings.wake_broadcast_ip,
        port=settings.wake_port,
    )
