"""
One-time local script (not part of the automated pipeline) that generates a
channel avatar + banner matching the actual video style: reuses the same
weapon icons (battle_sim.make_icon) and arena color palette (ARENA_THEMES)
the videos are rendered with, so the channel art and the content look like
one system instead of a mismatched Canva template.

Run once: python generate_branding.py
Then upload branding_profile.png / branding_banner.png manually in
YouTube Studio -> Customization -> Branding.
"""
import math

from PIL import Image, ImageDraw, ImageFont, ImageFilter

from battle_sim import make_icon, ARENA_THEMES

FONT_BOLD = "C:/Windows/Fonts/arialbd.ttf"
FONT_BLACK = "C:/Windows/Fonts/impact.ttf"

THEME = next(t for t in ARENA_THEMES if t["name"] == "Neon City")
BG_TOP = THEME["top"]
BG_BOTTOM = THEME["bottom"]
ACCENT_A = THEME["border"][:3]      # vivid magenta
ACCENT_B = (60, 220, 255)           # cyan, for contrast against the magenta theme
WHITE = (248, 248, 252)


def vertical_gradient(size, top, bottom):
    w, h = size
    img = Image.new("RGB", size, top)
    px = img.load()
    for y in range(h):
        t = y / max(h - 1, 1)
        r = int(top[0] + (bottom[0] - top[0]) * t)
        g = int(top[1] + (bottom[1] - top[1]) * t)
        b = int(top[2] + (bottom[2] - top[2]) * t)
        for x in range(w):
            px[x, y] = (r, g, b)
    return img


def fit_font(path, text, max_width, start_size, min_size=20):
    size = start_size
    while size > min_size:
        font = ImageFont.truetype(path, size)
        bbox = font.getbbox(text)
        w = bbox[2] - bbox[0]
        if w <= max_width:
            return font
        size -= 2
    return ImageFont.truetype(path, min_size)


def _glow_blob(size, center, radius, color, alpha, blur):
    glow = Image.new("RGBA", size, (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    cx, cy = center
    gd.ellipse([cx - radius, cy - radius, cx + radius, cy + radius], fill=(*color, alpha))
    return glow.filter(ImageFilter.GaussianBlur(blur))


def crossed_weapons(size, kind_a="katana", kind_b="axe"):
    """Two of our own polished weapon icons, crossed like a badge emblem."""
    icon_size = int(size * 0.62)
    icon_a = make_icon(kind_a, (240, 240, 248), icon_size).rotate(35, resample=Image.BICUBIC, expand=True)
    icon_b = make_icon(kind_b, (214, 92, 68), icon_size).rotate(-35, resample=Image.BICUBIC, expand=True)

    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    ax = (size - icon_a.width) // 2
    ay = (size - icon_a.height) // 2 - int(size * 0.04)
    bx = (size - icon_b.width) // 2
    by = (size - icon_b.height) // 2 + int(size * 0.04)
    canvas.alpha_composite(icon_b, (bx, by))
    canvas.alpha_composite(icon_a, (ax, ay))
    return canvas


def make_profile(path):
    S = 800
    img = vertical_gradient((S, S), BG_TOP, BG_BOTTOM).convert("RGBA")

    glow = _glow_blob((S, S), (S / 2, S / 2), S * 0.42, ACCENT_A, 90, 70)
    img = Image.alpha_composite(img, glow)

    ring_d = ImageDraw.Draw(img)
    ring_r = S * 0.44
    ring_d.ellipse(
        [S / 2 - ring_r, S / 2 - ring_r, S / 2 + ring_r, S / 2 + ring_r],
        outline=(*ACCENT_B, 220), width=int(S * 0.014),
    )

    emblem = crossed_weapons(int(S * 0.72))
    img.alpha_composite(emblem, (int(S * 0.14), int(S * 0.14)))

    img.convert("RGB").save(path, "PNG")
    print(f"OK: {path}")


def make_banner(path):
    W, H = 2048, 1152
    img = vertical_gradient((W, H), BG_TOP, BG_BOTTOM).convert("RGBA")

    glow1 = _glow_blob((W, H), (W * 0.12, H * 0.15), 520, ACCENT_A, 75, 120)
    glow2 = _glow_blob((W, H), (W * 0.9, H * 0.85), 520, ACCENT_B, 60, 120)
    img = Image.alpha_composite(img, glow1)
    img = Image.alpha_composite(img, glow2)

    # decorative weapon icons scattered outside the centered safe zone
    deco = [
        ("mace", (176, 100, 214), 210, (150, 900), -18),
        ("scythe", (72, 190, 226), 260, (1720, 940), 22),
        ("hammer", (150, 150, 160), 190, (1840, 160), -30),
        ("dagger", (236, 205, 70), 150, (120, 180), 15),
    ]
    for kind, color, isize, pos, angle in deco:
        icon = make_icon(kind, color, isize).rotate(angle, resample=Image.BICUBIC, expand=True)
        img.alpha_composite(icon, (pos[0] - icon.width // 2, pos[1] - icon.height // 2))

    draw = ImageDraw.Draw(img)

    safe_w = 1546
    safe_x0 = (W - safe_w) / 2

    title = "WEAPON BALL ARENA"
    title_font = fit_font(FONT_BLACK, title, safe_w * 0.95, 150, 70)
    tb = title_font.getbbox(title)
    tw, th = tb[2] - tb[0], tb[3] - tb[1]
    title_y = H / 2 - th - 20

    draw.text((safe_x0 + (safe_w - tw) / 2 + 6, title_y + 6), title, font=title_font, fill=(0, 0, 0, 170))
    draw.text((safe_x0 + (safe_w - tw) / 2, title_y), title, font=title_font, fill=WHITE)

    subtitle = "Daily Physics Battles — Who Wins?"
    sub_font = fit_font(FONT_BOLD, subtitle, safe_w * 0.8, 54, 28)
    sb = sub_font.getbbox(subtitle)
    sw, sh = sb[2] - sb[0], sb[3] - sb[1]
    sub_y = title_y + th + 34
    draw.text((safe_x0 + (safe_w - sw) / 2, sub_y), subtitle, font=sub_font, fill=ACCENT_B)

    img.convert("RGB").save(path, "PNG")
    print(f"OK: {path}")


if __name__ == "__main__":
    make_profile("branding_profile.png")
    make_banner("branding_banner.png")
