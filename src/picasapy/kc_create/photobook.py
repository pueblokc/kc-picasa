"""Photo book / album PDF with auto layouts, captions, cover and page numbers."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

from ._common import (
    ACCENT,
    GROUND,
    TEXT,
    contain,
    cover,
    fit_font,
    font,
    load_photo,
    photo_date,
    rgb,
)

_AUTO_PATTERN = (1, 2, 3, 4)


def _cells(count: int, box: tuple[int, int, int, int], gap: int):
    """Cell rectangles (x0, y0, x1, y1) for a 1/2/3/4-up page inside `box`."""
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    if count == 1:
        return [box]
    if count == 2:
        ch = (h - gap) // 2
        return [(x0, y0, x1, y0 + ch), (x0, y0 + ch + gap, x1, y1)]
    if count == 3:
        top = round(h * 0.52)
        cw = (w - gap) // 2
        return [
            (x0, y0, x1, y0 + top),
            (x0, y0 + top + gap, x0 + cw, y1),
            (x0 + cw + gap, y0 + top + gap, x1, y1),
        ]
    cw, ch = (w - gap) // 2, (h - gap) // 2
    return [
        (x0, y0, x0 + cw, y0 + ch),
        (x0 + cw + gap, y0, x1, y0 + ch),
        (x0, y0 + ch + gap, x0 + cw, y1),
        (x0 + cw + gap, y0 + ch + gap, x1, y1),
    ]


def _plan(n: int, per_page: int | None) -> list[int]:
    """How many photos go on each page."""
    plan: list[int] = []
    left, i = n, 0
    while left > 0:
        want = per_page or _AUTO_PATTERN[i % len(_AUTO_PATTERN)]
        take = min(want, left)
        plan.append(take)
        left -= take
        i += 1
    return plan


def _cover_page(title, subtitle, hero, size, ground, text, accent) -> Image.Image:
    W, H = size
    img = Image.new("RGB", size, ground)
    d = ImageDraw.Draw(img)
    m = round(W * 0.09)
    if hero is not None:
        ph = round(H * 0.55)
        img.paste(cover(hero, W - 2 * m, ph), (m, m))
        y = m + ph + round(H * 0.05)
    else:
        y = round(H * 0.35)
    d.rectangle((m, y, m + W * 0.18, y + max(3, W // 200)), fill=accent)
    y += round(H * 0.025)
    fnt = fit_font(d, title, "serif", W - 2 * m, round(W * 0.1), 16)
    d.text((m, y), title, font=fnt, fill=text)
    if subtitle:
        sf = font("sans", round(W * 0.034))
        d.text((m, y + fnt.size * 1.5), subtitle, font=sf, fill=accent)
    return img


def make_photobook(
    photos: list[Path],
    out: Path,
    *,
    title: str = "Photo Album",
    subtitle: str | None = None,
    captions: list[str] | None = None,
    date_captions: bool = False,
    per_page: int | None = None,
    dpi: int = 150,
    cover_page: bool = True,
    page_numbers: bool = True,
    ground: str = GROUND,
    text: str = TEXT,
    accent: str = ACCENT,
) -> Path:
    """Letter-size portrait album PDF. `per_page` 1-4 fixes the layout; None
    cycles 1,2,3,4. Photos are never cropped (fit inside their cell) with the
    caption centred under each. `date_captions` uses EXIF dates when no
    caption is given."""
    out = Path(out)
    if not photos:
        raise ValueError("photobook needs at least one photo")
    if per_page is not None and per_page not in (1, 2, 3, 4):
        raise ValueError("per_page must be 1, 2, 3, 4 or None")
    g, t, a = rgb(ground), rgb(text), rgb(accent)
    size = (round(8.5 * dpi), round(11 * dpi))
    W, H = size
    m = round(W * 0.08)
    gap = round(W * 0.03)
    label_h = round(H * 0.035)
    pages: list[Image.Image] = []
    if cover_page:
        hero = load_photo(photos[0], max_side=max(size))
        if subtitle is None:
            dates = sorted(photo_date(p) for p in photos)
            first, last = dates[0], dates[-1]
            subtitle = (
                first.strftime("%B %Y")
                if first.strftime("%Y%m") == last.strftime("%Y%m")
                else f"{first.strftime('%B %Y')} – {last.strftime('%B %Y')}"
            )
        pages.append(_cover_page(title, subtitle, hero, size, g, t, a))
    idx = 0
    for count in _plan(len(photos), per_page):
        page = Image.new("RGB", size, g)
        d = ImageDraw.Draw(page)
        box = (m, m, W - m, H - m - round(H * 0.04))
        for rect in _cells(count, box, gap):
            path = photos[idx]
            cap = None
            if captions and idx < len(captions) and captions[idx]:
                cap = captions[idx]
            elif date_captions:
                cap = photo_date(path).strftime("%B %d, %Y").replace(" 0", " ")
            idx += 1
            cw, ch = rect[2] - rect[0], rect[3] - rect[1] - (label_h if cap or True else 0)
            img = contain(load_photo(path, max_side=max(cw, ch) * 2), cw, ch)
            px = rect[0] + (cw - img.width) // 2
            py = rect[1] + (ch - img.height) // 2
            page.paste(img, (px, py))
            d.rectangle((px - 1, py - 1, px + img.width, py + img.height), outline=a)
            if cap:
                cf = fit_font(d, cap, "sans", cw, round(label_h * 0.7), 9)
                d.text(((rect[0] + rect[2]) / 2, py + img.height + label_h * 0.5), cap,
                       font=cf, fill=t, anchor="mm")  # fmt: skip
        if page_numbers:
            nf = font("sans", round(H * 0.016))
            d.text((W / 2, H - m * 0.7), str(len(pages) + 1), font=nf, fill=a, anchor="mm")
        pages.append(page)
    out.parent.mkdir(parents=True, exist_ok=True)
    pages[0].save(out, "PDF", save_all=True, append_images=pages[1:], resolution=float(dpi))
    return out
