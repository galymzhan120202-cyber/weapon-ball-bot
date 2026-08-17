"""
Fully generated (code-only) weapon-vs-weapon physics battle — no stock
footage, no real weapon images, no LLM script. 2-4 weapon icons (drawn as
vector shapes) bounce inside a box under pymunk physics; every collision
knocks HP off both sides involved until only one fighter is left standing.
Video frames, HP bars, hit flashes and impact sound effects are all
synthesized from the physics log, so a battle is fully reproducible from
its `seed`.
"""
import hashlib
import math
import random

import numpy as np
import pymunk
from PIL import Image, ImageDraw, ImageFont, ImageFilter

# --- Weapon roster -----------------------------------------------------

WEAPON_POOL = [
    {"name": "Sword", "kind": "sword", "color": (225, 225, 232), "power": 1.00, "material": "metal"},
    {"name": "Katana", "kind": "katana", "color": (240, 240, 248), "power": 1.02, "material": "metal"},
    {"name": "Axe", "kind": "axe", "color": (214, 92, 68), "power": 1.15, "material": "metal"},
    {"name": "Hammer", "kind": "hammer", "color": (150, 150, 160), "power": 1.28, "material": "blunt"},
    {"name": "Warhammer", "kind": "warhammer", "color": (120, 130, 150), "power": 1.38, "material": "blunt"},
    {"name": "Spear", "kind": "spear", "color": (96, 206, 148), "power": 0.92, "material": "metal"},
    {"name": "Trident", "kind": "trident", "color": (70, 190, 210), "power": 0.98, "material": "metal"},
    {"name": "Dagger", "kind": "dagger", "color": (236, 205, 70), "power": 0.78, "material": "metal"},
    {"name": "Kunai", "kind": "kunai", "color": (200, 200, 210), "power": 0.72, "material": "metal"},
    {"name": "Mace", "kind": "mace", "color": (176, 100, 214), "power": 1.22, "material": "blunt"},
    {"name": "Flail", "kind": "flail", "color": (210, 140, 60), "power": 1.30, "material": "blunt"},
    {"name": "Nunchaku", "kind": "nunchaku", "color": (140, 90, 50), "power": 0.85, "material": "wood"},
    {"name": "Whip", "kind": "whip", "color": (180, 60, 60), "power": 0.70, "material": "whip"},
    {"name": "Scythe", "kind": "scythe", "color": (72, 190, 226), "power": 1.08, "material": "metal"},
    {"name": "Claws", "kind": "claws", "color": (230, 230, 235), "power": 0.88, "material": "metal"},
    {"name": "Chainsaw", "kind": "chainsaw", "color": (230, 190, 40), "power": 1.35, "material": "mechanical"},
    {"name": "Staff", "kind": "staff", "color": (170, 130, 220), "power": 0.80, "material": "wood"},
    {"name": "Shuriken", "kind": "shuriken", "color": (210, 60, 90), "power": 0.75, "material": "metal"},
]

WOOD = (110, 74, 40)
STEEL = (150, 150, 160)


def _draw_icon_shape(kind, color, size=170):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    cx = size / 2
    c = (*color, 255)

    if kind == "sword":
        bw = size * 0.09
        d.polygon([(cx, size * 0.05), (cx + bw, size * 0.55), (cx - bw, size * 0.55)], fill=c)
        d.rectangle([cx - size * 0.17, size * 0.55, cx + size * 0.17, size * 0.62], fill=(*STEEL, 255))
        d.rectangle([cx - bw * 0.5, size * 0.62, cx + bw * 0.5, size * 0.85], fill=(*WOOD, 255))
        d.ellipse([cx - bw * 0.8, size * 0.83, cx + bw * 0.8, size * 0.93], fill=(*WOOD, 255))
    elif kind == "axe":
        d.line([(cx - size * 0.16, size * 0.90), (cx + size * 0.14, size * 0.12)], fill=(*WOOD, 255), width=int(size * 0.055))
        d.pieslice([cx - size * 0.06, size * 0.02, cx + size * 0.44, size * 0.42], start=195, end=345, fill=c)
    elif kind == "hammer":
        d.line([(cx, size * 0.90), (cx, size * 0.36)], fill=(*WOOD, 255), width=int(size * 0.07))
        d.rounded_rectangle([cx - size * 0.24, size * 0.10, cx + size * 0.24, size * 0.40], radius=int(size * 0.05), fill=c)
    elif kind == "spear":
        d.line([(cx, size * 0.95), (cx, size * 0.16)], fill=(*WOOD, 255), width=int(size * 0.045))
        d.polygon([(cx, size * 0.02), (cx + size * 0.075, size * 0.24), (cx - size * 0.075, size * 0.24)], fill=c)
    elif kind == "dagger":
        bw = size * 0.065
        d.polygon([(cx, size * 0.18), (cx + bw, size * 0.55), (cx - bw, size * 0.55)], fill=c)
        d.rectangle([cx - size * 0.12, size * 0.55, cx + size * 0.12, size * 0.60], fill=(*STEEL, 255))
        d.rectangle([cx - bw * 0.6, size * 0.60, cx + bw * 0.6, size * 0.75], fill=(*WOOD, 255))
    elif kind == "mace":
        d.line([(cx, size * 0.92), (cx, size * 0.46)], fill=(*WOOD, 255), width=int(size * 0.06))
        d.ellipse([cx - size * 0.17, size * 0.13, cx + size * 0.17, size * 0.47], fill=c)
        for ang in range(0, 360, 45):
            rad = math.radians(ang)
            x2 = cx + math.cos(rad) * size * 0.25
            y2 = size * 0.30 + math.sin(rad) * size * 0.25
            d.line([(cx, size * 0.30), (x2, y2)], fill=c, width=max(2, int(size * 0.025)))
    elif kind == "scythe":
        d.line([(cx, size * 0.96), (cx, size * 0.30)], fill=(*WOOD, 255), width=int(size * 0.04))
        d.arc([cx - size * 0.36, size * 0.02, cx + size * 0.34, size * 0.52], start=200, end=340, fill=c, width=int(size * 0.07))
    elif kind == "katana":
        bw = size * 0.06
        d.polygon([
            (cx + size * 0.06, size * 0.04), (cx + bw, size * 0.30), (cx + bw * 0.4, size * 0.58),
            (cx - bw * 0.4, size * 0.58), (cx - bw * 0.3, size * 0.30),
        ], fill=c)
        d.rectangle([cx - size * 0.15, size * 0.58, cx + size * 0.15, size * 0.64], fill=(20, 20, 24, 255))
        d.rectangle([cx - bw * 0.5, size * 0.64, cx + bw * 0.5, size * 0.88], fill=(30, 30, 34, 255))
        for i in range(3):
            yy = size * (0.66 + i * 0.07)
            d.line([(cx - bw * 0.5, yy), (cx + bw * 0.5, yy + size * 0.035)], fill=(200, 200, 60, 255), width=2)
    elif kind == "warhammer":
        d.line([(cx, size * 0.94), (cx, size * 0.40)], fill=(*WOOD, 255), width=int(size * 0.09))
        d.rounded_rectangle([cx - size * 0.30, size * 0.06, cx + size * 0.30, size * 0.44], radius=int(size * 0.06), fill=c)
        d.rounded_rectangle([cx - size * 0.30, size * 0.06, cx + size * 0.30, size * 0.44], radius=int(size * 0.06), outline=(40, 40, 44, 255), width=3)
    elif kind == "trident":
        d.line([(cx, size * 0.96), (cx, size * 0.22)], fill=(*WOOD, 255), width=int(size * 0.045))
        for off in (-0.16, 0, 0.16):
            d.polygon([
                (cx + size * off, size * 0.02), (cx + size * off + size * 0.045, size * 0.26),
                (cx + size * off - size * 0.045, size * 0.26),
            ], fill=c)
        d.line([(cx - size * 0.16, size * 0.20), (cx + size * 0.16, size * 0.20)], fill=c, width=max(2, int(size * 0.02)))
    elif kind == "kunai":
        bw = size * 0.10
        d.polygon([(cx, size * 0.10), (cx + bw, size * 0.46), (cx, size * 0.40), (cx - bw, size * 0.46)], fill=c)
        d.rectangle([cx - bw * 0.35, size * 0.46, cx + bw * 0.35, size * 0.78], fill=(60, 60, 66, 255))
        d.ellipse([cx - size * 0.11, size * 0.78, cx + size * 0.11, size * 0.94], outline=(60, 60, 66, 255), width=max(2, int(size * 0.025)))
    elif kind == "flail":
        d.line([(cx, size * 0.94), (cx, size * 0.62)], fill=(*WOOD, 255), width=int(size * 0.055))
        for i in range(3):
            yy = size * (0.58 - i * 0.09)
            d.ellipse([cx - size * 0.045, yy - size * 0.03, cx + size * 0.045, yy + size * 0.03], outline=(120, 120, 130, 255), width=3)
        d.ellipse([cx - size * 0.16, size * 0.10, cx + size * 0.16, size * 0.42], fill=c)
        for ang in range(0, 360, 40):
            rad = math.radians(ang)
            x2 = cx + math.cos(rad) * size * 0.23
            y2 = size * 0.26 + math.sin(rad) * size * 0.23
            d.line([(cx, size * 0.26), (x2, y2)], fill=(200, 200, 205, 255), width=max(2, int(size * 0.02)))
    elif kind == "nunchaku":
        d.rounded_rectangle([cx - size * 0.09, size * 0.04, cx + size * 0.09, size * 0.40], radius=int(size * 0.03), fill=c)
        d.rounded_rectangle([cx - size * 0.09, size * 0.58, cx + size * 0.09, size * 0.94], radius=int(size * 0.03), fill=c)
        mid1, mid2 = (cx, size * 0.40), (cx, size * 0.58)
        d.line([mid1, ((mid1[0] + mid2[0]) / 2 + size * 0.07, (mid1[1] + mid2[1]) / 2), mid2], fill=(90, 90, 96, 255), width=max(2, int(size * 0.02)))
    elif kind == "whip":
        pts = []
        for i in range(9):
            t = i / 8
            x = cx + math.sin(t * 3.6) * size * (0.05 + t * 0.16)
            y = size * (0.06 + t * 0.78)
            pts.append((x, y))
        d.line(pts, fill=c, width=max(2, int(size * 0.028)), joint="curve")
        d.rounded_rectangle([cx - size * 0.06, size * 0.84, cx + size * 0.06, size * 0.96], radius=4, fill=(*WOOD, 255))
    elif kind == "claws":
        for off in (-0.14, 0.0, 0.14):
            d.polygon([
                (cx + size * off, size * 0.06), (cx + size * off + size * 0.045, size * 0.52),
                (cx + size * off - size * 0.045, size * 0.52),
            ], fill=c)
        d.rounded_rectangle([cx - size * 0.20, size * 0.52, cx + size * 0.20, size * 0.72], radius=int(size * 0.04), fill=(70, 70, 76, 255))
    elif kind == "chainsaw":
        d.rounded_rectangle([cx - size * 0.16, size * 0.30, cx + size * 0.16, size * 0.78], radius=int(size * 0.05), fill=(70, 70, 76, 255))
        d.rounded_rectangle([cx - size * 0.10, size * 0.05, cx + size * 0.10, size * 0.34], radius=int(size * 0.03), fill=c)
        for i in range(6):
            yy = size * (0.07 + i * 0.045)
            side = 1 if i % 2 == 0 else -1
            d.polygon([(cx + side * size * 0.10, yy), (cx + side * size * 0.16, yy + size * 0.02), (cx + side * size * 0.10, yy + size * 0.04)], fill=(230, 230, 235, 255))
    elif kind == "staff":
        d.line([(cx, size * 0.96), (cx, size * 0.06)], fill=(*WOOD, 255), width=int(size * 0.05))
        d.ellipse([cx - size * 0.11, size * 0.02, cx + size * 0.11, size * 0.20], outline=c, width=max(3, int(size * 0.03)))
    elif kind == "shuriken":
        pts = []
        for i in range(8):
            ang = math.radians(i * 45)
            r = size * 0.40 if i % 2 == 0 else size * 0.14
            pts.append((cx + math.cos(ang) * r, size / 2 + math.sin(ang) * r))
        d.polygon(pts, fill=c)
        d.ellipse([cx - size * 0.06, size / 2 - size * 0.06, cx + size * 0.06, size / 2 + size * 0.06], fill=(40, 40, 44, 255))
    return img


def _polish_icon(icon):
    """Outline + drop shadow + diagonal light/dark shading, applied once per
    icon (not per frame) so any flat silhouette reads as a solid 3D object
    and pops against a busy arena background."""
    w, h = icon.size
    alpha = icon.split()[3]
    alpha_np = np.asarray(alpha, dtype=np.float32) / 255.0

    result = Image.new("RGBA", (w, h), (0, 0, 0, 0))

    # drop shadow: blurred + darkened silhouette, offset down-right
    shadow_alpha = alpha.filter(ImageFilter.GaussianBlur(4)).point(lambda p: int(p * 0.6))
    shadow = Image.new("RGBA", (w, h), (0, 0, 0, 255))
    shadow.putalpha(shadow_alpha)
    shifted_shadow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    shifted_shadow.paste(shadow, (4, 6), shadow)
    result.alpha_composite(shifted_shadow)

    # outline: dilated silhouette in a near-black tone, sits just behind the icon
    outline_alpha = alpha.filter(ImageFilter.MaxFilter(5))
    outline = Image.new("RGBA", (w, h), (14, 14, 18, 255))
    outline.putalpha(outline_alpha)
    result.alpha_composite(outline)

    result.alpha_composite(icon)

    # diagonal sheen (top-left, bright) + opposite shade (bottom-right, dark)
    # for a rounded/volumetric look — masked by the icon's own alpha so it
    # never bleeds outside the silhouette.
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    grad = np.clip(1.0 - (xx + yy) / (w + h), 0.0, 1.0) ** 1.4

    sheen_a = (grad * 95 * alpha_np).astype(np.uint8)
    sheen = Image.new("RGBA", (w, h), (255, 255, 255, 0))
    sheen.putalpha(Image.fromarray(sheen_a, mode="L"))
    result.alpha_composite(sheen)

    shade_a = ((1.0 - grad) * 75 * alpha_np).astype(np.uint8)
    shade = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    shade.putalpha(Image.fromarray(shade_a, mode="L"))
    result.alpha_composite(shade)

    # tight glossy specular streak — narrower and brighter than the broad
    # sheen above, so metal/wood alike pick up a "rendered" highlight
    # instead of reading as flat cartoon fill.
    diag = (xx + yy) / (w + h)
    band = np.clip(1.0 - np.abs(diag - 0.26) * 6.0, 0.0, 1.0) ** 2
    highlight_a = (band * 170 * alpha_np).astype(np.uint8)
    highlight = Image.new("RGBA", (w, h), (255, 255, 255, 0))
    highlight.putalpha(Image.fromarray(highlight_a, mode="L"))
    highlight = highlight.filter(ImageFilter.GaussianBlur(1.2))
    result.alpha_composite(highlight)

    return result


def make_icon(kind, color, size=170):
    return _polish_icon(_draw_icon_shape(kind, color, size))


def make_obstacle_icon(radius_px, accent_color):
    """A jagged rock/crystal obstacle, tinted with the arena theme's accent
    color, built with the same outline/shadow/sheen pass as weapon icons so
    it reads as part of the same visual system."""
    size = int(radius_px * 2.5)
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    cx = cy = size / 2
    shape_rng = random.Random(42)
    n_pts = 9
    pts = []
    for i in range(n_pts):
        ang = math.radians(i * 360 / n_pts)
        rr = radius_px * shape_rng.uniform(0.78, 1.0)
        pts.append((cx + math.cos(ang) * rr, cy + math.sin(ang) * rr))
    d.polygon(pts, fill=(66, 64, 62, 255))
    for i in range(0, n_pts, 3):
        d.line([pts[i], (cx, cy)], fill=(*accent_color, 130), width=2)
    return _polish_icon(img)


# --- Fonts ---------------------------------------------------------------

_FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "C:\\Windows\\Fonts\\arialbd.ttf",
    "C:\\Windows\\Fonts\\arial.ttf",
]


def get_font(size):
    for path in _FONT_CANDIDATES:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    return ImageFont.load_default()


# --- Physics simulation ---------------------------------------------------

# Countdown hold before the fight starts ("3", "2", "1", "FIGHT!"), shared
# between the video renderer and the SFX builder so their timelines line up.
INTRO_SECONDS = 2.0

PHYSICS_HZ = 120
START_HP = 100.0

# Fewer fighters = bigger icons/hitboxes; more fighters = smaller, so a 4-way
# melee doesn't turn into an unreadable pile in the same arena footprint.
RADIUS_BY_N = {2: 71.4, 3: 60.0, 4: 52.0}
ICON_SIZE_BY_N = {2: 170, 3: 146, 4: 126}

# How often a video is a 1v1 duel vs a 3-way / 4-way melee.
N_FIGHTERS_WEIGHTS = {2: 55, 3: 28, 4: 17}


def simulate_battle(w, h, seed, fps=24, max_seconds=30, min_seconds=13, n_fighters=None):
    rng = random.Random(seed)

    if n_fighters is None:
        options = list(N_FIGHTERS_WEIGHTS.keys())
        weights = list(N_FIGHTERS_WEIGHTS.values())
        n_fighters = rng.choices(options, weights=weights, k=1)[0]

    fighters = rng.sample(WEAPON_POOL, n_fighters)
    radius = RADIUS_BY_N[n_fighters]
    icon_size = ICON_SIZE_BY_N[n_fighters]

    top_arena = int(h * 0.24)
    bottom_arena = int(h * 0.965)
    left_arena = int(w * 0.055)
    right_arena = int(w * 0.945)
    center_x = (left_arena + right_arena) / 2
    center_y = (top_arena + bottom_arena) / 2

    space = pymunk.Space()
    space.gravity = (0, 0)

    def spawn(x, y, angle_deg, speed, ctype, mass):
        body = pymunk.Body(mass=mass, moment=pymunk.moment_for_circle(mass, 0, radius))
        body.position = (x, y)
        rad = math.radians(angle_deg)
        body.velocity = (math.cos(rad) * speed, math.sin(rad) * speed)
        body.angular_velocity = rng.uniform(-5.5, 5.5)
        shape = pymunk.Circle(body, radius)
        shape.elasticity = 1.0
        # A little friction (fighter-vs-fighter clashes only, walls stay at 0
        # so bounces off the arena edge stay clean) lets impacts transfer
        # spin, so a weapon's rotation visibly kicks or stalls on a hit
        # instead of spinning at one constant rate for the whole fight.
        shape.friction = 0.28
        shape.collision_type = ctype
        space.add(body, shape)
        return body, shape

    speed0 = min(w, h) * 0.40
    spawn_r = min(right_arena - left_arena, bottom_arena - top_arena) * (0.30 if n_fighters <= 2 else 0.33)
    angle_offset = rng.uniform(0, 360)

    # Mass tracks each weapon's "power" stat, so a heavy weapon (Warhammer,
    # power ~1.4) physically shrugs off a hit that sends a light one (Dagger,
    # power ~0.8) flying — the collision itself feels like weight, not just
    # the HP number ticking down.
    bodies, shapes = [], []
    for i in range(n_fighters):
        ang = math.radians(angle_offset + i * 360 / n_fighters)
        x = center_x + math.cos(ang) * spawn_r
        y = center_y + math.sin(ang) * spawn_r
        aim = math.degrees(math.atan2(center_y - y, center_x - x)) + rng.uniform(-25, 25)
        body, shape = spawn(x, y, aim, speed0, ctype=i + 1, mass=fighters[i]["power"])
        bodies.append(body)
        shapes.append(shape)

    pts = [(left_arena, top_arena), (right_arena, top_arena), (right_arena, bottom_arena), (left_arena, bottom_arena)]
    for i in range(4):
        seg = pymunk.Segment(space.static_body, pts[i], pts[(i + 1) % 4], 4)
        seg.elasticity = 1.0
        seg.friction = 0.0
        space.add(seg)

    # Occasional static obstacle(s) near the middle of the arena — bounced
    # off exactly like the walls (collision_type 0, no damage), so a fight
    # isn't always just an empty box. Offset off dead-center so a single
    # obstacle in a 1v1 doesn't sit perfectly on the direct line between the
    # two spawn points and choke the opening exchange.
    obstacle_radius = min(right_arena - left_arena, bottom_arena - top_arena) * 0.055
    obstacle_count = rng.choices([0, 1, 2], weights=[35, 45, 20], k=1)[0]
    obstacles = []
    if obstacle_count >= 1:
        oang = rng.uniform(0, 360)
        orad = spawn_r * rng.uniform(0.15, 0.35)
        obstacles.append((center_x + math.cos(math.radians(oang)) * orad, center_y + math.sin(math.radians(oang)) * orad))
    if obstacle_count >= 2:
        oang2 = oang + 180 + rng.uniform(-30, 30)
        orad2 = spawn_r * rng.uniform(0.55, 0.8)
        obstacles.append((center_x + math.cos(math.radians(oang2)) * orad2, center_y + math.sin(math.radians(oang2)) * orad2))
    for (ox, oy) in obstacles:
        obs_shape = pymunk.Circle(space.static_body, obstacle_radius, offset=(ox, oy))
        obs_shape.elasticity = 1.0
        obs_shape.friction = 0.0
        obs_shape.collision_type = 0
        space.add(obs_shape)

    hp = [START_HP] * n_fighters
    alive = [True] * n_fighters
    ctype_to_idx = {i + 1: i for i in range(n_fighters)}
    hit_log = []  # (step_index, x, y, total_dmg)
    step_counter = {"n": 0}

    def on_hit(arbiter, space, data):
        ct1, ct2 = arbiter.shapes[0].collision_type, arbiter.shapes[1].collision_type
        if ct1 not in ctype_to_idx or ct2 not in ctype_to_idx:
            return True  # a wall hit, not a fighter-vs-fighter clash
        i1, i2 = ctype_to_idx[ct1], ctype_to_idx[ct2]
        if not alive[i1] or not alive[i2]:
            return True

        impulse = arbiter.total_impulse.length
        base = min(24.0, max(2.5, impulse * 0.028))
        p1, p2 = fighters[i1]["power"], fighters[i2]["power"]
        d1 = base * (p2 / p1) * rng.uniform(0.82, 1.18)
        d2 = base * (p1 / p2) * rng.uniform(0.82, 1.18)
        hp[i1] = max(0.0, hp[i1] - d1)
        hp[i2] = max(0.0, hp[i2] - d2)

        cps = arbiter.contact_point_set.points
        cx, cy = (cps[0].point_a.x, cps[0].point_a.y) if cps else (bodies[i1].position.x, bodies[i1].position.y)
        hit_log.append((step_counter["n"], cx, cy, round(d1 + d2), i1, i2))
        return True

    space.on_collision(post_solve=on_hit)

    dt = 1.0 / PHYSICS_HZ
    steps_per_frame = max(1, PHYSICS_HZ // fps)
    max_steps = int(max_seconds * PHYSICS_HZ)
    min_steps = int(min_seconds * PHYSICS_HZ)

    # Periodic "seek" impulse: without this, perfectly elastic billiard
    # trajectories can drift apart and never intersect again. Each alive
    # fighter periodically lunges toward one random alive opponent, which
    # both guarantees the fight escalates and reads as active aggression
    # rather than passive floating — doubly important with 3-4 fighters,
    # where it also stops the pack from splitting into isolated orbits.
    lunge_interval_steps = int(1.1 * PHYSICS_HZ)
    lunge_strength = speed0 * 0.65
    max_speed = speed0 * 1.8

    frames = []
    hit_frame_flags = {}  # frame_index -> (x, y, dmg)
    ko_events = []  # list of (frame_index, fighter_idx, x, y) — a list, not a
    # dict keyed by frame, because two fighters can die in the very same
    # frame window (a mutual/simultaneous KO) and would otherwise clobber
    # each other's entry
    frame_idx = 0

    while step_counter["n"] < max_steps:
        step_counter["n"] += 1
        space.step(dt)

        if step_counter["n"] % lunge_interval_steps == 0:
            alive_idx = [i for i in range(n_fighters) if alive[i]]
            for i in alive_idx:
                others = [j for j in alive_idx if j != i]
                if not others:
                    continue
                j = rng.choice(others)
                dx = bodies[j].position.x - bodies[i].position.x
                dy = bodies[j].position.y - bodies[i].position.y
                dist = max(1.0, math.hypot(dx, dy))
                jitter = math.radians(rng.uniform(-20, 20))
                ux, uy = dx / dist, dy / dist
                ux, uy = ux * math.cos(jitter) - uy * math.sin(jitter), ux * math.sin(jitter) + uy * math.cos(jitter)
                bodies[i].velocity = (bodies[i].velocity.x + ux * lunge_strength, bodies[i].velocity.y + uy * lunge_strength)
                sp = bodies[i].velocity.length
                if sp > max_speed:
                    bodies[i].velocity = bodies[i].velocity * (max_speed / sp)

        if step_counter["n"] % steps_per_frame == 0:
            pos = []
            for i in range(n_fighters):
                b = bodies[i]
                pos.append((b.position.x, b.position.y, math.degrees(b.angle)))
            frames.append({"pos": pos, "hp": list(hp), "alive": list(alive)})
            frame_idx += 1

        if hit_log and hit_log[-1][0] == step_counter["n"]:
            _, hx, hy, dmg, hi1, hi2 = hit_log[-1]
            hit_frame_flags[frame_idx - 1] = (hx, hy, dmg, hi1, hi2)

        for i in range(n_fighters):
            if alive[i] and hp[i] <= 0:
                alive[i] = False
                ko_events.append((frame_idx - 1, i, bodies[i].position.x, bodies[i].position.y))
                try:
                    space.remove(bodies[i], shapes[i])
                except Exception:
                    pass

        if step_counter["n"] >= min_steps and sum(alive) <= 1:
            break

    # Winner = highest remaining HP. Tie-break (mainly for the rare
    # simultaneous "double KO" where the last two fighters finish each
    # other off in the same hit, leaving hp=[0,0,...]): whoever was
    # eliminated latest — i.e. outlasted the others — wins; fighters who
    # were never eliminated rank above everyone by treating their KO frame
    # as infinite.
    ko_frame_by_idx = {i: frame for (frame, i, _, _) in ko_events}
    winner_idx = max(
        range(n_fighters),
        key=lambda i: (hp[i], ko_frame_by_idx.get(i, float("inf"))),
    )
    loser_names = [fighters[i]["name"] for i in range(n_fighters) if i != winner_idx]

    # "Comeback" story: the eventual winner was at some point critically low
    # on HP (but never eliminated) before pulling out the win — flagged so
    # the finale banner can call it out specially.
    min_winner_hp = min((fr["hp"][winner_idx] for fr in frames), default=START_HP)
    is_comeback = 0 < min_winner_hp < START_HP * 0.20

    # "Double KO": two or more fighters were eliminated in the exact same
    # recorded frame — i.e. the fight ended in a genuinely simultaneous
    # mutual finish, not a clean single winner.
    last_ko_frame = max((k[0] for k in ko_events), default=None)
    is_double_ko = last_ko_frame is not None and sum(1 for k in ko_events if k[0] == last_ko_frame) >= 2

    # Slow-mo replay of the finishing blow: take the real frames right around
    # the last recorded hit, duplicate each one (2x slow motion) and append
    # them as their own segment *after* the live fight but *before* the
    # freeze/banner — the classic "fight plays out, then a quick cinematic
    # replay of the final clash" beat. hit_frame_flags/ko_events get mirrored
    # entries at the new indices so the flash/damage-popup/KO burst replay
    # too, not just the raw motion.
    REPLAY_PRE_FRAMES = 10
    REPLAY_POST_FRAMES = 6
    replay_range = None
    replay_focus = None
    if hit_frame_flags and frames:
        finishing_hit_frame = max(hit_frame_flags.keys())
        r0 = max(0, finishing_hit_frame - REPLAY_PRE_FRAMES)
        r1 = min(len(frames) - 1, finishing_hit_frame + REPLAY_POST_FRAMES)
        replay_focus = hit_frame_flags[finishing_hit_frame][:2]

        replay_start = len(frames)
        for src_idx in range(r0, r1 + 1):
            src = frames[src_idx]
            dup = {"pos": list(src["pos"]), "hp": list(src["hp"]), "alive": list(src["alive"])}
            for _ in range(2):  # each source frame plays twice => 2x slow-mo
                new_idx = len(frames)
                frames.append(dict(dup))
                if src_idx in hit_frame_flags:
                    hit_frame_flags[new_idx] = hit_frame_flags[src_idx]
                for (koi, fi, kx, ky) in list(ko_events):
                    if koi == src_idx:
                        ko_events.append((new_idx, fi, kx, ky))
        replay_range = (replay_start, len(frames))

    # Freeze-frame finale: hold the last state and pop victory text for ~1.6s
    finale_frames = int(1.6 * fps)
    if frames:
        last = dict(frames[-1])
        last["pos"] = list(last["pos"])
        for _ in range(finale_frames):
            frames.append(dict(last))

    return {
        "frames": frames,
        "hit_frame_flags": hit_frame_flags,
        "ko_events": ko_events,
        "fighters": fighters,
        "n_fighters": n_fighters,
        "icon_size": icon_size,
        "winner_idx": winner_idx,
        "winner_name": fighters[winner_idx]["name"],
        "loser_names": loser_names,
        "is_comeback": is_comeback,
        "is_double_ko": is_double_ko,
        "fps": fps,
        "w": w,
        "h": h,
        "arena": (left_arena, top_arena, right_arena, bottom_arena),
        "finale_start": len(frames) - finale_frames,
        "replay_range": replay_range,
        "replay_focus": replay_focus,
        "obstacles": obstacles,
        "obstacle_radius": obstacle_radius,
        "seed": seed,
    }


# --- Arena / background themes ---------------------------------------------
# Purely code-generated (gradient + grid tint + drifting glow particles) so
# every upload can look different with zero extra assets. Picked from a hash
# of the battle seed, independent of the physics RNG stream.

ARENA_THEMES = [
    {"name": "Midnight Arena", "top": (14, 12, 26), "bottom": (4, 4, 10), "grid": (255, 255, 255, 12), "border": (90, 90, 110, 255), "particle": (150, 150, 210)},
    {"name": "Neon City", "top": (42, 8, 52), "bottom": (10, 2, 16), "grid": (255, 70, 210, 20), "border": (210, 70, 230, 255), "particle": (255, 90, 220)},
    {"name": "Lava Pit", "top": (48, 10, 4), "bottom": (14, 4, 2), "grid": (255, 130, 45, 18), "border": (235, 100, 35, 255), "particle": (255, 150, 60)},
    {"name": "Ice Cave", "top": (6, 26, 40), "bottom": (2, 8, 14), "grid": (150, 220, 255, 20), "border": (130, 205, 245, 255), "particle": (190, 235, 255)},
    {"name": "Cyber Grid", "top": (4, 18, 9), "bottom": (2, 4, 4), "grid": (60, 255, 130, 24), "border": (60, 225, 115, 255), "particle": (90, 255, 150)},
    {"name": "Deep Space", "top": (6, 4, 28), "bottom": (2, 2, 9), "grid": (150, 150, 255, 12), "border": (120, 110, 225, 255), "particle": (205, 205, 255)},
    {"name": "Toxic Lab", "top": (10, 34, 6), "bottom": (3, 10, 2), "grid": (155, 255, 65, 18), "border": (145, 235, 55, 255), "particle": (175, 255, 85)},
    {"name": "Sunset Coliseum", "top": (48, 16, 27), "bottom": (14, 4, 10), "grid": (255, 165, 125, 16), "border": (235, 125, 155, 255), "particle": (255, 175, 135)},
    {"name": "Volcanic Forge", "top": (30, 4, 4), "bottom": (8, 2, 2), "grid": (255, 90, 30, 20), "border": (255, 60, 20, 255), "particle": (255, 120, 40)},
    {"name": "Frozen Peak", "top": (10, 14, 34), "bottom": (3, 5, 12), "grid": (200, 220, 255, 18), "border": (170, 200, 250, 255), "particle": (220, 235, 255)},
]


def pick_arena_theme(seed):
    theme_rng = random.Random(hashlib.sha256((str(seed) + "arena").encode()).hexdigest())
    return theme_rng.choice(ARENA_THEMES)


# Small wording variety for on-screen text that would otherwise read
# identically in every single upload (the KO burst label and the finale
# banner) — picked once per battle from a hash of the seed, independent of
# the physics RNG stream, same pattern as the arena theme.

WIN_TEXT_TEMPLATES = [
    "{name} WINS!",
    "{name} TAKES IT!",
    "{name} IS VICTORIOUS!",
    "{name} SURVIVES!",
    "{name} DOMINATES!",
]

KO_TEXT_TEMPLATES = [
    "{name} OUT!",
    "{name} ELIMINATED!",
    "{name} DOWN!",
    "{name} DEFEATED!",
]

COMEBACK_WIN_TEMPLATES = [
    "{name} COMEBACK VICTORY!",
    "{name} SURVIVES THE COMEBACK!",
    "{name} CLAWS BACK TO WIN!",
]

DOUBLE_KO_TEMPLATES = [
    "DOUBLE KO!",
    "MUTUAL DESTRUCTION!",
    "BOTH GO DOWN!",
]

FIGHT_WORD_TEMPLATES = ["FIGHT!", "CLASH!", "BEGIN!", "GO!"]

REPLAY_TEXT_TEMPLATES = ["REPLAY", "RUN IT BACK", "SLOW-MO", "ONE MORE TIME"]


def _pick_variant(seed, salt, templates):
    rng = random.Random(hashlib.sha256((str(seed) + salt).encode()).hexdigest())
    return rng.choice(templates)


# Which impact-visual style a clash gets, chosen from the two materials
# involved (lower priority number "wins" — metal/mechanical read as the most
# visually punchy, so they dominate a mixed-material hit).
_IMPACT_PRIORITY = {"metal": 0, "mechanical": 0, "blunt": 1, "wood": 2, "whip": 3}


def _impact_style(mat_a, mat_b):
    chosen = mat_a if _IMPACT_PRIORITY.get(mat_a, 0) <= _IMPACT_PRIORITY.get(mat_b, 0) else mat_b
    return "metal" if chosen == "mechanical" else chosen


def _make_ambient_particles(seed, count, w, h):
    rng = random.Random(hashlib.sha256((str(seed) + "ambient").encode()).hexdigest())
    particles = []
    for _ in range(count):
        depth = rng.random()
        particles.append({
            "x": rng.uniform(0, w), "y": rng.uniform(0, h),
            "r": 1.5 + depth * 4.5, "depth": depth,
            "phase": rng.uniform(0, 6.28318), "drift_x": rng.uniform(-4, 4),
        })
    return particles


# --- Rendering -------------------------------------------------------------

DANGER_HP_FRAC = 0.25


def _hp_bar(draw, x0, y0, x1, y1, frac, color, danger_pulse=0.0):
    draw.rounded_rectangle([x0, y0, x1, y1], radius=6, fill=(40, 40, 48, 230))
    frac = max(0.0, min(1.0, frac))
    if frac > 0:
        bx1 = x0 + (x1 - x0) * frac
        draw.rounded_rectangle([x0, y0, bx1, y1], radius=6, fill=(*color, 255))
    # Low-HP danger cue: a pulsing red outline once a fighter drops below
    # DANGER_HP_FRAC, building tension ahead of a possible KO.
    if 0 < frac < DANGER_HP_FRAC and danger_pulse > 0:
        alpha = int(90 + 140 * danger_pulse)
        pad = 3 + 2 * danger_pulse
        draw.rounded_rectangle([x0 - pad, y0 - pad, x1 + pad, y1 + pad], radius=8, outline=(255, 40, 40, alpha), width=3)


def build_battle_clip(battle):
    """Returns a moviepy VideoClip rendering the precomputed battle log."""
    from moviepy import VideoClip

    w, h, fps = battle["w"], battle["h"], battle["fps"]
    frames = battle["frames"]
    fighters = battle["fighters"]
    n = battle["n_fighters"]
    icon_size = battle["icon_size"]
    left, top, right, bottom = battle["arena"]
    finale_start = battle["finale_start"]

    icons = [make_icon(f["kind"], f["color"], icon_size) for f in fighters]
    ko_frame_by_idx = {i: frame for (frame, i, _, _) in battle["ko_events"]}
    first_hit_frame = min(battle["hit_frame_flags"].keys()) if battle["hit_frame_flags"] else None
    FIRST_BLOOD_FRAMES = int(fps * 0.9)

    font_scale = {2: 1.0, 3: 0.84, 4: 0.70}[n]
    title_font = get_font(int(h * 0.036 * font_scale))
    hp_font = get_font(max(14, int(h * 0.022 * font_scale)))
    win_font = get_font(int(h * 0.055))
    dmg_font = get_font(int(h * 0.026))
    first_blood_font = get_font(int(h * 0.048))
    count_font = get_font(int(h * 0.11))
    ko_font = get_font(int(h * 0.026))
    replay_font = get_font(int(h * 0.038))

    underdog_font = get_font(int(h * 0.026))
    max_power = max(f["power"] for f in fighters)
    underdog_idx = {i for i, f in enumerate(fighters) if f["power"] <= max_power * 0.75}

    replay_range = battle.get("replay_range")
    replay_focus = battle.get("replay_focus") or (w / 2, h / 2)
    REPLAY_ZOOM = 1.18

    # Gentle continuous "camera" for the main fight: a slow, heavily-smoothed
    # pan/zoom toward wherever the action currently is, instead of a static
    # wide shot for the whole fight. Precomputed once (not per make_frame
    # call) via an EMA over the alive fighters' centroid, since moviepy may
    # call make_frame out of order and a per-call running average wouldn't
    # be safe.
    MAIN_ZOOM = 1.07
    CAMERA_SMOOTH = 0.05
    HUD_MARGIN = int(h * 0.20)  # title + HP bar row always stays crisp/un-zoomed
    camera_centers = []
    _prev_center = None
    for fr in frames:
        alive_xy = [fr["pos"][i][:2] for i in range(n) if fr["alive"][i]] or [fr["pos"][i][:2] for i in range(n)]
        cx = sum(p[0] for p in alive_xy) / len(alive_xy)
        cy = sum(p[1] for p in alive_xy) / len(alive_xy)
        if _prev_center is None:
            _prev_center = (cx, cy)
        else:
            _prev_center = (
                _prev_center[0] + CAMERA_SMOOTH * (cx - _prev_center[0]),
                _prev_center[1] + CAMERA_SMOOTH * (cy - _prev_center[1]),
            )
        camera_centers.append(_prev_center)

    theme = pick_arena_theme(battle.get("seed", 0))
    ambient_particles = _make_ambient_particles(battle.get("seed", 0), 16, w, h)
    if battle.get("is_double_ko"):
        win_text_template = _pick_variant(battle.get("seed", 0), "wintext", DOUBLE_KO_TEMPLATES)
    elif battle.get("is_comeback"):
        win_text_template = _pick_variant(battle.get("seed", 0), "wintext", COMEBACK_WIN_TEMPLATES)
    else:
        win_text_template = _pick_variant(battle.get("seed", 0), "wintext", WIN_TEXT_TEMPLATES)
    ko_text_template = _pick_variant(battle.get("seed", 0), "kotext", KO_TEXT_TEMPLATES)
    fight_word = _pick_variant(battle.get("seed", 0), "fightword", FIGHT_WORD_TEMPLATES)
    replay_text = _pick_variant(battle.get("seed", 0), "replaytext", REPLAY_TEXT_TEMPLATES)

    obstacles = battle.get("obstacles") or []
    obstacle_radius = battle.get("obstacle_radius", 0)
    obstacle_icon = make_obstacle_icon(obstacle_radius, theme["border"][:3]) if obstacles else None

    grad = np.zeros((h, w, 3), dtype=np.uint8)
    for ch in range(3):
        grad[:, :, ch] = np.linspace(theme["top"][ch], theme["bottom"][ch], h).astype(np.uint8)[:, None]
    base_bg = Image.fromarray(grad, mode="RGB")

    title_text = " vs ".join(f["name"] for f in fighters)
    n_frames = len(frames)

    intro_frames = int(INTRO_SECONDS * fps)
    TRAIL_STEPS = ((3, 90), (6, 55), (9, 25))  # (frames back, alpha)
    KO_FADE_FRAMES = 12

    def _det_jitter(nn):
        x = math.sin(nn * 12.9898) * 43758.5453
        return x - math.floor(x)

    def _tinted(icon, alpha_mult):
        ghost = icon.copy()
        a = ghost.split()[3].point(lambda p: int(p * alpha_mult))
        ghost.putalpha(a)
        return ghost

    # HP bar row geometry: N equal-width bars across the top
    bar_area_x0, bar_area_x1 = w * 0.05, w * 0.95
    bar_gap = w * 0.02
    bar_w = (bar_area_x1 - bar_area_x0 - bar_gap * (n - 1)) / n
    bar_h = h * 0.020
    bar_y = h * 0.115
    bar_xs = [bar_area_x0 + i * (bar_w + bar_gap) for i in range(n)]

    # Entrance animation: instead of sitting frozen during "3-2-1", each
    # fighter flies in from off-screen (outward along the same direction
    # they already spawn on) and spins to a stop by the time "FIGHT!" hits —
    # gives the first 3 seconds, which matter most for Shorts retention,
    # actual motion instead of a static card.
    arena_cx, arena_cy = (left + right) / 2, (top + bottom) / 2
    entry_start = []
    entry_spin = []
    entry_rng = random.Random(hashlib.sha256((str(battle.get("seed", 0)) + "entry").encode()).hexdigest())
    for i in range(n):
        fx0, fy0, _ = frames[0]["pos"][i]
        dx, dy = fx0 - arena_cx, fy0 - arena_cy
        dist = math.hypot(dx, dy) or 1.0
        ux, uy = dx / dist, dy / dist
        offscreen = max(w, h) * 0.75
        entry_start.append((fx0 + ux * offscreen, fy0 + uy * offscreen))
        entry_spin.append(entry_rng.choice([-1, 1]) * entry_rng.uniform(420, 720))
    ENTRY_ARRIVE_FRAC = 0.7  # arrives/settles a bit before the countdown ends

    def _intro_state(raw_idx):
        ease_t = min(1.0, (raw_idx / max(1, intro_frames)) / ENTRY_ARRIVE_FRAC)
        ease = 1 - (1 - ease_t) ** 3
        pos = []
        for i in range(n):
            fx0, fy0, fang0 = frames[0]["pos"][i]
            sx, sy = entry_start[i]
            x = sx + (fx0 - sx) * ease
            y = sy + (fy0 - sy) * ease
            ang = fang0 + entry_spin[i] * (1 - ease)
            pos.append((x, y, ang))
        return {"pos": pos, "hp": frames[0]["hp"], "alive": frames[0]["alive"]}

    def make_frame(t):
        raw_idx = int(round(t * fps))
        in_intro = raw_idx < intro_frames
        idx = 0 if in_intro else min(n_frames - 1, raw_idx - intro_frames)
        st = _intro_state(raw_idx) if in_intro else frames[idx]
        img = base_bg.copy().convert("RGBA")
        d = ImageDraw.Draw(img, "RGBA")

        for p in ambient_particles:
            speed = 8 + p["depth"] * 30
            py = (p["y"] - t * speed) % (h * 1.1)
            px = (p["x"] + p["drift_x"] * t + 8 * math.sin(t * 0.5 + p["phase"])) % w
            twinkle = 0.5 + 0.5 * math.sin(t * 1.8 + p["phase"])
            alpha = int(30 + 70 * p["depth"] * twinkle)
            r = p["r"]
            d.ellipse([px - r, py - r, px + r, py + r], fill=(*theme["particle"], alpha))

        d.rounded_rectangle([left, top, right, bottom], radius=18, outline=theme["border"], width=4)
        for gx in range(left, right, int(w * 0.09)):
            d.line([(gx, top), (gx, bottom)], fill=theme["grid"], width=1)
        for gy in range(top, bottom, int(w * 0.09)):
            d.line([(left, gy), (right, gy)], fill=theme["grid"], width=1)

        if obstacle_icon is not None:
            for (ox, oy) in obstacles:
                img.alpha_composite(obstacle_icon, (int(ox - obstacle_icon.width / 2), int(oy - obstacle_icon.height / 2)))

        tw = d.textlength(title_text, font=title_font)
        d.text((w / 2 - tw / 2, h * 0.045), title_text, font=title_font, fill=(255, 255, 255, 255))

        danger_pulse = 0.5 + 0.5 * math.sin(t * 9.0)
        for i, f in enumerate(fighters):
            bx0 = bar_xs[i]
            _hp_bar(d, bx0, bar_y, bx0 + bar_w, bar_y + bar_h, st["hp"][i] / START_HP, f["color"], danger_pulse)
            label = f"{f['name']}  {int(st['hp'][i])}"
            lw = d.textlength(label, font=hp_font)
            lx = min(max(bx0, bx0 + bar_w / 2 - lw / 2), bar_area_x1 - lw)
            d.text((lx, bar_y + bar_h + h * 0.008), label, font=hp_font, fill=(*f["color"], 255))

        flash_alpha, flash_xy, flash_style = 0, None, "metal"
        dmg_popup = None
        shake_dx = shake_dy = 0.0
        punch_age = {}  # fighter_idx -> frames since a hit they were part of
        if not in_intro:
            for hi in range(max(0, idx - 10), idx + 1):
                if hi not in battle["hit_frame_flags"]:
                    continue
                hx, hy, dmg, hi1, hi2 = battle["hit_frame_flags"][hi]
                age = idx - hi
                if age <= 4:
                    a = max(0, int(230 * (1 - age / 4.0)))
                    if a > flash_alpha:
                        flash_alpha, flash_xy = a, (hx, hy)
                        flash_style = _impact_style(fighters[hi1]["material"], fighters[hi2]["material"])
                if age <= 10:
                    pa = max(0, int(255 - age * 26))
                    if dmg_popup is None or age < dmg_popup[2]:
                        dmg_popup = (hx, hy - age * 3.2, age, pa, dmg)
                if age <= 5:
                    amt = max(0.0, (5 - age)) * min(7.0, dmg / 18)
                    shake_dx = (_det_jitter(hi) * 2 - 1) * amt
                    shake_dy = (_det_jitter(hi + 4096) * 2 - 1) * amt
                if age <= 4:
                    for fi in (hi1, hi2):
                        if fi not in punch_age or age < punch_age[fi]:
                            punch_age[fi] = age

        first_blood_age = idx - first_hit_frame if (not in_intro and first_hit_frame is not None) else -1
        if 0 <= first_blood_age <= FIRST_BLOOD_FRAMES:
            pop = 1.0 + 0.35 * max(0, 1 - first_blood_age / 6)
            fade_start = int(FIRST_BLOOD_FRAMES * 0.7)
            if first_blood_age < fade_start:
                fb_alpha = 255
            else:
                fb_alpha = max(0, int(255 * (1 - (first_blood_age - fade_start) / max(1, FIRST_BLOOD_FRAMES - fade_start))))
            fbf = get_font(int(first_blood_font.size * pop)) if hasattr(first_blood_font, "size") else first_blood_font
            fb_text = "FIRST BLOOD!"
            fbw = d.textlength(fb_text, font=fbf)
            d.text((w / 2 - fbw / 2, h * 0.30), fb_text, font=fbf, fill=(255, 60, 40, fb_alpha), stroke_width=4, stroke_fill=(0, 0, 0, fb_alpha))

        if not in_intro:
            for back, al in TRAIL_STEPS:
                hidx = idx - back
                if hidx < 0:
                    continue
                hst = frames[hidx]
                for i in range(n):
                    if not hst["alive"][i]:
                        continue
                    ghost = _tinted(icons[i], al / 255)
                    x, y, ang = hst["pos"][i]
                    ghost = ghost.rotate(-ang, resample=Image.BICUBIC)
                    img.alpha_composite(ghost, (int(x - icon_size / 2), int(y - icon_size / 2)))

        if flash_alpha > 0:
            fx, fy = flash_xy
            elapsed = 1.0 - flash_alpha / 230.0  # 0 = just landed, 1 = fully faded
            if flash_style == "blunt":
                # thud: an expanding shockwave ring + soft dust puffs, no
                # sharp sparks — reads as a heavy, blunt impact.
                ring_r = 14 + elapsed * 46
                d.ellipse([fx - ring_r, fy - ring_r, fx + ring_r, fy + ring_r], outline=(200, 160, 110, flash_alpha), width=4)
                for i in range(5):
                    dang = math.radians(i * 72 + (int(fx) % 30))
                    dr = 8 + elapsed * 22
                    dx, dy = fx + math.cos(dang) * dr, fy + math.sin(dang) * dr
                    pr = 7 * (1 - elapsed * 0.5)
                    d.ellipse([dx - pr, dy - pr, dx + pr, dy + pr], fill=(190, 150, 110, int(flash_alpha * 0.7)))
            elif flash_style == "wood":
                # splinters: a handful of short irregular light-brown chips
                for i in range(5):
                    ang = math.radians(i * 72 + (int(fx + fy) % 40) - 20)
                    r1, r2 = 6, 20 + flash_alpha * 0.18
                    x1, y1 = fx + math.cos(ang) * r1, fy + math.sin(ang) * r1
                    x2, y2 = fx + math.cos(ang) * r2, fy + math.sin(ang) * r2
                    d.line([(x1, y1), (x2, y2)], fill=(200, 160, 90, flash_alpha), width=3)
                d.ellipse([fx - 8, fy - 8, fx + 8, fy + 8], fill=(210, 175, 110, int(flash_alpha * 0.8)))
            elif flash_style == "whip":
                # crack: a few short curved motion-streaks + a small spark
                for i in range(3):
                    base_ang = math.radians(i * 40 - 40 + (int(fx) % 20))
                    pts = []
                    for k in range(4):
                        rr = 6 + k * 6
                        aa = base_ang + k * 0.25
                        pts.append((fx + math.cos(aa) * rr, fy + math.sin(aa) * rr))
                    d.line(pts, fill=(230, 90, 90, flash_alpha), width=3, joint="curve")
                d.ellipse([fx - 9, fy - 9, fx + 9, fy + 9], fill=(255, 220, 200, flash_alpha))
            else:
                # metal (default): bright radiating sparks + a hot core
                for i in range(8):
                    ang = math.radians(i * 45 + (int(fx + fy) % 30))
                    r1, r2 = 12, 12 + flash_alpha * 0.28
                    x1, y1 = fx + math.cos(ang) * r1, fy + math.sin(ang) * r1
                    x2, y2 = fx + math.cos(ang) * r2, fy + math.sin(ang) * r2
                    d.line([(x1, y1), (x2, y2)], fill=(255, 240, 180, flash_alpha), width=4)
                d.ellipse([fx - 16, fy - 16, fx + 16, fy + 16], fill=(255, 250, 215, flash_alpha))

        if not in_intro:
            for koi, fi, kx, ky in battle["ko_events"]:
                age = idx - koi
                if age < 0 or age > KO_FADE_FRAMES:
                    continue
                pa = max(0, int(255 * (1 - age / KO_FADE_FRAMES)))
                if pa <= 0:
                    continue
                r = 20 + age * 4
                d.ellipse([kx - r, ky - r, kx + r, ky + r], outline=(255, 80, 60, pa), width=4)
                label = ko_text_template.format(name=fighters[fi]['name'])
                lw = d.textlength(label, font=ko_font)
                d.text((kx - lw / 2, ky - r - 26), label, font=ko_font, fill=(255, 110, 90, pa), stroke_width=2, stroke_fill=(0, 0, 0, pa))

        for i in range(n):
            x, y, ang = st["pos"][i]
            if st["alive"][i]:
                rot = icons[i].rotate(-ang, resample=Image.BICUBIC)
                if i in punch_age:
                    # impact "pop": the weapon itself briefly swells right on
                    # a hit and settles back over a few frames, so the blow
                    # reads as landing on the object, not just a screen flash.
                    scale = 1.0 + 0.28 * max(0.0, 1 - punch_age[i] / 4.0)
                    if scale > 1.001:
                        pw, ph = int(rot.width * scale), int(rot.height * scale)
                        rot = rot.resize((pw, ph), Image.BICUBIC)
                img.alpha_composite(rot, (int(x - rot.width / 2), int(y - rot.height / 2)))
            else:
                ko_frame = ko_frame_by_idx.get(i)
                if ko_frame is not None:
                    age = idx - ko_frame
                    if 0 <= age < KO_FADE_FRAMES:
                        fade = 1.0 - age / KO_FADE_FRAMES
                        ghost = _tinted(icons[i], fade)
                        ghost = ghost.rotate(-ang, resample=Image.BICUBIC)
                        img.alpha_composite(ghost, (int(x - icon_size / 2), int(y - icon_size / 2)))

        if dmg_popup is not None:
            px, py, _, pa, dmg = dmg_popup
            dtext = f"-{dmg}"
            dw = d.textlength(dtext, font=dmg_font)
            d.text((px - dw / 2, py), dtext, font=dmg_font, fill=(255, 90, 70, pa), stroke_width=2, stroke_fill=(0, 0, 0, pa))

        if not in_intro and idx >= finale_start:
            prog = min(1.0, (idx - finale_start) / max(1, fps * 0.35))
            overlay = Image.new("RGBA", (w, h), (0, 0, 0, int(120 * prog)))
            img.alpha_composite(overlay)
            win_text = win_text_template.format(name=battle['winner_name'])
            scale = 0.6 + 0.4 * prog
            f = get_font(int(win_font.size * scale)) if hasattr(win_font, "size") else win_font
            tw2 = d.textlength(win_text, font=f)
            if tw2 > w * 0.92 and hasattr(f, "size"):
                f = get_font(max(24, int(f.size * (w * 0.92) / tw2)))
                tw2 = d.textlength(win_text, font=f)
            d.text((w / 2 - tw2 / 2, h * 0.5 - 40), win_text, font=f, fill=(255, 215, 60, int(255 * prog)))

            # Subscribe CTA fades in a beat after the win text lands, so the
            # banner gets a clean moment on its own first.
            hold_idx = idx - finale_start
            cta_prog = max(0.0, min(1.0, (hold_idx - fps * 0.65) / max(1, fps * 0.45)))
            if cta_prog > 0:
                cta_text = "SUBSCRIBE for more battles!"
                cta_font = get_font(int(h * 0.030))
                cw = d.textlength(cta_text, font=cta_font)
                cta_y = h * 0.5 - 40 + (win_font.size if hasattr(win_font, "size") else 100) * scale + 26
                d.text((w / 2 - cw / 2, cta_y), cta_text, font=cta_font, fill=(255, 255, 255, int(230 * cta_prog)), stroke_width=2, stroke_fill=(0, 0, 0, int(230 * cta_prog)))

        if in_intro:
            overlay = Image.new("RGBA", (w, h), (0, 0, 0, 90))
            img.alpha_composite(overlay)
            d2 = ImageDraw.Draw(img, "RGBA")
            step = min(3, int(t / (INTRO_SECONDS / 4)))
            local_t = (t % (INTRO_SECONDS / 4)) / (INTRO_SECONDS / 4)
            pop = 1.25 - 0.25 * min(1.0, local_t * 4)
            word = ["3", "2", "1", fight_word][step]
            color = (255, 210, 60, 255) if step == 3 else (255, 255, 255, 255)
            base_size = count_font.size if hasattr(count_font, "size") else 90
            f2 = get_font(int(base_size * pop * (1.0 if step < 3 else 0.75)))
            tw3 = d2.textlength(word, font=f2)
            d2.text((w / 2 - tw3 / 2, h * 0.42), word, font=f2, fill=color, stroke_width=4, stroke_fill=(0, 0, 0, 255))

            if underdog_idx:
                fade_in = min(1.0, t / (INTRO_SECONDS * 0.4))
                for i in underdog_idx:
                    ux, uy, _ = st["pos"][i]
                    tag = "UNDERDOG"
                    tw4 = d2.textlength(tag, font=underdog_font)
                    d2.text((ux - tw4 / 2, uy - icon_size / 2 - 34), tag, font=underdog_font,
                             fill=(255, 130, 40, int(255 * fade_in)), stroke_width=2, stroke_fill=(0, 0, 0, int(255 * fade_in)))

        in_replay = replay_range is not None and replay_range[0] <= idx < replay_range[1]
        if in_replay:
            fx, fy = replay_focus
            crop_w, crop_h = w / REPLAY_ZOOM, h / REPLAY_ZOOM
            cx0 = min(max(0.0, fx - crop_w / 2), w - crop_w)
            cy0 = min(max(0.0, fy - crop_h / 2), h - crop_h)
            img = img.crop((int(cx0), int(cy0), int(cx0 + crop_w), int(cy0 + crop_h))).resize((w, h), Image.BICUBIC)
            d3 = ImageDraw.Draw(img, "RGBA")
            pulse = 0.65 + 0.35 * math.sin(t * 11)
            rtxt = replay_text
            rw = d3.textlength(rtxt, font=replay_font)
            d3.text((w / 2 - rw / 2, h * 0.185), rtxt, font=replay_font, fill=(255, 255, 255, int(255 * pulse)), stroke_width=3, stroke_fill=(200, 30, 30, 255))
        elif not in_intro and idx < finale_start:
            # Zoom/pan only the arena region — the title + HP bar strip above
            # it is pasted back untouched so it never gets cropped or blurred
            # by the camera drift. Frozen once the finale banner appears, so
            # the already-fitted win-text isn't re-scaled/re-panned by a
            # zoom applied on top of it.
            fx, fy = camera_centers[idx]
            region_h = h - HUD_MARGIN
            crop_w, crop_h = w / MAIN_ZOOM, region_h / MAIN_ZOOM
            cx0 = min(max(0.0, fx - crop_w / 2), w - crop_w)
            cy0 = min(max(HUD_MARGIN, fy - crop_h / 2), h - crop_h)
            sub = img.crop((int(cx0), int(cy0), int(cx0 + crop_w), int(cy0 + crop_h))).resize((w, region_h), Image.BICUBIC)
            img.paste(sub, (0, HUD_MARGIN))

        arr = np.array(img.convert("RGB"))
        if shake_dx or shake_dy:
            arr = np.roll(arr, (int(round(shake_dy)), int(round(shake_dx))), axis=(0, 1))
        return arr

    duration = (intro_frames + n_frames) / fps
    clip = VideoClip(make_frame, duration=duration).with_fps(fps)
    return clip


# --- Sound effects (fully synthesized, no external assets) ----------------

SR = 44100


def _clang_metal(intensity):
    intensity = max(0.15, min(1.0, intensity))
    dur = 0.18 + 0.05 * intensity
    n = int(SR * dur)
    t = np.linspace(0, dur, n, endpoint=False)
    freqs = [1200, 1800, 2600]
    env = np.exp(-t * (18 - 6 * intensity))
    tone = sum(np.sin(2 * np.pi * f * t) for f in freqs) / len(freqs)
    noise = (np.random.default_rng(int(intensity * 1000)).uniform(-1, 1, n)) * np.exp(-t * 45)
    sfx = (tone * 0.75 + noise * 0.5) * env * intensity
    return sfx.astype(np.float32)


def _thud_blunt(intensity):
    """Heavy weapons (hammer, mace, flail...): low-pitched boom, more punch,
    almost no metallic ring."""
    intensity = max(0.15, min(1.0, intensity))
    dur = 0.22 + 0.05 * intensity
    n = int(SR * dur)
    t = np.linspace(0, dur, n, endpoint=False)
    env = np.exp(-t * (13 - 4 * intensity))
    tone = sum(np.sin(2 * np.pi * f * t) for f in (85, 135)) / 2
    punch = np.sin(2 * np.pi * 55 * t) * np.exp(-t * 55)
    noise = np.random.default_rng(int(intensity * 777)).uniform(-1, 1, n) * np.exp(-t * 35) * 0.3
    sfx = (tone * 0.6 + punch * 0.55 + noise) * env * intensity
    return sfx.astype(np.float32)


def _clack_wood(intensity):
    """Nunchaku/staff: short, dry mid-frequency knock."""
    intensity = max(0.15, min(1.0, intensity))
    dur = 0.10 + 0.02 * intensity
    n = int(SR * dur)
    t = np.linspace(0, dur, n, endpoint=False)
    env = np.exp(-t * 42)
    tone = sum(np.sin(2 * np.pi * f * t) for f in (600, 950)) / 2
    sfx = tone * env * intensity
    return sfx.astype(np.float32)


def _crack_whip(intensity):
    """Whip: very short broadband snap, almost no tonal body."""
    intensity = max(0.15, min(1.0, intensity))
    dur = 0.08
    n = int(SR * dur)
    t = np.linspace(0, dur, n, endpoint=False)
    env = np.exp(-t * 70)
    noise = np.random.default_rng(int(intensity * 333)).uniform(-1, 1, n)
    snap = np.sin(2 * np.pi * 3200 * t) * np.exp(-t * 160)
    sfx = (noise * 0.8 + snap * 0.5) * env * intensity
    return sfx.astype(np.float32)


def _buzz_mechanical(intensity):
    """Chainsaw: a short grinding buzz instead of a single impact."""
    intensity = max(0.15, min(1.0, intensity))
    dur = 0.20 + 0.04 * intensity
    n = int(SR * dur)
    t = np.linspace(0, dur, n, endpoint=False)
    env = np.exp(-t * 9)
    buzz = np.sign(np.sin(2 * np.pi * 140 * t)) * 0.5
    grind = np.sin(2 * np.pi * 260 * t) * 0.3
    noise = np.random.default_rng(int(intensity * 555)).uniform(-1, 1, n) * 0.45
    sfx = (buzz + grind + noise) * env * intensity
    return sfx.astype(np.float32)


MATERIAL_SFX = {
    "metal": _clang_metal,
    "blunt": _thud_blunt,
    "wood": _clack_wood,
    "whip": _crack_whip,
    "mechanical": _buzz_mechanical,
}


def _hit_sound(material_a, material_b, intensity):
    a = MATERIAL_SFX.get(material_a, _clang_metal)(intensity)
    b = MATERIAL_SFX.get(material_b, _clang_metal)(intensity)
    n = max(len(a), len(b))
    out = np.zeros(n, dtype=np.float32)
    out[: len(a)] += a * (0.75 if material_a != material_b else 1.0)
    out[: len(b)] += b * (0.75 if material_a != material_b else 1.0)
    return out


def _victory_chime():
    notes = [523.25, 659.25, 783.99]
    parts = []
    for f in notes:
        dur = 0.22
        n = int(SR * dur)
        t = np.linspace(0, dur, n, endpoint=False)
        env = np.exp(-t * 4)
        parts.append(np.sin(2 * np.pi * f * t) * env * 0.5)
    gap = np.zeros(int(SR * 0.05), dtype=np.float32)
    out = []
    for p in parts:
        out.append(p.astype(np.float32))
        out.append(gap)
    return np.concatenate(out)


def _beep(freq, dur=0.12, vol=0.5):
    n = int(SR * dur)
    t = np.linspace(0, dur, n, endpoint=False)
    env = np.exp(-t * 9)
    return (np.sin(2 * np.pi * freq * t) * env * vol).astype(np.float32)


def _fight_horn():
    a = _beep(520, 0.22, 0.75)
    b = _beep(940, 0.26, 0.6)
    n = max(len(a), len(b))
    out = np.zeros(n, dtype=np.float32)
    out[: len(a)] += a
    out[: len(b)] += b
    return out


def build_sfx_array(battle):
    """Renders the countdown beeps + all clash + victory sounds into one
    stereo float32 array. Timeline matches build_battle_clip's video exactly:
    INTRO_SECONDS of countdown first, then the battle itself."""
    fps = battle["fps"]
    duration = INTRO_SECONDS + len(battle["frames"]) / fps
    n_samples = int(duration * SR) + SR
    buf = np.zeros(n_samples, dtype=np.float32)

    def _add(t, sfx, vol=1.0):
        pos = int(t * SR)
        end = min(n_samples, pos + len(sfx))
        if end > pos:
            buf[pos:end] += sfx[: end - pos] * vol

    quarter = INTRO_SECONDS / 4
    for i in range(3):
        _add(i * quarter, _beep(700, 0.10, 0.55))
    _add(3 * quarter, _fight_horn())

    fighters = battle["fighters"]
    dmgs = [dmg for (_, _, dmg, _, _) in battle["hit_frame_flags"].values()]
    max_dmg = max(dmgs) if dmgs else 1.0

    for frame_idx, (_, _, dmg, i1, i2) in battle["hit_frame_flags"].items():
        t = INTRO_SECONDS + frame_idx / fps
        mat_a = fighters[i1]["material"]
        mat_b = fighters[i2]["material"]
        _add(t, _hit_sound(mat_a, mat_b, dmg / max(1.0, max_dmg)))

    finale_t = INTRO_SECONDS + battle["finale_start"] / fps
    _add(finale_t, _victory_chime(), vol=0.9)

    peak = np.max(np.abs(buf)) or 1.0
    buf = (buf / peak) * 0.85
    stereo = np.stack([buf, buf], axis=1)
    return stereo, SR


def battle_seed_text():
    return hashlib.sha256(str(random.random()).encode()).hexdigest()


# --- Custom thumbnail (1280x720) -------------------------------------------
# Built from the exact same theme/icons as the video itself, so the
# thumbnail isn't a mismatched Canva template — it's a "poster" for the
# specific battle that was just generated.

def generate_thumbnail(battle, output_path, w=1280, h=720):
    theme = pick_arena_theme(battle.get("seed", 0))
    fighters = battle["fighters"]
    n = battle["n_fighters"]

    grad = np.zeros((h, w, 3), dtype=np.uint8)
    for ch in range(3):
        grad[:, :, ch] = np.linspace(theme["top"][ch], theme["bottom"][ch], w).astype(np.uint8)[None, :]
    img = Image.fromarray(grad, mode="RGB").convert("RGBA")

    glow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse([w * 0.30, -h * 0.35, w * 0.70, h * 0.75], fill=(*theme["particle"], 90))
    glow = glow.filter(ImageFilter.GaussianBlur(90))
    img = Image.alpha_composite(img, glow)

    d = ImageDraw.Draw(img, "RGBA")
    vs_font = get_font(int(h * 0.24))
    title_font = get_font(int(h * 0.075))

    if n == 2:
        icon_size = int(h * 0.66)
        left_icon = make_icon(fighters[0]["kind"], fighters[0]["color"], icon_size).rotate(18, resample=Image.BICUBIC, expand=True)
        right_icon = make_icon(fighters[1]["kind"], fighters[1]["color"], icon_size).rotate(-18, resample=Image.BICUBIC, expand=True)
        img.alpha_composite(left_icon, (int(w * 0.03), int(h / 2 - left_icon.height / 2)))
        img.alpha_composite(right_icon, (int(w * 0.97 - right_icon.width), int(h / 2 - right_icon.height / 2)))

        vs_text = "VS"
        tw = d.textlength(vs_text, font=vs_font)
        d.text((w / 2 - tw / 2, h * 0.30), vs_text, font=vs_font, fill=(255, 215, 60, 255), stroke_width=8, stroke_fill=(0, 0, 0, 255))

        title_text = f"{fighters[0]['name']} vs {fighters[1]['name']}"
    else:
        icon_size = int(h * (0.42 if n == 3 else 0.36))
        icons = [make_icon(f["kind"], f["color"], icon_size) for f in fighters]
        gap = w * 0.02
        total_w = sum(ic.width for ic in icons) + gap * (n - 1)
        x = (w - total_w) / 2
        for ic in icons:
            img.alpha_composite(ic, (int(x), int(h * 0.52 - ic.height / 2)))
            x += ic.width + gap

        badge_text = f"{n}-WAY BATTLE"
        bf = get_font(int(h * 0.09))
        tw = d.textlength(badge_text, font=bf)
        d.text((w / 2 - tw / 2, h * 0.06), badge_text, font=bf, fill=(255, 215, 60, 255), stroke_width=6, stroke_fill=(0, 0, 0, 255))

        title_text = " vs ".join(f["name"] for f in fighters)

    tw2 = d.textlength(title_text, font=title_font)
    tw2 = min(tw2, w * 0.94)
    while d.textlength(title_text, font=title_font) > w * 0.94:
        title_font = get_font(title_font.size - 4) if hasattr(title_font, "size") else title_font
        if not hasattr(title_font, "size") or title_font.size <= 30:
            break
    tw2 = d.textlength(title_text, font=title_font)
    d.text((w / 2 - tw2 / 2, h * 0.86), title_text, font=title_font, fill=(255, 255, 255, 255), stroke_width=5, stroke_fill=(0, 0, 0, 255))

    img.convert("RGB").save(output_path, "JPEG", quality=92)
    return output_path
