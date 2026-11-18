#!/usr/bin/env python3
"""Fetch the public default font from a pinned official Noto commit."""
from pathlib import Path
import hashlib
import os
import tempfile
import urllib.request

FONT_NAME = "NotoSansCJKsc-Bold.otf"
FONT_URL = "https://raw.githubusercontent.com/notofonts/noto-cjk/f8d157532fbfaeda587e826d4cd5b21a49186f7c/Sans/OTF/SimplifiedChinese/NotoSansCJKsc-Bold.otf"
FONT_SIZE = 17002248
FONT_BLOB_SHA = "ff4c0450e8a5bf0290fbb6013a72dc61a10e8e56"

def verify_bytes(data):
    if len(data) != FONT_SIZE:
        raise ValueError("Default font size does not match the pinned source")
    header = b"blob " + str(len(data)).encode("ascii") + b"\0"
    if hashlib.sha1(header + data).hexdigest() != FONT_BLOB_SHA:
        raise ValueError("Default font checksum does not match the pinned source")

def ensure_font(cache_dir=None):
    root = Path(__file__).resolve().parents[1]
    bundled = root / "assets" / "fonts" / FONT_NAME
    cache = Path(cache_dir or os.environ.get("REFERENCE_VIDEO_FONT_CACHE", str(Path.home() / ".cache" / "remake-reference-video")))
    target = cache / FONT_NAME
    for path in (bundled, target):
        if path.is_file():
            verify_bytes(path.read_bytes())
            return path
    cache.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(FONT_URL, headers={"User-Agent": "remake-reference-video-font-setup"})
    with urllib.request.urlopen(request, timeout=60) as response:
        data = response.read(FONT_SIZE + 1)
    verify_bytes(data)
    fd, temporary = tempfile.mkstemp(prefix=".noto-", suffix=".otf", dir=cache)
    try:
        with os.fdopen(fd, "wb") as output:
            output.write(data)
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return target

if __name__ == "__main__":
    print(ensure_font())
