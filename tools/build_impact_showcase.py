"""Summarize matched dense-crowd trials and retarget their measured motion."""
import argparse
import json
from pathlib import Path

import numpy as np

from build_boulder_motion import build, read
from build_contact_motion import add_recovery
from impact_showcase import DROPS, dense_spawns, drop_mass

CASES = ("palm", "medium", "large", "isolated")


def rock_contacts(trial, control, radius, mass):
    positions = trial["pose"]
    rock = trial["rock"][:, :3]
    offset = positions-rock[:,None,None,:]
    distance = np.linalg.norm(offset, axis=-1)
    direction = offset/np.maximum(.01,distance[...,None])
    forces = trial["body_force"] - control["body_force"]
    outward = np.sum(direction*forces,axis=-1)
    near = distance < radius+.29
    horizontal_load = np.linalg.norm(trial["rock_force"][:,:2],axis=-1)
    observed = np.max(np.where(near,outward,0.),axis=-1)
    return ((horizontal_load[:,None] > max(8.,.55*mass)) &
            (observed > max(14.,.55*mass)))


def compare(trial, control, direct):
    positions = trial["pose"]
    pelvis = positions[:,:,0]
    delta = np.linalg.norm(pelvis-control["pose"][:,:,0],axis=-1)
    events = []
    for j in range(pelvis.shape[1]):
        touches = np.flatnonzero(direct[:,j])
        signal = np.flatnonzero(delta[:,j] > .14)
        falls = np.flatnonzero(pelvis[:,j,2] < .50)
        onset = min((int(seq[0]) for seq in (touches,signal) if len(seq)),default=None)
        events.append({"actor":j+1, "outcome":("clear" if onset is None else
                                             "reaction" if len(falls) else "tracked"),
                       "contact":[] if onset is None else [onset],
                       "direct_frames":touches.tolist(),
                       "first_fall":int(falls[0]) if len(falls) else None,
                       "max_displacement_m":float(delta[:,j].max()),
                       "pelvis_min_m":float(pelvis[:,j,2].min())})
    return events


def identify_secondary(events, shared, isolated):
    """Find non-rock runners with a nearby disturbed runner and a matched difference."""
    poses = shared["pose"]
    delta = np.linalg.norm(poses[:,:,0]-isolated["pose"][:,:,0],axis=-1)
    for j,event in enumerate(events):
        event["neighbor"] = None
        if event["direct_frames"] or not event["contact"]:
            continue
        onset = event["contact"][0]
        for f in range(max(0,onset-8),min(len(poses),onset+12)):
            if max(delta[f:min(f+12,len(poses)),j]) < .23:
                continue
            distances = np.linalg.norm(poses[f,j,:,None,:]-poses[f,:,None,:,:],axis=-1).min(axis=(1,2))
            for k in np.argsort(distances):
                other = events[k]
                if (k != j and distances[k] < .22 and other["first_fall"] is not None
                        and other["first_fall"] <= f+5 and other["contact"] and other["contact"][0] < f):
                    event["neighbor"] = {"actor":int(k)+1,"frame":f,
                                         "isolated_displacement_m":float(delta[:,j].max())}
                    break
            if event["neighbor"]:
                break


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("batch", type=Path)
    parser.add_argument("manny", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--scale-test",action="store_true")
    args = parser.parse_args()
    frames = 240 if args.scale_test else 180
    meta, control = read(args.batch,"clear",frames=frames)
    manny = json.loads(args.manny.read_text(encoding="utf-8"))
    names = manny["names"]
    parents = [names.index(p) if p in names else -1 for p in manny["parents"]]
    isolated = None if args.scale_test else read(args.batch,"impact","isolated")[1]
    takes, review = [], {}
    for case in (("large",) if args.scale_test else CASES):
        capture, trial = read(args.batch,"impact",case,frames=frames)
        drop = "large" if case == "isolated" else case
        radius,density = DROPS[drop]
        if (capture["spawn"] != [list(p) for p in dense_spawns(100 if args.scale_test else 16)]
                or capture["spawn"] != meta["spawn"]
                or capture["radius"] != radius or capture["density"] != density
                or abs(capture["mass"]-drop_mass(drop)) > .001
                or trial["rock"][1,2] < 2.3
                or np.max(np.abs(trial["pose"][:8]-control["pose"][:8])) > .025):
            raise ValueError(f"{case}: unmatched drop")
        contacts = rock_contacts(trial,control,radius,capture["mass"])
        events = compare(trial,control,contacts)
        if case == "large" and isolated is not None:
            identify_secondary(events,trial,isolated)
        for j,event in enumerate(events):
            first_fall = event["first_fall"]
            if (case in ("large","isolated") and event["direct_frames"] and first_fall is not None
                    and event["pelvis_min_m"] < .35 and
                    np.count_nonzero(trial["pose"][first_fall:first_fall+18,j,0,2] < .45) >= 10):
                event["outcome"] = "down"
                event["freeze_by"] = min(len(trial["pose"])-12,first_fall+37)
        take = build(capture,trial,control,manny,events)
        take["rock"][0] = take["rock"][1]
        foot_bones = [capture["names"].index(name) for name in ("L_Ankle","L_Toe","R_Ankle","R_Toe")]
        for j,(actor,event) in enumerate(zip(take["actors"],events)):
            if event["outcome"] == "reaction":
                feet = trial["body_force"][:,j,foot_bones,2].reshape(-1,2,2).sum(axis=2)
                values = {"frames":[{"pose":p,"feet":f} for p,f in zip(trial["pose"][:,j],feet)]}
                speed = control["pose"][-1,j,0,0]-control["pose"][-31,j,0,0]
                add_recovery(actor,values,{"late_speed":float(speed)},take,manny,parents,required=False)
        take.update(case="100" if args.scale_test else case, mass=capture["mass"])
        takes.append(take)
        review[case] = {"diameter_m":2*radius,"mass_kg":capture["mass"],"runners":events}
        print(case,[(e["actor"],e["contact"],e["first_fall"],e.get("neighbor"))
                    for e in events if e["contact"]],flush=True)
    x = np.array([[np.array(actor["location"])[:,0] for actor in take["actors"]] for take in takes])
    left,right = x.min(axis=(0,1)),x.max(axis=(0,1))
    view = np.column_stack(((left+right)/2,
            np.maximum(1870 if args.scale_test else 975, (right-left)*1.03+430))).round(2).tolist()
    for take in takes:
        take["view"] = view
    (args.batch/"review.json").write_text(json.dumps(review,indent=2),encoding="utf-8")
    args.output.write_text(json.dumps(takes,allow_nan=False,separators=(",",":")),encoding="utf-8")


if __name__ == "__main__":
    main()
