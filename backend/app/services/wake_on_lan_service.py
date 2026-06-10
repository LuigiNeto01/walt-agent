import re
import socket
import time

from app.core.config import get_settings
from app.schemas.tools import WakePcResponse


MAC_RE = re.compile(r"^[0-9A-Fa-f]{2}([-:]?)[0-9A-Fa-f]{2}(\1[0-9A-Fa-f]{2}){4}$")


def _normalize_mac(mac: str) -> str:
    compact = re.sub(r"[-:]", "", mac).upper()
    if not MAC_RE.match(mac) or len(compact) != 12:
        raise ValueError("MAC address invalido para Wake-on-LAN.")
    return compact


def _wait_for_ssh_port() -> tuple[bool | None, int]:
    settings = get_settings()
    if not settings.ssh_enabled or not settings.ssh_host or settings.wake_verify_ssh_timeout <= 0:
        return None, 0

    timeout = max(0, settings.wake_verify_ssh_timeout)
    interval = max(1, settings.wake_verify_ssh_interval)
    deadline = time.monotonic() + timeout
    started_at = time.monotonic()

    while True:
        try:
            with socket.create_connection((settings.ssh_host, settings.ssh_port), timeout=min(3, interval)):
                return True, int(time.monotonic() - started_at)
        except OSError:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False, timeout
            time.sleep(min(interval, remaining))


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
    bound_source_ip: str | None = None
    bind_warning: str | None = None

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        if settings.wake_source_ip:
            try:
                sock.bind((settings.wake_source_ip, 0))
                bound_source_ip = settings.wake_source_ip
            except OSError:
                bind_warning = (
                    f" Interface solicitada {settings.wake_source_ip} indisponivel neste runtime; "
                    "envio seguiu sem bind explicito."
                )
        sock.sendto(magic_packet, (settings.wake_broadcast_ip, settings.wake_port))

    source_detail = f" pela interface {bound_source_ip}" if bound_source_ip else ""
    ssh_ready, ssh_check_seconds = _wait_for_ssh_port()
    if ssh_ready is True:
        ssh_detail = f" SSH respondeu apos {ssh_check_seconds}s."
    elif ssh_ready is False:
        ssh_detail = (
            f" SSH ainda nao respondeu apos {ssh_check_seconds}s; "
            "tente verificar novamente antes de executar comandos."
        )
    else:
        ssh_detail = ""

    return WakePcResponse(
        ok=True,
        message=f"Magic packet Wake-on-LAN enviado para ligar o PC{source_detail}.{bind_warning or ''}{ssh_detail}",
        target_mac=settings.wake_target_mac,
        broadcast_ip=settings.wake_broadcast_ip,
        source_ip=bound_source_ip,
        port=settings.wake_port,
        ssh_ready=ssh_ready,
        ssh_check_seconds=ssh_check_seconds,
    )
