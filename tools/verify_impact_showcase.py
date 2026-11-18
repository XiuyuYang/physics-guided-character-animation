"""Check dense Sequencer tracks against the simulated recovery and terminal branches."""
import argparse
import json
from pathlib import Path

import numpy as np


def verify(saved, file):
    takes = json.loads((saved/file).read_text(encoding="utf-8"))
    summary = {}
    for take in takes:
        case = take["case"].title()
        report = json.loads((saved/f"Drop_{case}-build.json").read_text(encoding="utf-8"))
        if (report["frames"] != take["frames"] or len(take["actors"]) != len(report["runners"])
                or len(take["actors"]) != (100 if case == "100" else 16)):
            raise ValueError(f"{case}: missing Sequencer bindings")
        result = {"runners":len(take["actors"]),"frames":take["frames"],
                  "terminal":[],"recovered":[],"secondary":[]}
        for row,native in zip(take["actors"],report["runners"]):
            event = row["event"]
            actor = event["actor"]
            if event.get("neighbor"):
                if event["direct_frames"]:
                    raise ValueError(f"{case}/{actor}: mislabeled runner contact")
                result["secondary"].append(actor)
            if event["hold"] is not None:
                hold = event["hold"]
                keys = row["keys"][hold-event["start"]:]
                positions = row["location"][hold:]
                if (native["hold"] != hold or native["sections"] != 2
                        or any(key != keys[0] for key in keys)
                        or any(pos != positions[0] for pos in positions)):
                    raise ValueError(f"{case}/{actor}: terminal branch drift")
                result["terminal"].append({"actor":actor,"hold":hold})
            if "recovery_end" in event:
                end,phase = event["recovery_end"],event["resume_phase"]
                a,b = np.array(row["keys"][-1]),np.array(take["run_keys"][phase])
                root = np.asarray(row["location"])
                if (native["resume"] != end or native["first_loop_phase"] != phase
                        or native["sections"] != 3
                        or np.max(np.abs(a[:,:3]-b[:,:3])) > .0001
                        or np.max(np.abs(1-np.abs(np.sum(a[:,3:]*b[:,3:],axis=1)))) > 1e-5
                        or np.linalg.norm(root[end+1]-2*root[end]+root[end-1]) > .001):
                    raise ValueError(f"{case}/{actor}: recovery handoff discontinuity")
                result["recovered"].append({"actor":actor,"resume":end})
        summary[case] = result
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("saved",type=Path)
    args = parser.parse_args()
    result = {**verify(args.saved,"impact_shots.json"),**verify(args.saved,"impact_100_shots.json")}
    print(json.dumps(result,indent=2))
