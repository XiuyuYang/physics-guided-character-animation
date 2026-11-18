"""Bake the measured drop tests as independent Sequencer maps."""
import json
import os
from pathlib import Path
import runpy

import unreal

project = Path(unreal.Paths.project_dir()).resolve()
saved = project / "Saved"
build = runpy.run_path(str(project/"Scripts/create_demo.py"))["build"]
sources = globals().get("SHOTS",os.environ.get("PGCA_DROP_SHOTS","impact_shots.json").split(","))
for source in sources:
    for shot in json.loads((saved/source).read_text(encoding="utf-8")):
        build(shot)
