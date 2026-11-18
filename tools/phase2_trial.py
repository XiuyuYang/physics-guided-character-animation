# -*- coding: utf-8 -*-
"""Matched running trials on the PHC GPU simulation."""
import json
import math
import os
from pathlib import Path

FRAME_COUNT = 180
PULSE_FRAMES = 6
LEVELS = (75, 700, 1800)
SCENARIOS = (
    ("side", "Pelvis", 1, 1),
    ("foot", "L_Toe", 0, -1),
    ("chest", "Chest", 0, -1),
)


def obstacle_force(position, velocity, plane, limit):
    """One-sided spring-damper that resists a foot moving into a plane."""
    if position <= plane or velocity <= 0:
        return 0
    return min(limit, 4500 * (position - plane) + 90 * velocity)


def classify(min_height, late_height, late_speed, ref_speed, late_error):
    if late_height < 0.7:
        return "fell" if min_height < 0.45 else "deviated"
    if late_speed >= 0.6 * ref_speed and late_error <= 0.35:
        return "running"
    if min_height < 0.45 and late_speed < 0.6 * ref_speed:
        return "stood"
    return "deviated"


def summarize(frames, baseline, dt, event, pelvis):
    def speed(key, start, end):
        return (frames[end][key][pelvis][0] - frames[start][key][pelvis][0]) / ((end-start)*dt)

    def error(frame):
        # Compare pose relative to its own pelvis to distinguish gait recovery
        # from a permanent spatial offset after the perturbation.
        actual, reference = frame["pose"], frame["reference"]
        aroot, rroot = actual[pelvis], reference[pelvis]
        return sum(math.sqrt(sum(((a[d]-aroot[d]) - (r[d]-rroot[d]))**2
                                 for d in range(3)))
                   for a, r in zip(actual, reference)) / len(reference)

    tail = frames[-30:]
    heights = [f["pose"][pelvis][2] for f in frames[event:]]
    late_height = sum(f["pose"][pelvis][2] for f in tail) / len(tail)
    late_error = sum(map(error, tail)) / len(tail)
    late_speed = speed("pose", len(frames)-31, len(frames)-1)
    ref_speed = speed("reference", len(frames)-31, len(frames)-1)
    path_error = max(math.dist(frame["pose"][pelvis][:2], other["pose"][pelvis][:2])
                     for frame, other in zip(frames[event:], baseline[event:]))
    return {
        "outcome": classify(min(heights), late_height, late_speed, ref_speed, late_error),
        "min_height": min(heights), "late_height": late_height,
        "late_speed": late_speed, "ref_speed": ref_speed, "late_pose_error": late_error,
        "max_path_difference": path_error, "early_pose_error": sum(map(error, frames[:event])) / event,
        "max_force": max(f["force"] for f in frames),
    }


class RunningTrial:
    pulse_frames = PULSE_FRAMES
    frame_count = FRAME_COUNT

    def __init__(self, env, torch, gymapi, gymtorch):
        self.env = env
        self.gymapi = gymapi
        self.gymtorch = gymtorch
        self.dt = float(env.dt)
        self.names = list(env._body_names)
        tree = env.skeleton_trees[0]
        if list(tree.node_names) != self.names:
            raise RuntimeError("PHC skeleton and simulation body order differ")
        self.parents = tree.parent_indices.tolist()
        self.pelvis = self.names.index("Pelvis")
        self.toe = self.names.index("L_Toe")
        self.feet = [[self.names.index(side + "_" + joint) for joint in ("Ankle", "Toe")]
                     for side in ("L", "R")]
        self.forces = torch.zeros((env._rigid_body_state.shape[0], 3), device=env.device)
        self.torques = torch.zeros_like(self.forces)
        self.frames = []
        self.results = []
        self.conditions = [("baseline", "Pelvis", 0, 1, 0)]
        self.conditions += [(*scenario, level) for scenario in SCENARIOS for level in LEVELS]
        self.event = 48
        self.plane = None
        self.applied_force = 0

    def apply_force(self):
        kind, body, axis, sign, force = self.conditions[len(self.results)]
        if not force or not self.event <= len(self.frames) < self.event + self.pulse_frames:
            return
        index = self.names.index(body)
        if kind == "foot":
            pos = float(self.env._rigid_body_pos[0, index, axis])
            vel = float(self.env._rigid_body_vel[0, index, axis])
            force = obstacle_force(pos, vel, self.plane, force)
        self.forces.zero_()
        self.forces[index, axis] = sign * force
        applied = self.env.gym.apply_rigid_body_force_tensors(
            self.env.sim, self.gymtorch.unwrap_tensor(self.forces),
            self.gymtorch.unwrap_tensor(self.torques), self.gymapi.ENV_SPACE)
        if not applied:
            raise RuntimeError(f"Isaac Gym rejected the Phase 2 force for {kind}")
        self.applied_force = force

    def record_frame(self):
        env = self.env
        times = env.progress_buf * env.dt + env._motion_start_times + env._motion_start_times_offset
        target = env._get_state_from_motionlib_cache(env._sampled_motion_ids, times, env._global_offset)
        contacts = env._contact_forces[0].detach().cpu().tolist()
        return {
            "pose": env._rigid_body_pos[0].detach().cpu().numpy().round(4).tolist(),
            "reference": target["rg_pos"][0].detach().cpu().numpy().round(4).tolist(),
            "feet": [round(sum(max(0, contacts[i][2]) for i in foot), 1) for foot in self.feet],
            "force": round(self.applied_force, 2),
            "progress": int(env.progress_buf[0]),
        }

    def on_control_step(self):
        self.frames.append(self.record_frame())
        self.applied_force = 0
        if len(self.frames) == self.frame_count:
            self.finish()

    def finish(self):
        kind, body, axis, sign, limit = self.conditions[len(self.results)]
        if kind == "baseline":
            self.prepare_events()
        control = self.frames if kind == "baseline" else self.results[0]["frames"]
        result = summarize(self.frames, control, self.dt, self.event, self.pelvis)
        result.update(kind=kind, body=body, axis=axis, sign=sign, limit=limit, frames=self.frames)
        self.results.append(result)
        self.save()
        print(self.trial_log, kind, limit, result["outcome"],
              "speed", round(result["late_speed"], 2), "error", round(result["late_pose_error"], 2),
              "force", result["max_force"], "early", round(result["early_pose_error"], 2), flush=True)
        if len(self.results) == len(self.conditions):
            os._exit(0)
        self.frames = []
        self.env.reset()

    trial_log = "phase2-done"

    def prepare_events(self):
        # Pick an advancing swing with 1 cm of initial plane penetration.
        self.event = max(range(37, 60), key=lambda i: (
            self.frames[i-1]["pose"][self.toe][0] - self.frames[i-3]["pose"][self.toe][0])
            * max(0, self.frames[i-1]["pose"][self.toe][2] - 0.05))
        self.plane = self.frames[self.event-1]["pose"][self.toe][0] - 0.01

    def save(self):
        path = Path(os.environ["PHC_REPORT_DIR"]) / "trials.json"
        draft = path.with_suffix(".tmp")
        payload = {"phase": "phase2", "dt": self.dt, "event": self.event,
                   "pulse_frames": PULSE_FRAMES, "obstacle_x": self.plane,
                   "names": self.names, "parents": self.parents, "trials": self.results}
        draft.write_text(json.dumps(payload, allow_nan=False, separators=(",", ":")), encoding="utf-8")
        draft.replace(path)
