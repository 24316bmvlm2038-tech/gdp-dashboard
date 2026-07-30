"""Share-card rendering.

Every answer can be exported as a 1080×1350 image built for Instagram Stories,
TikTok, X and the rest. Cards are drawn with Pillow — gradient mesh, glass
panel, the question, your answer and the crowd's split — so the export looks
like the app rather than a screenshot of it.
"""

from __future__ import annotations

import io
import urllib.parse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .theme import gradient_for

W, H = 1080, 1350

_FONT_CANDIDATES = {
    'bold': [
        '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
        '/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf',
        '/System/Library/Fonts/SFNSDisplay.ttf',
        'C:/Windows/Fonts/segoeuib.ttf',
    ],
    'regular': [
        '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
        '/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf',
        '/System/Library/Fonts/SFNSText.ttf',
        'C:/Windows/Fonts/segoeui.ttf',
    ],
}


def _font(weight: str, size: int) -> ImageFont.FreeTypeFont:
    for path in _FONT_CANDIDATES[weight]:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    return ImageFont.load_default(size=size)


def _hex(value: str) -> tuple[int, int, int]:
    value = value.lstrip('#')
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def _gradient(size: tuple[int, int], top: str, bottom: str, angle: bool = True) -> Image.Image:
    w, h = size
    c1, c2 = _hex(top), _hex(bottom)
    base = Image.new('RGB', (w, h))
    draw = ImageDraw.Draw(base)
    span = w + h if angle else h
    for i in range(span):
        t = i / max(1, span - 1)
        colour = tuple(round(c1[j] + (c2[j] - c1[j]) * t) for j in range(3))
        if angle:
            draw.line([(i, 0), (0, i)], fill=colour, width=2)
        else:
            draw.line([(0, i), (w, i)], fill=colour)
    return base


def _glow(img: Image.Image, cx: int, cy: int, radius: int, colour: str, alpha: int) -> None:
    layer = Image.new('RGBA', img.size, (0, 0, 0, 0))
    ImageDraw.Draw(layer).ellipse(
        [cx - radius, cy - radius, cx + radius, cy + radius], fill=_hex(colour) + (alpha,))
    layer = layer.filter(ImageFilter.GaussianBlur(radius // 2))
    img.alpha_composite(layer)


def _wrap(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont,
          max_width: int) -> list[str]:
    words, lines, current = text.split(), [], ''
    for word in words:
        trial = f'{current} {word}'.strip()
        if draw.textlength(trial, font=font) <= max_width:
            current = trial
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def render(card: dict, *, answer_text: str = '', percent: int | None = None,
           user_name: str = '', streak: int = 0, level: int = 1) -> Image.Image:
    """Draw the share card for one answered question."""
    top, bottom = gradient_for(card.get('grad', 'indigo'))
    img = _gradient((W, H), top, bottom).convert('RGBA')
    _glow(img, 130, 180, 380, '#FFFFFF', 46)
    _glow(img, W - 90, H - 260, 460, '#000000', 60)

    draw = ImageDraw.Draw(img)

    # top rule + brand
    f_brand = _font('bold', 34)
    f_eyebrow = _font('bold', 27)
    draw.rounded_rectangle([72, 78, 132, 138], 20, fill=(255, 255, 255, 230))
    draw.text((85, 88), 'CF', font=_font('bold', 38), fill=_hex(top))
    draw.text((152, 92), 'Curiosity Feed', font=f_brand, fill=(255, 255, 255, 245))

    eyebrow = f'{card.get("type", "").upper()}  ·  {card.get("category", "").upper()}'
    draw.text((72, 190), eyebrow, font=f_eyebrow, fill=(255, 255, 255, 190))

    # glass panel
    panel = Image.new('RGBA', (W - 144, 0), (0, 0, 0, 0))
    f_q = _font('bold', 66)
    q_lines = _wrap(draw, card.get('title', ''), f_q, W - 220)[:5]
    panel_h = 150 + len(q_lines) * 84
    if answer_text:
        panel_h += 150
    panel = Image.new('RGBA', (W - 144, panel_h), (255, 255, 255, 38))
    mask = Image.new('L', panel.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, panel.size[0] - 1, panel.size[1] - 1], 56, fill=255)
    img.paste(panel, (72, 250), mask)
    draw.rounded_rectangle([72, 250, W - 72, 250 + panel_h], 56,
                           outline=(255, 255, 255, 90), width=2)

    y = 320
    for line in q_lines:
        draw.text((116, y), line, font=f_q, fill=(255, 255, 255, 252))
        y += 84

    if answer_text:
        y += 26
        draw.text((116, y), 'MY ANSWER', font=_font('bold', 25), fill=(255, 255, 255, 175))
        y += 40
        f_a = _font('bold', 46)
        a_lines = _wrap(draw, answer_text, f_a, W - 260)[:2]
        for line in a_lines:
            draw.text((116, y), line, font=f_a, fill=(255, 255, 255, 250))
            y += 56

    # crowd split
    bar_y = 250 + panel_h + 90
    if percent is not None:
        f_pct = _font('bold', 130)
        draw.text((72, bar_y - 40), f'{percent}%', font=f_pct, fill=(255, 255, 255, 252))
        label = 'agreed with me' if percent >= 50 else 'agreed with me'
        draw.text((78, bar_y + 110), label.upper(), font=_font('bold', 30),
                  fill=(255, 255, 255, 200))
        track_y = bar_y + 175
        draw.rounded_rectangle([72, track_y, W - 72, track_y + 26], 13, fill=(255, 255, 255, 70))
        fill_w = int((W - 144) * max(2, min(100, percent)) / 100)
        draw.rounded_rectangle([72, track_y, 72 + fill_w, track_y + 26], 13,
                               fill=(255, 255, 255, 240))

    # footer
    foot_y = H - 168
    draw.line([(72, foot_y - 34), (W - 72, foot_y - 34)], fill=(255, 255, 255, 70), width=2)
    who = f'{user_name}' if user_name else 'Someone curious'
    draw.text((72, foot_y), who, font=_font('bold', 38), fill=(255, 255, 255, 245))
    meta = f'Level {level}'
    if streak:
        meta += f'  ·  {streak}-day streak'
    draw.text((72, foot_y + 52), meta, font=_font('regular', 30), fill=(255, 255, 255, 190))

    cta = "What's your answer?"
    f_cta = _font('bold', 34)
    cta_w = draw.textlength(cta, font=f_cta)
    draw.rounded_rectangle([W - 96 - cta_w - 56, foot_y + 2, W - 72, foot_y + 70], 34,
                           fill=(255, 255, 255, 235))
    draw.text((W - 96 - cta_w - 28, foot_y + 18), cta, font=f_cta, fill=_hex(bottom))

    return img.convert('RGB')


def to_png(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, 'PNG', optimize=True)
    return buffer.getvalue()


def caption(card: dict, answer_text: str = '', percent: int | None = None) -> str:
    parts = [f'“{card.get("title", "")}”']
    if answer_text:
        parts.append(f'I chose: {answer_text}.')
    if percent is not None:
        parts.append(f'Only {percent}% agreed.')
    parts.append("What's your answer? — Curiosity Feed")
    return ' '.join(parts)


def share_url(template: str, text: str, url: str) -> str:
    return template.format(text=urllib.parse.quote(text[:260]), url=urllib.parse.quote(url))
