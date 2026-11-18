# -*- coding: utf-8 -*-
"""Shared Phase 4 data rules, also loaded by Maya 2020's Python 2."""
import math
import os
from xml.etree import ElementTree

FPS = 30
SCHEMA = 1
RIG = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "third_party", "PHC", "phc", "data", "assets", "mjcf", "smpl_0_humanoid.xml")
DIRECTIONS = {"+X": (0, 1), "-X": (0, -1), "+Y": (2, 1), "-Y": (2, -1),
              "+Z": (1, -1), "-Z": (1, 1)}


def rig_layout():
    root = ElementTree.parse(RIG).find("worldbody/body")
    bones = list(root.iter("body"))
    names = [bone.attrib["name"] for bone in bones]
    parent = {child.attrib["name"]: i for i, bone in enumerate(bones)
              for child in bone.findall("body")}
    offsets = [list(map(float, bone.attrib["pos"].split())) for bone in bones]
    return names, [parent.get(name, -1) for name in names], offsets


def validate_job(job, names, sample_count):
    if job["body"] not in names:
        raise ValueError("Select a named body in the PHC skeleton.")
    if job["direction"] not in DIRECTIONS:
        raise ValueError("Choose a signed Maya world axis.")
    event, duration = job["event"], job["duration"]
    if type(event) is not int or type(duration) is not int or event < 1 or duration < 1:
        raise ValueError("Event and pulse length must be positive whole frames.")
    if event + duration + FPS >= sample_count or sample_count > 4000:
        raise ValueError("Use at most 4,000 source samples and leave 30 frames after the pulse.")
    strengths = job["strengths"]
    if not isinstance(strengths, list) or not strengths or any(
            type(v) not in (int, float) or math.isinf(v) or math.isnan(v) or v < .01 for v in strengths):
        raise ValueError("Enter at least one finite force in newtons (minimum 0.01 N).")
    if len(set(strengths)) != len(strengths):
        raise ValueError("Candidate strengths must differ.")


def conditions(job):
    axis, sign = DIRECTIONS[job["direction"]]
    return [("baseline", "Pelvis", 0, 1, 0)] + [
        ("pulse", job["body"], axis, sign, strength) for strength in job["strengths"]]


def to_maya(position, quaternion):
    x, y, z = position
    qx, qy, qz, w = quaternion
    return (100*x, 100*z, -100*y), (qx, qz, -qy, w)


def from_maya(position, quaternion):
    x, y, z = position
    qx, qy, qz, w = quaternion
    return (x/100, -z/100, y/100), (qx, -qz, qy, w)
