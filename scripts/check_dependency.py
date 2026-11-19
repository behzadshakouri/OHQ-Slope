"""Check pinned OHQ sources without building or changing them."""
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]

def git(path, *args):
    return subprocess.check_output(["git", "-C", str(path), *args], text=True).strip()

def main():
    lock = json.loads((ROOT / "config/engine.json").read_text())
    engine = ROOT / lock["path"]
    try:
        actual = git(engine, "rev-parse", "HEAD")
        nested = git(engine / "jsoncpp", "rev-parse", "HEAD")
        # An uninitialized submodule directory can resolve to its parent repo.
        checks = [actual == lock["commit"], nested == lock["jsoncpp_commit"]]
        dirty = git(engine, "status", "--porcelain", "--untracked-files=no")
        checks.append(not dirty)
        print("OHQ commit:", actual)
        print("jsoncpp commit:", nested)
        if not all(checks):
            print("Dependency mismatch or modified tracked files. Initialize submodules and review the lock.")
            return 1
        print("Pinned source check passed. Engine build and model validation are separate checks.")
        return 0
    except (OSError, subprocess.CalledProcessError) as error:
        print("Dependency check failed:", error, file=sys.stderr)
        return 1

if __name__ == "__main__":
    sys.exit(main())
