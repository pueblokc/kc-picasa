"""12-month photo calendar as a Letter-size PDF."""

from __future__ import annotations

import calendar as _cal
import datetime as _dt
from pathlib import Path

from PIL import Image, ImageDraw

from ._common import (
    ACCENT,
    GROUND,
    TEXT,
    cover,
    draw_centered,
    face_boxes,
    face_focus,
    font,
    load_photo,
    rgb,
    text_size,
)

LETTER_IN = (8.5, 11.0)


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> _dt.date:
    """n-th weekday (Mon=0) of a month; n=-1 for the last one."""
    if n > 0:
        first = _dt.date(year, month, 1)
        shift = (weekday - first.weekday()) % 7
        return first + _dt.timedelta(days=shift + 7 * (n - 1))
    last = _dt.date(year, month, _cal.monthrange(year, month)[1])
    return last - _dt.timedelta(days=(last.weekday() - weekday) % 7)


def us_holidays(year: int) -> dict[_dt.date, str]:
    """US federal holidays (observed on their calendar date)."""
    return {
        _dt.date(year, 1, 1): "New Year's Day",
        _nth_weekday(year, 1, 0, 3): "MLK Day",
        _nth_weekday(year, 2, 0, 3): "Presidents' Day",
        _nth_weekday(year, 5, 0, -1): "Memorial Day",
        _dt.date(year, 6, 19): "Juneteenth",
        _dt.date(year, 7, 4): "Independence Day",
        _nth_weekday(year, 9, 0, 1): "Labor Day",
        _nth_weekday(year, 10, 0, 2): "Columbus Day",
        _dt.date(year, 11, 11): "Veterans Day",
        _nth_weekday(year, 11, 3, 4): "Thanksgiving",
        _dt.date(year, 12, 25): "Christmas",
    }


def _page(
    photo: Image.Image,
    focus,
    year: int,
    month: int,
    size: tuple[int, int],
    holidays: dict[_dt.date, str],
    week_start: int,
    ground,
    text,
    accent,
) -> Image.Image:
    W, H = size
    img = Image.new("RGB", size, ground)
    d = ImageDraw.Draw(img)
    m = round(W * 0.06)
    ph = round(H * 0.55)
    img.paste(cover(photo, W - 2 * m, ph, focus or (0.5, 0.5)), (m, m))
    d.rectangle((m, m + ph, W - m, m + ph + max(2, W // 250)), fill=accent)
    # month heading
    y = m + ph + round(H * 0.025)
    head = font("serif", round(H * 0.045))
    d.text((m, y), _cal.month_name[month], font=head, fill=text)
    yr = font("sans", round(H * 0.03))
    d.text((W - m, y + H * 0.012), str(year), font=yr, fill=accent, anchor="ra")
    # grid
    gy = y + round(H * 0.075)
    cw = (W - 2 * m) / 7
    names = [_cal.day_abbr[(week_start + i) % 7].upper() for i in range(7)]
    nf = font("sans", round(H * 0.017))
    for i, name in enumerate(names):
        d.text((m + cw * i + cw / 2, gy), name, font=nf, fill=accent, anchor="ma")
    weeks = _cal.Calendar(firstweekday=week_start).monthdatescalendar(year, month)
    rh = (H - m - (gy + round(H * 0.03))) / 6
    top = gy + round(H * 0.03)
    df = font("sans", round(H * 0.024))
    hf = font("sans", round(H * 0.011))
    names_used: list[str] = []
    for r, week in enumerate(weeks):
        for c, day in enumerate(week):
            x0, y0 = m + cw * c, top + rh * r
            d.rectangle((x0, y0, x0 + cw, y0 + rh), outline=(*[max(0, v - 0) for v in ground],))
            d.line((x0, y0, x0 + cw, y0), fill=tuple(min(255, v + 28) for v in ground), width=1)
            if day.month != month:
                continue
            is_hol = day in holidays
            fill = accent if is_hol else text
            d.text((x0 + cw * 0.12, y0 + rh * 0.1), str(day.day), font=df, fill=fill)
            if is_hol:
                label = holidays[day]
                while text_size(d, label, hf)[0] > cw * 0.9 and len(label) > 4:
                    label = label[:-2]
                d.text((x0 + cw * 0.08, y0 + rh * 0.62), label, font=hf, fill=accent)
                names_used.append(label)
    return img


def make_calendar(
    photos: list[Path],
    out: Path,
    *,
    year: int | None = None,
    start_month: int = 1,
    holidays: bool = True,
    week_start: int = 6,
    dpi: int = 150,
    faces: bool = True,
    ground: str = GROUND,
    text: str = TEXT,
    accent: str = ACCENT,
) -> Path:
    """12 pages (one photo per month, month grid beneath) assembled into a
    Letter PDF. Photos are used in order and repeat if fewer than 12.
    `week_start`: 0=Monday ... 6=Sunday. Pages run from start_month of `year`."""
    out = Path(out)
    if not photos:
        raise ValueError("calendar needs at least one photo")
    if not 1 <= start_month <= 12:
        raise ValueError("start_month must be 1..12")
    year = year or _dt.date.today().year
    size = (round(LETTER_IN[0] * dpi), round(LETTER_IN[1] * dpi))
    g, t, a = rgb(ground), rgb(text), rgb(accent)
    pages: list[Image.Image] = []
    cache: dict[int, tuple[Image.Image, tuple[float, float] | None]] = {}
    hol: dict[_dt.date, str] = {}
    if holidays:
        for yy in (year, year + 1):
            hol.update(us_holidays(yy))
    for i in range(12):
        month0 = start_month - 1 + i
        yy, mm = year + month0 // 12, month0 % 12 + 1
        idx = i % len(photos)
        if idx not in cache:
            img = load_photo(photos[idx], max_side=max(size))
            cache[idx] = (img, face_focus(face_boxes(img)) if faces else None)
        img, focus = cache[idx]
        pages.append(_page(img, focus, yy, mm, size, hol, week_start, g, t, a))
    out.parent.mkdir(parents=True, exist_ok=True)
    pages[0].save(out, "PDF", save_all=True, append_images=pages[1:], resolution=float(dpi))
    return out
