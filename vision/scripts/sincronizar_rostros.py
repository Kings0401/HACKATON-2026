"""Compatibilidad con el script original: delega en nclub_vision.sync."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nclub_vision.sync import main  # noqa: E402

if __name__ == "__main__":
    main()
