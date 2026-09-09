#!/usr/bin/env python3
"""Preview-only: name watermark options on a real Storage photo. Does not upload."""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[1]
SRC = Path(r"C:\Users\ubhar\AppData\Local\Temp\sattva-img-check\rec_idli.jpg")
OUT = ROOT / "preview" / "watermark-previews" / "sattvasrsti-name-options.jpg"
LOGO = ROOT / "preview" / "assets" / "sattva-srsti-logo.png"
GEORGIA = Path(r"C:\Windows\Fonts\georgia.ttf")
GEORGIA_B = Path(r"C:\Windows\Fonts\georgiab.ttf")
SEGOE_B = Path(r"C:\Windows\Fonts\segoeuib.ttf")
GOLD = (201, 142, 36, 255)
WHITE = (255, 252, 246, 255)
INK = (20, 18, 16, 230)


def font(path: Path, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(path if path.exists() else GEORGIA), size)


def draw_text(base: Image.Image, text: str, xy: tuple[int, int], fnt, fill, stroke=3, stroke_fill=(20, 18, 16, 180)):
    layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.text(xy, text, font=fnt, fill=fill, stroke_width=stroke, stroke_fill=stroke_fill)
    shadow = layer.filter(ImageFilter.GaussianBlur(4))
    out = Image.alpha_composite(base.convert("RGBA"), shadow)
    return Image.alpha_composite(out, layer)


def word_size(text: str, fnt) -> tuple[int, int]:
    d = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    box = d.textbbox((0, 0), text, font=fnt)
    return box[2] - box[0], box[3] - box[1]


def circular_logo(size: int) -> Image.Image:
    im = Image.open(LOGO).convert("RGBA")
    im = im.resize((size, size), Image.Resampling.LANCZOS)
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse((1, 1, size - 2, size - 2), fill=255)
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.paste(im, (0, 0))
    out.putalpha(mask)
    return out


def option_a(photo: Image.Image) -> Image.Image:
    w, h = photo.size
    fnt = font(GEORGIA, max(28, int(w * 0.048)))
    tw, th = word_size("sattvasrsti", fnt)
    x, y = int(w * 0.045), h - th - int(h * 0.055)
    return draw_text(photo, "sattvasrsti", (x, y), fnt, WHITE)


def option_b(photo: Image.Image) -> Image.Image:
    w, h = photo.size
    fnt = font(GEORGIA_B if GEORGIA_B.exists() else GEORGIA, max(28, int(w * 0.046)))
    tw, th = word_size("SattvaSrsti", fnt)
    x, y = int(w * 0.045), h - th - int(h * 0.055)
    return draw_text(photo, "SattvaSrsti", (x, y), fnt, WHITE)


def option_c(photo: Image.Image) -> Image.Image:
    w, h = photo.size
    fnt = font(SEGOE_B, max(26, int(w * 0.04)))
    text = "sattvasrsti"
    tw, th = word_size(text, fnt)
    pad_x, pad_y = int(w * 0.018), int(h * 0.012)
    bw, bh = tw + pad_x * 2, th + pad_y * 2
    x, y = int(w * 0.04), h - bh - int(h * 0.04)
    layer = Image.new("RGBA", photo.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.rounded_rectangle((x, y, x + bw, y + bh), radius=int(bh * 0.45), fill=(20, 18, 16, 168))
    d.text((x + pad_x, y + pad_y - 2), text, font=fnt, fill=WHITE)
    return Image.alpha_composite(photo.convert("RGBA"), layer)


def option_d(photo: Image.Image) -> Image.Image:
    w, h = photo.size
    fnt = font(GEORGIA_B if GEORGIA_B.exists() else GEORGIA, max(28, int(w * 0.046)))
    tw, th = word_size("sattvasrsti", fnt)
    x, y = int(w * 0.045), h - th - int(h * 0.055)
    return draw_text(photo, "sattvasrsti", (x, y), fnt, GOLD, stroke=4, stroke_fill=(20, 18, 16, 210))


def option_e(photo: Image.Image) -> Image.Image:
    w, h = photo.size
    f1 = font(GEORGIA, max(24, int(w * 0.038)))
    f2 = font(GEORGIA_B if GEORGIA_B.exists() else GEORGIA, max(30, int(w * 0.052)))
    w1, h1 = word_size("Sattva", f1)
    w2, h2 = word_size("Srsti", f2)
    x = int(w * 0.045)
    y2 = h - h2 - int(h * 0.045)
    y1 = y2 - h1 - int(h * 0.004)
    out = draw_text(photo, "Sattva", (x, y1), f1, WHITE, stroke=2)
    return draw_text(out, "Srsti", (x, y2), f2, GOLD, stroke=3, stroke_fill=(20, 18, 16, 210))


def option_f(photo: Image.Image) -> Image.Image:
    w, h = photo.size
    mark = circular_logo(max(48, int(w * 0.09)))
    fnt = font(GEORGIA, max(26, int(w * 0.042)))
    tw, th = word_size("sattvasrsti", fnt)
    gap = int(w * 0.012)
    x = int(w * 0.04)
    y_mark = h - mark.height - int(h * 0.04)
    y_text = y_mark + (mark.height - th) // 2
    out = photo.convert("RGBA")
    out.alpha_composite(mark, (x, y_mark))
    return draw_text(out, "sattvasrsti", (x + mark.width + gap, y_text), fnt, WHITE)


def option_b_logo_beside(photo: Image.Image) -> Image.Image:
    """B wordmark with chef-hat logo to the left."""
    w, h = photo.size
    mark = circular_logo(max(52, int(w * 0.1)))
    fnt = font(GEORGIA_B if GEORGIA_B.exists() else GEORGIA, max(28, int(w * 0.046)))
    tw, th = word_size("SattvaSrsti", fnt)
    gap = int(w * 0.014)
    x = int(w * 0.04)
    y_mark = h - mark.height - int(h * 0.042)
    y_text = y_mark + (mark.height - th) // 2
    out = photo.convert("RGBA")
    out.alpha_composite(mark, (x, y_mark))
    return draw_text(out, "SattvaSrsti", (x + mark.width + gap, y_text), fnt, WHITE)


def option_b_logo_stack(photo: Image.Image) -> Image.Image:
    """B wordmark stacked under the chef-hat logo."""
    w, h = photo.size
    mark = circular_logo(max(52, int(w * 0.1)))
    fnt = font(GEORGIA_B if GEORGIA_B.exists() else GEORGIA, max(26, int(w * 0.042)))
    tw, th = word_size("SattvaSrsti", fnt)
    x = int(w * 0.045)
    y_text = h - th - int(h * 0.04)
    y_mark = y_text - mark.height - int(h * 0.012)
    out = photo.convert("RGBA")
    out.alpha_composite(mark, (x, y_mark))
    return draw_text(out, "SattvaSrsti", (x + (mark.width - tw) // 2 if tw < mark.width else x, y_text), fnt, WHITE)


def label_bar(im: Image.Image, title: str) -> Image.Image:
    w, h = im.size
    bar_h = max(56, int(h * 0.08))
    canvas = Image.new("RGB", (w, h + bar_h), (20, 18, 16))
    canvas.paste(im.convert("RGB"), (0, 0))
    d = ImageDraw.Draw(canvas)
    fnt = font(SEGOE_B, max(22, int(w * 0.032)))
    d.text((int(w * 0.04), h + (bar_h - word_size(title, fnt)[1]) // 2 - 4), title, font=fnt, fill=(247, 246, 243))
    return canvas


def main() -> int:
    if not SRC.exists():
        raise SystemExit(f"missing source photo: {SRC}")
    photo = Image.open(SRC).convert("RGB")
    # Work on a consistent preview width
    target_w = 900
    if photo.width != target_w:
        photo = photo.resize((target_w, int(photo.height * target_w / photo.width)), Image.Resampling.LANCZOS)

    cells = [
        label_bar(option_a(photo), "A  lowercase  ·  white"),
        label_bar(option_b(photo), "B  SattvaSrsti  ·  white"),
        label_bar(option_c(photo), "C  name in dark pill"),
        label_bar(option_d(photo), "D  gold wordmark"),
        label_bar(option_e(photo), "E  stacked Sattva / Srsti"),
        label_bar(option_f(photo), "F  hat + sattvasrsti"),
    ]
    cols, rows = 3, 2
    cw, ch = cells[0].size
    gap = 18
    sheet_w = cols * cw + (cols + 1) * gap
    sheet_h = rows * ch + (rows + 1) * gap + 72
    sheet = Image.new("RGB", (sheet_w, sheet_h), (247, 246, 243))
    d = ImageDraw.Draw(sheet)
    head = font(GEORGIA, 36)
    d.text((gap, 22), "sattvasrsti name watermark  ·  pick one", font=head, fill=(20, 18, 16))
    for i, cell in enumerate(cells):
        r, c = divmod(i, cols)
        if r >= rows:
            break
        x = gap + c * (cw + gap)
        y = 72 + gap + r * (ch + gap)
        sheet.paste(cell, (x, y))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(OUT, "JPEG", quality=90, optimize=True)
    print(OUT)

    b_out = ROOT / "preview" / "watermark-previews" / "b-plus-logo.jpg"
    pair = [
        label_bar(option_b_logo_beside(photo), "B + logo  ·  beside"),
        label_bar(option_b_logo_stack(photo), "B + logo  ·  stacked"),
    ]
    pw, ph = pair[0].size
    gap = 18
    board = Image.new("RGB", (pw * 2 + gap * 3, ph + gap * 2 + 64), (247, 246, 243))
    d = ImageDraw.Draw(board)
    d.text((gap, 18), "B  SattvaSrsti  +  chef-hat logo", font=font(GEORGIA, 32), fill=(20, 18, 16))
    board.paste(pair[0], (gap, 64 + gap))
    board.paste(pair[1], (gap * 2 + pw, 64 + gap))
    board.save(b_out, "JPEG", quality=90, optimize=True)
    print(b_out)
    return 0


if __name__ == "__main__":
  raise SystemExit(main())
