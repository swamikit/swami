#!/usr/bin/env python3
"""Wrap a raw pattern screenshot in a clean iPhone-style device frame.

The pixel gate (verify.yml) renders each pattern as a full-bleed simulator
screenshot — a bare rectangle, status bar and all. That reads as a raw capture,
not a product. Apple's own sample galleries (Fruta, Landmarks) show each screen
inside a device, which is what makes the DocC gallery grid look like a shelf of
apps rather than a contact sheet. This script does that compositing step: it
takes the raw screenshot and returns a PNG of the same screen seated in a
rounded device body with a soft drop shadow, on a transparent background so it
drops cleanly onto a DocC ``@PageImage(purpose: card)``.

It is deliberately asset-free — the frame is drawn, not a licensed device PNG —
so it has no bundled-image licensing question and adapts to whatever pixel
dimensions the sim picker chose for a given pattern (the frame geometry is all
proportional to the screenshot's own width).

Design notes:
  * The simulator screenshot already contains the Dynamic Island / notch as
    black pixels at the top of the display raster, so we do NOT draw our own —
    that would double it. We only round the four display corners (the raster is
    square-cornered even though the glass is not) and seat it in the body.
  * Everything is proportional to the screenshot width so a 1179-wide render and
    a 1290-wide render come out looking identical.

Usage:
    frame_render.py INPUT.png OUTPUT.png [--max-width N] [--body-color #RRGGBB]

Exit status is non-zero on any failure so a CI step can gate on it.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFilter, ImageStat
except ImportError:  # pragma: no cover - environment guard
    sys.stderr.write(
        "frame_render: Pillow is required (pip install Pillow)\n"
    )
    raise SystemExit(2)


# Geometry, all as a fraction of the screenshot's own width so the result is
# resolution-independent. Tuned to read like a current-generation iPhone.
SCREEN_CORNER_FRAC = 0.056     # display corner radius / screen width
BEZEL_FRAC = 0.026             # black border thickness around the display
RIM_FRAC = 0.004               # thin lighter rim just inside the body edge
MARGIN_FRAC = 0.10             # transparent breathing room around the body
SHADOW_BLUR_FRAC = 0.045       # drop-shadow gaussian blur radius
SHADOW_OFFSET_FRAC = 0.018     # how far the shadow drops below the body
SHADOW_ALPHA = 110             # 0..255 opacity of the drop shadow

BODY_COLOR = (26, 26, 28, 255)     # iOS "system gray 6" dark — near-black body
RIM_COLOR = (68, 68, 72, 255)      # a hair lighter, reads as the titanium edge

# A capture that is a single solid color (all-channel stddev at or below this)
# is almost certainly a blank/wrong-view screenshot, not a rendered pattern —
# even a flat-background pattern has a shape that lifts the spread well above it.
# Used only when --reject-uniform is passed, so a bad card is skipped instead of
# published.
UNIFORM_STDDEV_FLOOR = 2.0


def is_near_uniform(image: Image.Image, floor: float = UNIFORM_STDDEV_FLOOR) -> bool:
    """True when every color channel varies less than ``floor`` (a blank capture)."""
    stats = ImageStat.Stat(image.convert("RGB"))
    return max(stats.stddev) <= floor


def _rounded_mask(size: tuple[int, int], radius: int) -> Image.Image:
    """An L-mode mask: opaque inside a rounded rectangle, transparent outside."""
    w, h = size
    radius = max(0, min(radius, w // 2, h // 2))
    mask = Image.new("L", size, 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle((0, 0, w - 1, h - 1), radius=radius, fill=255)
    return mask


def frame_screenshot(
    screenshot: Image.Image,
    *,
    body_color: tuple[int, int, int, int] = BODY_COLOR,
    max_width: int | None = 900,
) -> Image.Image:
    """Return ``screenshot`` seated in a drawn device body, RGBA, transparent bg."""
    shot = screenshot.convert("RGBA")
    sw, sh = shot.size
    if sw == 0 or sh == 0:
        raise ValueError("screenshot has zero dimension")

    screen_r = round(sw * SCREEN_CORNER_FRAC)
    bezel = round(sw * BEZEL_FRAC)
    rim = max(1, round(sw * RIM_FRAC))
    margin = round(sw * MARGIN_FRAC)
    shadow_blur = max(1, round(sw * SHADOW_BLUR_FRAC))
    shadow_dy = round(sw * SHADOW_OFFSET_FRAC)

    # Round the display corners so the seated screen matches the glass, not the
    # square raster.
    shot.putalpha(_rounded_mask((sw, sh), screen_r))

    # Device body: screen + a bezel on every side, corners concentric with the
    # display (body radius = screen radius + bezel).
    body_w = sw + bezel * 2
    body_h = sh + bezel * 2
    body_r = screen_r + bezel
    body = Image.new("RGBA", (body_w, body_h), (0, 0, 0, 0))
    body_mask = _rounded_mask((body_w, body_h), body_r)
    body_fill = Image.new("RGBA", (body_w, body_h), body_color)
    body.paste(body_fill, (0, 0), body_mask)

    # A thin lighter rim just inside the body outline — catches the eye as a
    # metal edge without a full gradient.
    rim_draw = ImageDraw.Draw(body)
    rim_draw.rounded_rectangle(
        (rim // 2, rim // 2, body_w - 1 - rim // 2, body_h - 1 - rim // 2),
        radius=body_r,
        outline=RIM_COLOR,
        width=rim,
    )

    # Seat the (already corner-rounded) screenshot inside the bezel.
    body.alpha_composite(shot, (bezel, bezel))

    # Final canvas: body + transparent margin, with room for the dropped shadow.
    canvas_w = body_w + margin * 2
    canvas_h = body_h + margin * 2 + shadow_dy
    canvas = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))

    # Drop shadow: the body silhouette, blurred, offset down, behind the body.
    shadow = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
    sil = Image.new("RGBA", (body_w, body_h), (0, 0, 0, SHADOW_ALPHA))
    shadow.paste(sil, (margin, margin + shadow_dy), body_mask)
    shadow = shadow.filter(ImageFilter.GaussianBlur(shadow_blur))
    canvas.alpha_composite(shadow)
    canvas.alpha_composite(body, (margin, margin))

    if max_width and canvas_w > max_width:
        scale = max_width / canvas_w
        canvas = canvas.resize(
            (max_width, round(canvas_h * scale)),
            resample=Image.LANCZOS,
        )

    return canvas


# DocC's detailedGrid card image slot is landscape (~1.58:1). A tall portrait
# device dropped into it gets object-fit:cover — filled and cropped top/bottom.
# Seating the device on a card-aspect canvas (transparent margins, so it sits on
# the card's own background and the device stands out) lets cover show the whole
# device. Output slightly WIDER than the slot so cover only ever crops the
# transparent side margin, never the device.
CARD_ASPECT = 1.6
CARD_HEIGHT_FRAC = 0.9   # device occupies this fraction of the card height
CARD_MAX_WIDTH = 1200


def fit_to_card(
    framed: Image.Image,
    *,
    aspect: float = CARD_ASPECT,
    height_frac: float = CARD_HEIGHT_FRAC,
    max_width: int | None = CARD_MAX_WIDTH,
) -> Image.Image:
    """Center the framed device on a transparent landscape card canvas."""
    fw, fh = framed.size
    canvas_h = max(1, round(fh / height_frac))
    canvas_w = max(fw, round(canvas_h * aspect))
    canvas = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
    canvas.alpha_composite(framed, ((canvas_w - fw) // 2, (canvas_h - fh) // 2))
    if max_width and canvas.width > max_width:
        scale = max_width / canvas.width
        canvas = canvas.resize(
            (max_width, round(canvas.height * scale)), resample=Image.LANCZOS
        )
    return canvas


def _parse_color(text: str) -> tuple[int, int, int, int]:
    t = text.strip().lstrip("#")
    if len(t) not in (6, 8):
        raise argparse.ArgumentTypeError(f"expected #RRGGBB or #RRGGBBAA, got {text!r}")
    try:
        vals = [int(t[i : i + 2], 16) for i in range(0, len(t), 2)]
    except ValueError:
        raise argparse.ArgumentTypeError(f"invalid hex color {text!r}")
    if len(vals) == 3:
        vals.append(255)
    return tuple(vals)  # type: ignore[return-value]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("input", type=Path, help="raw screenshot PNG")
    ap.add_argument("output", type=Path, help="framed PNG to write")
    ap.add_argument(
        "--max-width",
        type=int,
        default=900,
        help="downscale the framed card to at most this width (0 = keep native)",
    )
    ap.add_argument(
        "--body-color",
        type=_parse_color,
        default=BODY_COLOR,
        help="device body color as #RRGGBB or #RRGGBBAA (default near-black)",
    )
    ap.add_argument(
        "--reject-uniform",
        action="store_true",
        help="fail (non-zero) if the input is a single solid color, so a blank "
        "capture is skipped instead of framed and published",
    )
    ap.add_argument(
        "--card-fit",
        action="store_true",
        help="seat the framed device on a landscape card-aspect canvas (transparent "
        "margins) so it fits a DocC gallery card whole, without cover-cropping",
    )
    ap.add_argument(
        "--card-aspect",
        type=float,
        default=CARD_ASPECT,
        help="width:height ratio of the card canvas (default 1.6)",
    )
    args = ap.parse_args(argv)

    if not args.input.is_file():
        sys.stderr.write(f"frame_render: no such file: {args.input}\n")
        return 1
    try:
        with Image.open(args.input) as im:
            im.load()
            if args.reject_uniform and is_near_uniform(im):
                sys.stderr.write(
                    f"frame_render: {args.input} is near-uniform (likely a blank "
                    "capture) — refusing to frame it\n"
                )
                return 3
            framed = frame_screenshot(
                im,
                body_color=args.body_color,
                # When card-fitting, defer downscaling to the card canvas so the
                # device isn't scaled twice.
                max_width=None if args.card_fit else (args.max_width or None),
            )
            out_img = (
                fit_to_card(framed, aspect=args.card_aspect)
                if args.card_fit
                else framed
            )
    except Exception as exc:  # noqa: BLE001 - CLI boundary
        sys.stderr.write(f"frame_render: failed to frame {args.input}: {exc}\n")
        return 1

    args.output.parent.mkdir(parents=True, exist_ok=True)
    out_img.save(args.output, "PNG")
    print(f"framed {args.input} -> {args.output} ({out_img.width}x{out_img.height})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
