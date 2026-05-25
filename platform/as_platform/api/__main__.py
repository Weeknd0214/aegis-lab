import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]  # HSAP repo root
_PLATFORM = _ROOT / "platform"
for p in (_ROOT, _PLATFORM):
    s = str(p)
    if s not in sys.path:
        sys.path.insert(0, s)

from as_platform.api.server import main

if __name__ == "__main__":
    main()
