from dataclasses import dataclass, field
from pathlib import Path
import os
import sys


def bundle_root() -> Path:
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))


@dataclass
class Config:
    data_dir: Path = field(default_factory=lambda: Path(os.getenv("LENS_DATA_DIR", str(Path.home() / ".lens-atlas"))))
    allowed_roots: list[Path] = field(default_factory=lambda: [Path(p).resolve() for p in os.getenv("LENS_MEDIA_ROOTS", "").split(os.pathsep) if p])
    desktop: bool = False
    local_token: str = ""
    workers: int = field(default_factory=lambda: max(1,min(8,int(os.getenv('LENS_SCAN_WORKERS','2')))))
    timeout: float = field(default_factory=lambda: max(5,min(300,float(os.getenv('LENS_FILE_TIMEOUT','35')))))
    cache_bytes: int = 2 * 1024**3
    static_dir: Path = field(default_factory=lambda: bundle_root() / "frontend" / "dist")
    native_player: object = None
    native_player_status: object = None
    local_origin: str = ''

    def __post_init__(self):
        self.data_dir = self.data_dir.resolve()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        (self.data_dir / "cache").mkdir(exist_ok=True)

