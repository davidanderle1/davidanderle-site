from __future__ import annotations

from template_patch_v3 import apply_v3_patches, must_replace


def apply_v4_patches(files: dict[str, str]) -> dict[str, str]:
    files = apply_v3_patches(files)
    package = files["scripts/package_r7e.py"]
    package = must_replace(
        package,
        "PACKAGE = ROOT / 'R7E_PACKAGE'",
        "PACKAGE = ROOT.parent / 'R7E_PACKAGE_WORK'",
        "external package work directory"
    )
    files["scripts/package_r7e.py"] = package
    return files
