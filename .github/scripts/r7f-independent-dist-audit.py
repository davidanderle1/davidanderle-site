#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import stat
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit

EXECUTABLE_TYPES = {"", "module", "text/javascript", "application/javascript"}
ALLOWED_MODULE_RE = re.compile(r"^/assets/js/vce-sequence\.[a-f0-9]+\.js$")
PORTRAIT_FORBIDDEN_RE = re.compile(r"portrait-(?:640|960|1280)|portrait-[2-9]\d{2}x", re.I)
TEXT_EXTENSIONS = {".html", ".css", ".js", ".json", ".txt", ".xml", ".svg"}


@dataclass
class ScriptRecord:
    file: str
    type: str
    src: str | None
    executable: bool
    inline_non_whitespace: bool
    json_valid: bool | None


class DistHTMLParser(HTMLParser):
    def __init__(self, source: str) -> None:
        super().__init__(convert_charrefs=True)
        self.source = source
        self.scripts: list[ScriptRecord] = []
        self.external_runtime_assets: list[dict[str, str]] = []
        self._active_script: dict[str, object] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = {key.lower(): (value or "") for key, value in attrs}
        lowered = tag.lower()
        if lowered == "script":
            script_type = attr.get("type", "").strip().lower()
            src = attr.get("src", "").strip() or None
            self._active_script = {"type": script_type, "src": src, "body": []}
            if src and urlsplit(src).scheme in {"http", "https"}:
                self.external_runtime_assets.append({"file": self.source, "tag": "script", "url": src})
        elif lowered == "link":
            rel = {part.lower() for part in attr.get("rel", "").split()}
            href = attr.get("href", "").strip()
            if "stylesheet" in rel and href and urlsplit(href).scheme in {"http", "https"}:
                self.external_runtime_assets.append({"file": self.source, "tag": "link", "url": href})

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag.lower() == "script":
            self.handle_endtag(tag)

    def handle_data(self, data: str) -> None:
        if self._active_script is not None:
            body = self._active_script["body"]
            assert isinstance(body, list)
            body.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() != "script" or self._active_script is None:
            return
        script_type = str(self._active_script["type"])
        src_value = self._active_script["src"]
        src = str(src_value) if src_value else None
        body = "".join(str(part) for part in self._active_script["body"])
        executable = script_type in EXECUTABLE_TYPES
        json_valid: bool | None = None
        if script_type == "application/ld+json" and not src:
            try:
                json.loads(body)
                json_valid = True
            except json.JSONDecodeError:
                json_valid = False
        self.scripts.append(
            ScriptRecord(
                file=self.source,
                type=script_type or "classic",
                src=src,
                executable=executable,
                inline_non_whitespace=bool(body.strip()),
                json_valid=json_valid,
            )
        )
        self._active_script = None


def rel(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def audit(root: Path, stress: bool) -> dict[str, object]:
    root = root.resolve()
    if not root.is_dir():
        raise SystemExit(f"Dist root is not a directory: {root}")

    files: list[Path] = []
    findings: list[dict[str, object]] = []
    for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
        mode = path.lstat().st_mode
        relative = rel(root, path)
        if stat.S_ISLNK(mode):
            findings.append({"code": "SYMLINK", "file": relative, "target": os.readlink(path)})
        elif path.is_file():
            files.append(path)
        elif not path.is_dir():
            findings.append({"code": "UNSUPPORTED_ENTRY", "file": relative})

    relative_files = [rel(root, path) for path in files]
    html_files = [path for path in files if path.suffix.lower() == ".html"]
    js_assets = sorted(relative for relative in relative_files if relative.endswith(".js"))
    runtime_scripts: list[ScriptRecord] = []
    external_runtime_assets: list[dict[str, str]] = []

    for path in files:
        relative = rel(root, path)
        if relative.endswith(".map"):
            findings.append({"code": "SOURCE_MAP", "file": relative})
        if PORTRAIT_FORBIDDEN_RE.search(relative):
            findings.append({"code": "PORTRAIT_DIMENSION", "file": relative})
        if path.suffix.lower() not in TEXT_EXTENSIONS:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            findings.append({"code": "TEXT_DECODE", "file": relative, "message": str(exc)})
            continue
        if re.search(r"https?://(?:localhost|127\.0\.0\.1)", text, re.I):
            findings.append({"code": "LOCALHOST_REFERENCE", "file": relative})
        if re.search(r"/(?:home|Users|mnt|private)/", text):
            findings.append({"code": "PRIVATE_PATH", "file": relative})
        if re.search(r"testFixture\s*[\"':=]+\s*true|Synthetic TEST WorkRecord", text, re.I) and not stress:
            findings.append({"code": "SYNTHETIC_PRODUCTION_CONTENT", "file": relative})
        if path.suffix.lower() == ".html":
            parser = DistHTMLParser(relative)
            try:
                parser.feed(text)
                parser.close()
            except Exception as exc:  # noqa: BLE001
                findings.append({"code": "HTML_PARSE", "file": relative, "message": str(exc)})
                continue
            runtime_scripts.extend(parser.scripts)
            external_runtime_assets.extend(parser.external_runtime_assets)

    findings.extend({"code": "EXTERNAL_RUNTIME_ASSET", **row} for row in external_runtime_assets)
    executable = [row for row in runtime_scripts if row.executable]
    non_executable = [row for row in runtime_scripts if not row.executable]

    for row in non_executable:
        if row.type != "application/ld+json" or row.src is not None or row.json_valid is not True:
            findings.append({"code": "UNEXPECTED_NONEXECUTABLE_SCRIPT", **row.__dict__})

    for row in executable:
        allowed = (
            row.file == "work/volatility-cascade-engine/index.html"
            and row.type == "module"
            and row.src is not None
            and ALLOWED_MODULE_RE.fullmatch(row.src) is not None
            and not row.inline_non_whitespace
        )
        if not allowed:
            findings.append({"code": "EXECUTABLE_SCRIPT_SCOPE", **row.__dict__})

    if len(executable) != 1:
        findings.append({"code": "EXECUTABLE_SCRIPT_COUNT", "count": len(executable)})
    if len(js_assets) != 1 or re.fullmatch(r"assets/js/vce-sequence\.[a-f0-9]+\.js", js_assets[0] if js_assets else "") is None:
        findings.append({"code": "JS_ASSET_SCOPE", "jsAssets": js_assets})
    if executable and executable[0].src and executable[0].src.lstrip("/") not in set(relative_files):
        findings.append({"code": "SCRIPT_ASSET_MISSING", "src": executable[0].src})
    if not html_files:
        findings.append({"code": "VACUOUS_HTML_SET"})
    if len(files) < 30:
        findings.append({"code": "IMPLAUSIBLE_DIST_FILE_COUNT", "count": len(files)})

    synthetic_pages = sorted(relative for relative in relative_files if relative.startswith("work/synthetic-test-record-") and relative.endswith("/index.html"))
    marker = root / "TEST_ONLY_DO_NOT_DEPLOY.txt"
    if stress:
        if len(synthetic_pages) != 500:
            findings.append({"code": "STRESS_PAGE_COUNT", "count": len(synthetic_pages)})
        if not marker.is_file():
            findings.append({"code": "STRESS_MARKER_MISSING"})
    else:
        if synthetic_pages:
            findings.append({"code": "SYNTHETIC_PRODUCTION_ROUTES", "count": len(synthetic_pages)})
        if marker.exists():
            findings.append({"code": "PRODUCTION_STRESS_MARKER"})

    result: dict[str, object] = {
        "auditor": "r7f-independent-dist-audit.py",
        "root": str(root),
        "stressMode": stress,
        "fileCount": len(files),
        "htmlFileCount": len(html_files),
        "scriptTagCount": len(runtime_scripts),
        "executableScriptCount": len(executable),
        "nonExecutableScriptCount": len(non_executable),
        "jsAssets": js_assets,
        "externalRuntimeAssetCount": len(external_runtime_assets),
        "syntheticDetailPageCount": len(synthetic_pages),
        "findings": findings,
        "findingCount": len(findings),
        "passed": not findings,
    }
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Independent dist-wide JavaScript/runtime/synthetic-content audit")
    parser.add_argument("root", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--stress", action="store_true")
    args = parser.parse_args()
    result = audit(args.root, args.stress)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    if not result["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
