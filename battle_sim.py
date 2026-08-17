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
    {"name": "Sword", "kind": "sword", "color": (225, 225, 232), "power": 1.00},
    {"name": "Katana", "kind": "katana", "color": (240, 240, 248), "power": 1.02},
    {"name": "Axe", "kind": "axe", "color": (214, 92, 68), "power": 1.15},
    {"name": "Hammer", "kind": "hammer", "color": (150, 150, 160), "power": 1.28},
    {"name": "Warhammer", "kind": "warhammer", "color": (120, 130, 150), "power": 1.38},
    {"name": "Spear", "kind": "spear", "color": (96, 206, 148), "power": 0.92},
    {"name": "Trident", "kind": "trident", "color": (70, 190, 210), "power": 0.98},
    {"name": "Dagger", "kind": "dagger", "color": (236, 205, 70), "power": 0.78},
    {"name": "Kunai", "kind": "kunai", "color": (200, 200, 210), "power": 0.72},
    {"name": "Mace", "kind": "mace", "color": (176, 100, 214), "power": 1.22},
    {"name": "Flail", "kind": "flail", "color": (210, 140, 60), "power": 1.30},
    {"name": "Nunchaku", "kind": "nunchaku", "color": (140, 90, 50), "power": 0.85},
    {"name": "Whip", "kind": "whip", "color": (180, 60, 60), "power": 0.70},
    {"name": "Scythe", "kind": "scythe", "color": (72, 190, 226), "power": 1.08},
    {"name": "Claws", "kind": "claws", "color": (230, 230, 235), "power": 0.88},
    {"name": "Chainsaw", "kind": "chainsaw", "color": (230, 190, 40), "power": 1.35},
    {"name": "Staff", "kind": "staff", "color": (170, 130, 220), "power": 0.80},
    {"name": "Shuriken", "kind": "shuriken", "color": (210, 60, 90), "power": 0.75},
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
    shadow_alpha = alpha.filter(ImageFilter.GaussianBlur(3)).point(lambda p: int(p * 0.55))
    shadow = Image.new("RGBA", (w, h), (0, 0, 0, 255))
    shadow.putalpha(shadow_alpha)
    shifted_shadow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    shifted_shadow.paste(shadow, (3, 5), shadow)
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

    return result


def make_icon(kind, color, size=170):
    return _polish_icon(_draw_icon_shape(kind, color, size))


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
        hit_log.append((step_counter["n"], cx, cy, round(d1 + d2)))
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
            _, hx, hy, dmg = hit_log[-1]
            hit_frame_flags[frame_idx - 1] = (hx, hy, dmg)

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
        "fps": fps,
        "w": w,
        "h": h,
        "arena": (left_arena, top_arena, right_arena, bottom_arena),
        "finale_start": len(frames) - finale_frames,
        "replay_range": replay_range,
        "replay_focus": replay_focus,
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

def _hp_bar(draw, x0, y0, x1, y1, frac, color):
    draw.rounded_rectangle([x0, y0, x1, y1], radius=6, fill=(40, 40, 48, 230))
    frac = max(0.0, min(1.0, frac))
    if frac > 0:
        bx1 = x0 + (x1 - x0) * frac
        draw.rounded_rectangle([x0, y0, bx1, y1], radius=6, fill=(*color, 255))


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

    font_scale = {2: 1.0, 3: 0.84, 4: 0.70}[n]
    title_font = get_font(int(h * 0.036 * font_scale))
    hp_font = get_font(max(14, int(h * 0.022 * font_scale)))
    win_font = get_font(int(h * 0.055))
    dmg_font = get_font(int(h * 0.026))
    count_font = get_font(int(h * 0.11))
    ko_font = get_font(int(h * 0.026))
    replay_font = get_font(int(h * 0.038))

    replay_range = battle.get("replay_range")
    replay_focus = battle.get("replay_focus") or (w / 2, h / 2)
    REPLAY_ZOOM = 1.18

    theme = pick_arena_theme(battle.get("seed", 0))
    ambient_particles = _make_ambient_particles(battle.get("seed", 0), 16, w, h)

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

    def make_frame(t):
        raw_idx = int(round(t * fps))
        in_intro = raw_idx < intro_frames
        idx = 0 if in_intro else min(n_frames - 1, raw_idx - intro_frames)
        st = frames[idx]
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

        tw = d.textlength(title_text, font=title_font)
        d.text((w / 2 - tw / 2, h * 0.045), title_text, font=title_font, fill=(255, 255, 255, 255))

        for i, f in enumerate(fighters):
            bx0 = bar_xs[i]
            _hp_bar(d, bx0, bar_y, bx0 + bar_w, bar_y + bar_h, st["hp"][i] / START_HP, f["color"])
            label = f"{f['name']}  {int(st['hp'][i])}"
            lw = d.textlength(label, font=hp_font)
            lx = min(max(bx0, bx0 + bar_w / 2 - lw / 2), bar_area_x1 - lw)
            d.text((lx, bar_y + bar_h + h * 0.008), label, font=hp_font, fill=(*f["color"], 255))

        flash_alpha, flash_xy = 0, None
        dmg_popup = None
        shake_dx = shake_dy = 0.0
        if not in_intro:
            for hi in range(max(0, idx - 10), idx + 1):
                if hi not in battle["hit_frame_flags"]:
                    continue
                hx, hy, dmg = battle["hit_frame_flags"][hi]
                age = idx - hi
                if age <= 4:
                    a = max(0, int(230 * (1 - age / 4.0)))
                    if a > flash_alpha:
                        flash_alpha, flash_xy = a, (hx, hy)
                if age <= 10:
                    pa = max(0, int(255 - age * 26))
                    if dmg_popup is None or age < dmg_popup[2]:
                        dmg_popup = (hx, hy - age * 3.2, age, pa, dmg)
                if age <= 5:
                    amt = max(0.0, (5 - age)) * min(7.0, dmg / 18)
                    shake_dx = (_det_jitter(hi) * 2 - 1) * amt
                    shake_dy = (_det_jitter(hi + 4096) * 2 - 1) * amt

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
                label = f"{fighters[fi]['name']} OUT!"
                lw = d.textlength(label, font=ko_font)
                d.text((kx - lw / 2, ky - r - 26), label, font=ko_font, fill=(255, 110, 90, pa), stroke_width=2, stroke_fill=(0, 0, 0, pa))

        for i in range(n):
            x, y, ang = st["pos"][i]
            if st["alive"][i]:
                rot = icons[i].rotate(-ang, resample=Image.BICUBIC)
                img.alpha_composite(rot, (int(x - icon_size / 2), int(y - icon_size / 2)))
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
            win_text = f"{battle['winner_name']} WINS!"
            scale = 0.6 + 0.4 * prog
            f = get_font(int(win_font.size * scale)) if hasattr(win_font, "size") else win_font
            tw2 = d.textlength(win_text, font=f)
            d.text((w / 2 - tw2 / 2, h * 0.5 - 40), win_text, font=f, fill=(255, 215, 60, int(255 * prog)))

        if in_intro:
            overlay = Image.new("RGBA", (w, h), (0, 0, 0, 90))
            img.alpha_composite(overlay)
            d2 = ImageDraw.Draw(img, "RGBA")
            step = min(3, int(t / (INTRO_SECONDS / 4)))
            local_t = (t % (INTRO_SECONDS / 4)) / (INTRO_SECONDS / 4)
            pop = 1.25 - 0.25 * min(1.0, local_t * 4)
            word = ["3", "2", "1", "FIGHT!"][step]
            color = (255, 210, 60, 255) if step == 3 else (255, 255, 255, 255)
            base_size = count_font.size if hasattr(count_font, "size") else 90
            f2 = get_font(int(base_size * pop * (1.0 if step < 3 else 0.75)))
            tw3 = d2.textlength(word, font=f2)
            d2.text((w / 2 - tw3 / 2, h * 0.42), word, font=f2, fill=color, stroke_width=4, stroke_fill=(0, 0, 0, 255))

        in_replay = replay_range is not None and replay_range[0] <= idx < replay_range[1]
        if in_replay:
            fx, fy = replay_focus
            crop_w, crop_h = w / REPLAY_ZOOM, h / REPLAY_ZOOM
            cx0 = min(max(0.0, fx - crop_w / 2), w - crop_w)
            cy0 = min(max(0.0, fy - crop_h / 2), h - crop_h)
            img = img.crop((int(cx0), int(cy0), int(cx0 + crop_w), int(cy0 + crop_h))).resize((w, h), Image.BICUBIC)
            d3 = ImageDraw.Draw(img, "RGBA")
            pulse = 0.65 + 0.35 * math.sin(t * 11)
            rtxt = "REPLAY"
            rw = d3.textlength(rtxt, font=replay_font)
            d3.text((w / 2 - rw / 2, h * 0.185), rtxt, font=replay_font, fill=(255, 255, 255, int(255 * pulse)), stroke_width=3, stroke_fill=(200, 30, 30, 255))

        arr = np.array(img.convert("RGB"))
        if shake_dx or shake_dy:
            arr = np.roll(arr, (int(round(shake_dy)), int(round(shake_dx))), axis=(0, 1))
        return arr

    duration = (intro_frames + n_frames) / fps
    clip = VideoClip(make_frame, duration=duration).with_fps(fps)
    return clip


# --- Sound effects (fully synthesized, no external assets) ----------------

SR = 44100


def _clang(intensity):
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

    dmgs = [dmg for (_, _, dmg) in battle["hit_frame_flags"].values()]
    max_dmg = max(dmgs) if dmgs else 1.0

    for frame_idx, (_, _, dmg) in battle["hit_frame_flags"].items():
        t = INTRO_SECONDS + frame_idx / fps
        _add(t, _clang(dmg / max(1.0, max_dmg)))

    finale_t = INTRO_SECONDS + battle["finale_start"] / fps
    _add(finale_t, _victory_chime(), vol=0.9)

    peak = np.max(np.abs(buf)) or 1.0
    buf = (buf / peak) * 0.85
    stereo = np.stack([buf, buf], axis=1)
    return stereo, SR


def battle_seed_text():
    return hashlib.sha256(str(random.random()).encode()).hexdigest()
