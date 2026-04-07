"""Wrapper for invoking R scripts (clmm_analysis.R, rater_glmm.R) from Python.

Locates Rscript on PATH or in standard Windows install locations,
runs the script with the chosen CSV input, and parses the JSON it writes.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

R_SCRIPT_DIR = Path(__file__).parent


def find_rscript() -> str | None:
    """Locate Rscript binary. Returns path or None if R is not installed."""
    # 1. PATH
    rscript = shutil.which("Rscript")
    if rscript:
        return rscript

    # 2. Standard Windows R install locations
    if sys.platform == "win32":
        candidates = list(Path("C:/Program Files/R").glob("R-*/bin/Rscript.exe"))
        candidates += list(Path("C:/Program Files/R").glob("R-*/bin/x64/Rscript.exe"))
        if candidates:
            # Use the most recent version
            candidates.sort(reverse=True)
            return str(candidates[0])

    return None


def check_r_packages(rscript_path: str, packages: list[str]) -> dict[str, bool]:
    """Check whether the given R packages are installed.

    Returns a dict mapping package name to availability boolean.
    """
    pkg_list = ",".join(f'"{p}"' for p in packages)
    code = (
        f'pkgs <- c({pkg_list}); '
        'res <- sapply(pkgs, function(p) requireNamespace(p, quietly=TRUE)); '
        'cat(paste(names(res), as.integer(res), sep="="), sep="\\n")'
    )
    try:
        result = subprocess.run(
            [rscript_path, "-e", code],
            capture_output=True, text=True, timeout=60,
        )
        availability = {}
        for line in result.stdout.strip().splitlines():
            if "=" in line:
                name, val = line.split("=", 1)
                availability[name.strip()] = val.strip() == "1"
        return availability
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return {p: False for p in packages}


def run_r_script(
    rscript_path: str,
    script: Path,
    input_csv: Path,
    output_json: Path,
    timeout: int = 1800,
) -> dict | None:
    """Run an R script and return the parsed JSON output.

    Args:
        rscript_path: Path to Rscript binary.
        script: Path to .R script file.
        input_csv: CSV input passed as first arg.
        output_json: JSON output path passed as second arg.
        timeout: Seconds before killing the process (default 30 min).

    Returns:
        Parsed JSON dict from the R script, or None on failure.
    """
    cmd = [rscript_path, str(script), str(input_csv), str(output_json)]
    print(f"  Running: {' '.join(cmd)}")
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
        )
        # Print R stdout/stderr so user can see progress
        if result.stdout:
            for line in result.stdout.splitlines():
                print(f"    [R] {line}")
        if result.returncode != 0:
            print(f"  R script exited with code {result.returncode}")
            if result.stderr:
                for line in result.stderr.splitlines()[-20:]:
                    print(f"    [R-err] {line}")
            return None

        if not output_json.exists():
            print(f"  R script did not produce output: {output_json}")
            return None

        return json.loads(output_json.read_text(encoding="utf-8"))

    except subprocess.TimeoutExpired:
        print(f"  R script timed out after {timeout}s")
        return None
    except (FileNotFoundError, OSError) as e:
        print(f"  R script failed: {e}")
        return None
    except json.JSONDecodeError as e:
        print(f"  Could not parse R output JSON: {e}")
        return None


def run_clmm(tom_csv: Path, output_json: Path) -> dict | None:
    """Run the V3 CLMM R script."""
    rscript = find_rscript()
    if not rscript:
        print("  Rscript not found — skipping R-based V3")
        return {"skipped": True, "reason": "Rscript not found"}

    pkg_check = check_r_packages(rscript, ["ordinal", "jsonlite"])
    missing = [p for p, ok in pkg_check.items() if not ok]
    if missing:
        print(f"  Missing R packages: {missing} — skipping R-based V3")
        print(f"    Install with: install.packages(c({', '.join(repr(p) for p in missing)}))")
        return {"skipped": True, "reason": f"Missing R packages: {missing}"}

    script = R_SCRIPT_DIR / "clmm_analysis.R"
    return run_r_script(rscript, script, tom_csv, output_json)


def run_glmm(rater_csv: Path, output_json: Path) -> dict | None:
    """Run the V4 GLMM R script."""
    rscript = find_rscript()
    if not rscript:
        print("  Rscript not found — skipping R-based V4")
        return {"skipped": True, "reason": "Rscript not found"}

    pkg_check = check_r_packages(rscript, ["lme4", "jsonlite"])
    missing = [p for p, ok in pkg_check.items() if not ok]
    if missing:
        print(f"  Missing R packages: {missing} — skipping R-based V4")
        print(f"    Install with: install.packages(c({', '.join(repr(p) for p in missing)}))")
        return {"skipped": True, "reason": f"Missing R packages: {missing}"}

    script = R_SCRIPT_DIR / "rater_glmm.R"
    return run_r_script(rscript, script, rater_csv, output_json)
