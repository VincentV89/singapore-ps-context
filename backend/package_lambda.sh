#!/usr/bin/env bash
set -euo pipefail
task_backend_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
task_python="${PYTHON:-$task_backend_root/.venv/bin/python}"
if [[ ! -x "$task_python" ]]; then
  task_python="$(command -v python3)"
fi
"$task_python" "$task_backend_root/build_graph.py"
# Only the generated deployment artifact is replaced.
rm -rf -- "$task_backend_root/package"
mkdir -p -- "$task_backend_root/package"
"$task_python" -m pip install --quiet --no-cache-dir \
  --platform manylinux2014_x86_64 --python-version 3.12 --implementation cp \
  --only-binary=:all: --target "$task_backend_root/package" \
  -r "$task_backend_root/requirements.txt"
cp -- "$task_backend_root/app.py" "$task_backend_root/engine.py" \
  "$task_backend_root/fixture.py" "$task_backend_root/build_graph.py" \
  "$task_backend_root/package/"
cp -R -- "$task_backend_root/data" "$task_backend_root/vendor" "$task_backend_root/package/"
"$task_python" - "$task_backend_root" <<'PY'
from pathlib import Path
import sys
import zipfile
root = Path(sys.argv[1])
with zipfile.ZipFile(root / "package.zip", "w", zipfile.ZIP_DEFLATED) as archive:
    for path in sorted((root / "package").rglob("*")):
        if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc":
            archive.write(path, path.relative_to(root / "package"))
print(f"Lambda package: {root / 'package.zip'}")
PY
