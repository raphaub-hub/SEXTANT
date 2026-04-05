"""
setup_env.py — Backtest Engine environment checker and installer.
Called by install.bat — do not rename this file.
"""

import sys
import subprocess
import importlib.metadata as _meta

# ---------------------------------------------------------------------------
# Package list  (pip_name, min_version, display_name)
# ---------------------------------------------------------------------------
REQUIREMENTS = [
    ("streamlit",    "1.35.0",  "Streamlit       — web interface"),
    ("pandas",       "2.0.0",   "Pandas          — data manipulation"),
    ("numpy",        "1.26.0",  "NumPy           — numerical computing"),
    ("matplotlib",   "3.8.0",   "Matplotlib      — reporting charts"),
    ("plotly",       "5.18.0",  "Plotly          — interactive charts"),
    ("pyarrow",      "14.0.0",  "PyArrow         — Parquet read/write"),
    ("yfinance",     "0.2.40",  "yfinance        — Yahoo Finance import"),
    ("openpyxl",     "3.1.0",   "openpyxl        — Excel file support"),
]

W = 62   # console width


def _banner(text):
    print("=" * W)
    pad = (W - len(text) - 2) // 2
    print(" " * pad + " " + text)
    print("=" * W)


def _parse(v):
    try:
        return tuple(int(x) for x in str(v).split(".")[:3])
    except Exception:
        return (0,)


def _check(pip_name, min_ver):
    """Return ('ok'|'outdated'|'missing', installed_version_or_None)."""
    try:
        inst = _meta.version(pip_name)
        if _parse(inst) >= _parse(min_ver):
            return "ok", inst
        return "outdated", inst
    except _meta.PackageNotFoundError:
        return "missing", None


def _pip_install(specs: list[str]) -> bool:
    """Run pip install for the given specs. Return True on success."""
    cmd = [sys.executable, "-m", "pip", "install"] + specs
    result = subprocess.run(cmd)
    return result.returncode == 0


def main():
    _banner("Backtest Engine  —  Environment Setup")
    print()

    # ── Python version check ────────────────────────────────────────────────
    pv = sys.version_info
    py_str = f"Python {pv.major}.{pv.minor}.{pv.micro}"
    if pv.major < 3 or (pv.major == 3 and pv.minor < 10):
        print(f"  [!]  {py_str}  —  Python 3.10+ is recommended.")
        print("       Download: https://www.python.org/downloads/")
    else:
        print(f"  [OK] {py_str}")
    print()

    # ── Status table ────────────────────────────────────────────────────────
    ok_list      = []
    install_list = []   # (pip_name, min_ver, display_name, status, inst_ver)

    print(f"  {'Package':<38} {'Required':<12} {'Installed':<12} Status")
    print(f"  {'-'*38} {'-'*12} {'-'*12} {'-'*10}")

    for pip_name, min_ver, label in REQUIREMENTS:
        status, inst_ver = _check(pip_name, min_ver)
        inst_str = inst_ver if inst_ver else "—"
        req_str  = ">= " + min_ver

        if status == "ok":
            mark = "[OK]     already installed"
            ok_list.append((pip_name, inst_ver))
        elif status == "outdated":
            mark = "[!]      needs update"
            install_list.append((pip_name, min_ver, label, status, inst_ver))
        else:
            mark = "[ ]      not installed"
            install_list.append((pip_name, min_ver, label, status, inst_ver))

        print(f"  {label:<38} {req_str:<12} {inst_str:<12} {mark}")

    print()

    # ── Nothing to do ───────────────────────────────────────────────────────
    if not install_list:
        print("  All packages are already installed and up to date.")
        print()
        _banner("Ready — launch the app with  launch_sextant.bat")
        return

    # ── Summary of what needs installing ────────────────────────────────────
    missing   = [x for x in install_list if x[3] == "missing"]
    outdated  = [x for x in install_list if x[3] == "outdated"]

    if missing:
        print(f"  {len(missing)} package(s) not installed:")
        for p, mv, lbl, *_ in missing:
            print(f"    •  {lbl}  (>= {mv})")
        print()
    if outdated:
        print(f"  {len(outdated)} package(s) need an update:")
        for p, mv, lbl, _, inst in outdated:
            print(f"    •  {lbl}  (installed: {inst},  required: >= {mv})")
        print()

    # ── Per-package selection ────────────────────────────────────────────────
    print("  Select packages to install/update.")
    print("  Press Enter to accept the default shown in brackets.")
    print()

    to_install = []
    for pip_name, min_ver, label, status, inst_ver in install_list:
        default = "Y"
        try:
            ans = input(f"    Install  {label}? [Y/n] ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            ans = ""
        if ans in ("", "y", "yes"):
            to_install.append(f"{pip_name}>={min_ver}")
            print(f"      -> queued")
        else:
            print(f"      -> skipped")
    print()

    # ── Install ─────────────────────────────────────────────────────────────
    if not to_install:
        print("  Nothing selected — no changes made.")
        print()
        return

    print(f"  Installing {len(to_install)} package(s)...")
    print()

    all_ok = True
    for spec in to_install:
        print(f"  pip install {spec}")
        print("  " + "-" * (W - 2))
        ok = _pip_install([spec])
        print()
        if ok:
            print(f"  [OK] {spec}")
        else:
            print(f"  [FAIL] {spec}  — see error above")
            all_ok = False
        print()

    # ── Final status ─────────────────────────────────────────────────────────
    _banner("Installation complete" if all_ok else "Finished with errors")
    print()
    if all_ok:
        print("  All selected packages are installed.")
        print("  Launch the app:  double-click  launch_sextant.bat")
    else:
        print("  Some packages failed. Check the error messages above.")
        print("  You may need to run as Administrator or check your network.")
    print()


if __name__ == "__main__":
    main()
