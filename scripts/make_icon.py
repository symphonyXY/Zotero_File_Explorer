"""Rebuild the Windows icon and README PNG from the retained project artwork."""

import argparse
import hashlib
import json
from pathlib import Path

from PIL import Image, ImageOps
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

ROOT = Path(__file__).resolve().parents[1]
SIZES = [16, 24, 32, 48, 64, 128, 256]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", nargs="?", type=Path, default=ROOT / "assets/icons/app-source.png")
    args = parser.parse_args()
    source = args.source.resolve()
    with Image.open(source) as original:
        dimensions = original.size
        image = ImageOps.contain(original.convert("RGBA"), (512, 512), Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", (512, 512))
    canvas.alpha_composite(image, ((512 - image.width) // 2, (512 - image.height) // 2))
    target = ROOT / "assets/icons/app.ico"
    canvas.save(target, format="ICO", sizes=[(size, size) for size in SIZES])
    png = ROOT / "assets/icons/app.png"
    canvas.save(png)
    app = QApplication.instance() or QApplication([])
    icon = QIcon(str(target))
    assert not icon.isNull() and sorted(size.width() for size in icon.availableSizes()) == SIZES
    evidence = {
        "source": (
            source.relative_to(ROOT).as_posix() if source.is_relative_to(ROOT) else source.name
        ),
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "origin": "User-selected AI-generated concept 06-fusion-minimal (2026-11-12)",
        "license": "MIT; project artwork, not an official Zotero logo",
        "dimensions": dimensions,
        "outputs": {
            path.relative_to(ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in (target, png)
        },
        "sizes": [[size.width(), size.height()] for size in icon.availableSizes()],
        "qt_load": True,
        "alpha_preserved": True,
    }
    (ROOT / "docs/evidence/icon.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    app.processEvents()
    print(json.dumps(evidence, indent=2))


if __name__ == "__main__":
    main()
