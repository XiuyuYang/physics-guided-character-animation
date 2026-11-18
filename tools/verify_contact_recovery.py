"""Verify the unchanged PHC prefix and the pose and speed through Unreal's run handoff."""
import argparse
import json
from pathlib import Path

import numpy as np
from scipy.spatial.transform import Rotation

from build_boulder_motion import fk


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def audit(saved):
    old = read(saved/"contact_shots.json")
    new = read(saved/"recovery_shots.json")
    skeleton = read(saved/"manny_samples.json")
    native = read(saved/"recovery-build.json")
    names = skeleton["names"]
    parents = [names.index(p) if p in names else -1 for p in skeleton["parents"]]
    proof = []
    for raw,take,scene in zip(old,new,native):
        force = take["force"]
        samples = read(saved/f"recovery-runtime-{force}"/"samples.json")
        loop = np.asarray(take["run_keys"])
        rotate = Rotation.from_euler("z",take["mesh_yaw"],degrees=True)
        for before,after,role in zip(raw["actors"],take["actors"],scene["roles"]):
            event = after["event"]
            if "recovery_end" not in event:
                if (before["keys"]!=after["keys"] or before["location"]!=after["location"]
                        or role["sections"] != (1 if not before["keys"] else 2)):
                    raise ValueError("A non-recovering lane was modified.")
                continue
            first,end,start = (event[k] for k in ("recovery_start","recovery_end","start"))
            phase = event["resume_phase"]
            initial = first-start+1
            keys = np.asarray(after["keys"])
            source_path = np.asarray(before["location"])
            path = np.asarray(after["location"])
            if (not np.array_equal(keys[:initial],np.asarray(before["keys"])[:initial])
                    or not np.allclose(path[:first+1],source_path[:first+1],rtol=0,atol=1e-5)
                    or not np.allclose(loop[phase,:,:3],keys[-1,:,:3],atol=.0001)
                    or np.max(abs(1-abs(np.sum(loop[phase,:,3:]*keys[-1,:,3:],axis=1)))) > 1e-5
                    or scene["force"] != force or role["sections"]!=3):
                raise ValueError("Recovery changed the impact prefix or did not meet the same run pose.")
            measured = []
            residual = []
            for frame in (end-1,end,end+1):
                observation = samples[str(frame)][after["label"]]
                root = np.array([*path[frame],2.])
                measured.append(observation["root"])
                target = keys[frame-start] if frame<end else loop[(phase+frame-end)%take["loop_frames"]]
                world = rotate.apply(fk(target,parents)[0])+root
                for bone in ("pelvis","head","foot_l","foot_r"):
                    residual.append(float(np.linalg.norm(observation[bone]-world[names.index(bone)])))
            measured = np.diff(measured,axis=0)*.30
            if max(residual) > 1. or np.linalg.norm(measured[1]-measured[0]) > .01:
                raise ValueError(f"{force} {after['label']}: Unreal recovery seam ({max(residual):.3f} cm).")
            proof.append({"force_n":force,"role":after["label"],"start":first,"end":end,
                          "seam_velocity_jump_m_s":float(np.linalg.norm(measured[1]-measured[0])),
                          "max_sample_bone_error_cm":max(residual)})
    if len(proof) != 3:
        raise ValueError("Missing recovery comparisons.")
    return proof


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("saved",type=Path)
    parser.add_argument("report",type=Path)
    args=parser.parse_args()
    proof=audit(args.saved)
    args.report.write_text(json.dumps(proof,indent=2),encoding="utf-8")
    print(json.dumps(proof))
