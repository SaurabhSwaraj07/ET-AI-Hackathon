"""
create_placeholder_png.py — generates a minimal valid PNG in backend/ml/
Run once: python create_placeholder_png.py
"""
import struct, zlib, os

def _minimal_png(width=1, height=1, color=(255, 255, 255)) -> bytes:
    def chunk(name: bytes, data: bytes) -> bytes:
        c = name + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)

    header = b"\x89PNG\r\n\x1a\n"
    ihdr   = chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
    raw    = b"\x00" + bytes(color) * width
    idat   = chunk(b"IDAT", zlib.compress(raw * height))
    iend   = chunk(b"IEND", b"")
    return header + ihdr + idat + iend

out = os.path.join(os.path.dirname(__file__), "shap_chart.png")
with open(out, "wb") as f:
    f.write(_minimal_png())
print(f"Placeholder PNG written to: {out}")