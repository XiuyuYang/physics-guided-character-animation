"""Matched single-body contact pulses for the Unreal comparison."""
import json
import os
from pathlib import Path
from xml.etree import ElementTree

import numpy as np

from phase2_trial import RunningTrial
from phase4_contract import RIG

TARGETS = ("Chest", "L_Shoulder", "L_Knee")
LEVELS = (250, 700)
EVENT = 60
DURATION = 4
OUTWARD = np.array([0., 1., 0.])


def probe_conditions():
    return [("baseline", "Pelvis", 1, -1, 0)] + [
        ("probe", body, 1, -1, level) for level in LEVELS for body in TARGETS]


def capsule_point(start, end, radius, outward):
    axis = (end-start) / np.linalg.norm(end-start)
    projection = float(np.dot(axis, outward))
    normal = outward - projection*axis
    length = np.linalg.norm(normal)
    if length < 1e-8:
        return (end if projection > 0 else start) + radius*outward
    return (start+end)/2 + (radius/length)*normal


class ContactProbeTrial(RunningTrial):
    trial_log = "contact-probe-done"
    pulse_frames = DURATION

    def __init__(self, env, torch, gymapi, gymtorch):
        super().__init__(env, torch, gymapi, gymtorch)
        from scipy.spatial.transform import Rotation

        self.rotations = Rotation
        self.conditions = probe_conditions()
        self.event = EVENT
        self.positions = torch.zeros_like(self.forces)
        self.contact_point = None
        self.capsules = {}
        tree = ElementTree.parse(RIG)
        for body in TARGETS:
            geom = tree.find(".//body[@name='{}']/geom".format(body))
            if geom is None or geom.attrib["type"] != "capsule":
                raise ValueError(f"{body} must have one specified capsule collider.")
            ends = np.fromstring(geom.attrib["fromto"], sep=" ").reshape(2,3)
            self.capsules[body] = ends, float(geom.attrib["size"])

    def prepare_events(self):
        pass

    def apply_force(self):
        _, body, axis, sign, force = self.conditions[len(self.results)]
        if not force or not self.event <= len(self.frames) < self.event + self.pulse_frames:
            return
        i = self.names.index(body)
        ends, radius = self.capsules[body]
        orientation = self.rotations.from_quat(self.env._rigid_body_rot[0,i].detach().cpu().numpy())
        position = self.env._rigid_body_pos[0,i]
        a,b = orientation.apply(ends) + position.detach().cpu().numpy()
        point = capsule_point(a,b,radius,OUTWARD)
        self.forces.zero_()
        self.forces[i,axis] = sign*force
        self.positions[i] = position.new_tensor(point)
        applied = self.env.gym.apply_rigid_body_force_at_pos_tensors(
            self.env.sim, self.gymtorch.unwrap_tensor(self.forces),
            self.gymtorch.unwrap_tensor(self.positions), self.gymapi.ENV_SPACE)
        if not applied:
            raise RuntimeError("PhysX rejected localized contact.")
        self.applied_force = force
        self.contact_point = point.tolist()

    def record_frame(self):
        frame = super().record_frame()
        frame["rot"] = self.env._rigid_body_rot[0].detach().cpu().tolist()
        frame["point"] = self.contact_point if self.applied_force else None
        return frame

    def save(self):
        path = Path(os.environ["PHC_REPORT_DIR"]) / "trials.json"
        draft = path.with_suffix(".tmp")
        draft.write_text(json.dumps({
            "phase":"contact_probe","dt":self.dt,"event":self.event,"pulse":self.pulse_frames,
            "names":self.names,"parents":self.parents,"trials":self.results,
        },ensure_ascii=False,allow_nan=False,separators=(",",":")),encoding="utf-8")
        draft.replace(path)
