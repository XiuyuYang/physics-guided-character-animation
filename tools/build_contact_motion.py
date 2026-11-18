"""Create matched Unreal takes and target-bone marker tracks from PHC records."""
import argparse
import json
from pathlib import Path

import numpy as np
from scipy.spatial.transform import Rotation

from build_boulder_motion import blend, build, fk
from boulder_outcome import settle_frame
from contact_probe import DURATION, EVENT, LEVELS, probe_conditions
from contact_recovery import matching_phase, recovery_start, transition_path, transition_weight

LABEL = {"Chest": "CHEST", "L_Shoulder": "SHOULDER", "L_Knee": "LOWER LEG"}
MARKER = {"Chest": ("spine_05","neck_01",.28,12.),
          "L_Shoulder": ("upperarm_l","lowerarm_l",.24,8.),
          "L_Knee": ("calf_l","foot_l",.46,7.)}


def validated(dataset):
    cases = dataset["trials"]
    if (dataset["phase"] != "contact_probe" or dataset["event"] != EVENT or dataset["pulse"] != DURATION
            or abs(dataset["dt"]*30-1) > 1e-5
            or [tuple(c[k] for k in ("kind","body","axis","sign","limit")) for c in cases] != probe_conditions()):
        raise ValueError("Incomplete matched local contact batch.")
    control = cases[0]["frames"]
    for case in cases:
        if len(case["frames"]) != 180:
            raise ValueError("A contact take has missing frames.")
        for i, (frame, base) in enumerate(zip(case["frames"],control)):
            force = case["limit"] if EVENT <= i < EVENT+DURATION else 0
            if (frame["progress"] != i+1 or frame["reference"] != base["reference"]
                    or frame["force"] != force or (frame["point"] is None) != (force == 0)):
                raise ValueError(f"{case['body']}: mismatched recorded pulse or time")
            if i < EVENT and np.max(np.linalg.norm(np.array(frame["pose"])-base["pose"],axis=1)) > .03:
                raise ValueError("The takes are not matched before the force.")
    return cases


def snapshots(cases):
    return {k: np.asarray([[f[k] for f in case["frames"]] for case in cases]).transpose(1,0,2,3)
            for k in ("pose","rot")}


def add_recovery(row, case, baseline, payload, manny, parents, required=True):
    heights = np.asarray([f["pose"][0][2] for f in case["frames"]])
    feet = np.asarray([f["feet"] for f in case["frames"]])
    first = recovery_start(heights,feet)
    if first is None or first+34 >= len(heights):
        if required:
            raise ValueError("A standing recovery did not leave enough footage for the handoff.")
        return
    last = first+32
    event = row["event"]
    raw = np.asarray(row["keys"])
    cycle = np.asarray(payload["run_keys"][:-1])
    names = manny["names"]
    toes = [names.index(x) for x in ("foot_l","ball_l","foot_r","ball_r")]
    hips = names.index("pelvis")

    def stance(keys):
        points = fk(keys,parents)[0]
        return points[toes]-points[hips]

    phase = matching_phase(np.array([stance(raw[i-event["start"]]) for i in range(first,first+5)]),
                           np.array([stance(key) for key in cycle]), feet[first:first+5])
    cropped = raw[:last-event["start"]+1].copy()
    for i in range(first+1,last+1):
        t = (i-first)/(last-first)
        w = transition_weight(t)
        slot = (phase+i-first)%len(cycle)
        j = i-event["start"]
        reference = cycle[slot]
        cropped[j,:,:3] = (1-w)*raw[j,:,:3] + w*reference[:,:3]
        cropped[j,:,3:] = blend(Rotation.from_quat(raw[j,:,3:]),
                                  Rotation.from_quat(reference[:,3:]),w).as_quat()
        flip = np.sum(cropped[j-1,:,3:]*cropped[j,:,3:],axis=1) < 0
        cropped[j,flip,3:] *= -1
    motion = np.asarray(row["location"])
    speed = baseline["late_speed"]
    new_motion = transition_path(motion,first,last,speed*100/30)
    row["keys"] = cropped.round(7).tolist()
    row["location"] = new_motion.round(4).tolist()
    event.update(recovery_start=first,recovery_end=last,initial_phase=phase,
                 resume_phase=(phase+last-first)%len(cycle),
                 entry_speed_m_s=float((motion[first,0]-motion[first-5,0])*.06),
                 running_speed_m_s=speed)


def make_take(dataset, cases, manny, force, recovery=False):
    selected = cases[:1]+[c for c in cases if c["limit"]==force]
    result = snapshots(selected)
    clear = snapshots([selected[0]]*len(selected))
    events = []
    for i,case in enumerate(selected):
        active = bool(case["limit"])
        branch = ("tracked" if case["outcome"]=="running" else "reaction") if active else "clear"
        row = {"actor":i+1,"body":case["body"],"outcome":branch,
               "contact":list(range(EVENT,EVENT+DURATION)) if active else [],
               "observed":case["outcome"],"min_height":case["min_height"],
               "late_speed":case["late_speed"],"world_delta":case["max_path_difference"]}
        events.append(row)
    payload = build(dataset,result,clear,manny,events)
    payload["force"] = force
    payload["recovery"] = recovery
    payload["event"] = EVENT
    payload["pulse"] = DURATION
    names = manny["names"]
    parents = [names.index(p) if p in names else -1 for p in manny["parents"]]
    rotate = Rotation.from_euler("z",payload["mesh_yaw"],degrees=True)
    for i,(row,case) in enumerate(zip(payload["actors"],selected)):
        branch = row["event"]
        row["label"] = "CONTROL" if i == 0 else LABEL[case["body"]]
        lane = (i-1.5)*225
        row["location"] = [[x,y+lane] for x,y in row["location"]]
        if i == 0:
            continue
        a,b,t,radius = MARKER[case["body"]]
        markers = []
        for frame in range(EVENT,EVENT+DURATION):
            bones,_ = fk(np.asarray(row["keys"][frame-branch["start"]]),parents)
            position = rotate.apply((1-t)*bones[names.index(a)]+t*bones[names.index(b)])
            x,y = row["location"][frame]
            markers.append((position+[x,y-radius,2]).round(4).tolist())
        row["marker"] = markers
        branch["actual_points_m"] = [case["frames"][f]["point"] for f in range(EVENT,EVENT+DURATION)]
        if recovery and case["outcome"] == "stood":
            add_recovery(row,case,cases[0],payload,manny,parents)
        if recovery and case["outcome"] == "fell":
            positions = np.asarray([f["pose"] for f in case["frames"]])
            velocities = np.linalg.norm(np.diff(positions,axis=0,prepend=positions[:1]),axis=-1).mean(1)
            motion = np.convolve(velocities,np.ones(5)/5,mode="same")
            hold = settle_frame(positions[:,0,2],motion,EVENT+12)
            key = hold-branch["start"]
            row["keys"][key:] = [row["keys"][key]]*(len(row["keys"])-key)
            row["location"][hold:] = [row["location"][hold]]*(len(row["location"])-hold)
            branch["hold"] = hold
            branch["terminal"] = True
    return payload


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("batch",type=Path)
    parser.add_argument("manny",type=Path)
    parser.add_argument("output",type=Path)
    parser.add_argument("--recovery",action="store_true")
    args=parser.parse_args()
    dataset=json.loads((args.batch/"trials.json").read_text(encoding="utf-8"))
    results=validated(dataset)
    manny=json.loads(args.manny.read_text(encoding="utf-8"))
    takes=[make_take(dataset,results,manny,force,args.recovery) for force in LEVELS]
    args.output.write_text(json.dumps(takes,allow_nan=False,separators=(",",":")),encoding="utf-8")
    metrics={take["force"]:[row["event"] for row in take["actors"]] for take in takes}
    audit = "recovery-review.json" if args.recovery else "contact-review.json"
    (args.batch/audit).write_text(json.dumps(metrics,indent=2),encoding="utf-8")
    for force,rows in metrics.items():
        print(force,[(r["body"],r["observed"],round(r["world_delta"],2)) for r in rows])


if __name__=="__main__":
    main()
