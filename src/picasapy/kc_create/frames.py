"""Single-photo frames and cards: polaroid, film strip, shadow card, matte, postcard."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

from ._common import (
    ACCENT,
    GROUND,
    TEXT,
    contain,
    cover,
    draw_centered,
    fit_font,
    font,
    load_photo,
    paste_with_shadow,
    photo_date,
    rgb,
    rounded_mask,
    text_size,
    wrap_text,
)

STYLES = ("polaroid", "filmstrip", "card", "matte", "postcard")


def _polaroid(img, size, caption, ground, text, accent) -> Image.Image:
    side = size
    pad = round(side * 0.05)
    paper = (250, 248, 242) if sum(ground) > 500 else ground
    ink = (52, 56, 60) if sum(ground) > 500 else text
    ph = contain(img, side - 2 * pad, side - 2 * pad)
    pw, phh = ph.size
    frame_w = max(pw, round(side * 0.7)) + 2 * pad
    chin = round(side * 0.2)
    frame_h = pad + phh + chin
    canvas = Image.new("RGB", (frame_w + 2 * pad * 3, frame_h + 2 * pad * 3), ground)
    card = Image.new("RGB", (frame_w, frame_h), paper)
    card.paste(ph, ((frame_w - pw) // 2, pad))
    d = ImageDraw.Draw(card)
    if caption:
        fnt = fit_font(d, caption, "hand", frame_w - 2 * pad, round(chin * 0.5), 12)
        draw_centered(d, (frame_w / 2, pad + phh + chin / 2), caption, fnt, ink)
    paste_with_shadow(canvas, card, (pad * 3, pad * 3), radius=round(pad * 0.9), offset=(0, round(pad * 0.5)))
    return canvas


def _filmstrip(imgs, size, caption, ground, text, accent) -> Image.Image:
    cell = size // 2
    gap = round(cell * 0.06)
    margin = round(cell * 0.2)
    n = len(imgs)
    W = n * cell + (n + 1) * gap + 2 * margin // 2
    H = cell + 2 * margin
    strip = Image.new("RGB", (W, H), (18, 18, 18) if sum(ground) < 200 else (30, 30, 30))
    d = ImageDraw.Draw(strip)
    hole_w, hole_h = round(margin * 0.42), round(margin * 0.5)
    step = round(hole_w * 2.1)
    x = gap
    while x < W - hole_w:
        for y in (round(margin * 0.25), H - round(margin * 0.25) - hole_h):
            d.rounded_rectangle((x, y, x + hole_w, y + hole_h), radius=3, fill=ground)
        x += step
    x = gap + margin // 2
    for img in imgs:
        strip.paste(cover(img, cell, cell), (x, margin))
        d.rectangle((x - 1, margin - 1, x + cell, margin + cell), outline=accent)
        x += cell + gap
    pad = round(margin * 0.8)
    canvas = Image.new("RGB", (W + 2 * pad, H + 2 * pad + (round(size * 0.1) if caption else 0)), ground)
    paste_with_shadow(canvas, strip, (pad, pad), radius=round(pad * 0.5))
    if caption:
        cd = ImageDraw.Draw(canvas)
        fnt = fit_font(cd, caption, "sans", canvas.width - 2 * pad, round(size * 0.05), 12)
        draw_centered(cd, (canvas.width / 2, H + pad * 1.6), caption, fnt, text)
    return canvas


def _card(img, size, caption, ground, text, accent) -> Image.Image:
    ph = contain(img, size, size)
    radius = round(min(ph.size) * 0.05)
    ph = ph.convert("RGBA")
    ph.putalpha(rounded_mask(ph.size, radius))
    pad = round(size * 0.1)
    extra = round(size * 0.1) if caption else 0
    canvas = Image.new("RGB", (ph.width + 2 * pad, ph.height + 2 * pad + extra), ground)
    layer = Image.new("RGB", ph.size, (0, 0, 0))
    from ._common import shadow_layer

    r = round(pad * 0.5)
    sh = shadow_layer(ph.size, r, 170)
    canvas.paste(layer.resize(sh.size), (pad - r * 3, pad - r * 3 + r), sh)
    canvas.paste(ph.convert("RGB"), (pad, pad), ph.getchannel("A"))
    if caption:
        d = ImageDraw.Draw(canvas)
        fnt = fit_font(d, caption, "sans", canvas.width - 2 * pad, round(size * 0.04), 12)
        draw_centered(d, (canvas.width / 2, pad + ph.height + pad * 0.7), caption, fnt, text)
    return canvas


def _matte(img, size, caption, ground, text, accent, date_line) -> Image.Image:
    ph = contain(img, size, size)
    mat = round(size * 0.12)
    bottom = round(size * 0.2)
    canvas = Image.new("RGB", (ph.width + 2 * mat, ph.height + mat + bottom), ground)
    d = ImageDraw.Draw(canvas)
    d.rectangle((mat - 3, mat - 3, mat + ph.width + 2, mat + ph.height + 2), outline=accent, width=2)
    canvas.paste(ph, (mat, mat))
    y = mat + ph.height + bottom * 0.4
    if caption:
        fnt = fit_font(d, caption, "serif", canvas.width - 2 * mat, round(size * 0.05), 12)
        draw_centered(d, (canvas.width / 2, y), caption, fnt, text)
        y += size * 0.065
    if date_line:
        fnt = fit_font(d, date_line.upper(), "sans", canvas.width - 2 * mat, round(size * 0.028), 10)
        draw_centered(d, (canvas.width / 2, y), date_line.upper(), fnt, accent)
    return canvas


def _postcard(img, size, message, ground, text, accent, date_line) -> Image.Image:
    W = size * 3 // 2
    H = size
    pad = round(size * 0.04)
    paper = (250, 248, 242) if sum(ground) > 500 else ground
    ink = (52, 56, 60) if sum(ground) > 500 else text
    card = Image.new("RGB", (W, H), paper)
    d = ImageDraw.Draw(card)
    # photo side (left) / message side (right)
    pw = round(W * 0.52)
    card.paste(cover(img, pw - pad, H - 2 * pad), (pad, pad))
    mx = pw + pad * 2
    d.line((pw + pad, pad * 2, pw + pad, H - pad * 2), fill=(170, 164, 150), width=2)
    # stamp
    sw, sh = round(H * 0.17), round(H * 0.2)
    sx, sy = W - pad - sw, pad
    d.rectangle((sx, sy, sx + sw, sy + sh), outline=accent, width=3)
    d.rectangle((sx + 8, sy + 8, sx + sw - 8, sy + sh - 8), outline=accent, width=1)
    sf = font("sans", round(sh * 0.2))
    draw_centered(d, (sx + sw / 2, sy + sh / 2), "KC", sf, accent)
    # message
    fnt = font("hand", round(H * 0.065))
    lines = wrap_text(d, message or "", fnt, W - mx - pad * 2 - (0 if True else 0))
    y = sy + sh + pad
    lh = text_size(d, "Ag", fnt)[1] * 1.5
    for line in lines[: int((H - y - pad * 4) / lh)]:
        d.text((mx, y), line, font=fnt, fill=ink)
        y += lh
    # address lines
    for i in range(3):
        yy = H - pad * 3 - i * round(H * 0.07)
        d.line((mx, yy, W - pad, yy), fill=(170, 164, 150), width=2)
    if date_line:
        df = font("sans", round(H * 0.03))
        d.text((mx, H - pad * 1.4), date_line, font=df, fill=accent)
    canvas = Image.new("RGB", (W + 2 * pad * 2, H + 2 * pad * 2), ground)
    paste_with_shadow(canvas, card, (pad * 2, pad * 2), radius=round(pad * 0.8))
    return canvas


def make_frame(
    photos: list[Path],
    out: Path,
    *,
    style: str = "polaroid",
    caption: str | None = None,
    date: str | None = None,
    location: str | None = None,
    size: int = 1200,
    ground: str = "#1c2328",
    text: str = TEXT,
    accent: str = ACCENT,
    classic: bool = False,
) -> Path:
    """Wrap photo(s) in a frame. `style`: polaroid, filmstrip (3-5 photos),
    card, matte, postcard. `date` defaults to the photo's EXIF date for matte
    and postcard; `location` is appended to the date line."""
    out = Path(out)
    if style not in STYLES:
        raise ValueError(f"style must be one of {STYLES}")
    if not photos:
        raise ValueError("frames needs at least one photo")
    if classic:
        ground, text = "#f0eadd", "#34383c"
    g, t, a = rgb(ground), rgb(text), rgb(accent)
    maxside = size * 2
    if style == "filmstrip":
        if not 3 <= len(photos) <= 5:
            raise ValueError("filmstrip needs 3 to 5 photos")
        result = _filmstrip([load_photo(p, maxside) for p in photos], size, caption, g, t, a)
    else:
        img = load_photo(photos[0], maxside)
        if date is None and style in ("matte", "postcard"):
            date = photo_date(photos[0]).strftime("%B %d, %Y").replace(" 0", " ")
        date_line = " · ".join(x for x in (date, location) if x)
        if style == "polaroid":
            result = _polaroid(img, size, caption, g, t, a)
        elif style == "card":
            result = _card(img, size, caption, g, t, a)
        elif style == "matte":
            result = _matte(img, size, caption, g, t, a, date_line)
        else:
            result = _postcard(img, size, caption, g, t, a, date_line)
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.suffix.lower() in (".jpg", ".jpeg"):
        result.save(out, quality=92)
    else:
        result.save(out)
    return out
