"""
Fully generated (code-only) weapon-vs-weapon physics battle — no stock
footage, no real weapon images, no LLM script. 2-4 weapon icons (drawn as
vector shapes) bounce inside a box under pymunk physics; every collision
knocks HP off both sides involved until only one fighter is left standing.
Video frames, HP bars, hit flashes and impact sound effects are all
synthesized from the physics log, so a battle is fully reproducible from
its `seed`.
"""
import colorsys
import hashlib
import math
import os
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
    {"name": "Whip", "kind": "whip", "color": (180, 60, 60), "power": 0.85, "material": "whip"},
    {"name": "Scythe", "kind": "scythe", "color": (72, 190, 226), "power": 1.08, "material": "metal"},
    {"name": "Claws", "kind": "claws", "color": (230, 230, 235), "power": 0.88, "material": "metal"},
    {"name": "Chainsaw", "kind": "chainsaw", "color": (230, 190, 40), "power": 1.35, "material": "mechanical"},
    {"name": "Staff", "kind": "staff", "color": (170, 130, 220), "power": 0.80, "material": "wood"},
    {"name": "Shuriken", "kind": "shuriken", "color": (210, 60, 90), "power": 0.75, "material": "metal"},
    {"name": "Rapier", "kind": "rapier", "color": (235, 235, 240), "power": 0.85, "material": "metal"},
    {"name": "Halberd", "kind": "halberd", "color": (200, 100, 60), "power": 1.20, "material": "metal"},
    {"name": "Cleaver", "kind": "cleaver", "color": (210, 90, 90), "power": 1.10, "material": "metal"},
    {"name": "Boomerang", "kind": "boomerang", "color": (190, 140, 75), "power": 0.82, "material": "wood"},
    {"name": "Pistol", "kind": "pistol", "color": (70, 70, 78), "power": 0.74, "material": "metal"},
    {"name": "Dual Daggers", "kind": "dual_daggers", "color": (255, 165, 45), "power": 0.80, "material": "metal"},
    {"name": "War Axe", "kind": "war_axe", "color": (176, 66, 48), "power": 1.11, "material": "metal"},
    {"name": "Tomahawk", "kind": "tomahawk", "color": (150, 182, 92), "power": 0.90, "material": "metal"},
]

# Physical collision-radius multiplier per weapon kind, independent of the
# "power"/mass stat — a weapon that visually reads as long (spear, whip,
# staff) gets a bigger effective hitbox and correspondingly earlier/wider
# collisions, while a compact one (dagger, kunai, shuriken) gets a smaller
# one, so a weapon's reach affects how a fight actually plays out, not just
# how it looks standing still.
WEAPON_REACH = {
    "sword": 1.00, "katana": 1.05, "axe": 0.95, "hammer": 0.85, "warhammer": 1.05,
    "spear": 1.25, "trident": 1.22, "dagger": 0.72, "kunai": 0.70, "mace": 0.85,
    "flail": 0.95, "nunchaku": 0.90, "whip": 0.95, "scythe": 1.15, "claws": 0.75,
    "chainsaw": 1.00, "staff": 1.20, "shuriken": 0.65, "rapier": 1.15,
    "halberd": 1.25, "cleaver": 0.85, "boomerang": 0.90, "pistol": 0.80,
    "dual_daggers": 0.80, "war_axe": 1.05, "tomahawk": 0.82,
}

# Per-material collision feel: metal stays crisp/springy (near-elastic,
# slick), blunt weapons absorb more energy and grip harder (a heavy dull
# thud that transfers more spin than bounce-back), wood sits in between,
# and whip is the floppiest/least bouncy of all — the periodic "lunge"
# impulse re-injects energy regardless, so a fight never actually stalls
# even though lower-elasticity materials bleed energy faster between hits.
_MATERIAL_PHYSICS = {
    "metal": {"elasticity": 1.00, "friction": 0.20},
    "mechanical": {"elasticity": 0.92, "friction": 0.34},
    "blunt": {"elasticity": 0.78, "friction": 0.38},
    "wood": {"elasticity": 0.90, "friction": 0.30},
    "whip": {"elasticity": 0.70, "friction": 0.44},
}

# --- Segmented hitboxes (viewer feedback: "all damage is done through
# contact and is predetermined, both weapons get damaged each time which is
# pointless") -----------------------------------------------------------
# Every fighter's main body circle is only ever a "body" (handle/guard)
# collision shape — it never deals real damage on its own, it just bounces.
# Real damage is only dealt by a small extra "active" shape placed at the
# weapon's actual cutting/striking part (blade tip, hammer head, axe edge,
# ...), offset from body center in LOCAL space as a fraction of the
# fighter's own collision radius. Offset convention: (0, -f) sits toward the
# icon's drawn tip (small local-y = "up"), matching icon.rotate(-angle)'s
# render convention 1:1 (verified in round 20 by cross-checking
# body.local_to_world against the equivalent PIL rotation) — a positive x
# offset swings the zone out to one side, used for asymmetric blades like
# the Axe. Multiple entries = multiple independent damage points on one
# weapon (e.g. Halberd's spike tip + its side blade).
#
# To add a new weapon class: add a WEAPON_POOL entry + WEAPON_REACH +
# material physics fallback (existing per-material defaults apply if the
# material is already known) + one ACTIVE_ZONES entry (or add the kind to
# WHOLE_BODY_ACTIVE_KINDS for a thrown/all-edge weapon, or CHAIN_WEAPON_KINDS
# inside simulate_battle for a flexible weapon) + an icon draw case. No
# other engine code needs to change — a ranged weapon follows the Pistol's
# existing separate projectile subsystem instead of/alongside a melee zone.
# NOTE: offset + radius must exceed 1.0 (the main body's own collision
# radius) or the zone is a dead letter — a circle fully contained inside the
# bigger main-body circle can never be the shape that actually reaches an
# opponent first, since the main circle's boundary is farther out in every
# direction than a contained zone can ever be. Every entry below pokes past
# the body silhouette by a real margin so it can independently register a
# hit when the weapon is aimed tip-first at an opponent, while a graze from
# any other angle still only offers up the plain body/guard circle.
ACTIVE_ZONES = {
    "sword": [(0, -0.72, 0.46)],
    "katana": [(0, -0.72, 0.46)],
    "dagger": [(0, -0.72, 0.46)],
    "kunai": [(0, -0.72, 0.46)],
    "cleaver": [(0, -0.62, 0.56)],
    "rapier": [(0, -0.90, 0.38)],
    "hammer": [(0, -0.58, 0.62)],
    "warhammer": [(0, -0.55, 0.68)],
    "mace": [(0, -0.58, 0.62)],
    "axe": [(0.28, -0.59, 0.55)],
    "halberd": [(0, -0.85, 0.43), (0.26, -0.56, 0.52)],  # spike tip + blade
    "scythe": [(0.22, -0.62, 0.55)],
    "spear": [(0, -0.85, 0.43)],
    "trident": [(0, -0.85, 0.43)],
    "staff": [(0, -0.85, 0.43)],
    "claws": [(0, -0.55, 0.62)],
    "chainsaw": [(0, -0.42, 0.66)],
    "pistol": [(0, -0.68, 0.45)],
    "dual_daggers": [(-0.45, -0.62, 0.42), (0.45, -0.62, 0.42)],  # twin blades
    "war_axe": [(-0.31, -0.58, 0.46), (0.31, -0.58, 0.46)],  # double-bladed head
    "tomahawk": [(0.26, -0.60, 0.48)],  # compact single-side blade
}
# Thrown/all-edge weapons — the entire silhouette is a cutting surface, so
# the main body shape itself is "active" instead of getting a separate zone.
WHOLE_BODY_ACTIVE_KINDS = {"shuriken", "boomerang"}

# Damage multiplier when the STRIKING shape that touched an opponent was an
# "active" zone vs just the passive body/handle/guard — this is what makes
# hits asymmetric: your blade landing on their handle deals real damage,
# their handle bumping your blade does not deal damage back for free.
ACTIVE_DAMAGE_MULT = 1.15
GUARD_DAMAGE_MULT = 0.28
# Bonus for landing an active-zone hit while the victim's own colliding
# shape was passive (they weren't mid-swing with their own active zone) —
# rewards a clean, undefended hit over a mutual clash.
CLEAN_HIT_BONUS = 1.15
# Shuriken/Boomerang's WHOLE_BODY_ACTIVE_KINDS status means literally every
# collision they're in registers as an "active" strike on offense (there is
# no passive handle part to miss with), while a normal weapon frequently
# wastes a touch on its handle before its small zone lines up. That
# structural always-on advantage made them dominate the win-rate stats once
# guard/active damage split apart — this discount brings their offense back
# in line without touching their mass/knockback feel.
WHOLE_BODY_DAMAGE_DISCOUNT = 0.50

# How hard a power (mass) advantage converts into a per-hit DAMAGE advantage.
# Damage to a fighter scales with (attacker_power / victim_power) ** this.
# At 1.0 a Warhammer (1.38) vs Staff (0.80) dealt/took a ~3x damage ratio
# every exchange, which — stacked on top of the heavier body also winning the
# elastic-collision impulse and barely being knocked back — pushed heavy
# weapons to a ~62% win rate and buried light ones near 10%. Softening the
# exponent keeps "heavy hits harder" legible without making the power stat the
# whole fight. Physics feel (mass, knockback, recovery) is untouched.
POWER_DMG_EXPONENT = 0.5

# Critical hit: a real (non-block) exchange has a CRIT_CHANCE roll to land
# for CRIT_MULT x damage, with its own bigger flash/shake, a "CRITICAL!"
# callout and a layered heavier impact sound. Applied symmetrically (scales
# the whole exchange, both directions) and rolled from a dedicated RNG
# stream, so it's a pure highlight moment: ~45% of battles get at least one
# (~0.75 per battle), and tier win rates move < 2pt vs crits disabled
# (measured over 400 battles).
CRIT_CHANCE = 0.10
CRIT_MULT = 2.0

# Parry: when both fighters land with an active zone at once (a "clash"),
# PARRY_CHANCE of the time it instead reads as a clean deflection — zero
# damage, a hard symmetric shove apart, a bright double-clang and a "PARRY!"
# callout. Turns the rarest exchange type into a recognisable highlight
# without removing much damage (clashes are ~8% of hits, so this zeroes
# ~3%). A parry is never also a crit.
PARRY_CHANCE = 0.40
PARRY_KNOCK_MULT = 1.9


def _color_dist(c1, c2):
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(c1, c2)))


def _boost_color_contrast(fighters, rng):
    """Several weapons (Sword/Katana/Claws/Rapier/Kunai) share a near-white/
    silver color — fine on their own, but if two of them end up in the same
    battle, their HP bars, name labels, and motion trails become nearly
    impossible to tell apart at a glance. Nudge the hue (and raise
    saturation, since a hue rotation does nothing to a near-gray color) of
    any fighter whose color is too close to an already-placed one, so every
    fighter in a given battle reads as visually distinct. Mutates a
    battle-local copy, never the shared WEAPON_POOL entries."""
    used = []
    for f in fighters:
        color = f["color"]
        tries = 0
        while any(_color_dist(color, u) < 70 for u in used) and tries < 6:
            h, s, v = colorsys.rgb_to_hsv(*(c / 255 for c in color))
            h = (h + 0.16 + tries * 0.07) % 1.0
            s = max(s, 0.35 + tries * 0.1)
            r, g, b = colorsys.hsv_to_rgb(h, s, v)
            color = (int(r * 255), int(g * 255), int(b * 255))
            tries += 1
        f["color"] = color
        used.append(color)


WOOD = (110, 74, 40)
STEEL = (150, 150, 160)


def _wood_line(d, p1, p2, width, color=WOOD):
    """A handle/shaft line with a thin darker grain streak running beside
    it, instead of one flat color band."""
    d.line([p1, p2], fill=(*color, 255), width=width)
    dx, dy = p2[0] - p1[0], p2[1] - p1[1]
    length = math.hypot(dx, dy) or 1.0
    nx, ny = -dy / length, dx / length
    off = width * 0.22
    g1 = (p1[0] + nx * off, p1[1] + ny * off)
    g2 = (p2[0] + nx * off, p2[1] + ny * off)
    dark = tuple(max(0, c - 35) for c in color)
    d.line([g1, g2], fill=(*dark, 170), width=max(1, int(width * 0.18)))


def _metal_fuller(d, p1, p2, width, color):
    """A thin bright centerline groove down a blade, like a sword fuller —
    reads as a machined/forged blade instead of a flat triangle."""
    d.line([p1, p2], fill=(255, 255, 255, 90), width=max(1, int(width)))


def _crescent_blade(md, cx, cy, outer_r, inner_r, offset):
    """Draws a crescent-moon blade silhouette (two overlapping filled
    circles, the second cut away) onto a mask — tapered tips top and
    bottom, a convex outer cutting edge bulging out to one side. This is
    what an axe/halberd/scythe blade actually needs; a plain symmetric
    dome/pieslice reads as a mushroom or pickaxe head instead."""
    md.ellipse([cx - outer_r, cy - outer_r, cx + outer_r, cy + outer_r], fill=255)
    md.ellipse([cx - inner_r + offset, cy - inner_r, cx + inner_r + offset, cy + inner_r], fill=0)


def _gradient_fill(size, shape_fn, color, angle_deg=115, light=1.5, dark=0.5):
    """Renders whatever shape_fn(mask_draw) fills solid onto a mask, then
    composites a directional light->dark gradient through that mask —
    a real rendered-metal look for a weapon's main shape instead of one
    flat color, on top of which _polish_icon's global sheen still applies.
    Returns an RGBA image the same size as the icon canvas; alpha_composite
    it in place of the old flat `fill=c` draw call."""
    mask_img = Image.new("L", (size, size), 0)
    shape_fn(ImageDraw.Draw(mask_img))

    rad = math.radians(angle_deg)
    ux, uy = math.cos(rad), math.sin(rad)
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float32)
    proj = xx * ux + yy * uy
    pmin, pmax = proj.min(), proj.max()
    t = (proj - pmin) / max(1e-6, (pmax - pmin))

    light_c = tuple(min(255, int(c * light)) for c in color)
    dark_c = tuple(max(0, int(c * dark)) for c in color)
    grad = np.empty((size, size, 3), dtype=np.uint8)
    for ch in range(3):
        grad[:, :, ch] = (dark_c[ch] + (light_c[ch] - dark_c[ch]) * (1 - t)).astype(np.uint8)

    grad_img = Image.fromarray(grad, mode="RGB").convert("RGBA")
    grad_img.putalpha(mask_img)
    return grad_img


def _draw_icon_shape(kind, color, size=170):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    cx = size / 2
    c = (*color, 255)

    if kind == "sword":
        bw = size * 0.09
        img.alpha_composite(_gradient_fill(size, lambda md: md.polygon(
            [(cx, size * 0.05), (cx + bw, size * 0.55), (cx - bw, size * 0.55)], fill=255), color))
        _metal_fuller(d, (cx, size * 0.09), (cx, size * 0.52), max(1, int(bw * 0.25)), color)
        d.rectangle([cx - size * 0.17, size * 0.55, cx + size * 0.17, size * 0.62], fill=(*STEEL, 255))
        d.rectangle([cx - bw * 0.5, size * 0.62, cx + bw * 0.5, size * 0.85], fill=(*WOOD, 255))
        d.ellipse([cx - bw * 0.8, size * 0.83, cx + bw * 0.8, size * 0.93], fill=(*WOOD, 255))
    elif kind == "axe":
        _wood_line(d, (cx, size * 0.92), (cx, size * 0.20), int(size * 0.05))
        bcx, bcy = cx + size * 0.09, size * 0.24
        img.alpha_composite(_gradient_fill(size, lambda md: _crescent_blade(
            md, bcx, bcy, size * 0.26, size * 0.20, size * 0.155), color), (0, 0))
    elif kind == "hammer":
        _wood_line(d, (cx, size * 0.90), (cx, size * 0.36), int(size * 0.07))
        img.alpha_composite(_gradient_fill(size, lambda md: md.rounded_rectangle(
            [cx - size * 0.24, size * 0.10, cx + size * 0.24, size * 0.40], radius=int(size * 0.05), fill=255), color), (0, 0))
    elif kind == "spear":
        _wood_line(d, (cx, size * 0.95), (cx, size * 0.16), int(size * 0.045))
        img.alpha_composite(_gradient_fill(size, lambda md: md.polygon(
            [(cx, size * 0.02), (cx + size * 0.075, size * 0.24), (cx - size * 0.075, size * 0.24)], fill=255), color), (0, 0))
    elif kind == "dagger":
        bw = size * 0.065
        img.alpha_composite(_gradient_fill(size, lambda md: md.polygon(
            [(cx, size * 0.18), (cx + bw, size * 0.55), (cx - bw, size * 0.55)], fill=255), color), (0, 0))
        _metal_fuller(d, (cx, size * 0.21), (cx, size * 0.52), max(1, int(bw * 0.25)), color)
        d.rectangle([cx - size * 0.12, size * 0.55, cx + size * 0.12, size * 0.60], fill=(*STEEL, 255))
        d.rectangle([cx - bw * 0.6, size * 0.60, cx + bw * 0.6, size * 0.75], fill=(*WOOD, 255))
    elif kind == "mace":
        _wood_line(d, (cx, size * 0.92), (cx, size * 0.46), int(size * 0.06))
        img.alpha_composite(_gradient_fill(size, lambda md: md.ellipse(
            [cx - size * 0.17, size * 0.13, cx + size * 0.17, size * 0.47], fill=255), color), (0, 0))
        for ang in range(0, 360, 45):
            rad = math.radians(ang)
            x2 = cx + math.cos(rad) * size * 0.25
            y2 = size * 0.30 + math.sin(rad) * size * 0.25
            d.line([(cx, size * 0.30), (x2, y2)], fill=c, width=max(2, int(size * 0.025)))
    elif kind == "scythe":
        # A real scythe blade is a single asymmetric hook swept out to one
        # side of the pole, not a symmetric dome (a symmetric arc reads as
        # a pickaxe head instead — confirmed by viewer feedback).
        _wood_line(d, (cx, size * 0.97), (cx, size * 0.28), int(size * 0.04))
        scx, scy = cx + size * 0.12, size * 0.20
        img.alpha_composite(_gradient_fill(size, lambda md: _crescent_blade(
            md, scx, scy, size * 0.34, size * 0.28, size * 0.22), color), (0, 0))
    elif kind == "katana":
        bw = size * 0.06
        katana_pts = [
            (cx + size * 0.06, size * 0.04), (cx + bw, size * 0.30), (cx + bw * 0.4, size * 0.58),
            (cx - bw * 0.4, size * 0.58), (cx - bw * 0.3, size * 0.30),
        ]
        img.alpha_composite(_gradient_fill(size, lambda md: md.polygon(katana_pts, fill=255), color), (0, 0))
        _metal_fuller(d, (cx + size * 0.03, size * 0.08), (cx - bw * 0.35, size * 0.56), max(1, int(bw * 0.2)), color)
        d.rectangle([cx - size * 0.15, size * 0.58, cx + size * 0.15, size * 0.64], fill=(20, 20, 24, 255))
        d.rectangle([cx - bw * 0.5, size * 0.64, cx + bw * 0.5, size * 0.88], fill=(30, 30, 34, 255))
        for i in range(3):
            yy = size * (0.66 + i * 0.07)
            d.line([(cx - bw * 0.5, yy), (cx + bw * 0.5, yy + size * 0.035)], fill=(200, 200, 60, 255), width=2)
    elif kind == "warhammer":
        _wood_line(d, (cx, size * 0.94), (cx, size * 0.40), int(size * 0.09))
        img.alpha_composite(_gradient_fill(size, lambda md: md.rounded_rectangle(
            [cx - size * 0.30, size * 0.06, cx + size * 0.30, size * 0.44], radius=int(size * 0.06), fill=255), color), (0, 0))
        d.rounded_rectangle([cx - size * 0.30, size * 0.06, cx + size * 0.30, size * 0.44], radius=int(size * 0.06), outline=(40, 40, 44, 255), width=3)
        # back spike — the classic warhammer detail (flat striking face on
        # one side, a piercing spike on the other) that keeps its silhouette
        # from reading as just a bigger plain Hammer.
        spike_pts = [(cx + size * 0.30, size * 0.19), (cx + size * 0.48, size * 0.25), (cx + size * 0.30, size * 0.31)]
        img.alpha_composite(_gradient_fill(size, lambda md: md.polygon(spike_pts, fill=255), color), (0, 0))
    elif kind == "trident":
        _wood_line(d, (cx, size * 0.96), (cx, size * 0.22), int(size * 0.045))
        for off in (-0.16, 0, 0.16):
            prong_pts = [
                (cx + size * off, size * 0.02), (cx + size * off + size * 0.045, size * 0.26),
                (cx + size * off - size * 0.045, size * 0.26),
            ]
            img.alpha_composite(_gradient_fill(size, lambda md, p=prong_pts: md.polygon(p, fill=255), color), (0, 0))
        d.line([(cx - size * 0.16, size * 0.20), (cx + size * 0.16, size * 0.20)], fill=c, width=max(2, int(size * 0.02)))
    elif kind == "kunai":
        bw = size * 0.10
        img.alpha_composite(_gradient_fill(size, lambda md: md.polygon(
            [(cx, size * 0.10), (cx + bw, size * 0.46), (cx, size * 0.40), (cx - bw, size * 0.46)], fill=255), color), (0, 0))
        d.rectangle([cx - bw * 0.35, size * 0.46, cx + bw * 0.35, size * 0.78], fill=(60, 60, 66, 255))
        d.ellipse([cx - size * 0.11, size * 0.78, cx + size * 0.11, size * 0.94], outline=(60, 60, 66, 255), width=max(2, int(size * 0.025)))
    elif kind == "flail":
        _wood_line(d, (cx, size * 0.94), (cx, size * 0.62), int(size * 0.055))
        for i in range(3):
            yy = size * (0.58 - i * 0.09)
            d.ellipse([cx - size * 0.045, yy - size * 0.03, cx + size * 0.045, yy + size * 0.03], outline=(120, 120, 130, 255), width=3)
        img.alpha_composite(_gradient_fill(size, lambda md: md.ellipse(
            [cx - size * 0.16, size * 0.10, cx + size * 0.16, size * 0.42], fill=255), color), (0, 0))
        for ang in range(0, 360, 40):
            rad = math.radians(ang)
            x2 = cx + math.cos(rad) * size * 0.23
            y2 = size * 0.26 + math.sin(rad) * size * 0.23
            d.line([(cx, size * 0.26), (x2, y2)], fill=(200, 200, 205, 255), width=max(2, int(size * 0.02)))
    elif kind == "nunchaku":
        img.alpha_composite(_gradient_fill(size, lambda md: md.rounded_rectangle(
            [cx - size * 0.09, size * 0.04, cx + size * 0.09, size * 0.40], radius=int(size * 0.03), fill=255), color, angle_deg=90), (0, 0))
        img.alpha_composite(_gradient_fill(size, lambda md: md.rounded_rectangle(
            [cx - size * 0.09, size * 0.58, cx + size * 0.09, size * 0.94], radius=int(size * 0.03), fill=255), color, angle_deg=90), (0, 0))
        mid1, mid2 = (cx, size * 0.40), (cx, size * 0.58)
        d.line([mid1, ((mid1[0] + mid2[0]) / 2 + size * 0.07, (mid1[1] + mid2[1]) / 2), mid2], fill=(90, 90, 96, 255), width=max(2, int(size * 0.02)))
    elif kind == "whip":
        pts = []
        for i in range(9):
            t = i / 8
            x = cx + math.sin(t * 3.6) * size * (0.05 + t * 0.16)
            y = size * (0.06 + t * 0.78)
            pts.append((x, y))
        whip_w = max(2, int(size * 0.028))
        img.alpha_composite(_gradient_fill(size, lambda md: md.line(pts, fill=255, width=whip_w, joint="curve"), color, angle_deg=90), (0, 0))
        d.rounded_rectangle([cx - size * 0.06, size * 0.84, cx + size * 0.06, size * 0.96], radius=4, fill=(*WOOD, 255))
    elif kind == "claws":
        for off in (-0.14, 0.0, 0.14):
            claw_pts = [
                (cx + size * off, size * 0.06), (cx + size * off + size * 0.045, size * 0.52),
                (cx + size * off - size * 0.045, size * 0.52),
            ]
            img.alpha_composite(_gradient_fill(size, lambda md, p=claw_pts: md.polygon(p, fill=255), color), (0, 0))
        d.rounded_rectangle([cx - size * 0.20, size * 0.52, cx + size * 0.20, size * 0.72], radius=int(size * 0.04), fill=(70, 70, 76, 255))
    elif kind == "chainsaw":
        d.rounded_rectangle([cx - size * 0.16, size * 0.30, cx + size * 0.16, size * 0.78], radius=int(size * 0.05), fill=(70, 70, 76, 255))
        img.alpha_composite(_gradient_fill(size, lambda md: md.rounded_rectangle(
            [cx - size * 0.10, size * 0.05, cx + size * 0.10, size * 0.34], radius=int(size * 0.03), fill=255), color, angle_deg=90), (0, 0))
        for i in range(6):
            yy = size * (0.07 + i * 0.045)
            side = 1 if i % 2 == 0 else -1
            d.polygon([(cx + side * size * 0.10, yy), (cx + side * size * 0.16, yy + size * 0.02), (cx + side * size * 0.10, yy + size * 0.04)], fill=(230, 230, 235, 255))
    elif kind == "staff":
        _wood_line(d, (cx, size * 0.96), (cx, size * 0.06), int(size * 0.05))
        d.ellipse([cx - size * 0.11, size * 0.02, cx + size * 0.11, size * 0.20], outline=c, width=max(3, int(size * 0.03)))
    elif kind == "shuriken":
        pts = []
        for i in range(8):
            ang = math.radians(i * 45)
            r = size * 0.40 if i % 2 == 0 else size * 0.14
            pts.append((cx + math.cos(ang) * r, size / 2 + math.sin(ang) * r))
        img.alpha_composite(_gradient_fill(size, lambda md: md.polygon(pts, fill=255), color), (0, 0))
        d.ellipse([cx - size * 0.06, size / 2 - size * 0.06, cx + size * 0.06, size / 2 + size * 0.06], fill=(40, 40, 44, 255))
    elif kind == "rapier":
        bw = size * 0.032
        rapier_pts = [(cx, size * 0.03), (cx + bw, size * 0.62), (cx - bw, size * 0.62)]
        img.alpha_composite(_gradient_fill(size, lambda md: md.polygon(rapier_pts, fill=255), color), (0, 0))
        _metal_fuller(d, (cx, size * 0.07), (cx, size * 0.58), max(1, int(bw * 0.5)), color)
        d.polygon([(cx, size * 0.60), (cx + size * 0.10, size * 0.66), (cx, size * 0.72), (cx - size * 0.10, size * 0.66)], fill=(*STEEL, 255))
        _wood_line(d, (cx, size * 0.72), (cx, size * 0.90), int(size * 0.035))
        d.ellipse([cx - size * 0.045, size * 0.88, cx + size * 0.045, size * 0.96], fill=(*WOOD, 255))
    elif kind == "halberd":
        _wood_line(d, (cx, size * 0.97), (cx, size * 0.22), int(size * 0.05))
        hbcx, hbcy = cx + size * 0.07, size * 0.24
        img.alpha_composite(_gradient_fill(size, lambda md: _crescent_blade(
            md, hbcx, hbcy, size * 0.20, size * 0.155, size * 0.12), color), (0, 0))
        spike_pts = [(cx, size * 0.02), (cx + size * 0.06, size * 0.14), (cx - size * 0.06, size * 0.14)]
        img.alpha_composite(_gradient_fill(size, lambda md: md.polygon(spike_pts, fill=255), color), (0, 0))
    elif kind == "cleaver":
        bw = size * 0.17
        cleaver_pts = [(cx - bw, size * 0.10), (cx + bw, size * 0.10), (cx + bw * 0.75, size * 0.52), (cx - bw * 0.75, size * 0.52)]
        img.alpha_composite(_gradient_fill(size, lambda md: md.polygon(cleaver_pts, fill=255), color, angle_deg=20), (0, 0))
        d.rectangle([cx - size * 0.10, size * 0.52, cx + size * 0.10, size * 0.58], fill=(*STEEL, 255))
        _wood_line(d, (cx, size * 0.58), (cx, size * 0.86), int(size * 0.055))
    elif kind == "boomerang":
        arm1 = [(cx, size * 0.86), (cx - size * 0.34, size * 0.16), (cx - size * 0.22, size * 0.12), (cx + size * 0.03, size * 0.78)]
        arm2 = [(cx, size * 0.86), (cx + size * 0.34, size * 0.16), (cx + size * 0.22, size * 0.12), (cx - size * 0.03, size * 0.78)]
        img.alpha_composite(_gradient_fill(size, lambda md: md.polygon(arm1, fill=255), color, angle_deg=140), (0, 0))
        img.alpha_composite(_gradient_fill(size, lambda md: md.polygon(arm2, fill=255), color, angle_deg=40), (0, 0))
    elif kind == "pistol":
        # Barrel points up (this file's "tip = -Y" convention), grip angles
        # back down — a compact sidearm silhouette instead of a big blade.
        barrel_pts = [(cx - size * 0.05, size * 0.10), (cx + size * 0.05, size * 0.10),
                      (cx + size * 0.05, size * 0.40), (cx - size * 0.05, size * 0.40)]
        img.alpha_composite(_gradient_fill(size, lambda md: md.polygon(barrel_pts, fill=255), color), (0, 0))
        grip_pts = [(cx - size * 0.04, size * 0.38), (cx + size * 0.11, size * 0.38),
                    (cx + size * 0.19, size * 0.72), (cx + size * 0.01, size * 0.76)]
        img.alpha_composite(_gradient_fill(size, lambda md: md.polygon(grip_pts, fill=255), color), (0, 0))
        d.rectangle([cx - size * 0.05, size * 0.35, cx + size * 0.15, size * 0.41], fill=(20, 20, 24, 255))
        d.ellipse([cx - size * 0.045, size * 0.11, cx + size * 0.045, size * 0.16], fill=(15, 15, 18, 255))
    elif kind == "dual_daggers":
        # Two mirrored dagger blades — same blade/guard/handle construction
        # as the single Dagger, just duplicated left and right of center.
        # Widened from the first pass (bw 0.05->0.075, matching/exceeding
        # single Dagger's 0.065) — a visual audit found the original too
        # thin/spindly to clearly read as blades at battle render size.
        bw = size * 0.075
        for side in (-1, 1):
            bx = cx + side * size * 0.17
            img.alpha_composite(_gradient_fill(size, lambda md, bx=bx: md.polygon(
                [(bx, size * 0.12), (bx + bw, size * 0.52), (bx - bw, size * 0.52)], fill=255), color), (0, 0))
            _metal_fuller(d, (bx, size * 0.15), (bx, size * 0.49), max(1, int(bw * 0.25)), color)
            d.rectangle([bx - size * 0.11, size * 0.52, bx + size * 0.11, size * 0.58], fill=(*STEEL, 255))
            d.rectangle([bx - bw * 0.6, size * 0.58, bx + bw * 0.6, size * 0.84], fill=(*WOOD, 255))
    elif kind == "war_axe":
        # A double-bladed axe head: the crescent-blade formula that fixed
        # Axe's silhouette in round 19, mirrored onto both sides of the
        # shaft. First pass placed the two blade centers only 0.18*size
        # apart with a 0.26*size radius each — a visual audit found they
        # fully overlapped into a fused bowtie/hourglass blob with the
        # handle completely hidden behind them, not reading as an axe at
        # all (the exact bug class round 19 fixed for the single Axe).
        # Centers are now far enough apart (0.30*size each side) that each
        # blade's near edge clears the handle's own width, so the shaft
        # stays visible between the two blades.
        _wood_line(d, (cx, size * 0.92), (cx, size * 0.16), int(size * 0.05))
        for side in (-1, 1):
            bcx = cx + side * size * 0.30
            img.alpha_composite(_gradient_fill(size, lambda md, bcx=bcx, side=side: _crescent_blade(
                md, bcx, size * 0.22, size * 0.24, size * 0.185, side * size * 0.143), color), (0, 0))
    elif kind == "tomahawk":
        # A compact single-side hatchet: Axe's crescent blade, scaled down
        # and set lower on a shorter handle for a one-handed throwing-axe
        # silhouette instead of Axe's full two-handed size.
        _wood_line(d, (cx, size * 0.88), (cx, size * 0.32), int(size * 0.045))
        bcx, bcy = cx + size * 0.10, size * 0.30
        img.alpha_composite(_gradient_fill(size, lambda md: _crescent_blade(
            md, bcx, bcy, size * 0.22, size * 0.17, size * 0.13), color), (0, 0))
    return img


_MATERIAL_POLISH = {
    "metal": {"sheen": 95, "hi_peak": 170, "hi_width": 6.0, "hi_blur": 1.2, "rim": 190, "shadow": 0.60},
    "mechanical": {"sheen": 95, "hi_peak": 170, "hi_width": 6.0, "hi_blur": 1.2, "rim": 190, "shadow": 0.60},
    "wood": {"sheen": 35, "hi_peak": 40, "hi_width": 6.0, "hi_blur": 2.0, "rim": 90, "shadow": 0.55},
    "blunt": {"sheen": 70, "hi_peak": 110, "hi_width": 3.5, "hi_blur": 2.6, "rim": 150, "shadow": 0.68},
    "whip": {"sheen": 50, "hi_peak": 60, "hi_width": 5.0, "hi_blur": 1.8, "rim": 100, "shadow": 0.55},
}


def _polish_icon(icon, material="metal"):
    """Outline + drop shadow + diagonal light/dark shading + a material-
    tuned specular streak and rim-light, applied once per icon (not per
    frame) so any flat silhouette reads as a solid 3D object of the right
    finish (shiny metal vs matte wood vs dull stone) and pops against a
    busy arena background."""
    cfg = _MATERIAL_POLISH.get(material, _MATERIAL_POLISH["metal"])
    w, h = icon.size
    alpha = icon.split()[3]
    alpha_np = np.asarray(alpha, dtype=np.float32) / 255.0

    result = Image.new("RGBA", (w, h), (0, 0, 0, 0))

    # drop shadow: blurred + darkened silhouette, offset down-right
    shadow_alpha = alpha.filter(ImageFilter.GaussianBlur(4)).point(lambda p: int(p * cfg["shadow"]))
    shadow = Image.new("RGBA", (w, h), (0, 0, 0, 255))
    shadow.putalpha(shadow_alpha)
    shifted_shadow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    shifted_shadow.paste(shadow, (4, 6), shadow)
    result.alpha_composite(shifted_shadow)

    # soft light halo, wider than the outline below — this is what actually
    # separates the icon from same-toned dark arena backgrounds (Midnight,
    # Deep Space, Blood Moon), where a plain near-black outline on a
    # near-black backdrop nearly disappears.
    halo_alpha = alpha.filter(ImageFilter.MaxFilter(9)).filter(ImageFilter.GaussianBlur(2))
    halo = Image.new("RGBA", (w, h), (235, 238, 245, 255))
    halo.putalpha(halo_alpha.point(lambda p: int(p * 0.35)))
    result.alpha_composite(halo)

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

    sheen_a = (grad * cfg["sheen"] * alpha_np).astype(np.uint8)
    sheen = Image.new("RGBA", (w, h), (255, 255, 255, 0))
    sheen.putalpha(Image.fromarray(sheen_a, mode="L"))
    result.alpha_composite(sheen)

    shade_a = ((1.0 - grad) * 75 * alpha_np).astype(np.uint8)
    shade = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    shade.putalpha(Image.fromarray(shade_a, mode="L"))
    result.alpha_composite(shade)

    # specular streak — narrower/brighter for glossy materials (metal),
    # wider/softer for matte ones (wood, blunt stone heads).
    diag = (xx + yy) / (w + h)
    band = np.clip(1.0 - np.abs(diag - 0.26) * cfg["hi_width"], 0.0, 1.0) ** 2
    highlight_a = (band * cfg["hi_peak"] * alpha_np).astype(np.uint8)
    highlight = Image.new("RGBA", (w, h), (255, 255, 255, 0))
    highlight.putalpha(Image.fromarray(highlight_a, mode="L"))
    highlight = highlight.filter(ImageFilter.GaussianBlur(cfg["hi_blur"]))
    result.alpha_composite(highlight)

    # rim light: a thin bright edge along the lit (top-left) side of the
    # silhouette only, like light catching the edge of the object.
    eroded = alpha.filter(ImageFilter.MinFilter(3))
    ring = np.clip(np.asarray(alpha, dtype=np.float32) - np.asarray(eroded, dtype=np.float32), 0, 255) / 255.0
    rim_a = (ring * np.clip(grad, 0.0, 1.0) * cfg["rim"]).astype(np.uint8)
    rim = Image.new("RGBA", (w, h), (255, 255, 255, 0))
    rim.putalpha(Image.fromarray(rim_a, mode="L"))
    result.alpha_composite(rim)

    return result


def make_icon(kind, color, size=170, material="metal"):
    return _polish_icon(_draw_icon_shape(kind, color, size), material)


def _draw_obstacle_shape(kind, radius_px, accent_color):
    """Draws one of several obstacle silhouettes matched to an arena theme
    (jagged rock, ice shard, glowing lava rock, tech crate, bone, coral,
    gold crystal, sandstone) so the arena's static hazard reads as part of
    that theme instead of one generic rock reused everywhere."""
    size = int(radius_px * 2.5)
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    cx = cy = size / 2
    shape_rng = random.Random(42)

    if kind == "ice_shard":
        n_pts = 7
        pts = []
        for i in range(n_pts):
            ang = math.radians(-90 + i * 360 / n_pts)
            rr = radius_px * (1.15 if i % 2 == 0 else 0.5) * shape_rng.uniform(0.9, 1.05)
            pts.append((cx + math.cos(ang) * rr, cy + math.sin(ang) * rr * 1.3))
        d.polygon(pts, fill=(190, 230, 250, 220))
        for i in range(0, n_pts, 2):
            d.line([pts[i], (cx, cy - radius_px * 0.2)], fill=(255, 255, 255, 170), width=2)
        d.polygon(pts, outline=(*accent_color, 255), width=2)

    elif kind == "lava_rock":
        n_pts = 9
        pts = []
        for i in range(n_pts):
            ang = math.radians(i * 360 / n_pts)
            rr = radius_px * shape_rng.uniform(0.78, 1.0)
            pts.append((cx + math.cos(ang) * rr, cy + math.sin(ang) * rr))
        d.polygon(pts, fill=(40, 24, 20, 255))
        for i in range(0, n_pts, 2):
            d.line([pts[i], (cx, cy)], fill=(*accent_color, 220), width=3)
        d.ellipse([cx - radius_px * 0.28, cy - radius_px * 0.28, cx + radius_px * 0.28, cy + radius_px * 0.28], fill=(*accent_color, 255))

    elif kind == "tech_crate":
        r2 = radius_px * 0.82
        d.rounded_rectangle([cx - r2, cy - r2, cx + r2, cy + r2], radius=r2 * 0.15, fill=(45, 48, 52, 255))
        d.rectangle([cx - r2, cy - r2 * 0.15, cx + r2, cy + r2 * 0.15], fill=(*accent_color, 200))
        for ex, ey in [(-1, -1), (1, -1), (-1, 1), (1, 1)]:
            kx, ky = cx + ex * r2 * 0.75, cy + ey * r2 * 0.75
            d.ellipse([kx - 3, ky - 3, kx + 3, ky + 3], fill=(*accent_color, 255))

    elif kind == "bone":
        d.ellipse([cx - radius_px, cy - radius_px * 0.35, cx + radius_px, cy + radius_px * 0.35], fill=(225, 220, 205, 255))
        for sx in (-1, 1):
            kx = cx + sx * radius_px * 0.85
            d.ellipse([kx - radius_px * 0.32, cy - radius_px * 0.5, kx + radius_px * 0.32, cy + radius_px * 0.5], fill=(225, 220, 205, 255))
        d.ellipse([cx - radius_px * 0.18, cy - radius_px * 0.18, cx + radius_px * 0.18, cy + radius_px * 0.18], fill=(*accent_color, 200))

    elif kind == "coral":
        d.polygon([(cx - radius_px * 0.3, cy + radius_px), (cx + radius_px * 0.3, cy + radius_px), (cx, cy + radius_px * 0.3)], fill=(*accent_color, 255))
        for ang_deg in (-55, -20, 15, 50):
            ang = math.radians(ang_deg - 90)
            ex, ey = cx + math.cos(ang) * radius_px, cy + math.sin(ang) * radius_px
            d.line([(cx, cy + radius_px * 0.3), (ex, ey)], fill=(*accent_color, 230), width=max(3, int(radius_px * 0.18)))
            d.ellipse([ex - radius_px * 0.12, ey - radius_px * 0.12, ex + radius_px * 0.12, ey + radius_px * 0.12], fill=(*accent_color, 255))

    elif kind == "gold_crystal":
        pts = [(cx, cy - radius_px), (cx + radius_px * 0.62, cy - radius_px * 0.15), (cx + radius_px * 0.32, cy + radius_px),
               (cx - radius_px * 0.32, cy + radius_px), (cx - radius_px * 0.62, cy - radius_px * 0.15)]
        d.polygon(pts, fill=(60, 46, 10, 255))
        d.line([pts[0], (cx, cy + radius_px * 0.3)], fill=(*accent_color, 220), width=2)
        d.polygon(pts, outline=(*accent_color, 255), width=2)

    elif kind == "sand_rock":
        n_pts = 8
        pts = []
        for i in range(n_pts):
            ang = math.radians(i * 360 / n_pts)
            rr = radius_px * shape_rng.uniform(0.85, 1.0)
            pts.append((cx + math.cos(ang) * rr, cy + math.sin(ang) * rr * 0.8))
        d.polygon(pts, fill=(70, 56, 34, 255))
        for i in range(0, n_pts, 3):
            d.line([pts[i], (cx, cy)], fill=(*accent_color, 110), width=2)

    else:  # "rock" default
        n_pts = 9
        pts = []
        for i in range(n_pts):
            ang = math.radians(i * 360 / n_pts)
            rr = radius_px * shape_rng.uniform(0.78, 1.0)
            pts.append((cx + math.cos(ang) * rr, cy + math.sin(ang) * rr))
        d.polygon(pts, fill=(66, 64, 62, 255))
        for i in range(0, n_pts, 3):
            d.line([pts[i], (cx, cy)], fill=(*accent_color, 130), width=2)

    return img


_OBSTACLE_MATERIAL = {
    "rock": "blunt",
    "ice_shard": "metal",
    "lava_rock": "blunt",
    "tech_crate": "mechanical",
    "bone": "wood",
    "coral": "whip",
    "gold_crystal": "metal",
    "sand_rock": "blunt",
}

# Physical bounce feel per obstacle kind — previously every obstacle used
# the exact same elasticity=1.0/friction=0.0 regardless of what it looked
# like. Ice is slick and stays lively, tech crates are hard and springy,
# coral/bone/sand are soft/grippy and dull the bounce, matching each
# obstacle's now-distinct visual material.
_OBSTACLE_PHYSICS = {
    "rock": {"elasticity": 0.88, "friction": 0.12},
    "ice_shard": {"elasticity": 1.00, "friction": 0.03},
    "lava_rock": {"elasticity": 0.82, "friction": 0.18},
    "tech_crate": {"elasticity": 0.95, "friction": 0.08},
    "bone": {"elasticity": 0.78, "friction": 0.22},
    "coral": {"elasticity": 0.72, "friction": 0.28},
    "gold_crystal": {"elasticity": 0.98, "friction": 0.06},
    "sand_rock": {"elasticity": 0.68, "friction": 0.32},
}


def make_obstacle_icon(radius_px, accent_color, kind="rock"):
    material = _OBSTACLE_MATERIAL.get(kind, "blunt")
    return _polish_icon(_draw_obstacle_shape(kind, radius_px, accent_color), material)


# --- Fonts ---------------------------------------------------------------

_FONTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")

# Anton (SIL Open Font License, bundled in fonts/) is a bold, condensed
# "impact" display face — it's what actually makes titles/HP labels/banners
# read as a gaming channel instead of generic bold-sans UI text. The system
# fonts stay as fallbacks in case the bundled file is ever missing.
_FONT_CANDIDATES = [
    os.path.join(_FONTS_DIR, "Anton-Regular.ttf"),
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

# A "cold open" prepended before the countdown even starts: a quick punched-
# in, flash-cut freeze on the fight's finishing blow (no OUT!/victory text
# visible yet, so it teases impact without spoiling the winner), the way a
# lot of viral Shorts/Reels open on a payoff moment before rewinding to "how
# did we get here" — a first-impression hook for a viewer scrolling past in
# a muted, autoplaying feed. Shared between the video renderer and the SFX
# builder so their timelines line up, same pattern as INTRO_SECONDS.
COLD_OPEN_SECONDS = 0.9

PHYSICS_HZ = 120
START_HP = 100.0

# Fewer fighters = bigger icons/hitboxes; more fighters = smaller, so a 4-way
# melee doesn't turn into an unreadable pile in the same arena footprint.
RADIUS_BY_N = {2: 71.4, 3: 60.0, 4: 52.0}
ICON_SIZE_BY_N = {2: 190, 3: 164, 4: 141}

# How often a video is a 1v1 duel vs a 3-way / 4-way melee.
N_FIGHTERS_WEIGHTS = {2: 55, 3: 28, 4: 17}


def simulate_battle(w, h, seed, fps=24, max_seconds=30, min_seconds=13, n_fighters=None):
    rng = random.Random(seed)
    # Crit rolls draw from their own stream so adding/tuning the crit feature
    # never reshuffles spawn positions, AI jitter or damage variance — the
    # rest of the fight stays byte-identical for a given seed.
    crit_rng = random.Random(hashlib.sha256((str(seed) + "crit").encode()).hexdigest())
    parry_rng = random.Random(hashlib.sha256((str(seed) + "parry").encode()).hexdigest())
    theme = pick_arena_theme(seed)

    if n_fighters is None:
        options = list(N_FIGHTERS_WEIGHTS.keys())
        weights = list(N_FIGHTERS_WEIGHTS.values())
        n_fighters = rng.choices(options, weights=weights, k=1)[0]

    fighters = [dict(f) for f in rng.sample(WEAPON_POOL, n_fighters)]
    _boost_color_contrast(fighters, rng)
    base_radius = RADIUS_BY_N[n_fighters]
    icon_size = ICON_SIZE_BY_N[n_fighters]

    top_arena = int(h * 0.24)
    bottom_arena = int(h * 0.965)
    left_arena = int(w * 0.055)
    right_arena = int(w * 0.945)
    center_x = (left_arena + right_arena) / 2
    center_y = (top_arena + bottom_arena) / 2

    space = pymunk.Space()
    space.gravity = (0, 0)

    def spawn(x, y, angle_deg, speed, ctype, mass, radius, elasticity, friction):
        body = pymunk.Body(mass=mass, moment=pymunk.moment_for_circle(mass, 0, radius))
        body.position = (x, y)
        rad = math.radians(angle_deg)
        body.velocity = (math.cos(rad) * speed, math.sin(rad) * speed)
        body.angular_velocity = rng.uniform(-5.5, 5.5)
        shape = pymunk.Circle(body, radius)
        shape.elasticity = elasticity
        # Friction (fighter-vs-fighter clashes only, walls stay at 0 so
        # bounces off the arena edge stay clean) lets impacts transfer spin,
        # so a weapon's rotation visibly kicks or stalls on a hit instead of
        # spinning at one constant rate for the whole fight.
        shape.friction = friction
        shape.collision_type = ctype
        space.add(body, shape)
        return body, shape

    speed0 = min(w, h) * 0.50
    spawn_r = min(right_arena - left_arena, bottom_arena - top_arena) * (0.30 if n_fighters <= 2 else 0.33)
    angle_offset = rng.uniform(0, 360)

    # Mass tracks each weapon's "power" stat, so a heavy weapon (Warhammer,
    # power ~1.4) physically shrugs off a hit that sends a light one (Dagger,
    # power ~0.8) flying — the collision itself feels like weight, not just
    # the HP number ticking down.
    bodies, shapes, fighter_radii = [], [], []
    # shape -> "active" (a real blade/head/point — deals real damage) or
    # "body" (handle/shaft/guard — bounces but never deals damage on its
    # own). See the ACTIVE_ZONES comment above for the full design.
    shape_role = {}
    # Flail/nunchaku/whip are chain/flexible weapons in concept — give each
    # one a tiny second body tethered to the main body by a soft
    # DampedSpring. Real inertia makes it lag behind during travel and
    # swing/overshoot on a sudden velocity change (a hit), then settle into
    # an orbit — genuine physics, not scripted. The swinging head is this
    # weapon's actual "active" damage zone (a flail/whip hits with its tip,
    # not the hand holding it); the head carries no mass-relevant collision
    # shape of the main fighter body, so it can never distort the fighter's
    # own mass/moment.
    CHAIN_WEAPON_KINDS = {"flail", "nunchaku", "whip"}
    chain_bodies = [None] * n_fighters
    chain_springs = [None] * n_fighters
    for i in range(n_fighters):
        ang = math.radians(angle_offset + i * 360 / n_fighters)
        x = center_x + math.cos(ang) * spawn_r
        y = center_y + math.sin(ang) * spawn_r
        aim = math.degrees(math.atan2(center_y - y, center_x - x)) + rng.uniform(-25, 25)
        kind = fighters[i]["kind"]
        fighter_radius = base_radius * WEAPON_REACH.get(kind, 1.0)
        phys = _MATERIAL_PHYSICS.get(fighters[i]["material"], _MATERIAL_PHYSICS["metal"])
        body, shape = spawn(
            x, y, aim, speed0, ctype=i + 1, mass=fighters[i]["power"], radius=fighter_radius,
            elasticity=phys["elasticity"], friction=phys["friction"],
        )
        # All of a single fighter's own shapes (body + every active zone,
        # including a chain weapon's separately-bodied head) share one
        # pymunk collision group so pymunk never resolves a "collision"
        # between a fighter's own parts. Without this, a chain weapon's
        # head — a genuinely separate physics body tethered by a spring —
        # can physically clip its own owner's body shape (most violently
        # right at spawn, where the head starts at rest while the main body
        # launches at full speed) and silently deal that fighter
        # self-damage before the fight even starts.
        own_shape_filter = pymunk.ShapeFilter(group=i + 1)
        shape.filter = own_shape_filter
        bodies.append(body)
        shapes.append(shape)
        fighter_radii.append(fighter_radius)
        shape_role[shape] = "active" if kind in WHOLE_BODY_ACTIVE_KINDS else "body"

        if kind in CHAIN_WEAPON_KINDS:
            # rest_length > 1.0*fighter_radius so the head sits genuinely
            # outside the main body's own collision circle even at rest, not
            # tucked inside it — same "must poke past the body silhouette"
            # requirement as every other active zone (see ACTIVE_ZONES note).
            chain_len = fighter_radius * 1.20
            # Mass matters here: collision impulse (and thus damage, via
            # on_hit's impulse-driven `base`) scales with the reduced mass
            # of the two colliding bodies, which collapses toward the
            # SMALLER body's mass when they're very unequal. The original
            # mass=0.12 was chosen back when this head had no collision
            # shape at all and was purely a render-time flourish — now that
            # it's the weapon's actual active damage zone, that same
            # tininess was silently starving its own hits (measured: ~2.5x
            # smaller impulse than a normal body-body collision, landing at
            # the damage floor 55% of the time vs 28% normally). 0.35 keeps
            # it lighter than a full fighter body (so it still lags/swings
            # with real inertia) without crippling the impulse it can land.
            head_body = pymunk.Body(mass=0.35, moment=1.0)
            head_body.position = (x + chain_len, y)
            # Match the main body's launch velocity so the spring doesn't
            # get yanked taut by a sudden relative-velocity mismatch on the
            # very first physics step (the head would otherwise start at
            # rest while its own body rockets off at speed0).
            head_body.velocity = body.velocity
            space.add(head_body)
            spring = pymunk.DampedSpring(body, head_body, (0, 0), (0, 0), rest_length=chain_len, stiffness=90, damping=4.0)
            space.add(spring)
            chain_bodies[i] = head_body
            chain_springs[i] = spring
            head_shape = pymunk.Circle(head_body, fighter_radius * 0.32)
            head_shape.elasticity = phys["elasticity"]
            head_shape.friction = phys["friction"]
            head_shape.collision_type = i + 1
            head_shape.filter = own_shape_filter
            space.add(head_shape)
            shape_role[head_shape] = "active"
        elif kind in ACTIVE_ZONES:
            # One or more small collision circles offset toward the icon's
            # actual blade/head/point, in LOCAL space (so each one swings
            # with the body and stays over the visible striking part at any
            # rotation — see the ACTIVE_ZONES comment for the offset
            # convention). Same collision_type as the main body, so damage
            # attribution is unaffected; only shape_role distinguishes them.
            for (ox_frac, oy_frac, r_frac) in ACTIVE_ZONES[kind]:
                zone_shape = pymunk.Circle(
                    body, fighter_radius * r_frac,
                    offset=(fighter_radius * ox_frac, fighter_radius * oy_frac),
                )
                zone_shape.elasticity = phys["elasticity"]
                zone_shape.friction = phys["friction"]
                zone_shape.collision_type = i + 1
                zone_shape.filter = own_shape_filter
                space.add(zone_shape)
                shape_role[zone_shape] = "active"

    # Pistol: the one ranged weapon in the roster. It still has a normal
    # melee circle above (bounces/gets hit like everyone else) but also
    # periodically fires a small fast projectile at a random living
    # opponent — a genuinely separate subsystem (its own collision type,
    # its own damage path, single-use/despawns on any hit or timeout)
    # layered on top of the existing per-fighter melee model rather than
    # replacing it.
    PROJECTILE_COLLISION_TYPE = 150
    PROJECTILE_SPEED = speed0 * 2.4
    PROJECTILE_RADIUS = min(w, h) * 0.007
    PISTOL_FIRE_MIN_STEPS = int(1.4 * PHYSICS_HZ)
    PISTOL_FIRE_MAX_STEPS = int(2.0 * PHYSICS_HZ)
    PROJECTILE_LIFE_STEPS = int(1.4 * PHYSICS_HZ)
    projectiles = []  # each: {"body", "shape", "shooter"}
    to_remove_projectiles = []
    next_fire_step = [
        rng.randint(PISTOL_FIRE_MIN_STEPS, PISTOL_FIRE_MAX_STEPS) if fighters[i]["kind"] == "pistol" else None
        for i in range(n_fighters)
    ]

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
    OBSTACLE_COLLISION_TYPE = 99  # distinct from walls (0) and fighters (1..4)
    obs_phys = _OBSTACLE_PHYSICS.get(theme.get("obstacle_kind", "rock"), _OBSTACLE_PHYSICS["rock"])
    for (ox, oy) in obstacles:
        obs_shape = pymunk.Circle(space.static_body, obstacle_radius, offset=(ox, oy))
        obs_shape.elasticity = obs_phys["elasticity"]
        obs_shape.friction = obs_phys["friction"]
        obs_shape.collision_type = OBSTACLE_COLLISION_TYPE
        space.add(obs_shape)

    hp = [START_HP] * n_fighters
    alive = [True] * n_fighters
    ctype_to_idx = {i + 1: i for i in range(n_fighters)}
    hit_log = []  # (step_index, x, y, total_dmg, i1, i2, hit_type) — hit_type
    # is one of "block" (both sides only touched with a passive body/guard
    # shape), "clean" (exactly one side struck with an active zone), or
    # "clash" (both sides struck with an active zone) — see the ACTIVE_ZONES
    # comment near the top of the file.
    obstacle_hit_log = []  # (step_index, x, y) — a weapon bounced off a static obstacle
    wall_hit_log = []  # (step_index, x, y) — a weapon bounced off the arena boundary
    # Weapons clip the arena wall constantly (perfectly elastic bounces), far
    # more often than they touch an obstacle — a per-fighter cooldown keeps
    # the wall-bounce reaction to an occasional punchy beat instead of a
    # flash on every single touch.
    WALL_FLASH_COOLDOWN_STEPS = int(0.5 * PHYSICS_HZ)
    last_wall_flash_step = [-WALL_FLASH_COOLDOWN_STEPS] * n_fighters
    muzzle_flash_log = []  # (step_index, x, y, angle_deg)
    projectile_hit_log = []  # (step_index, x, y, dmg, shooter_idx, target_idx)
    step_counter = {"n": 0}

    def on_hit(arbiter, space, data):
        ct1, ct2 = arbiter.shapes[0].collision_type, arbiter.shapes[1].collision_type
        if PROJECTILE_COLLISION_TYPE in (ct1, ct2):
            proj_shape = arbiter.shapes[0] if ct1 == PROJECTILE_COLLISION_TYPE else arbiter.shapes[1]
            other_ct = ct2 if ct1 == PROJECTILE_COLLISION_TYPE else ct1
            proj = next((p for p in projectiles if p["shape"] is proj_shape), None)
            if proj is None or proj in to_remove_projectiles:
                return True
            fi = ctype_to_idx.get(other_ct)
            if fi == proj["shooter"]:
                return True  # never hits its own shooter
            if fi is not None and alive[fi]:
                dmg = rng.uniform(6.0, 11.0)
                hp[fi] = max(0.0, hp[fi] - dmg)
                cx_, cy_ = proj["body"].position.x, proj["body"].position.y
                projectile_hit_log.append((step_counter["n"], cx_, cy_, round(dmg), proj["shooter"], fi))
            to_remove_projectiles.append(proj)
            return True
        if OBSTACLE_COLLISION_TYPE in (ct1, ct2):
            other_ct = ct2 if ct1 == OBSTACLE_COLLISION_TYPE else ct1
            fi = ctype_to_idx.get(other_ct)
            if fi is not None and alive[fi]:
                cps = arbiter.contact_point_set.points
                cx, cy = (cps[0].point_a.x, cps[0].point_a.y) if cps else (bodies[fi].position.x, bodies[fi].position.y)
                obstacle_hit_log.append((step_counter["n"], cx, cy))
            return True
        if ct1 not in ctype_to_idx or ct2 not in ctype_to_idx:
            # a wall hit, not a fighter-vs-fighter clash — no damage, but an
            # occasional (cooldown-gated) reaction so bouncing off the arena
            # boundary reads as hitting something solid, not silent/invisible.
            other_ct = ct1 if ct1 in ctype_to_idx else ct2
            fi = ctype_to_idx.get(other_ct)
            if fi is not None and alive[fi] and step_counter["n"] - last_wall_flash_step[fi] >= WALL_FLASH_COOLDOWN_STEPS:
                last_wall_flash_step[fi] = step_counter["n"]
                cps = arbiter.contact_point_set.points
                cx, cy = (cps[0].point_a.x, cps[0].point_a.y) if cps else (bodies[fi].position.x, bodies[fi].position.y)
                wall_hit_log.append((step_counter["n"], cx, cy))
            return True
        i1, i2 = ctype_to_idx[ct1], ctype_to_idx[ct2]
        if not alive[i1] or not alive[i2]:
            return True

        # Segmented hitboxes: which physical shape each fighter actually hit
        # with — "active" (blade/head/point) or "body" (handle/guard) — is
        # what decides whether this exchange deals real damage, not just the
        # raw fact that a collision happened. See the ACTIVE_ZONES comment
        # near the top of the file for the full rationale.
        role1 = shape_role.get(arbiter.shapes[0], "body")
        role2 = shape_role.get(arbiter.shapes[1], "body")

        def _hit_mult(attacker_role, victim_role, attacker_kind):
            if attacker_role != "active":
                return GUARD_DAMAGE_MULT
            m = ACTIVE_DAMAGE_MULT
            if attacker_kind in WHOLE_BODY_ACTIVE_KINDS:
                m *= WHOLE_BODY_DAMAGE_DISCOUNT
            return m * (CLEAN_HIT_BONUS if victim_role == "body" else 1.0)

        mult_for_d1 = _hit_mult(role2, role1, fighters[i2]["kind"])  # damage TO i1, dealt by i2's shape
        mult_for_d2 = _hit_mult(role1, role2, fighters[i1]["kind"])  # damage TO i2, dealt by i1's shape

        # Classify the exchange itself, purely from which shapes actually
        # touched — used downstream to make the mechanic visible/audible,
        # not just a hidden number: a "block" (both sides only offered up
        # their passive handle/guard) should read as a cheap, undramatic
        # bump; a "clash" (both landed with an active zone) or "clean" hit
        # (one side struck an undefended opponent) should read as a real
        # moment.
        if role1 == "active" and role2 == "active":
            hit_type = "clash"
        elif role1 == "active" or role2 == "active":
            hit_type = "clean"
        else:
            hit_type = "block"

        impulse = arbiter.total_impulse.length
        base = min(24.0, max(2.5, impulse * 0.028))
        p1, p2 = fighters[i1]["power"], fighters[i2]["power"]
        # A weapon's own spin adds extra bite to the hit it lands — a
        # chainsaw or shuriken caught mid-spin cuts harder than one moving
        # with the same impulse but no rotation.
        spin1 = min(0.35, abs(bodies[i1].angular_velocity) * 0.035)
        spin2 = min(0.35, abs(bodies[i2].angular_velocity) * 0.035)
        pr = (p2 / p1) ** POWER_DMG_EXPONENT
        d1 = base * pr * (1.0 + spin2) * rng.uniform(0.82, 1.18) * mult_for_d1
        d2 = base * (1.0 / pr) * (1.0 + spin1) * rng.uniform(0.82, 1.18) * mult_for_d2

        # Advance both side-RNG streams exactly once per fighter-vs-fighter
        # hit, no matter the outcome, so tuning one feature never reshuffles
        # the other.
        parry_roll = parry_rng.random()
        crit_roll = crit_rng.random()
        if hit_type == "clash" and parry_roll < PARRY_CHANCE:
            hit_type = "parry"
            d1 = d2 = 0.0
        is_crit = hit_type in ("clean", "clash") and crit_roll < CRIT_CHANCE
        if is_crit:
            d1 *= CRIT_MULT
            d2 *= CRIT_MULT

        hp[i1] = max(0.0, hp[i1] - d1)
        hp[i2] = max(0.0, hp[i2] - d2)

        cps = arbiter.contact_point_set.points
        cx, cy = (cps[0].point_a.x, cps[0].point_a.y) if cps else (bodies[i1].position.x, bodies[i1].position.y)
        hit_log.append((step_counter["n"], cx, cy, round(d1 + d2), i1, i2, hit_type, is_crit))

        # A real (non-blocked) exchange gets an explicit extra separating
        # knockback beyond whatever the elastic collision itself already
        # produced. A FIXED impulse split by each fighter's own mass (mass
        # == "power") means the heavier weapon barely moves while the
        # lighter one gets shoved much further — momentum, not a scripted
        # "heavy weapon wins" rule. Pure handle-vs-handle blocks stay a
        # cheap, undramatic bounce.
        if hit_type != "block":
            dx = bodies[i2].position.x - bodies[i1].position.x
            dy = bodies[i2].position.y - bodies[i1].position.y
            dist = max(1.0, math.hypot(dx, dy))
            ux, uy = dx / dist, dy / dist
            knock = impulse * 0.55 * (PARRY_KNOCK_MULT if hit_type == "parry" else 1.0)
            bodies[i1].apply_impulse_at_world_point((-ux * knock, -uy * knock), (cx, cy))
            bodies[i2].apply_impulse_at_world_point((ux * knock, uy * knock), (cx, cy))
            _apply_recovery(i1)
            _apply_recovery(i2)
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
    #
    # Attack Speed & Recovery: this schedule is now per-fighter instead of
    # one global tick for everyone. A light weapon (low "power") lunges
    # again sooner — reads as quick, high-tempo strikes. A heavy weapon
    # lunges less often (slower windup) but every landed or received hit
    # additionally forces a short recovery delay before its NEXT lunge and
    # saps its angular velocity — a heavy weapon that just swung (or just
    # got hit) is genuinely more exposed for a moment, not just numerically
    # slower. A light weapon gets the opposite: its next lunge comes sooner
    # after any exchange, reflecting a quick recovery.
    BASE_LUNGE_INTERVAL_STEPS = int(0.95 * PHYSICS_HZ)
    lunge_strength = speed0 * 0.70
    max_speed = speed0 * 2.0
    RECOVERY_HEAVY_THRESHOLD = 1.15
    RECOVERY_LIGHT_THRESHOLD = 0.85

    def _lunge_interval_for(fi):
        p = fighters[fi]["power"]
        mult = 0.60 + max(0.0, min(1.0, (p - 0.70) / 0.70)) * 0.90
        return max(int(0.45 * PHYSICS_HZ), int(BASE_LUNGE_INTERVAL_STEPS * mult))

    next_lunge_step = [rng.randint(int(0.3 * PHYSICS_HZ), _lunge_interval_for(i)) for i in range(n_fighters)]

    def _apply_recovery(fi):
        p = fighters[fi]["power"]
        if p >= RECOVERY_HEAVY_THRESHOLD:
            bodies[fi].angular_velocity *= 0.55
            next_lunge_step[fi] = max(next_lunge_step[fi], step_counter["n"] + int(0.35 * PHYSICS_HZ))
        elif p <= RECOVERY_LIGHT_THRESHOLD:
            next_lunge_step[fi] = min(next_lunge_step[fi], step_counter["n"] + int(0.20 * PHYSICS_HZ))

    frames = []
    hit_frame_flags = {}  # frame_index -> (x, y, dmg, i1, i2, hit_type, is_crit)
    obstacle_hit_frames = {}  # frame_index -> (x, y)
    wall_hit_frames = {}  # frame_index -> (x, y)
    muzzle_flash_frames = {}  # frame_index -> (x, y, angle_deg)
    projectile_hit_frames = {}  # frame_index -> (x, y, dmg, shooter_idx, target_idx)
    ko_events = []  # list of (frame_index, fighter_idx, x, y) — a list, not a
    # dict keyed by frame, because two fighters can die in the very same
    # frame window (a mutual/simultaneous KO) and would otherwise clobber
    # each other's entry
    frame_idx = 0

    while step_counter["n"] < max_steps:
        step_counter["n"] += 1
        space.step(dt)

        for proj in projectiles:
            if step_counter["n"] - proj["spawn_step"] > PROJECTILE_LIFE_STEPS and proj not in to_remove_projectiles:
                to_remove_projectiles.append(proj)  # missed — timed out
        if to_remove_projectiles:
            for proj in to_remove_projectiles:
                try:
                    space.remove(proj["body"], proj["shape"])
                except Exception:
                    pass
                if proj in projectiles:
                    projectiles.remove(proj)
            to_remove_projectiles.clear()

        for i in range(n_fighters):
            if not alive[i] or fighters[i]["kind"] != "pistol" or next_fire_step[i] is None:
                continue
            if step_counter["n"] < next_fire_step[i]:
                continue
            alive_targets = [j for j in range(n_fighters) if j != i and alive[j]]
            if alive_targets:
                j = rng.choice(alive_targets)
                sx, sy = bodies[i].position.x, bodies[i].position.y
                tx, ty = bodies[j].position.x, bodies[j].position.y
                fire_ang = math.atan2(ty - sy, tx - sx) + math.radians(rng.uniform(-6, 6))
                spawn_dist = fighter_radii[i] + PROJECTILE_RADIUS + 10
                px = sx + math.cos(fire_ang) * spawn_dist
                py = sy + math.sin(fire_ang) * spawn_dist
                pbody = pymunk.Body(mass=0.05, moment=1.0)
                pbody.position = (px, py)
                pbody.velocity = (math.cos(fire_ang) * PROJECTILE_SPEED, math.sin(fire_ang) * PROJECTILE_SPEED)
                pshape = pymunk.Circle(pbody, PROJECTILE_RADIUS)
                pshape.elasticity = 0.0
                pshape.friction = 0.0
                pshape.collision_type = PROJECTILE_COLLISION_TYPE
                space.add(pbody, pshape)
                projectiles.append({"body": pbody, "shape": pshape, "shooter": i, "spawn_step": step_counter["n"]})
                muzzle_flash_log.append((step_counter["n"], sx, sy, math.degrees(fire_ang)))
            next_fire_step[i] = step_counter["n"] + rng.randint(PISTOL_FIRE_MIN_STEPS, PISTOL_FIRE_MAX_STEPS)

        # Late-fight aggression ramp: ~1 in 8 fights used to run the full
        # max_seconds and time out with >1 fighter still alive (two low-power
        # weapons trading handle-blocks that never push enough damage
        # through). Past 55% of the clock the lunge grows stronger and fires
        # more often, linearly, up to ~1.8x strength / ~0.6x interval at the
        # buzzer — enough to force the survivors together and break a
        # block-stall without changing how a normal-length fight feels.
        progress = step_counter["n"] / max_steps
        aggr = 1.0 + max(0.0, (progress - 0.55) / 0.45) * 0.8
        alive_idx = [i for i in range(n_fighters) if alive[i]]
        for i in alive_idx:
            if step_counter["n"] < next_lunge_step[i]:
                continue
            others = [j for j in alive_idx if j != i]
            if others:
                j = rng.choice(others)
                dx = bodies[j].position.x - bodies[i].position.x
                dy = bodies[j].position.y - bodies[i].position.y
                dist = max(1.0, math.hypot(dx, dy))
                jitter = math.radians(rng.uniform(-20, 20))
                ux, uy = dx / dist, dy / dist
                ux, uy = ux * math.cos(jitter) - uy * math.sin(jitter), ux * math.sin(jitter) + uy * math.cos(jitter)
                bodies[i].velocity = (bodies[i].velocity.x + ux * lunge_strength * aggr, bodies[i].velocity.y + uy * lunge_strength * aggr)
                sp = bodies[i].velocity.length
                if sp > max_speed:
                    bodies[i].velocity = bodies[i].velocity * (max_speed / sp)
            step_gap = _lunge_interval_for(i)
            if aggr > 1.0:
                step_gap = max(int(0.30 * PHYSICS_HZ), int(step_gap / aggr))
            next_lunge_step[i] = step_counter["n"] + step_gap

        if step_counter["n"] % steps_per_frame == 0:
            pos = []
            chain_pos = []
            for i in range(n_fighters):
                b = bodies[i]
                pos.append((b.position.x, b.position.y, math.degrees(b.angle)))
                chain_pos.append((chain_bodies[i].position.x, chain_bodies[i].position.y) if chain_bodies[i] else None)
            proj_snapshot = [(p["body"].position.x, p["body"].position.y, math.degrees(p["body"].velocity.angle)) for p in projectiles]
            frames.append({"pos": pos, "hp": list(hp), "alive": list(alive), "chain_pos": chain_pos, "projectiles": proj_snapshot})
            frame_idx += 1

        if hit_log and hit_log[-1][0] == step_counter["n"]:
            _, hx, hy, dmg, hi1, hi2, hit_type, is_crit = hit_log[-1]
            hit_frame_flags[frame_idx - 1] = (hx, hy, dmg, hi1, hi2, hit_type, is_crit)

        if muzzle_flash_log and muzzle_flash_log[-1][0] == step_counter["n"]:
            _, mfx, mfy, mfang = muzzle_flash_log[-1]
            muzzle_flash_frames[frame_idx - 1] = (mfx, mfy, mfang)

        if projectile_hit_log and projectile_hit_log[-1][0] == step_counter["n"]:
            _, phx, phy, pdmg, pshooter, ptarget = projectile_hit_log[-1]
            projectile_hit_frames[frame_idx - 1] = (phx, phy, pdmg, pshooter, ptarget)

        if obstacle_hit_log and obstacle_hit_log[-1][0] == step_counter["n"]:
            _, ohx, ohy = obstacle_hit_log[-1]
            obstacle_hit_frames[frame_idx - 1] = (ohx, ohy)

        if wall_hit_log and wall_hit_log[-1][0] == step_counter["n"]:
            _, whx, why = wall_hit_log[-1]
            wall_hit_frames[frame_idx - 1] = (whx, why)

        for i in range(n_fighters):
            if alive[i] and hp[i] <= 0:
                alive[i] = False
                ko_events.append((frame_idx - 1, i, bodies[i].position.x, bodies[i].position.y))
                try:
                    space.remove(bodies[i], shapes[i])
                except Exception:
                    pass
                if chain_bodies[i] is not None:
                    try:
                        space.remove(chain_springs[i], chain_bodies[i])
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
            dup = {"pos": list(src["pos"]), "hp": list(src["hp"]), "alive": list(src["alive"]), "chain_pos": list(src.get("chain_pos", [])), "projectiles": list(src.get("projectiles", []))}
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
        "obstacle_hit_frames": obstacle_hit_frames,
        "wall_hit_frames": wall_hit_frames,
        "muzzle_flash_frames": muzzle_flash_frames,
        "projectile_hit_frames": projectile_hit_frames,
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

def _brighten_theme_color(rgb, val_floor=0.60, val_span=0.30, sat_target=0.40):
    """Arena backgrounds were originally tuned as a very dark night-battle
    backdrop; a round-23 pass boosted saturation/brightness multiplicatively
    but starting from such low raw values that the result was still mostly
    crushed near-black (measured luminance 2-70 out of 255 across the 16
    themes) — direct viewer feedback ("make the background a light color,
    it gets mixed with the weapons") confirmed this wasn't nearly enough. A
    multiplicative boost off wildly different starting values also produced
    inconsistent results per theme (Deep Space stayed near-black while
    Golden Temple got fairly bright). This instead targets an explicit
    brightness FLOOR (in HSV space, hue preserved so each theme keeps its
    identity) so every theme lands in a genuinely light range regardless of
    its original darkness, with only a modest per-theme spread on top of
    the floor for organic variation. Saturation is pulled toward a lower
    target too — a light background reads as a soft tinted color, not a
    neon light source at high brightness/high saturation."""
    h, s, v = colorsys.rgb_to_hsv(*(c / 255 for c in rgb))
    v = min(0.94, val_floor + v * val_span)
    s = min(1.0, max(0.16, sat_target * (0.5 + s)))
    r, g, b = colorsys.hsv_to_rgb(h, s, v)
    return (int(r * 255), int(g * 255), int(b * 255))


ARENA_THEMES = [
    {"name": "Midnight Arena", "top": (14, 12, 26), "bottom": (4, 4, 10), "grid": (255, 255, 255, 12), "border": (90, 90, 110, 255), "particle": (150, 150, 210), "obstacle_kind": "rock", "particle_kind": "up", "impact_fx": "dust_ring", "edge_kind": "none"},
    {"name": "Neon City", "top": (42, 8, 52), "bottom": (10, 2, 16), "grid": (255, 70, 210, 20), "border": (210, 70, 230, 255), "particle": (255, 90, 220), "obstacle_kind": "tech_crate", "particle_kind": "up", "impact_fx": "spark_grid", "edge_kind": "circuit"},
    {"name": "Lava Pit", "top": (48, 10, 4), "bottom": (14, 4, 2), "grid": (255, 130, 45, 18), "border": (235, 100, 35, 255), "particle": (255, 150, 60), "obstacle_kind": "lava_rock", "particle_kind": "up", "impact_fx": "embers", "edge_kind": "ember_glow"},
    {"name": "Ice Cave", "top": (6, 26, 40), "bottom": (2, 8, 14), "grid": (150, 220, 255, 20), "border": (130, 205, 245, 255), "particle": (190, 235, 255), "obstacle_kind": "ice_shard", "particle_kind": "down", "impact_fx": "frost", "edge_kind": "icicles"},
    {"name": "Cyber Grid", "top": (4, 18, 9), "bottom": (2, 4, 4), "grid": (60, 255, 130, 24), "border": (60, 225, 115, 255), "particle": (90, 255, 150), "obstacle_kind": "tech_crate", "particle_kind": "still_pulse", "impact_fx": "spark_grid", "edge_kind": "circuit"},
    {"name": "Deep Space", "top": (6, 4, 28), "bottom": (2, 2, 9), "grid": (150, 150, 255, 12), "border": (120, 110, 225, 255), "particle": (205, 205, 255), "obstacle_kind": "rock", "particle_kind": "still_pulse", "impact_fx": "starburst", "edge_kind": "none"},
    {"name": "Toxic Lab", "top": (10, 34, 6), "bottom": (3, 10, 2), "grid": (155, 255, 65, 18), "border": (145, 235, 55, 255), "particle": (175, 255, 85), "obstacle_kind": "tech_crate", "particle_kind": "up", "impact_fx": "spark_grid", "edge_kind": "circuit"},
    {"name": "Sunset Coliseum", "top": (48, 16, 27), "bottom": (14, 4, 10), "grid": (255, 165, 125, 16), "border": (235, 125, 155, 255), "particle": (255, 175, 135), "obstacle_kind": "rock", "particle_kind": "sideways", "impact_fx": "dust_ring", "edge_kind": "horizon_silhouette"},
    {"name": "Volcanic Forge", "top": (30, 4, 4), "bottom": (8, 2, 2), "grid": (255, 90, 30, 20), "border": (255, 60, 20, 255), "particle": (255, 120, 40), "obstacle_kind": "lava_rock", "particle_kind": "up", "impact_fx": "embers", "edge_kind": "ember_glow"},
    {"name": "Frozen Peak", "top": (10, 14, 34), "bottom": (3, 5, 12), "grid": (200, 220, 255, 18), "border": (170, 200, 250, 255), "particle": (220, 235, 255), "obstacle_kind": "ice_shard", "particle_kind": "down", "impact_fx": "frost", "edge_kind": "icicles"},
    {"name": "Golden Temple", "top": (40, 28, 4), "bottom": (12, 8, 1), "grid": (255, 210, 90, 20), "border": (240, 190, 70, 255), "particle": (255, 220, 130), "obstacle_kind": "gold_crystal", "particle_kind": "up", "impact_fx": "starburst", "edge_kind": "horizon_silhouette"},
    {"name": "Storm Clouds", "top": (18, 20, 28), "bottom": (5, 6, 9), "grid": (170, 190, 220, 18), "border": (150, 175, 210, 255), "particle": (200, 215, 255), "obstacle_kind": "rock", "particle_kind": "rain", "impact_fx": "dust_ring", "edge_kind": "lightning"},
    {"name": "Blood Moon", "top": (34, 3, 6), "bottom": (9, 1, 2), "grid": (220, 40, 50, 18), "border": (200, 30, 45, 255), "particle": (255, 70, 80), "obstacle_kind": "bone", "particle_kind": "up", "impact_fx": "embers", "edge_kind": "ember_glow"},
    {"name": "Coral Reef", "top": (4, 30, 32), "bottom": (2, 8, 10), "grid": (100, 230, 210, 18), "border": (90, 220, 200, 255), "particle": (255, 130, 170), "obstacle_kind": "coral", "particle_kind": "bubble", "impact_fx": "bubbles", "edge_kind": "coral_fringe"},
    {"name": "Desert Dunes", "top": (38, 24, 10), "bottom": (12, 7, 3), "grid": (230, 180, 110, 16), "border": (220, 165, 95, 255), "particle": (255, 200, 130), "obstacle_kind": "sand_rock", "particle_kind": "sideways", "impact_fx": "dust_ring", "edge_kind": "horizon_silhouette"},
    {"name": "Radioactive Waste", "top": (14, 30, 2), "bottom": (4, 9, 1), "grid": (190, 255, 30, 22), "border": (170, 235, 20, 255), "particle": (210, 255, 60), "obstacle_kind": "tech_crate", "particle_kind": "still_pulse", "impact_fx": "spark_grid", "edge_kind": "circuit"},
]

for _theme in ARENA_THEMES:
    _theme["top"] = _brighten_theme_color(_theme["top"])
    _theme["bottom"] = _brighten_theme_color(_theme["bottom"], val_floor=0.44, val_span=0.24)


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


def _draw_arena_impact_fx(d, kind, fx, fy, elapsed, alpha, color):
    """A secondary, theme-colored burst layered on top of the material hit
    flash so impacts pick up the arena's identity too (embers in lava,
    frost in ice caves, glitchy sparks in cyber/toxic/radioactive arenas,
    bubbles underwater, a starburst in space/gold temple, a dust ring
    everywhere else) instead of every arena's hits looking the same."""
    if kind == "embers":
        for i in range(6):
            ang = math.radians(i * 60 + int(fx * 3) % 30) - math.pi / 2
            rr = 10 + elapsed * 34
            ex, ey = fx + math.cos(ang) * rr, fy + math.sin(ang) * rr - elapsed * 10
            pr = max(1, 3 * (1 - elapsed))
            d.ellipse([ex - pr, ey - pr, ex + pr, ey + pr], fill=(*color, int(alpha * 0.75)))
    elif kind == "frost":
        for i in range(6):
            ang = math.radians(i * 60 + int(fx) % 25)
            r1, r2 = 10, 10 + elapsed * 28
            x1, y1 = fx + math.cos(ang) * r1, fy + math.sin(ang) * r1
            x2, y2 = fx + math.cos(ang) * r2, fy + math.sin(ang) * r2
            d.line([(x1, y1), (x2, y2)], fill=(*color, int(alpha * 0.8)), width=2)
        rr = 6 + elapsed * 10
        d.ellipse([fx - rr, fy - rr, fx + rr, fy + rr], outline=(*color, alpha), width=2)
    elif kind == "spark_grid":
        rng_seed = int(fx * 7 + fy * 13)
        for i in range(5):
            ang = math.radians((rng_seed + i * 73) % 360)
            rr = 8 + elapsed * 30
            ex, ey = fx + math.cos(ang) * rr, fy + math.sin(ang) * rr
            s = max(1, 3 * (1 - elapsed))
            d.rectangle([ex - s, ey - s, ex + s, ey + s], fill=(*color, int(alpha * 0.85)))
    elif kind == "bubbles":
        for i in range(4):
            ang = math.radians(i * 90 + 30)
            rr = 6 + elapsed * 20
            ex, ey = fx + math.cos(ang) * rr * 0.6, fy - elapsed * 22 + math.sin(ang) * 6
            pr = max(1, 3.5 * (1 - elapsed * 0.6))
            d.ellipse([ex - pr, ey - pr, ex + pr, ey + pr], outline=(*color, int(alpha * 0.8)), width=1)
    elif kind == "starburst":
        for i in range(6):
            ang = math.radians(i * 60 + 15)
            r1, r2 = 6, 6 + elapsed * 26
            x1, y1 = fx + math.cos(ang) * r1, fy + math.sin(ang) * r1
            x2, y2 = fx + math.cos(ang) * r2, fy + math.sin(ang) * r2
            d.line([(x1, y1), (x2, y2)], fill=(*color, int(alpha * 0.7)), width=1)
    else:  # "dust_ring"
        rr = 12 + elapsed * 30
        d.ellipse([fx - rr, fy - rr * 0.5, fx + rr, fy + rr * 0.5], outline=(*color, int(alpha * 0.6)), width=3)


def _draw_arena_edge_decor(d, kind, left, top, right, bottom, color, t):
    """A light per-theme decoration drawn along the arena border every
    frame, so the box itself carries some of the arena's identity, not
    just the background gradient and grid tint."""
    if kind == "icicles":
        n = 9
        for i in range(n):
            x = left + (right - left) * (i + 0.5) / n
            ln = 10 + 14 * ((i * 37) % 5) / 4.0
            d.polygon([(x - 5, top), (x + 5, top), (x, top + ln)], fill=(*color, 140))
    elif kind == "ember_glow":
        pulse = 0.5 + 0.5 * math.sin(t * 2.2)
        glow_h = 10 + pulse * 8
        d.rectangle([left, bottom - glow_h, right, bottom], fill=(*color, int(50 + 40 * pulse)))
    elif kind == "circuit":
        seg = 22
        for (cx, cy, sx, sy) in [(left, top, 1, 1), (right, top, -1, 1), (left, bottom, 1, -1), (right, bottom, -1, -1)]:
            d.line([(cx, cy), (cx + sx * seg, cy)], fill=(*color, 190), width=2)
            d.line([(cx, cy), (cx, cy + sy * seg)], fill=(*color, 190), width=2)
            d.ellipse([cx + sx * seg - 3, cy - 3, cx + sx * seg + 3, cy + 3], fill=(*color, 220))
            d.ellipse([cx - 3, cy + sy * seg - 3, cx + 3, cy + sy * seg + 3], fill=(*color, 220))
    elif kind == "lightning":
        if int(t * 6) % 7 == 0:
            frame_rng = random.Random(int(t * 6))
            x0 = left + (right - left) * 0.3
            pts = [(x0, top)]
            xx, yy = x0, top
            for _ in range(4):
                xx += frame_rng.uniform(-30, 30)
                yy += 25
                pts.append((xx, yy))
            d.line(pts, fill=(*color, 220), width=2)
    elif kind == "coral_fringe":
        n = 6
        for i in range(n):
            x = left + (right - left) * (i + 0.5) / n
            hh = 14 + (i * 53) % 10
            d.line([(x, bottom), (x, bottom - hh)], fill=(*color, 160), width=3)
    elif kind == "horizon_silhouette":
        n = 5
        for i in range(n):
            x = left + (right - left) * (i + 0.5) / n
            hh = 8 + (i * 41) % 12
            ww = (right - left) / n * 0.5
            d.polygon([(x - ww / 2, bottom), (x + ww / 2, bottom), (x, bottom - hh)], fill=(*color, 90))


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


def _hp_bar(draw, x0, y0, x1, y1, frac, color, danger_pulse=0.0, chip_frac=None):
    draw.rounded_rectangle([x0, y0, x1, y1], radius=6, fill=(40, 40, 48, 230))
    frac = max(0.0, min(1.0, frac))
    # "Chip damage" trail: a bright sliver showing HP recently lost, lagging
    # behind the real (colored) bar and catching down to it over ~0.6s —
    # standard fighting-game juice so a big hit reads as a visible drop, not
    # just an instant bar-length change.
    if chip_frac is not None:
        chip_frac = max(0.0, min(1.0, chip_frac))
        if chip_frac > frac:
            cx1 = x0 + (x1 - x0) * chip_frac
            draw.rounded_rectangle([x0, y0, cx1, y1], radius=6, fill=(235, 235, 240, 200))
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

    icons = [make_icon(f["kind"], f["color"], icon_size, f["material"]) for f in fighters]
    # A softly blurred copy for the motion trail — three sharp, fully-detailed
    # duplicate icons behind a fast-moving weapon read as "extra weapons"
    # rather than a speed blur and hurt readability, especially on small
    # ones like Dagger. A blurred ghost reads as motion, not a duplicate.
    trail_icons = [icon.filter(ImageFilter.GaussianBlur(icon_size * 0.035)) for icon in icons]
    ko_frame_by_idx = {i: frame for (frame, i, _, _) in battle["ko_events"]}
    first_hit_frame = min(battle["hit_frame_flags"].keys()) if battle["hit_frame_flags"] else None
    FIRST_BLOOD_FRAMES = int(fps * 0.9)

    font_scale = {2: 1.0, 3: 0.84, 4: 0.70}[n]
    title_font = get_font(int(h * 0.036 * font_scale))
    hp_font = get_font(max(14, int(h * 0.022 * font_scale)))
    win_font = get_font(int(h * 0.055))
    dmg_font = get_font(int(h * 0.026))
    first_blood_font = get_font(int(h * 0.048))
    clean_hit_font = get_font(int(h * 0.024))
    crit_font = get_font(int(h * 0.040))
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
    obstacle_icon = make_obstacle_icon(obstacle_radius, theme["border"][:3], theme.get("obstacle_kind", "rock")) if obstacles else None

    grad = np.zeros((h, w, 3), dtype=np.float32)
    for ch in range(3):
        grad[:, :, ch] = np.linspace(theme["top"][ch], theme["bottom"][ch], h).astype(np.float32)[:, None]

    # Atmospheric depth: a soft radial glow from a light source near the
    # top of the arena, tinted with the theme's own accent color — turns
    # the flat top-to-bottom band into something with real depth instead
    # of one uniform gradient across the whole width.
    gy, gx = np.mgrid[0:h, 0:w].astype(np.float32)
    light_x, light_y = w * 0.5, h * 0.16
    gdist = np.sqrt(((gx - light_x) / (w * 0.65)) ** 2 + ((gy - light_y) / (h * 0.5)) ** 2)
    glow_falloff = np.clip(1.0 - gdist, 0.0, 1.0) ** 2.2
    accent = np.array(theme["particle"], dtype=np.float32)
    # Weaker than before (was 0.4) — the background gradient itself is now
    # the light-background fix's main source of brightness (see
    # _brighten_theme_color), so a glow of the old strength stacked on top
    # of an already-light base would blow out toward white near the light
    # source instead of reading as a subtle accent.
    grad += glow_falloff[:, :, None] * accent[None, None, :] * 0.16

    base_bg = Image.fromarray(np.clip(grad, 0, 255).astype(np.uint8), mode="RGB")

    title_text = " vs ".join(f["name"] for f in fighters)
    n_frames = len(frames)

    intro_frames = int(INTRO_SECONDS * fps)

    # Cold-open source frame: the moment the finishing blow lands, before
    # any "{name} OUT!"/victory text has appeared (those render at later
    # frame indices), so the tease shows real impact without giving away
    # who wins. Falls back to the last real hit, or just the final frame,
    # if a battle somehow has no replay (shouldn't normally happen).
    if battle.get("replay_range"):
        cold_open_src_idx = battle["replay_range"][0]
    elif battle["hit_frame_flags"]:
        cold_open_src_idx = max(battle["hit_frame_flags"].keys())
    else:
        cold_open_src_idx = max(0, n_frames - 1)

    TRAIL_STEPS = ((3, 65), (7, 28))  # (frames back, alpha) — kept short/faint
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

    # Cinematic post-process: a soft radial vignette (darkened corners keep
    # the eye on the arena center) precomputed once so every frame only
    # pays for a cheap numpy multiply, not a re-render.
    vy, vx = np.mgrid[0:h, 0:w].astype(np.float32)
    vdist = np.sqrt(((vx - w / 2) / (w / 2)) ** 2 + ((vy - h / 2) / (h / 2)) ** 2)
    # Softened from the original (0.35 depth, 0.55 floor) now that the
    # background itself is light — the old vignette strength was tuned
    # against a near-black base where corner-darkening barely registered;
    # against a light base it would pull corners back toward the same dark
    # blending problem the background fix exists to solve.
    vignette_mask = np.clip(1.0 - 0.20 * np.clip(vdist - 0.55, 0, None) ** 1.4, 0.72, 1.0).astype(np.float32)[:, :, None]

    def make_frame(t):
        if t < COLD_OPEN_SECONDS:
            # Render the normal frame for the finishing-blow moment (via a
            # self-recursive call at the shifted timestamp it actually
            # falls at post-cold-open) and punch it up: a slow zoom-in for
            # tension, a quick white impact-flash at the very start to grab
            # a scrolling viewer's eye, and a fade to black right before
            # the cut into the "3-2-1" countdown.
            base_t = COLD_OPEN_SECONDS + INTRO_SECONDS + cold_open_src_idx / fps
            arr = make_frame(base_t).astype(np.float32)
            zoom = 1.05 + 0.15 * (t / COLD_OPEN_SECONDS)
            zw, zh = max(1, int(w / zoom)), max(1, int(h / zoom))
            zx0, zy0 = (w - zw) // 2, (h - zh) // 2
            zimg = Image.fromarray(arr.astype(np.uint8)).crop((zx0, zy0, zx0 + zw, zy0 + zh)).resize((w, h), Image.BICUBIC)
            arr = np.array(zimg).astype(np.float32)
            if t < 0.15:
                flash_amt = (1.0 - t / 0.15) ** 1.5
                arr = arr + (255 - arr) * flash_amt * 0.85
            fade_start = COLD_OPEN_SECONDS - 0.12
            if t > fade_start:
                arr = arr * (1 - (t - fade_start) / 0.12)
            return np.clip(arr, 0, 255).astype(np.uint8)

        t = t - COLD_OPEN_SECONDS
        raw_idx = int(round(t * fps))
        in_intro = raw_idx < intro_frames
        idx = 0 if in_intro else min(n_frames - 1, raw_idx - intro_frames)
        st = _intro_state(raw_idx) if in_intro else frames[idx]
        img = base_bg.copy().convert("RGBA")
        d = ImageDraw.Draw(img, "RGBA")

        particle_kind = theme.get("particle_kind", "up")
        for p in ambient_particles:
            speed = 8 + p["depth"] * 30
            twinkle = 0.5 + 0.5 * math.sin(t * 1.8 + p["phase"])
            r = p["r"]
            if particle_kind == "down":
                # snow: drifts gently downward
                py = (p["y"] + t * speed * 0.6) % (h * 1.1)
                px = (p["x"] + p["drift_x"] * t + 8 * math.sin(t * 0.5 + p["phase"])) % w
                alpha = int(35 + 65 * p["depth"])
                d.ellipse([px - r, py - r, px + r, py + r], fill=(*theme["particle"], alpha))
            elif particle_kind == "rain":
                # storm rain: fast falling streaks, no twinkle
                fall_speed = speed * 3.2
                py = (p["y"] + t * fall_speed) % (h * 1.1)
                px = (p["x"] + p["drift_x"] * 0.3 * t) % w
                alpha = int(40 + 60 * p["depth"])
                streak = 6 + p["depth"] * 10
                d.line([(px, py), (px - streak * 0.25, py - streak)], fill=(*theme["particle"], alpha), width=max(1, int(r * 0.6)))
            elif particle_kind == "sideways":
                # blown sand/dust: drifts across, low vertical bob
                px = (p["x"] + t * speed * 1.4) % w
                py = (p["y"] + 6 * math.sin(t * 0.6 + p["phase"])) % h
                alpha = int(30 + 60 * p["depth"] * twinkle)
                d.ellipse([px - r * 1.4, py - r * 0.6, px + r * 1.4, py + r * 0.6], fill=(*theme["particle"], alpha))
            elif particle_kind == "bubble":
                # rising bubbles: outline ring, not filled
                py = (p["y"] - t * speed * 0.5) % (h * 1.1)
                px = (p["x"] + 10 * math.sin(t * 0.7 + p["phase"])) % w
                alpha = int(35 + 55 * p["depth"])
                d.ellipse([px - r, py - r, px + r, py + r], outline=(*theme["particle"], alpha), width=max(1, int(r * 0.4)))
            elif particle_kind == "still_pulse":
                # glowing motes/stars: barely drift, pulse in place
                px = (p["x"] + 3 * math.sin(t * 0.4 + p["phase"])) % w
                py = (p["y"] + 3 * math.cos(t * 0.4 + p["phase"])) % h
                alpha = int(25 + 90 * p["depth"] * twinkle)
                d.ellipse([px - r, py - r, px + r, py + r], fill=(*theme["particle"], alpha))
            else:  # "up" — embers/motes rising
                py = (p["y"] - t * speed) % (h * 1.1)
                px = (p["x"] + p["drift_x"] * t + 8 * math.sin(t * 0.5 + p["phase"])) % w
                alpha = int(30 + 70 * p["depth"] * twinkle)
                d.ellipse([px - r, py - r, px + r, py + r], fill=(*theme["particle"], alpha))

        d.rounded_rectangle([left, top, right, bottom], radius=18, outline=theme["border"], width=4)
        for gx in range(left, right, int(w * 0.09)):
            d.line([(gx, top), (gx, bottom)], fill=theme["grid"], width=1)
        for gy in range(top, bottom, int(w * 0.09)):
            d.line([(left, gy), (right, gy)], fill=theme["grid"], width=1)

        _draw_arena_edge_decor(d, theme.get("edge_kind", "none"), left, top, right, bottom, theme["particle"], t)

        if obstacle_icon is not None:
            for (ox, oy) in obstacles:
                img.alpha_composite(obstacle_icon, (int(ox - obstacle_icon.width / 2), int(oy - obstacle_icon.height / 2)))

        tw = d.textlength(title_text, font=title_font)
        d.text((w / 2 - tw / 2, h * 0.045), title_text, font=title_font, fill=(255, 255, 255, 255))

        danger_pulse = 0.5 + 0.5 * math.sin(t * 9.0)
        CHIP_DECAY_FRAMES = int(fps * 0.6)
        for i, f in enumerate(fighters):
            bx0 = bar_xs[i]
            real_frac = st["hp"][i] / START_HP
            if in_intro:
                chip_frac = real_frac
            else:
                lag_idx = max(0, idx - CHIP_DECAY_FRAMES)
                chip_frac = frames[lag_idx]["hp"][i] / START_HP
            _hp_bar(d, bx0, bar_y, bx0 + bar_w, bar_y + bar_h, real_frac, f["color"], danger_pulse, chip_frac)
            label = f"{f['name']}  {int(st['hp'][i])}"
            lw = d.textlength(label, font=hp_font)
            lx = min(max(bx0, bx0 + bar_w / 2 - lw / 2), bar_area_x1 - lw)
            d.text((lx, bar_y + bar_h + h * 0.008), label, font=hp_font, fill=(*f["color"], 255))

        flash_alpha, flash_xy, flash_style = 0, None, "metal"
        dmg_popup = None
        shake_dx = shake_dy = 0.0
        punch_age = {}  # fighter_idx -> frames since a hit they were part of
        block_flash_alpha, block_flash_xy = 0, None
        clean_tag = None  # (x, y, age, alpha) — "CLEAN HIT!" callout
        crit_tag = None  # (x, y, age, alpha) — "CRITICAL!" callout
        parry_tag = None  # (x, y, age, alpha) — "PARRY!" callout
        if not in_intro:
            for hi in range(max(0, idx - 12), idx + 1):
                if hi not in battle["hit_frame_flags"]:
                    continue
                hx, hy, dmg, hi1, hi2, hit_type, is_crit = battle["hit_frame_flags"][hi]
                age = idx - hi
                if hit_type == "block":
                    # Handle-vs-handle: a cheap, quiet parry spark only — no
                    # flash/shake/damage-popup/weapon-pop, so a "block" reads
                    # as visibly weaker than a real hit instead of getting
                    # the same full-strength treatment every collision used
                    # to get.
                    if age <= 5:
                        a = max(0, int(140 * (1 - age / 5.0)))
                        if a > block_flash_alpha:
                            block_flash_alpha, block_flash_xy = a, (hx, hy)
                    continue
                # A crit's flash burns brighter and lingers a couple frames
                # longer than a normal hit; everything else (shake, popup)
                # gets a multiplier below.
                flash_life = 6 if is_crit else 4
                if age <= flash_life:
                    a = max(0, int((255 if is_crit else 230) * (1 - age / flash_life)))
                    if a > flash_alpha:
                        flash_alpha, flash_xy = a, (hx, hy)
                        flash_style = _impact_style(fighters[hi1]["material"], fighters[hi2]["material"])
                if dmg > 0 and age <= 10:
                    pa = max(0, int(255 - age * 26))
                    if dmg_popup is None or age < dmg_popup[2]:
                        dmg_popup = (hx, hy - age * 3.2, age, pa, dmg, is_crit)
                shake_life = 7 if is_crit else 5
                if age <= shake_life:
                    # a parry deals no damage but still lands as a hard clang,
                    # so give it a fixed mid-strength shake instead of the
                    # dmg-scaled one
                    unit = 4.0 if hit_type == "parry" else min(7.0, dmg / 18)
                    amt = max(0.0, (shake_life - age)) * unit * (1.8 if is_crit else 1.0)
                    shake_dx = (_det_jitter(hi) * 2 - 1) * amt
                    shake_dy = (_det_jitter(hi + 4096) * 2 - 1) * amt
                if age <= 4:
                    for fi in (hi1, hi2):
                        if fi not in punch_age or age < punch_age[fi]:
                            punch_age[fi] = age
                if hit_type == "parry" and age <= 11:
                    pa = max(0, int(255 * (1 - age / 11.0)))
                    if parry_tag is None or age < parry_tag[2]:
                        parry_tag = (hx, hy, age, pa)
                elif is_crit and age <= 12:
                    pa = max(0, int(255 * (1 - age / 12.0)))
                    if crit_tag is None or age < crit_tag[2]:
                        crit_tag = (hx, hy, age, pa)
                elif hit_type == "clean" and age <= 9:
                    pa = max(0, int(255 * (1 - age / 9.0)))
                    if clean_tag is None or age < clean_tag[2]:
                        clean_tag = (hx, hy, age, pa)

        obs_flash_alpha, obs_flash_xy = 0, None
        if not in_intro:
            for hi in range(max(0, idx - 8), idx + 1):
                if hi not in battle["obstacle_hit_frames"]:
                    continue
                ohx, ohy = battle["obstacle_hit_frames"][hi]
                age = idx - hi
                if age <= 6:
                    a = max(0, int(200 * (1 - age / 6.0)))
                    if a > obs_flash_alpha:
                        obs_flash_alpha, obs_flash_xy = a, (ohx, ohy)

        wall_flash_alpha, wall_flash_xy = 0, None
        if not in_intro:
            for hi in range(max(0, idx - 5), idx + 1):
                if hi not in battle["wall_hit_frames"]:
                    continue
                wxh, wyh = battle["wall_hit_frames"][hi]
                age = idx - hi
                if age <= 4:
                    a = max(0, int(130 * (1 - age / 4.0)))
                    if a > wall_flash_alpha:
                        wall_flash_alpha, wall_flash_xy = a, (wxh, wyh)

        muzzle_alpha, muzzle_info = 0, None
        proj_hit_alpha, proj_hit_xy = 0, None
        if not in_intro:
            for hi in range(max(0, idx - 3), idx + 1):
                if hi in battle["muzzle_flash_frames"]:
                    mfx, mfy, mfang = battle["muzzle_flash_frames"][hi]
                    age = idx - hi
                    if age <= 3:
                        a = max(0, int(220 * (1 - age / 3.0)))
                        if a > muzzle_alpha:
                            muzzle_alpha, muzzle_info = a, (mfx, mfy, mfang)
            for hi in range(max(0, idx - 5), idx + 1):
                if hi in battle["projectile_hit_frames"]:
                    phx, phy, pdmg, psh, ptg = battle["projectile_hit_frames"][hi]
                    age = idx - hi
                    if age <= 5:
                        a = max(0, int(220 * (1 - age / 5.0)))
                        if a > proj_hit_alpha:
                            proj_hit_alpha, proj_hit_xy = a, (phx, phy)

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
                    ghost = _tinted(trail_icons[i], al / 255)
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

            _draw_arena_impact_fx(d, theme.get("impact_fx", "dust_ring"), fx, fy, elapsed, flash_alpha, theme["particle"])

        if block_flash_alpha > 0:
            # A handle-vs-handle block — deliberately the plainest reaction
            # in the file (smaller/quieter than even the obstacle bounce):
            # a small pale ring with no sparks, no arena impact FX, so it
            # unmistakably reads as "nothing happened" next to a real hit.
            bfx, bfy = block_flash_xy
            block_elapsed = 1.0 - block_flash_alpha / 140.0
            ring_r = 8 + block_elapsed * 12
            d.ellipse([bfx - ring_r, bfy - ring_r, bfx + ring_r, bfy + ring_r], outline=(225, 225, 232, block_flash_alpha), width=2)

        if clean_tag is not None:
            ctx, cty, ct_age, ct_alpha = clean_tag
            # A finishing blow is very often also a "clean" hit, and this
            # tag drifting up from the same spot the "{name} OUT!" banner
            # occupies made the two pile into illegible overlapping text —
            # found via a UI audit render, not a viewer report. The KO
            # banner is the more important message at that exact moment, so
            # it wins; suppress CLEAN HIT! whenever one is active nearby.
            near_ko = any(
                0 <= idx - koi <= KO_FADE_FRAMES and math.hypot(kx - ctx, ky - cty) < h * 0.12
                for (koi, fi, kx, ky) in battle["ko_events"]
            )
            # A crit/parry callout (below) always outranks CLEAN HIT! — when
            # one is on screen the smaller yellow tag is just noise stacked
            # on top of it, so drop it entirely for those few frames.
            if not near_ko and crit_tag is None and parry_tag is None:
                ct_text = "CLEAN HIT!"
                ctw = d.textlength(ct_text, font=clean_hit_font)
                ct_y = cty - h * 0.05 - ct_age * 1.6
                d.text((ctx - ctw / 2, ct_y), ct_text, font=clean_hit_font, fill=(255, 235, 90, ct_alpha), stroke_width=2, stroke_fill=(0, 0, 0, ct_alpha))

        if crit_tag is not None:
            crx, cry, cr_age, cr_alpha = crit_tag
            # Bold gold "CRITICAL!" that pops in slightly oversized and
            # settles — bigger and higher than CLEAN HIT! so it clearly
            # outranks it when a crit is also a clean hit. Drawn straight
            # over the KO banner is fine: a crit finishing blow is exactly
            # the beat we want to call out, and the slow-mo replay re-shows
            # it anyway.
            cr_scale = 1.25 - min(1.0, cr_age / 4.0) * 0.25
            cf = get_font(max(20, int(crit_font.size * cr_scale))) if hasattr(crit_font, "size") else crit_font
            cr_text = "CRITICAL!"
            crw = d.textlength(cr_text, font=cf)
            cr_y = cry - h * 0.085 - cr_age * 1.4
            # keep the whole word on screen even when the impact was right
            # against a wall
            cr_x = min(max(w * 0.03, crx - crw / 2), w * 0.97 - crw)
            d.text((cr_x, cr_y), cr_text, font=cf, fill=(255, 205, 45, cr_alpha), stroke_width=3, stroke_fill=(150, 20, 0, cr_alpha))

        if parry_tag is not None and crit_tag is None:
            prx, pry, pr_age, pr_alpha = parry_tag
            # Cyan-white "PARRY!" — same pop-in as the crit tag but a cold
            # colour, so a deflection reads as distinct from a damage crit at
            # a glance.
            pr_scale = 1.25 - min(1.0, pr_age / 4.0) * 0.25
            pf = get_font(max(20, int(crit_font.size * pr_scale))) if hasattr(crit_font, "size") else crit_font
            pr_text = "PARRY!"
            prw = d.textlength(pr_text, font=pf)
            pr_y = pry - h * 0.085 - pr_age * 1.4
            pr_x = min(max(w * 0.03, prx - prw / 2), w * 0.97 - prw)
            d.text((pr_x, pr_y), pr_text, font=pf, fill=(150, 235, 255, pr_alpha), stroke_width=3, stroke_fill=(10, 40, 70, pr_alpha))

        if obs_flash_alpha > 0:
            # a weapon bounced off the static obstacle — give it its own
            # small themed reaction so the obstacle reads as a real object
            # being struck, not just an inert prop.
            ofx, ofy = obs_flash_xy
            obs_elapsed = 1.0 - obs_flash_alpha / 200.0
            _draw_arena_impact_fx(d, theme.get("impact_fx", "dust_ring"), ofx, ofy, obs_elapsed, obs_flash_alpha, theme["border"][:3])
            ring_r = 10 + obs_elapsed * 16
            d.ellipse([ofx - ring_r, ofy - ring_r, ofx + ring_r, ofy + ring_r], outline=(*theme["border"][:3], obs_flash_alpha), width=3)

        if wall_flash_alpha > 0:
            # a small, quiet spark where a weapon clipped the arena boundary
            # — deliberately lighter than the obstacle reaction since it
            # fires far more often (cooldown-gated above).
            wfx, wfy = wall_flash_xy
            wall_elapsed = 1.0 - wall_flash_alpha / 130.0
            ring_r = 6 + wall_elapsed * 10
            d.ellipse([wfx - ring_r, wfy - ring_r, wfx + ring_r, wfy + ring_r], outline=(*theme["border"][:3], wall_flash_alpha), width=2)

        if not in_intro:
            for (px, py, pang) in st.get("projectiles", []):
                # a small streaking bullet with a short motion trail, drawn
                # every frame it's alive (independent of the flash/spark
                # events below, which only mark the muzzle and the impact).
                prad = math.radians(pang)
                trail_len = icon_size * 0.16
                tx2 = px - math.cos(prad) * trail_len
                ty2 = py - math.sin(prad) * trail_len
                d.line([(tx2, ty2), (px, py)], fill=(255, 225, 120, 190), width=max(2, int(icon_size * 0.02)))
                br = icon_size * 0.028
                d.ellipse([px - br, py - br, px + br, py + br], fill=(255, 250, 210, 255))

        if muzzle_alpha > 0:
            mfx, mfy, mfang = muzzle_info
            mrad = math.radians(mfang)
            flx = mfx + math.cos(mrad) * icon_size * 0.22
            fly = mfy + math.sin(mrad) * icon_size * 0.22
            d.ellipse([flx - 15, fly - 15, flx + 15, fly + 15], fill=(255, 225, 120, muzzle_alpha))
            d.ellipse([flx - 6, fly - 6, flx + 6, fly + 6], fill=(255, 255, 235, muzzle_alpha))

        if proj_hit_alpha > 0:
            phx, phy = proj_hit_xy
            for k in range(6):
                pang2 = math.radians(k * 60 + (int(phx) % 30))
                x2 = phx + math.cos(pang2) * 15
                y2 = phy + math.sin(pang2) * 15
                d.line([(phx, phy), (x2, y2)], fill=(255, 235, 170, proj_hit_alpha), width=2)
            d.ellipse([phx - 6, phy - 6, phx + 6, phy + 6], fill=(255, 250, 220, proj_hit_alpha))

        if not in_intro:
            # A near-simultaneous double KO (two fighters eliminated close
            # together in position and time — e.g. a mutual finishing
            # clash) previously drew both "{name} OUT!" banners at the same
            # spot, piling into illegible overlapping text. Stagger each
            # additional banner that lands near an already-placed one
            # further up the screen instead.
            placed_ko_xy = []
            for koi, fi, kx, ky in battle["ko_events"]:
                age = idx - koi
                if age < 0 or age > KO_FADE_FRAMES:
                    continue
                pa = max(0, int(255 * (1 - age / KO_FADE_FRAMES)))
                if pa <= 0:
                    continue
                stack = sum(1 for (pkx, pky) in placed_ko_xy if math.hypot(pkx - kx, pky - ky) < h * 0.1)
                placed_ko_xy.append((kx, ky))
                r = 20 + age * 4
                d.ellipse([kx - r, ky - r, kx + r, ky + r], outline=(255, 80, 60, pa), width=4)
                label = ko_text_template.format(name=fighters[fi]['name'])
                lw = d.textlength(label, font=ko_font)
                label_y = ky - r - 26 - stack * (h * 0.032)
                d.text((kx - lw / 2, label_y), label, font=ko_font, fill=(255, 110, 90, pa), stroke_width=2, stroke_fill=(0, 0, 0, pa))

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
                if not in_intro:
                    cpos = st.get("chain_pos")
                    if cpos is not None and i < len(cpos) and cpos[i] is not None:
                        hx2, hy2 = cpos[i]
                        col = fighters[i]["color"]
                        d.line([(x, y), (hx2, hy2)], fill=(*col, 150), width=max(1, int(icon_size * 0.03)))
                        orb_r = icon_size * 0.06
                        d.ellipse([hx2 - orb_r, hy2 - orb_r, hx2 + orb_r, hy2 + orb_r], fill=(*col, 220))
                        d.ellipse([hx2 - orb_r * 0.5, hy2 - orb_r * 0.5, hx2 + orb_r * 0.5, hy2 + orb_r * 0.5], fill=(255, 255, 255, 200))
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
            px, py, _, pa, dmg, popup_crit = dmg_popup
            # Same overlap problem as CLEAN HIT! above: a finishing blow's
            # damage number can drift up right into the "{name} OUT!"
            # banner's territory. Suppress it there too — the OUT! banner
            # already conveys the moment mattered.
            near_ko = any(
                0 <= idx - koi <= KO_FADE_FRAMES and math.hypot(kx - px, ky - py) < h * 0.12
                for (koi, fi, kx, ky) in battle["ko_events"]
            )
            if not near_ko:
                dtext = f"-{dmg}"
                # Crit damage numbers are gold and drawn a size up, so the
                # big number reads as "that one hurt" at a glance.
                dfont = get_font(int(dmg_font.size * 1.35)) if (popup_crit and hasattr(dmg_font, "size")) else dmg_font
                dfill = (255, 205, 45, pa) if popup_crit else (255, 90, 70, pa)
                dw = d.textlength(dtext, font=dfont)
                d.text((px - dw / 2, py), dtext, font=dfont, fill=dfill, stroke_width=2, stroke_fill=(0, 0, 0, pa))

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

        arr = np.array(img.convert("RGB")).astype(np.float32)
        # A punchier, "яркий" (vibrant) saturation + contrast lift and the
        # precomputed vignette — a real color grade, not a flat render.
        gray = arr.mean(axis=-1, keepdims=True)
        arr = gray + (arr - gray) * 1.32
        arr = (arr - 128.0) * 1.08 + 128.0
        arr *= vignette_mask
        arr = np.clip(arr, 0, 255).astype(np.uint8)
        if shake_dx or shake_dy:
            arr = np.roll(arr, (int(round(shake_dy)), int(round(shake_dx))), axis=(0, 1))
        return arr

    duration = COLD_OPEN_SECONDS + (intro_frames + n_frames) / fps
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


def _obstacle_clack():
    """A short, higher-pitched knock for a weapon bouncing off a static
    arena obstacle — deliberately quieter/shorter than a fighter-vs-fighter
    hit so it reads as scenery feedback, not a real clash."""
    dur = 0.12
    n = int(SR * dur)
    t = np.linspace(0, dur, n, endpoint=False)
    env = np.exp(-t * 40)
    tone = np.sin(2 * np.pi * 220 * t) * np.exp(-t * 60)
    noise = np.random.default_rng(int(dur * 10000)).uniform(-1, 1, n) * np.exp(-t * 50) * 0.35
    sfx = (tone * 0.6 + noise) * env
    return sfx.astype(np.float32)


def _gunshot():
    """A short synthesized pistol crack — broadband noise burst plus a low
    thump, no tonal ring (real gunfire has almost none)."""
    dur = 0.11
    n = int(SR * dur)
    t = np.linspace(0, dur, n, endpoint=False)
    env = np.exp(-t * 45)
    noise = np.random.default_rng(int(dur * 88888)).uniform(-1, 1, n)
    thump = np.sin(2 * np.pi * 130 * t) * np.exp(-t * 70)
    sfx = (noise * 0.75 + thump * 0.5) * env
    return sfx.astype(np.float32)


def _hit_sound(material_a, material_b, intensity):
    a = MATERIAL_SFX.get(material_a, _clang_metal)(intensity)
    b = MATERIAL_SFX.get(material_b, _clang_metal)(intensity)
    n = max(len(a), len(b))
    out = np.zeros(n, dtype=np.float32)
    out[: len(a)] += a * (0.75 if material_a != material_b else 1.0)
    out[: len(b)] += b * (0.75 if material_a != material_b else 1.0)
    # A punchier "hook" layer on every hit regardless of material: a sharp
    # sub-bass transient (like a kick-drum click) at the onset for felt
    # weight, plus mild soft-clip saturation for bite/aggression — layered
    # on top of, not replacing, each material's own tonal identity above.
    punch_dur = 0.05
    pn = int(SR * punch_dur)
    pt = np.linspace(0, punch_dur, pn, endpoint=False)
    punch = np.sin(2 * np.pi * 60 * pt) * np.exp(-pt * 90) * (0.5 + 0.5 * intensity)
    out[:pn] += punch
    out = np.tanh(out * 1.35) * 0.9
    return out.astype(np.float32)


def _hook_sting():
    """A short, punchy attention-grab for the very first instant of the
    video (during the cold-open flash) — a fast pitch-rising noise
    whoosh into a sharp low boom, the kind of trailer-style sting meant to
    register even for a viewer scrolling a muted, autoplaying feed."""
    dur = 0.4
    n = int(SR * dur)
    t = np.linspace(0, dur, n, endpoint=False)
    rng = np.random.default_rng(4242)
    noise = rng.uniform(-1, 1, n)
    # Rising "whoosh": a slowly-opening low-pass via a rising cutoff proxy
    # (blend raw noise in more as t increases) plus a rising pitched tone.
    open_amt = np.clip(t / 0.22, 0, 1)
    rise_tone = np.sin(2 * np.pi * (200 + 1400 * open_amt) * t)
    whoosh = (noise * 0.5 + rise_tone * 0.5) * np.clip(1.2 - t / 0.22, 0, 1) * open_amt
    boom_t = np.maximum(0, t - 0.18)
    boom = np.sin(2 * np.pi * 68 * boom_t) * np.exp(-boom_t * 9) * (t > 0.18)
    boom_click = np.exp(-boom_t * 120) * (t > 0.18)
    sfx = whoosh * 0.7 + boom * 0.9 + boom_click * 0.6
    return np.tanh(sfx * 1.2).astype(np.float32)


def _victory_chime():
    """The finale/victory sound — bigger and punchier than the original
    plain 3-note sine chime, to match this round's "hook" pass on the rest
    of the audio: a sub-bass impact thump ties the victory banner's
    appearance to a felt hit, a 4-note rising arpeggio (each note layered
    with soft overtones, not a bare sine, for a real bell-like richness)
    resolves into a sustained triumphant chord, capped with a short high
    shimmer for sparkle."""
    parts = []  # (start_time, samples)

    thump_dur = 0.18
    tn = int(SR * thump_dur)
    tt = np.linspace(0, thump_dur, tn, endpoint=False)
    thump = np.sin(2 * np.pi * 70 * tt) * np.exp(-tt * 16) * 0.9
    parts.append((0.0, thump))

    notes = [523.25, 659.25, 783.99, 1046.50]  # C5 E5 G5 C6, rising arpeggio
    t_cursor = 0.05
    for f in notes:
        dur = 0.26
        n = int(SR * dur)
        t = np.linspace(0, dur, n, endpoint=False)
        env = np.exp(-t * 3.2)
        tone = (np.sin(2 * np.pi * f * t) * 0.7
                + np.sin(2 * np.pi * f * 2 * t) * 0.2
                + np.sin(2 * np.pi * f * 3 * t) * 0.1)
        parts.append((t_cursor, tone * env * 0.45))
        t_cursor += 0.11

    chord_dur = 0.6
    cn = int(SR * chord_dur)
    ct = np.linspace(0, chord_dur, cn, endpoint=False)
    cenv = np.exp(-ct * 2.0)
    chord = sum(np.sin(2 * np.pi * f * ct) for f in notes[:3]) / 3
    parts.append((t_cursor, chord * cenv * 0.5))

    shimmer_dur = 0.35
    sn = int(SR * shimmer_dur)
    st = np.linspace(0, shimmer_dur, sn, endpoint=False)
    senv = np.exp(-st * 6)
    shimmer = (np.sin(2 * np.pi * 2093 * st) + np.sin(2 * np.pi * 2637 * st) * 0.7) * senv * 0.15
    parts.append((t_cursor + 0.05, shimmer))

    total_dur = max(start + len(p) / SR for start, p in parts)
    n_total = int(total_dur * SR) + 1
    out = np.zeros(n_total, dtype=np.float32)
    for start, p in parts:
        pos = int(start * SR)
        end = min(n_total, pos + len(p))
        if end > pos:
            out[pos:end] += p[: end - pos]
    return np.tanh(out * 1.1).astype(np.float32)


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
    """Renders the cold-open sting + countdown beeps + all clash + victory
    sounds into one stereo float32 array. Timeline matches
    build_battle_clip's video exactly: COLD_OPEN_SECONDS tease, then
    INTRO_SECONDS of countdown, then the battle itself."""
    fps = battle["fps"]
    T0 = COLD_OPEN_SECONDS + INTRO_SECONDS
    duration = T0 + len(battle["frames"]) / fps
    n_samples = int(duration * SR) + SR
    buf = np.zeros(n_samples, dtype=np.float32)

    def _add(t, sfx, vol=1.0):
        pos = int(t * SR)
        end = min(n_samples, pos + len(sfx))
        if end > pos:
            buf[pos:end] += sfx[: end - pos] * vol

    # The audio half of the cold-open hook — lands right as the visual
    # flash does, so a viewer scrolling with sound on registers something
    # happened even before the countdown starts.
    _add(0.0, _hook_sting(), vol=0.95)

    quarter = INTRO_SECONDS / 4
    for i in range(3):
        _add(COLD_OPEN_SECONDS + i * quarter, _beep(700, 0.10, 0.55))
    _add(COLD_OPEN_SECONDS + 3 * quarter, _fight_horn())

    fighters = battle["fighters"]
    dmgs = [v[2] for v in battle["hit_frame_flags"].values() if v[5] != "block"]
    max_dmg = max(dmgs) if dmgs else 1.0

    for frame_idx, (_, _, dmg, i1, i2, hit_type, is_crit) in battle["hit_frame_flags"].items():
        t = T0 + frame_idx / fps
        if hit_type == "block":
            # A handle bump gets its own quiet, distinct "tink" instead of a
            # scaled-down clash sound — audibly different from a real hit,
            # not just quieter.
            _add(t, _obstacle_clack(), vol=0.35)
            continue
        if hit_type == "parry":
            # Bright, ringing double-clang — no low-end thud (nothing landed),
            # just steel on steel.
            _add(t, _clang_metal(1.0), vol=0.9)
            _add(t + 0.04, _clang_metal(0.6), vol=0.5)
            continue
        mat_a = fighters[i1]["material"]
        mat_b = fighters[i2]["material"]
        _add(t, _hit_sound(mat_a, mat_b, dmg / max(1.0, max_dmg)))
        if is_crit:
            # Layer a full-intensity metal clang + low blunt boom over the
            # normal hit so a crit is unmistakably heavier on the ears, not
            # just a louder copy of the same sound.
            _add(t, _clang_metal(1.0), vol=0.7)
            _add(t, _thud_blunt(1.0), vol=0.6)

    for frame_idx in battle["obstacle_hit_frames"]:
        t = T0 + frame_idx / fps
        _add(t, _obstacle_clack(), vol=0.5)

    for frame_idx in battle["wall_hit_frames"]:
        t = T0 + frame_idx / fps
        _add(t, _obstacle_clack(), vol=0.22)

    for frame_idx in battle["muzzle_flash_frames"]:
        t = T0 + frame_idx / fps
        _add(t, _gunshot(), vol=0.7)

    for frame_idx in battle["projectile_hit_frames"]:
        t = T0 + frame_idx / fps
        _add(t, _clang_metal(0.55), vol=0.5)

    finale_t = T0 + battle["finale_start"] / fps
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

    # A faint, blurred obstacle silhouette behind the weapon icons so the
    # thumbnail hints at the same arena identity as the video, without
    # competing with the icons/title for attention.
    bg_obstacle = make_obstacle_icon(int(h * 0.22), theme["border"][:3], theme.get("obstacle_kind", "rock"))
    bg_obstacle = bg_obstacle.filter(ImageFilter.GaussianBlur(3))
    bg_obstacle.putalpha(bg_obstacle.split()[3].point(lambda p: int(p * 0.30)))
    img.alpha_composite(bg_obstacle, (int(w / 2 - bg_obstacle.width / 2), int(h / 2 - bg_obstacle.height / 2)))

    d = ImageDraw.Draw(img, "RGBA")
    _draw_arena_edge_decor(d, theme.get("edge_kind", "none"), 0, 0, w, h, theme["particle"], 0)
    vs_font = get_font(int(h * 0.24))
    title_font = get_font(int(h * 0.075))

    if n == 2:
        icon_size = int(h * 0.66)
        left_icon = make_icon(fighters[0]["kind"], fighters[0]["color"], icon_size, fighters[0]["material"]).rotate(18, resample=Image.BICUBIC, expand=True)
        right_icon = make_icon(fighters[1]["kind"], fighters[1]["color"], icon_size, fighters[1]["material"]).rotate(-18, resample=Image.BICUBIC, expand=True)
        img.alpha_composite(left_icon, (int(w * 0.03), int(h / 2 - left_icon.height / 2)))
        img.alpha_composite(right_icon, (int(w * 0.97 - right_icon.width), int(h / 2 - right_icon.height / 2)))

        vs_text = "VS"
        tw = d.textlength(vs_text, font=vs_font)
        d.text((w / 2 - tw / 2, h * 0.30), vs_text, font=vs_font, fill=(255, 215, 60, 255), stroke_width=8, stroke_fill=(0, 0, 0, 255))

        title_text = f"{fighters[0]['name']} vs {fighters[1]['name']}"
    else:
        icon_size = int(h * (0.42 if n == 3 else 0.36))
        icons = [make_icon(f["kind"], f["color"], icon_size, f["material"]) for f in fighters]
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
