"""Author the native map, Manny animation assets, and replay sequence."""
import json
from pathlib import Path

import unreal as ue

ROOT = "/Game/BoulderDemo"
LEVEL = ROOT + "/L_BoulderCrowd"
TAG = "BoulderDemoGenerated"
ASSETS = ue.AssetToolsHelpers.get_asset_tools()
LIB = ue.EditorAssetLibrary
LEVELS = ue.get_editor_subsystem(ue.LevelEditorSubsystem)
ACTORS = ue.get_editor_subsystem(ue.EditorActorSubsystem)
SAVED = Path(ue.Paths.project_saved_dir())


def asset(name, cls, factory):
    path = ROOT + "/" + name
    if LIB.does_asset_exist(path):
        return LIB.load_asset(path)
    return ASSETS.create_asset(name, ROOT, cls, factory)


def vector(p):
    return ue.Vector(*p)


def spawn(cls, label, pos=(0, 0, 0), rot=None):
    actor = ACTORS.spawn_actor_from_class(cls, vector(pos), rot or ue.Rotator())
    assert actor, label
    actor.set_actor_label(label)
    actor.set_editor_property("tags", [ue.Name(TAG)])
    return actor


def material(name, color, striped=False, emissive=False):
    mat = asset(name, ue.Material, ue.MaterialFactoryNew())
    edit = ue.MaterialEditingLibrary
    edit.delete_all_material_expressions(mat)

    def node(cls, x, y, **values):
        expression = edit.create_material_expression(mat, cls, x, y)
        expression.set_editor_properties(values)
        return expression

    base = node(ue.MaterialExpressionConstant3Vector, -650, 0, constant=ue.LinearColor(*color, 1))
    if striped:
        uv = node(ue.MaterialExpressionTextureCoordinate, -1100, 220)
        mask = node(ue.MaterialExpressionComponentMask, -940, 220, r=True)
        amount = node(ue.MaterialExpressionMultiply, -760, 220, const_b=7.0)
        sine = node(ue.MaterialExpressionSine, -590, 220)
        band = node(ue.MaterialExpressionSaturate, -410, 220)
        dark = node(ue.MaterialExpressionConstant3Vector, -650, 80,
                    constant=ue.LinearColor(*(v*.43 for v in color), 1))
        ramp = node(ue.MaterialExpressionLinearInterpolate, -175, 60)
        for src, dst, key in ((uv, mask, "Input"), (mask, amount, "A"), (amount, sine, "Input"),
                              (sine, band, "Input"), (base, ramp, "A"), (dark, ramp, "B"),
                              (band, ramp, "Alpha")):
            edit.connect_material_expressions(src, "", dst, key)
        base = ramp
    rough = node(ue.MaterialExpressionConstant, -370, 385, r=.83)
    edit.connect_material_property(base, "", ue.MaterialProperty.MP_BASE_COLOR)
    if emissive:
        edit.connect_material_property(base, "", ue.MaterialProperty.MP_EMISSIVE_COLOR)
    edit.connect_material_property(rough, "", ue.MaterialProperty.MP_ROUGHNESS)
    edit.recompile_material(mat)
    LIB.save_loaded_asset(mat)
    return mat


def shape(label, mesh, surface, pos, scale, rot=None, movable=False):
    actor = spawn(ue.StaticMeshActor, label, pos, rot)
    component = actor.static_mesh_component
    component.set_static_mesh(mesh)
    component.set_material(0, surface)
    if movable:
        component.set_mobility(ue.ComponentMobility.MOVABLE)
    actor.set_actor_scale3d(vector(scale))
    return actor


def frame(value):
    return ue.FrameNumber(value=int(value))


def transform(binding, positions, rotations=None, scale=(1, 1, 1), scales=None):
    track = binding.add_track(ue.MovieScene3DTransformTrack)
    section = track.add_section()
    section.set_range(0, len(positions))
    if rotations:
        section.set_editor_property("use_quaternion_interpolation", True)
    channels = section.get_all_channels()
    for i, pos in enumerate(positions):
        rotation = rotations[i] if rotations else ue.Rotator()
        row = (*pos, rotation.roll, rotation.pitch, rotation.yaw, *(scales[i] if scales is not None else scale))
        for j, (channel, value) in enumerate(zip(channels, row)):
            interpolation = (ue.MovieSceneKeyInterpolation.CONSTANT if scales is not None and j >= 6
                             else ue.MovieSceneKeyInterpolation.LINEAR)
            channel.add_key(frame(i), float(value), interpolation=interpolation)
    return section


def animation(track, clip, start, end, offset=0):
    if start >= end:
        return
    section = track.add_section()
    section.set_range(start, end)
    params = ue.MovieSceneSkeletalAnimationParams()
    params.set_editor_property("animation", clip)
    params.set_editor_property("first_loop_start_frame_offset", frame(offset*800))
    section.set_editor_property("params", params)
    return section


def reaction_clip(name, mesh, bones, values):
    factory = ue.AnimSequenceFactory()
    factory.set_editor_property("target_skeleton", mesh.get_editor_property("skeleton"))
    factory.set_editor_property("preview_skeletal_mesh", mesh)
    clip = asset(name, ue.AnimSequence, factory)
    assert clip, name
    controller = clip.controller
    controller.open_bracket("Transfer PHC rollout to Manny", False)
    try:
        controller.set_frame_rate(ue.FrameRate(30, 1), False)
        controller.set_number_of_frames(frame(len(values)-1), False)
        controller.remove_all_bone_tracks(False)
        unity = vector((1,1,1))
        for j, bone in enumerate(bones):
            if bone.startswith("VB "):
                continue
            name_key = ue.Name(bone)
            controller.add_bone_curve(name_key, False)
            source = [row[j] for row in values]
            if not controller.set_bone_track_keys(name_key, [vector(p[:3]) for p in source],
                                                  [ue.Quat(*p[3:7]) for p in source],
                                                  [unity]*len(source), False):
                raise RuntimeError("Unable to write Manny bone track: " + bone)
    finally:
        controller.close_bracket(False)
    clip.set_editor_property("enable_root_motion", False)
    LIB.save_loaded_asset(clip)
    return clip


def build():
    data = json.loads((SAVED / "boulder_shot.json").read_text(encoding="utf-8"))
    n = data["frames"]
    mesh, original = (ue.load_asset(data[name]) for name in ("mesh","run"))
    assert mesh and original
    if LIB.does_asset_exist(LEVEL):
        assert LEVELS.load_level(LEVEL)
        for actor in ACTORS.get_all_level_actors():
            if ue.Name(TAG) in actor.tags:
                ACTORS.destroy_actor(actor)
    else:
        assert LEVELS.new_level(LEVEL)
    sequence = asset("LS_BoulderCrowd", ue.LevelSequence, ue.LevelSequenceFactoryNew())
    for binding in sequence.get_bindings():
        binding.remove()
    for track in sequence.get_tracks():
        sequence.remove_track(track)
    sequence.set_display_rate(ue.FrameRate(30, 1))
    sequence.set_tick_resolution(ue.FrameRate(24000, 1))
    sequence.set_playback_start(0)
    sequence.set_playback_end(n)
    running = reaction_clip("Manny_Run_InPlace", mesh, data["bones"], data["run_keys"])

    cube = ue.load_asset("/Engine/BasicShapes/Cube")
    ball = ue.load_asset("/Engine/BasicShapes/Sphere")
    ground = material("M_Dust", (.19,.15,.105))
    stone = material("M_Cliff", (.24,.19,.14))
    band = material("M_TrackPaint", (.72,.52,.19))
    rock_surface = material("M_RollingStone", (.24,.21,.17), striped=True)
    cool = material("M_Recovery", (.06,.65,.46))
    warm = material("M_Collapse", (.81,.19,.055))
    shape("Test range ground", cube, ground, (1025,0,-25), (41,35,.5))
    for edge in (-820,820):
        shape("Track boundary", cube, band, (960,edge,1), (34,.055,.025))
    for i in range(-3,25,2):
        shape("Distance tick", cube, band, (i*100, -805, 2), (.03,.35,.025))
    for i in range(12):
        j = (i*19)%7
        shape("Cut rock", cube, stone, (-400+255*i, 1270+23*j, 55+19*j),
              (2.8,3.5,1.65+.46*j), ue.Rotator(yaw=37+17*i, roll=j*1.5))
    key = spawn(ue.DirectionalLight, "Sun · key", rot=ue.Rotator(pitch=-48,yaw=-42))
    key.get_component_by_class(ue.DirectionalLightComponent).set_editor_property("intensity", 8.5)
    fill = spawn(ue.DirectionalLight, "Sky bounce", rot=ue.Rotator(pitch=-27,yaw=136))
    fill_comp = fill.get_component_by_class(ue.DirectionalLightComponent)
    fill_comp.set_editor_property("intensity", 3.2)
    fill_comp.set_editor_property("cast_shadows", False)
    fill_comp.set_light_color(ue.LinearColor(.55,.71,1,1))

    sphere_scale = data["radius_cm"]/50
    rock = spawn(ue.StaticMeshActor, "PHC | Rolling boulder", tuple(data["rock"][0][:3]))
    rock.static_mesh_component.set_static_mesh(ball)
    rock.static_mesh_component.set_material(0, rock_surface)
    rock.static_mesh_component.set_mobility(ue.ComponentMobility.MOVABLE)
    transform(sequence.add_possessable(rock), [row[:3] for row in data["rock"]],
              [ue.Quat(*row[3:]).rotator() for row in data["rock"]], (sphere_scale,)*3)
    summaries = []
    for row in data["actors"]:
        event = row["event"]
        number = event["actor"]
        branch = event["outcome"]
        label = f"A{number:02d} | {branch.upper()}"
        loc = [(*item,2.0) for item in row["location"]]
        actor = spawn(ue.SkeletalMeshActor, label, loc[0])
        component = actor.skeletal_mesh_component
        component.set_skeletal_mesh_asset(mesh)
        component.set_animation_mode(ue.AnimationMode.ANIMATION_SINGLE_NODE)
        component.set_animation(running)
        component.set_collision_enabled(ue.CollisionEnabled.NO_COLLISION)
        component.set_editor_property("enable_update_rate_optimizations", False)
        binding = sequence.add_possessable(actor)
        transform(binding, loc, [ue.Rotator(yaw=data["mesh_yaw"])] * n)
        track = binding.add_track(ue.MovieSceneSkeletalAnimationTrack)
        phase_offset = None
        if branch == "clear":
            animation(track, running, 0, n)
        else:
            start, resume = event["start"], event["resume"]
            clip = reaction_clip(f"A{number:02d}_PHC_{branch}", mesh, data["bones"], row["keys"])
            animation(track, running, 0, start)
            animation(track, clip, start, resume or n)
            if resume:
                tail = animation(track, running, resume, n, resume % data["loop_frames"])
                tail_params = tail.get_editor_property("params")
                assert tail_params.get_editor_property("start_frame_offset").value == 0
                phase_offset = tail_params.get_editor_property("first_loop_start_frame_offset").value // 800
        # Small lane markers make the two physics outcomes easy to track in the wide shot.
        if branch != "clear":
            loc_marker = [(x,y,2.5) for x,y,_ in loc]
            marker = shape(f"A{number:02d} · result marker", ball, cool if branch == "graze" else warm,
                           loc_marker[0], (.52,.52,.021), movable=True)
            transform(sequence.add_possessable(marker), loc_marker, scale=(.52,.52,.021))
        summaries.append({"id": number, "branch": branch, "sections": len(track.get_sections()),
                          "start": event["start"], "resume": event["resume"], "hold": event["hold"],
                          "first_loop_phase": phase_offset})

    camera = spawn(ue.CameraActor, "Camera · running group")
    camera.get_component_by_class(ue.CameraComponent).set_field_of_view(46)
    positions, angles = [], []
    for i in range(n):
        rock_position = data["rock"][i]
        runners = [a["location"][i] for a in data["actors"]]
        left, right = min(p[0] for p in runners), max(p[0] for p in runners)
        drift = min(1, max(0, (i-65)/35))
        x = (1-drift)*sum(p[0] for p in runners)/len(runners) + drift*(left+right)/2
        y = min(30, max(-80, rock_position[1]*.17))
        at = (x,y,80)
        back = max(0, (right-left)*1.27-1140)*drift
        eye = (x-280, y-1140-back, 580+back*.27)
        positions.append(eye)
        angles.append(ue.MathLibrary.find_look_at_rotation(vector(eye), vector(at)))
    camera_binding = sequence.add_possessable(camera)
    transform(camera_binding, positions, angles)
    camera_track = sequence.add_track(ue.MovieSceneCameraCutTrack)
    cut = camera_track.add_section()
    cut.set_range(0,n)
    cut.set_camera_binding_id(sequence.get_binding_id(camera_binding))

    player = spawn(ue.LevelSequenceActor, "PLAY | Boulder crowd")
    player.set_sequence(sequence)
    settings = player.get_editor_property("playback_settings")
    settings.set_editor_property("auto_play", True)
    settings.set_editor_property("hide_player", True)
    settings.set_editor_property("disable_movement_input", True)
    settings.set_editor_property("hide_hud", True)
    loops = settings.get_editor_property("loop_count")
    loops.set_editor_property("value", -1)
    settings.set_editor_property("loop_count", loops)
    player.set_editor_property("playback_settings", settings)
    LIB.save_loaded_asset(sequence)
    assert LEVELS.save_current_level()
    (SAVED / "build-report.json").write_text(json.dumps({"level":LEVEL,"frames":n,"runners":summaries},indent=2),
                                           encoding="utf-8")
    ue.log("BOULDER DEMO SAVED")


if __name__ == "__main__":
    build()
