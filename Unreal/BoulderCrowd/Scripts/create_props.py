"""Compare two fictional visual cues using the same recorded local impacts."""
from pathlib import Path
import runpy

import unreal

scripts = Path(unreal.Paths.project_dir()) / "Scripts"
runpy.run_path(str(scripts / "create_contact.py"),
               init_globals={"RECOVERY_MODE":True,"PROJECTILE_STYLES":("Pulse","Dart")})
