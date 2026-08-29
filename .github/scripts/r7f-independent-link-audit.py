#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import stat
from dataclasses import asdict, dataclass
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urljoin, urlsplit

CANONICAL_ORIGIN = "https://davidanderle.com"
CANONICAL_HOSTS = {"davidanderle.com", "www.davidanderle.com"}
IGNORED_SCHEMES = {"mailto", "tel", "data", "blob", "about"}
URL_ATTRS = {"href", "src", "srcset", "poster", "action", "xlink:href"}
CSS_URL_RE = re.compile(r"url\(\s*(?:\"([^\"]*)\"|'([^']*)'|([^\s)'\";]+))\s*\)", re.I)
SVG_ATTR_RE = re.compile(
    r"\b(href|xlink:href|src|srcset|poster|action)\s*=\s*(?:\"([^\"]*)\"|'([^']*)'|([^\s\"'=<>`]+))",
    re.I,
)
ID_RE = re.compile(r"\b(?:id|name)\s*=\s*(?:\"([^\"]*)\"|'([^']*)'|([^\s\"'=<>`]+))", re.I)


@dataclass(frozen=True)
class Reference:
    source: str
    attribute: str
    value: str


class ReferenceParser(HTMLParser):
    def __init__(self, source: str) -> None:
        super().__init__(convert_charrefs=True)
        self.source = source
        self.references: list[Reference] = []
        self.identifiers: set[str] = set()

    def _consume(self, attrs: list[tuple[str, str | None]]) -> None:
        for key, raw_value in attrs:
            name = key.lower()
            value = (raw_value or "").strip()
            if name in {"id", "name"} and value:
                self.identifiers.add(value)
            if name not in URL_ATTRS:
                continue
            values = split_srcset(value) if name == "srcset" else [value]
            self.references.extend(Reference(self.source, name, item) for item in values)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._consume(attrs)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._consume(attrs)


def split_srcset(value: str) -> list[str]:
    if value.lstrip().lower().startswith("data:"):
        return [value.strip()]
    return [item.strip().split()[0] for item in value.split(",") if item.strip()]


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def relative_path(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def route_for_file(relative: str) -> str:
    if relative == "index.html":
        return "/"
    if relative.endswith("/index.html"):
        return f"/{relative[:-len('index.html')]}"
    return f"/{relative}"


def safe_unquote(value: str) -> str:
    decoded = unquote(value, errors="strict")
    if "\x00" in decoded:
        raise ValueError("NUL byte in URL path")
    return decoded


def resolve_generated_target(pathname: str, file_inventory: set[str]) -> tuple[str | None, list[str]]:
    decoded = safe_unquote(pathname)
    if not decoded.startswith("/"):
        raise ValueError(f"Resolved path is not absolute: {decoded}")
    normalized = str(PurePosixPath(decoded))
    if decoded.endswith("/") and normalized != "/":
        normalized += "/"
    if normalized.startswith("/../") or normalized == "/..":
        raise ValueError(f"Path escapes generated root: {decoded}")
    relative = normalized.lstrip("/")
    if normalized == "/":
        candidates = ["index.html"]
    elif normalized.endswith("/"):
        candidates = [f"{relative}index.html"]
    else:
        candidates = [relative, f"{relative}/index.html"]
    return next((candidate for candidate in candidates if candidate in file_inventory), None), candidates


def scan_tree(root: Path) -> tuple[list[Path], list[dict[str, object]]]:
    files: list[Path] = []
    unsupported: list[dict[str, object]] = []
    for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
        mode = path.lstat().st_mode
        if stat.S_ISLNK(mode):
            unsupported.append({"code": "SYMLINK", "path": relative_path(root, path), "target": os.readlink(path)})
        elif path.is_file():
            files.append(path)
        elif not path.is_dir():
            unsupported.append({"code": "UNSUPPORTED_ENTRY", "path": relative_path(root, path)})
    return files, unsupported


def audit(root: Path) -> dict[str, object]:
    root = root.resolve()
    if not root.is_dir():
        raise SystemExit(f"Generated site root is not a directory: {root}")

    files, errors = scan_tree(root)
    relative_files = {relative_path(root, path) for path in files}
    html_files = [path for path in files if path.suffix.lower() == ".html"]
    text_files = [path for path in files if path.suffix.lower() in {".html", ".css", ".svg"}]
    ids_by_html: dict[str, set[str]] = {}
    references: list[Reference] = []
    parse_errors: list[dict[str, object]] = []

    for path in html_files:
        relative = relative_path(root, path)
        try:
            text = path.read_text(encoding="utf-8")
            parser = ReferenceParser(relative)
            parser.feed(text)
            parser.close()
            ids_by_html[relative] = parser.identifiers
            references.extend(parser.references)
        except Exception as exc:  # noqa: BLE001
            parse_errors.append({"code": "HTML_PARSE_ERROR", "path": relative, "message": str(exc)})

    for path in text_files:
        relative = relative_path(root, path)
        if path.suffix.lower() == ".html":
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            parse_errors.append({"code": "TEXT_DECODE_ERROR", "path": relative, "message": str(exc)})
            continue
        if path.suffix.lower() == ".css":
            for match in CSS_URL_RE.finditer(text):
                references.append(Reference(relative, "css-url", html.unescape(next(group for group in match.groups() if group is not None)).strip()))
        else:
            for match in SVG_ATTR_RE.finditer(text):
                attribute = match.group(1).lower()
                value = html.unescape(next(group for group in match.groups()[1:] if group is not None)).strip()
                values = split_srcset(value) if attribute == "srcset" else [value]
                references.extend(Reference(relative, attribute, item) for item in values)

    errors.extend(parse_errors)
    inventory: list[dict[str, object]] = []
    files_with_references = {reference.source for reference in references}
    internal_targets: set[str] = set()
    internal_reference_count = 0
    external_reference_count = 0
    ignored_reference_count = 0
    document_reference_count = 0
    asset_reference_count = 0
    fragment_reference_count = 0

    for reference in references:
        row = asdict(reference)
        value = reference.value.strip()
        if not value:
            ignored_reference_count += 1
            inventory.append({**row, "classification": "empty"})
            continue
        try:
            parsed = urlsplit(urljoin(f"{CANONICAL_ORIGIN}{route_for_file(reference.source)}", value))
        except Exception as exc:  # noqa: BLE001
            errors.append({**row, "code": "INVALID_URL", "message": str(exc)})
            continue
        scheme = parsed.scheme.lower()
        if scheme == "javascript":
            errors.append({**row, "code": "JAVASCRIPT_URL", "message": "javascript: references are prohibited"})
            continue
        if scheme in IGNORED_SCHEMES:
            ignored_reference_count += 1
            inventory.append({**row, "classification": "ignored", "scheme": scheme})
            continue
        if scheme not in {"http", "https"}:
            errors.append({**row, "code": "UNSUPPORTED_SCHEME", "message": f"Unsupported URL scheme: {scheme}"})
            continue
        if (parsed.hostname or "").lower() not in CANONICAL_HOSTS:
            external_reference_count += 1
            inventory.append({**row, "classification": "external", "target": parsed.geturl()})
            continue

        internal_reference_count += 1
        try:
            target, candidates = resolve_generated_target(parsed.path or "/", relative_files)
        except Exception as exc:  # noqa: BLE001
            errors.append({**row, "code": "INVALID_LOCAL_PATH", "message": str(exc)})
            continue
        if target is None:
            errors.append({**row, "code": "MISSING_TARGET", "pathname": parsed.path, "candidates": candidates})
            continue
        internal_targets.add(target)
        is_document = target.endswith(".html")
        document_reference_count += int(is_document)
        asset_reference_count += int(not is_document)
        fragment = ""
        if parsed.fragment:
            fragment_reference_count += 1
            try:
                fragment = safe_unquote(parsed.fragment)
            except Exception as exc:  # noqa: BLE001
                errors.append({**row, "code": "INVALID_FRAGMENT", "message": str(exc)})
                continue
            if is_document and fragment not in ids_by_html.get(target, set()):
                errors.append({**row, "code": "MISSING_FRAGMENT", "target": target, "fragment": fragment})
                continue
        inventory.append({**row, "classification": "internal", "target": target, "fragment": fragment})

    html_without_references = sorted(relative_path(root, path) for path in html_files if relative_path(root, path) not in files_with_references)
    if not html_files:
        errors.append({"code": "VACUOUS_HTML_SET", "message": "No generated HTML files were found"})
    if not references:
        errors.append({"code": "VACUOUS_REFERENCE_SET", "message": "No references were extracted"})
    if internal_reference_count == 0:
        errors.append({"code": "VACUOUS_INTERNAL_SET", "message": "No same-site references were validated"})
    if document_reference_count == 0:
        errors.append({"code": "VACUOUS_DOCUMENT_SET", "message": "No generated document references were validated"})
    if asset_reference_count == 0:
        errors.append({"code": "VACUOUS_ASSET_SET", "message": "No generated asset references were validated"})

    normalized_inventory = "\n".join(sorted(json.dumps(row, sort_keys=True, separators=(",", ":")) for row in inventory)) + "\n"
    result: dict[str, object] = {
        "auditor": "r7f-independent-link-audit.py",
        "root": str(root),
        "generatedFileCount": len(files),
        "htmlFileCount": len(html_files),
        "scannedTextFileCount": len(text_files),
        "referenceCount": len(references),
        "internalReferenceCount": internal_reference_count,
        "externalReferenceCount": external_reference_count,
        "ignoredReferenceCount": ignored_reference_count,
        "documentReferenceCount": document_reference_count,
        "assetReferenceCount": asset_reference_count,
        "fragmentReferenceCount": fragment_reference_count,
        "uniqueInternalTargetCount": len(internal_targets),
        "htmlFilesWithoutReferences": html_without_references,
        "inventorySha256": sha256_bytes(normalized_inventory.encode()),
        "brokenCount": len(errors),
        "errors": errors,
        "passed": not errors,
    }
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Independent, non-vacuous generated-site link/asset/fragment audit")
    parser.add_argument("root", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    result = audit(args.root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    if not result["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
