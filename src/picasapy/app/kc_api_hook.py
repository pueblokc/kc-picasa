"""Optional local API entry point; the API module is supplied separately."""

from __future__ import annotations

from pathlib import Path


def start_kc_api(data_dir: Path, port: int = 8781) -> object | None:
    """Start the optional API when installed, otherwise leave startup unchanged."""
    try:
        from picasapy.app.kc_api import start_server
    except ModuleNotFoundError as exc:
        if exc.name == "picasapy.app.kc_api":
            return None
        raise
    return start_server(data_dir, port=port)
