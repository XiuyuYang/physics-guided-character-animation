"""Author two native four-lane body-contact comparison maps."""
import json
from math import sqrt
import runpy
from pathlib import Path

import unreal as ue

project = Path(ue.Paths.project_dir()).resolve()
helper = runpy.run_path(str(project / "Scripts/create_demo.py"))
asset, spawn, shape, material, transform, animation, clip = (
    helper[n] for n in ("asset","spawn","shape","material","transform","animation","reaction_clip"))
LIB, LEVELS, ACTORS, TAG = (helper[n] for n in ("LIB","LEVELS","ACTORS","TAG"))


def label(text, position):
    actor = spawn(ue.TextRenderActor, "Lane label • "+text, position, ue.Rotator(yaw=-15))
    comp = actor.get_component_by_class(ue.TextRenderComponent)
    comp.set_text(ue.Text(text))
    comp.set_world_size(34.)
    comp.set_text_render_color(ue.Color(230,237,255,255))
    return actor


def take(data, camera_data, prop=None):
    force = data["force"]
    root = "/Game/BoulderDemo"
    variant = prop or ("Recovery" if data.get("recovery") else "Contact")
    suffix = variant if prop else f"{variant}_{force}"
    level = f"{root}/L_{suffix}"
    n = data["frames"]
    if LIB.does_asset_exist(level):
        assert LEVELS.load_level(level)
        for actor in ACTORS.get_all_level_actors():
            if ue.Name(TAG) in actor.tags:
                ACTORS.destroy_actor(actor)
    else:
        assert LEVELS.new_level(level)
    sequence = asset(f"LS_{suffix}",ue.LevelSequence,ue.LevelSequenceFactoryNew())
    for binding in sequence.get_bindings():
        binding.remove()
    for track in sequence.get_tracks():
        sequence.remove_track(track)
    sequence.set_display_rate(ue.FrameRate(30,1))
    sequence.set_tick_resolution(ue.FrameRate(24000,1))
    sequence.set_playback_start(0)
    sequence.set_playback_end(n)

    cube = ue.load_asset("/Engine/BasicShapes/Cube")
    sphere = ue.load_asset("/Engine/BasicShapes/Sphere")
    cylinder = ue.load_asset("/Engine/BasicShapes/Cylinder")
    mesh = ue.load_asset(data["mesh"])
    running = clip("Manny_Run_InPlace",mesh,data["bones"],data["run_keys"])
    stage = material("M_Probe_Floor",(.045,.07,.105))
    strips = material("M_Probe_Tracks",(.085,.21,.28))
    pulse = material("M_Probe_Pulse",(.025,.68,1.0),emissive=True)
    dart = material("M_Impact_Dart",(1.,.42,.09),emissive=True) if prop == "Dart" else None
    cone = ue.load_asset("/Engine/BasicShapes/Cone") if dart else None
    shape("Contact stage",cube,stage,(930,0,-22),(65,30,.44))
    for i in range(5):
        shape("Synchronized lane divider",cube,strips,(870,(i-2)*225,1),(40,.032,.024))
    lights = ((-52,-38,8.5,True),(-26,160,4.2,False))
    for pitch,yaw,intensity,shadow in lights:
        source = spawn(ue.DirectionalLight,"Lab light",rot=ue.Rotator(pitch=pitch,yaw=yaw))
        light = source.get_component_by_class(ue.DirectionalLightComponent)
        light.set_editor_property("intensity",intensity)
        light.set_editor_property("cast_shadows",shadow)

    results = []
    for row in data["actors"]:
        event = row["event"]
        loc = [(*p,2.) for p in row["location"]]
        name = row["label"]
        body = spawn(ue.SkeletalMeshActor,f"{name} | {event['observed']}",loc[0])
        body.skeletal_mesh_component.set_skeletal_mesh_asset(mesh)
        body.skeletal_mesh_component.set_animation_mode(ue.AnimationMode.ANIMATION_SINGLE_NODE)
        body.skeletal_mesh_component.set_animation(running)
        body.skeletal_mesh_component.set_collision_enabled(ue.CollisionEnabled.NO_COLLISION)
        binding = sequence.add_possessable(body)
        transform(binding,loc,[ue.Rotator(yaw=data["mesh_yaw"])]*n)
        track = binding.add_track(ue.MovieSceneSkeletalAnimationTrack)
        if row["keys"]:
            start = event["start"]
            prefix = "Recovery" if data.get("recovery") else "Probe"
            if prop:
                prefix = prop
            reaction = clip(f"{prefix}_{force}_{event['body']}",mesh,data["bones"],row["keys"])
            animation(track,running,0,start)
            end = event.get("recovery_end",n)
            animation(track,reaction,start,end)
            if end < n:
                animation(track,running,end,n,event["resume_phase"])
            point = row["marker"][0]
            marker = shape("Contact point • "+name,sphere,pulse,point,(.09,.09,.09),movable=True)
            points,scales = [],[]
            for i in range(n):
                if data["event"] <= i < data["event"]+data["pulse"]:
                    points.append(row["marker"][i-data["event"]])
                    scales.append((.09,.09,.09))
                else:
                    points.append(point)
                    scales.append((0,0,0))
            transform(sequence.add_possessable(marker),points,scales=scales)
            if dart:
                bolt = shape("Stylized dart • "+name,cylinder,dart,point,(.05,.05,.48),movable=True)
                tip = shape("Dart tip • "+name,cone,dart,point,(.12,.12,.18),movable=True)
                path, tips, rotations, shaft_scales, tip_scales = [], [], [], [], []
                arrival = data["event"]
                for i in range(n):
                    t = max(0., min(1., (i-arrival+18)/18))
                    x,y,z = point
                    position = (x-105*(1-t),y-355*(1-t),z+280*t*(1-t))
                    vz = 280*(1-2*t)
                    length = sqrt(105**2+355**2+vz**2)
                    direction = tuple(value/length for value in (105,355,vz))
                    path.append(tuple(a-b*30 for a,b in zip(position,direction)))
                    tips.append(tuple(a-b*7 for a,b in zip(position,direction)))
                    rotations.append(ue.MathLibrary.make_rot_from_z(ue.Vector(*direction)))
                    visible = arrival-18 <= i <= arrival
                    shaft_scales.append((.05,.05,.48) if visible else (0,0,0))
                    tip_scales.append((.12,.12,.18) if visible else (0,0,0))
                transform(sequence.add_possessable(bolt),path,rotations,scales=shaft_scales)
                transform(sequence.add_possessable(tip),tips,rotations,scales=tip_scales)
            else:
                vector = shape("Contact vector • "+name,cylinder,pulse,point,(.025,.025,.40),movable=True)
                vector_path = [(x,y-20,z) for x,y,z in points]
                vector_scales = [(.023,.023,1.35) if prop and i == data["event"] else
                                 (.025,.025,.40) if not prop and s[0] else (0,0,0)
                                 for i,s in enumerate(scales)]
                if prop:
                    vector_path = [(x,y-67,z) for x,y,z in points]
                transform(sequence.add_possessable(vector),vector_path,[ue.Rotator(roll=90)]*n,scales=vector_scales)
        else:
            animation(track,running,0,n)
        sign = label(name, (loc[0][0]+80,loc[0][1],205))
        positions = [(x+65,y,206.) for x,y,_ in loc]
        transform(sequence.add_possessable(sign),positions,[ue.Rotator(yaw=-15)]*n)
        results.append({"label":name,"outcome":event["observed"],"sections":len(track.get_sections())})
    camera = spawn(ue.CameraActor,"Comparison camera")
    camera.get_component_by_class(ue.CameraComponent).set_field_of_view(47)
    positions, rotations = [], []
    for i in range(n):
        xs = [row["location"][i][0] for row in camera_data["actors"]]
        center = (min(xs)+max(xs))/2
        look = (center,0,97)
        backup = max(0,max(xs)-min(xs)-650)*.35
        eye = (max(xs)+1190,-505,620+backup)
        positions.append(eye)
        rotations.append(ue.MathLibrary.find_look_at_rotation(ue.Vector(*eye),ue.Vector(*look)))
    camera_binding = sequence.add_possessable(camera)
    transform(camera_binding,positions,rotations)
    cut = sequence.add_track(ue.MovieSceneCameraCutTrack).add_section()
    cut.set_range(0,n)
    cut.set_camera_binding_id(sequence.get_binding_id(camera_binding))
    player = spawn(ue.LevelSequenceActor, "Autoplay • matched takes")
    player.set_sequence(sequence)
    settings = player.get_editor_property("playback_settings")
    settings.set_editor_property("auto_play",True)
    settings.set_editor_property("hide_player",True)
    settings.set_editor_property("disable_movement_input",True)
    loops = settings.get_editor_property("loop_count")
    loops.set_editor_property("value",-1)
    settings.set_editor_property("loop_count",loops)
    player.set_editor_property("playback_settings",settings)
    assert LIB.save_loaded_asset(sequence)
    assert LEVELS.save_current_level()
    return {"map":level,"frames":n,"force":force,"roles":results}


saved = Path(ue.Paths.project_saved_dir()).resolve()
original = json.loads((saved/"contact_shots.json").read_text(encoding="utf-8"))
recovery_mode = globals().get("RECOVERY_MODE", False)
shots = json.loads((saved/"recovery_shots.json").read_text(encoding="utf-8")) if recovery_mode else original
props = globals().get("PROJECTILE_STYLES", ())
report = ([take(shots[0],original[0],prop) for prop in props] if props else
          [take(shot,base) for shot,base in zip(shots,original)])
name = ("prop-build.json" if props else "recovery-build.json" if recovery_mode else "contact-build.json")
(saved/name).write_text(json.dumps(report,indent=2),encoding="utf-8")
