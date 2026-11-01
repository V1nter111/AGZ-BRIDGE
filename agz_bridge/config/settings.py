"""Global settings for AGZ Bridge Host."""
import os
import secrets
import shutil
import socket
from functools import lru_cache
from pathlib import Path
from typing import List, Optional
from pydantic import BaseModel, Field


def detect_host_ip() -> str:
    """Detect the most likely real LAN IP address of this machine."""
    try:
        import psutil
        # Priority: real physical LAN interface (192.168.x.x or 10.x.x.x)
        lan_candidates = []
        for iface_name, addrs in psutil.net_if_addrs().items():
            # Skip loopback and known VPN / virtual names if possible
            lower_name = iface_name.lower()
            if any(k in lower_name for k in ["loopback", "bluetooth", "tun", "tap", "vethernet"]):
                continue
            for addr in addrs:
                if addr.family == socket.AF_INET and not addr.address.startswith("127."):
                    if addr.address.startswith("192.168."):
                        return addr.address
                    if addr.address.startswith("10.") and "vpn" not in lower_name:
                        lan_candidates.append(addr.address)
                    elif addr.address.startswith("172."):
                        lan_candidates.append(addr.address)

        if lan_candidates:
            return lan_candidates[0]
    except Exception:
        pass

    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        pass

    try:
        hostname = socket.gethostname()
        return socket.gethostbyname(hostname)
    except Exception:
        return "127.0.0.1"


def detect_tailscale_ip() -> Optional[str]:
    """Detect Tailscale IP if Tailscale interface exists."""
    try:
        import psutil
        for iface, addrs in psutil.net_if_addrs().items():
            if "tailscale" in iface.lower():
                for addr in addrs:
                    if addr.family == socket.AF_INET and addr.address.startswith("100."):
                        return addr.address
    except Exception:
        pass
    return None


def get_default_data_dir() -> Path:
    """Return persistent configuration and state directory for AGZ Bridge."""
    path = Path.home() / ".agz_bridge"
    path.mkdir(parents=True, exist_ok=True)
    (path / "data").mkdir(exist_ok=True)
    return path


def get_or_create_secret_key() -> str:
    """Retrieve or generate persistent master secret key for token signing."""
    secret_file = get_default_data_dir() / "secret.key"
    if secret_file.exists():
        key = secret_file.read_text(encoding="utf-8").strip()
        if key:
            return key
    key = secrets.token_hex(32)
    secret_file.write_text(key, encoding="utf-8")
    return key


class Settings(BaseModel):
    # Network and Service
    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8765)
    lan_ip: str = Field(default_factory=detect_host_ip)
    tailscale_ip: Optional[str] = Field(default_factory=detect_tailscale_ip)

    # CLI Discovery
    agy_path: str = Field(default_factory=lambda: shutil.which("agy") or str(Path.home() / "AppData" / "Local" / "agy" / "bin" / "agy.exe"))
    cli_timeout_seconds: int = Field(default=180)

    # Models
    default_model: str = Field(default="gemini-3.8-flash-high")
    available_models: List[str] = Field(
        default=[
            "gemini-3.8-flash-high",
            "gemini-3.8-flash-medium",
            "gemini-3.8-flash-low",
            "claude-sonnet-4-6",
            "claude-opus-4-6-thinking",
            "gpt-oss-120b-medium",
        ]
    )

    # Security & Pairing
    pairing_code_lifetime_seconds: int = Field(default=900)  # 15 minutes
    secret_key: str = Field(default_factory=get_or_create_secret_key)
    data_dir: Path = Field(default_factory=get_default_data_dir)

    # Allowed network ranges (RFC 1918 + Tailscale + Loopback)
    allowed_cidrs: List[str] = Field(
        default=[
            "127.0.0.0/8",
            "10.0.0.0/8",
            "172.16.0.0/12",
            "192.168.0.0/16",
            "100.64.0.0/10",  # Tailscale CGNAT
            "198.18.0.0/15",  # Local bench / benchmark
            "::1/128",
        ]
    )

    # Logging
    log_level: str = Field(default="INFO")

    @property
    def primary_url(self) -> str:
        """Returns the primary accessible URL for worker connection."""
        if self.tailscale_ip:
            return f"http://{self.tailscale_ip}:{self.port}"
        return f"http://{self.lan_ip}:{self.port}"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
