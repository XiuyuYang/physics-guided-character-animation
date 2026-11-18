"""Matched drop and crowd settings shared by the GPU simulation and review."""
from math import pi

DROPS = {"palm": (.06, 1000.), "medium": (.225, 1000.), "large": (.50, 1000.)}


def dense_spawns(size=16):
    side = {16: 4, 100: 10}[size]
    center = (side-1)/2
    return tuple((round(.90*(row-center) + .12*(lane % 2), 3),
                  round(.85*(lane-center), 3))
                 for lane in range(side) for row in range(side))


def runner_group(actor, mode):
    return actor if mode == "isolated" else 0


def drop_mass(variant):
    radius, density = DROPS[variant]
    return 4/3*pi*radius**3*density
