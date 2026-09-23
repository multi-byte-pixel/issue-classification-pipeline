"""Build a deterministic Linux/Python 3.12 zip from locked dependencies.

No AWS access occurs here. Do not include the evaluation harness or dev tools
in the archive. The package uses Linux wheels even when built on another host.
"""

import shutil
import subprocess
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

root = Path(__file__).resolve().parents[1]
dist = root / "dist"
target = dist / "package"
if target.exists():
    shutil.rmtree(target)
target.mkdir(parents=True)
requirements = dist / "requirements.txt"
subprocess.run(
    [
        "uv",
        "export",
        "--frozen",
        "--no-dev",
        "--no-emit-project",
        "--no-editable",
        "--output-file",
        str(requirements),
    ],
    cwd=root,
    check=True,
)
subprocess.run(
    [
        "uv",
        "pip",
        "install",
        "--target",
        str(target),
        "--python-version",
        "3.12",
        "--python-platform",
        "x86_64-manylinux2014",
        "--only-binary",
        ":all:",
        "--require-hashes",
        "-r",
        str(requirements),
    ],
    cwd=root,
    check=True,
)
shutil.copytree(
    root / "src" / "event_classifier",
    target / "event_classifier",
    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
)
with ZipFile(dist / "lambda.zip", "w", compression=ZIP_DEFLATED) as archive:
    for file in sorted(target.rglob("*")):
        if file.is_file() and "__pycache__" not in file.parts and file.suffix != ".pyc":
            info = ZipInfo(file.relative_to(target).as_posix(), date_time=(2020, 1, 1, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, file.read_bytes())
