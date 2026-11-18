"""Export Manny's rest pose and original run loop for the offline transfer."""
import json
from pathlib import Path

import unreal

MESH = "/Game/Characters/Mannequins/Meshes/SKM_Manny_Simple"
RUN = "/Game/Characters/Mannequins/Animations/Manny/MM_Run_Fwd"


def values(transform):
    t = transform.translation
    q = transform.rotation
    return [t.x, t.y, t.z, q.x, q.y, q.z, q.w]


mesh = unreal.load_asset(MESH)
run = unreal.load_asset(RUN)
assert mesh and run, "Install the Epic Manny assets and forward run first."
pose_api = unreal.AnimPoseExtensions
rest = pose_api.get_reference_pose(mesh.get_editor_property("skeleton"))
names = [str(n) for n in pose_api.get_bone_names(rest)]
component = unreal.SkeletalMeshComponent()
component.set_skeletal_mesh_asset(mesh)
parents = [str(mesh.get_bone_parent(n)) if component.get_bone_index(n) >= 0 else "None" for n in names]
local = unreal.AnimPoseSpaces.LOCAL
options = unreal.AnimPoseEvaluationOptions()
steps = round(run.get_play_length() * 30)
poses = []
for frame in range(steps):
    pose = pose_api.get_anim_pose_at_time(run, frame / 30, options)
    poses.append([values(pose_api.get_bone_pose(pose, bone, local)) for bone in names])
payload = {"mesh": MESH, "run": RUN, "names": names, "parents": parents, "loop_seconds": run.get_play_length(),
           "rest": [values(pose_api.get_bone_pose(rest, n, local)) for n in names], "frames": poses}
path = Path(unreal.Paths.project_saved_dir()) / "manny_samples.json"
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
unreal.log(f"BOULDER MANNY: {len(names)} bones, {steps} loop frames, {path}")
