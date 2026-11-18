"""Bake the public demonstration from recorded load cases and local Epic assets."""
import os
from pathlib import Path
import runpy
import subprocess

import unreal

project = Path(unreal.Paths.project_dir()).resolve()
repo = project.parents[1]
scripts = project / "Scripts"
saved = project / "Saved"
evidence = repo / "evidence"


def convert(tool, batch, output, *options):
    subprocess.run(
        [os.environ["PGCA_BUILD_PYTHON"], str(repo / "tools" / tool),
         str(evidence / batch), str(saved / "manny_samples.json"),
         str(saved / output), *options],
        cwd=repo, check=True,
    )


runpy.run_path(str(scripts / "sample_manny.py"))
convert("build_boulder_motion.py", "boulder/unreal-acceptance", "boulder_shot.json")
runpy.run_path(str(scripts / "create_demo.py"), run_name="__main__")
convert("build_contact_motion.py", "contact-probe/exact-contact", "contact_shots.json")
runpy.run_path(str(scripts / "create_contact.py"))
convert("build_contact_motion.py", "contact-probe/exact-contact", "recovery_shots.json", "--recovery")
runpy.run_path(str(scripts / "create_recovery.py"))
