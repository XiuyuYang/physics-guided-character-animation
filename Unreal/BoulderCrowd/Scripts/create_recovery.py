"""Create the recovery variant without replacing the captured comparison."""
from pathlib import Path
import runpy

import unreal

project = Path(unreal.Paths.project_dir())
runpy.run_path(str(project/"Scripts/create_contact.py"),init_globals={"RECOVERY_MODE":True})
