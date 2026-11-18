"""Compare PhysX captures and transfer each measured PHC reaction to Manny."""
import argparse
import gzip
import json
import math
from pathlib import Path

import numpy as np
from scipy.spatial.transform import Rotation

from boulder_outcome import DOWN_IMPULSE, outcome, settle_frame
from contact_recovery import transition_path, transition_weight

TRACKS = {"pelvis": "Pelvis", "spine_01": "Torso", "spine_02": "Spine",
          "spine_03": "Spine", "spine_04": "Chest", "spine_05": "Chest",
          "neck_01": "Neck", "neck_02": "Neck", "head": "Head"}
for side in ("l", "r"):
    TRACKS.update({key+"_"+side: side.upper()+"_"+value for key,value in (
        ("clavicle","Thorax"),("upperarm","Shoulder"),("lowerarm","Elbow"),("hand","Wrist"),
        ("thigh","Hip"),("calf","Knee"),("foot","Ankle"),("ball","Toe"))})
CHILD = {"pelvis": "spine_01", "spine_01": "spine_02", "spine_03": "spine_04",
         "spine_05": "neck_01", "neck_02": "head"}
for side in ("l", "r"):
    CHILD.update({key+"_"+side: value+"_"+side for key,value in (
        ("clavicle","upperarm"),("upperarm","lowerarm"),("lowerarm","hand"),
        ("thigh","calf"),("calf","foot"),("foot","ball"))})


def read(folder, mode, case=None):
    with gzip.open(folder / (case or mode) / "boulder.json.gz", "rt", encoding="utf-8") as stream:
        capture = json.load(stream)
    if capture["fps"] != 30 or len(capture["frames"]) != 180 or capture["mode"] != mode:
        raise ValueError("Expected a complete matched boulder capture.")
    frames = capture["frames"]
    return capture, {k: np.asarray([f[k] for f in frames]) for k in
                     ("pose", "rot", "rock", "rock_force", "body_force")}


def collisions(hit, clear, radius):
    body_pos = hit["pose"]
    rock_pos = hit["rock"][:, :3]
    rock_contact = np.linalg.norm(hit["rock_force"][:, :2], axis=-1) > 250
    result = []
    for actor in range(body_pos.shape[1]):
        distance = body_pos[:, actor] - rock_pos[:, None, :]
        near = np.linalg.norm(distance, axis=-1) <= radius + .25
        horizontal = distance[:, :, :2]
        normal = horizontal / np.maximum(.01, np.linalg.norm(horizontal, axis=-1, keepdims=True))
        difference = hit["body_force"][:, actor, :, :2] - clear["body_force"][:, actor, :, :2]
        force = np.sum(np.maximum(0, np.sum(normal*difference, axis=-1))*near, axis=-1)
        events = np.flatnonzero(rock_contact & (force > 400))
        impulse = float(force[events].sum() / 30)
        result.append({"actor": actor + 1, "outcome": outcome(bool(len(events)), impulse),
                       "contact": events.tolist(), "impulse_proxy": impulse,
                       "peak_force_proxy": float(max(force[events], default=0)),
                       "pelvis_min_m": float(body_pos[:, actor, 0, 2].min())})
    return result


def direction_rotation(source, target):
    a, b = (v / np.linalg.norm(v) for v in (source, target))
    dot = float(np.clip(np.dot(a,b), -1, 1))
    axis = np.cross(a,b)
    if dot < -.99999:
        basis = np.eye(3)[np.argmin(np.abs(a))]
        axis = np.cross(a, basis)
    norm = np.linalg.norm(axis)
    if norm < 1e-8:
        return Rotation.identity()
    return Rotation.from_rotvec(axis * (math.acos(dot) / norm))


def blend(base, target, weight):
    return Rotation.from_rotvec((target * base.inv()).as_rotvec()*weight) * base


def ease(value):
    p = np.clip(value, 0, 1)
    return float(p*p*(3-2*p))


def fk(pose, parents):
    rotations = Rotation.from_quat(pose[:, 3:])
    world_pos, world_rot = [], []
    for i,p in enumerate(parents):
        world_pos.append(pose[i, :3] if p < 0 else world_pos[p] + world_rot[p].apply(pose[i,:3]))
        world_rot.append(rotations[i] if p < 0 else world_rot[p]*rotations[i])
    return np.asarray(world_pos), world_rot


def build(capture, hit, clear, manny, events, smooth=False):
    bones = manny["names"]
    parent = [bones.index(p) if p in bones else -1 for p in manny["parents"]]
    source = capture["names"]
    source_index = {bone: source.index(value) for bone,value in TRACKS.items() if bone in bones}
    assert all(key in source_index for key in ("pelvis", "head", "thigh_l", "thigh_r", "foot_l", "foot_r"))
    source_loop = np.asarray(manny["frames"])
    root = bones.index("root")
    original_shift = np.linalg.norm(source_loop[-1,root,:2] - source_loop[0,root,:2])
    control_speed = float(np.median(clear["pose"][-1,:,0,0]-clear["pose"][-31,:,0,0]))
    steps = round(original_shift / (len(source_loop)-1) / (control_speed*100/30) * len(source_loop))
    if not 10 <= steps <= 180:
        raise ValueError("Unexpected scaling between Manny run and PHC travel.")
    source_loop[:,root,:2] = source_loop[0,root,:2].copy()
    base_list = []
    for i in range(steps):
        offset = i/steps*len(source_loop)
        ia, weight = int(offset), offset % 1
        a, b = source_loop[ia], source_loop[(ia+1) % len(source_loop)]
        row = a*(1-weight)+b*weight
        row[:,3:] = blend(Rotation.from_quat(a[:,3:]),Rotation.from_quat(b[:,3:]),weight).as_quat()
        base_list.append(row)
    base = np.asarray(base_list)
    steps = len(base)
    rest_pos, _ = fk(np.asarray(manny["rest"]), parent)
    left = rest_pos[bones.index("thigh_l")] - rest_pos[bones.index("thigh_r")]
    forward = np.cross((0,0,1), left)
    yaw = -math.atan2(forward[1], forward[0])
    body_yaw = Rotation.from_euler("z", yaw)
    pelvis = bones.index("pelvis")
    # Manny's mesh is normally in-place. Explicit actor keys carry the captured world travel.
    native = [fk(frame, parent) for frame in base]
    reflection = np.array([1,-1,1])
    source_basis = np.array([-1,1,-1,1])
    rock = hit.get("rock")
    actors = []
    for i, event in enumerate(events):
        branch = event["outcome"]
        actual, control = hit["pose"][:,i], clear["pose"][:,i]
        center = actual[:,0] if branch != "clear" else control[:,0]
        location = center[:, :2].copy()
        first = event["contact"][0] if event["contact"] else -1
        last = event["contact"][-1] if event["contact"] else -1
        n = len(center)
        start = max(0, first-2) if first >= 0 else 0
        hold = None
        resume = None
        rendered = []
        if branch == "down":
            velocities = np.zeros(n)
            velocities[1:] = np.linalg.norm(np.diff(actual, axis=0), axis=-1).mean(1)
            motion = np.convolve(velocities, np.ones(5)/5, mode="same")
            limit = event.get("freeze_by",n)
            settle_start = event.get("first_fall",last+12)
            hold = settle_frame(center[:limit,2],motion[:limit],settle_start)
            location[hold:] = location[hold]
        if branch == "graze":
            resume = event.get("resume_requested", last+(32 if smooth else 23))
            if resume >= n or np.min(center[resume-8:resume,2]) < .7:
                raise ValueError("Light contact did not reach the running handoff.")
            if smooth:
                location = transition_path(location,last,resume,control_speed/30)
            else:
                location[resume:] = control[resume:,0,:2] + location[resume-1] - control[resume-1,0,:2]
        if branch != "clear":
            source_hit = hit["rot"][:,i] * source_basis
            source_reference = clear["rot"][:,i] * source_basis
            _, anchor_manny = native[start % steps]
            anchor_phc = Rotation.from_quat(source_reference[start])
            end = n if resume is None else resume
            for frame in range(start, end+1):
                if hold is not None and frame > hold:
                    rendered.append(rendered[-1])
                    continue
                sample = min(frame, n-1)
                slot = frame % steps
                track = base[slot].copy()
                _, running_world = native[slot]
                entry_start = first-1 if branch in ("reaction","tracked") else start
                entry = ease((frame-entry_start)/7)
                amount = entry if resume is None else entry*ease((resume-frame)/12)
                if smooth and resume is not None:
                    amount = entry*(1-transition_weight(float(np.clip((frame-last)/(resume-last),0,1))))
                world_rot = []
                run_source = Rotation.from_quat(source_reference[sample])
                impact_source = Rotation.from_quat(source_hit[sample])
                for j,name in enumerate(bones):
                    p = parent[j]
                    previous = world_rot[p] if p >= 0 else Rotation.identity()
                    local = Rotation.from_quat(track[j,3:])
                    if name in source_index:
                        k = source_index[name]
                        if branch in ("graze","tracked"):
                            delta = body_yaw.inv() * impact_source[k] * run_source[k].inv() * body_yaw
                            desired = delta * running_world[j]
                        else:
                            delta = body_yaw.inv() * impact_source[k] * anchor_phc[k].inv() * body_yaw
                            desired = delta * anchor_manny[j]
                            child = CHILD.get(name)
                            if child in source_index and parent[bones.index(child)] == j:
                                j_child = bones.index(child)
                                vector = (actual[sample,source_index[child]] - actual[sample,k])*reflection
                                target = body_yaw.inv().apply(vector)
                                default = desired.apply(track[j_child,:3])
                                if min(np.linalg.norm(target),np.linalg.norm(default)) > 1e-5:
                                    desired = direction_rotation(default,target)*desired
                        local = blend(local, previous.inv()*desired, amount)
                    world_rot.append(previous*local)
                    track[j,3:] = local.as_quat()
                height_delta = (center[sample,2]-control[sample,0,2])*100*amount
                track[root,2] += height_delta
                if branch in ("down", "reaction"):
                    computed, _ = fk(track,parent)
                    floor = min(computed[j,2] for j,key in enumerate(bones)
                                if key in ("ball_l","ball_r","hand_l","hand_r","head","calf_l","calf_r"))
                    track[root,2] += max(0, 5-floor) * amount
                if rendered:
                    prior = np.asarray(rendered[-1])[:,3:]
                    track[np.sum(prior*track[:,3:],axis=1)<0,3:] *= -1
                rendered.append(track.round(7).tolist())
        event.update(first=first if first >= 0 else None, last=last if last >= 0 else None,
                     start=start, hold=hold, resume=resume)
        actors.append({"event": event, "location": (location * [100,-100]).round(4).tolist(),
                       "keys": rendered})
    result = {"fps": 30, "frames": len(hit["pose"]),
            "mesh": manny["mesh"], "run": manny["run"], "bones": bones, "loop_frames": steps,
            "run_keys": np.concatenate((base,base[:1])).round(7).tolist(),
            "mesh_yaw": math.degrees(yaw),
            "actors": actors}
    if rock is not None:
        result["radius_cm"] = capture["radius"]*100
        result["rock"] = np.column_stack((rock[:,:3]*[100,-100,100],rock[:,3:7]*source_basis)).round(7).tolist()
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("batch",type=Path)
    parser.add_argument("manny",type=Path)
    parser.add_argument("output",type=Path)
    args=parser.parse_args()
    capture, hit=read(args.batch,"impact")
    alternate, clear=read(args.batch,"clear")
    if any(capture[key] != alternate[key] for key in ("radius","spawn","names","parents","fps")):
        raise ValueError("Mismatched physical control.")
    events=collisions(hit,clear,capture["radius"])
    if {event["outcome"] for event in events} != {"graze","down","clear"}:
        raise ValueError("Missing acceptance outcomes.")
    first = min(e["contact"][0] for e in events if e["contact"])
    if np.linalg.norm(hit["pose"][:first-1]-clear["pose"][:first-1],axis=-1).max() > .05:
        raise ValueError("Crowd diverged before contact.")
    manny=json.loads(args.manny.read_text(encoding="utf-8"))
    payload=build(capture,hit,clear,manny,events,smooth=True)
    args.output.write_text(json.dumps(payload,allow_nan=False,separators=(",",":")),encoding="utf-8")
    (args.batch/"contact-review.json").write_text(json.dumps({
        "fps":30,"down_impulse_proxy_threshold":DOWN_IMPULSE,"actors":events},indent=2),encoding="utf-8")
    print([(e["actor"], e["outcome"], round(e["impulse_proxy"]), e["hold"], e["resume"]) for e in events])


if __name__=="__main__":
    main()
