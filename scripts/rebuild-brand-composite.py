#!/usr/bin/env python3
"""Rebuild the First West collection image: no white frame, Figma blur + overlay + vignette."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

MEDIA = Path(__file__).resolve().parent / "seed-media"
OUT = MEDIA / "brand-composite.png"

# Figma 406:1946 is 619.59 x 345.37. Export @2x.
WIDTH, HEIGHT = 1240, 690
# Figma layer blur is 3.443px at 1x.
BLUR = 6.886
OVERLAY_ALPHA = 0.3


def figma_bg_crop(im: Image.Image, size: tuple[int, int]) -> Image.Image:
    """Match Figma 406:1948: 155.54% wide, 155.74% tall, left -27.72%, top -45.85%."""
    tw, th = size
    scaled = im.resize((round(tw * 1.5554), round(th * 1.5574)), Image.Resampling.LANCZOS)
    left = round(tw * 0.2772)
    top = round(th * 0.4585)
    return scaled.crop((left, top, left + tw, top + th))


def logo_on_transparent(path: Path) -> Image.Image:
    """Treat the logo's light pixels as alpha so it sits on the dark crop."""
    logo = Image.open(path).convert("RGBA")
    arr = np.asarray(logo).copy()
    luminance = arr[:, :, :3].max(axis=2)
    arr[:, :, 3] = luminance
    return Image.fromarray(arr, "RGBA")


def edge_feather(rgb: Image.Image, px: int = 20) -> Image.Image:
    """~10px fade at 1x (asset is @2x), matching Figma's 8–12px edge blend."""
    arr = np.asarray(rgb).astype(np.float32)
    ramp = np.linspace(0.0, 1.0, px, dtype=np.float32)
    arr[:px] *= ramp[:, None, None]
    arr[-px:] *= ramp[::-1, None, None]
    arr[:, :px] *= ramp[None, :, None]
    arr[:, -px:] *= ramp[None, ::-1, None]
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB")


def main() -> None:
    """Compose brand-bg.png + brand-logo.png into brand-composite.png."""
    bg = figma_bg_crop(Image.open(MEDIA / "brand-bg.png").convert("RGB"), (WIDTH, HEIGHT))
    bg = bg.filter(ImageFilter.GaussianBlur(radius=BLUR))
    bg = Image.blend(bg, Image.new("RGB", bg.size, (0, 0, 0)), OVERLAY_ALPHA)
    bg = edge_feather(bg, px=20)

    logo = logo_on_transparent(MEDIA / "brand-logo.png")
    logo_w = round(WIDTH * (390.99755859375 / 619.5879516601562))
    logo_h = round(logo_w * (logo.height / logo.width))
    logo = logo.resize((logo_w, logo_h), Image.Resampling.LANCZOS)
    x = (WIDTH - logo_w) // 2
    y = (HEIGHT - logo_h) // 2
    canvas = bg.convert("RGBA")
    canvas.alpha_composite(logo, (x, y))
    canvas.convert("RGB").save(OUT, "PNG", optimize=True)
    print(f"Wrote {OUT} {WIDTH}x{HEIGHT}", flush=True)


if __name__ == "__main__":
    main()
