#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def replace_exact(root: Path, relative: str, old: str, new: str, label: str) -> None:
    path = root / relative
    text = path.read_text(encoding='utf-8')
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'{label}: expected exactly one source pattern in {relative}, found {count}')
    path.write_text(text.replace(old, new), encoding='utf-8')


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit('usage: r7e-finalize-candidate.py <candidate-root>')
    root = Path(sys.argv[1]).resolve()
    if not (root / 'package.json').is_file():
        raise SystemExit(f'candidate source missing: {root}')

    old = """async function settle(page: Page) {
  await page.evaluate(async () => {
    if ('fonts' in document) await (document as Document & { fonts: FontFaceSet }).fonts.ready;
    for (const image of Array.from(document.images)) {
      if (!image.complete) await new Promise<void>((resolve) => {
        image.addEventListener('load', () => resolve(), { once: true });
        image.addEventListener('error', () => resolve(), { once: true });
      });
      try { await image.decode(); } catch {}
    }
    await new Promise<void>((resolve) => requestAnimationFrame(() => requestAnimationFrame(() => resolve())));
  });
}
"""
    new = """async function settle(page: Page) {
  await page.evaluate(async () => {
    if ('fonts' in document) await (document as Document & { fonts: FontFaceSet }).fonts.ready;
    await Promise.all(Array.from(document.images).map(async (image) => {
      if (!image.complete) {
        await new Promise<void>((resolve) => {
          let finished = false;
          const finish = () => {
            if (finished) return;
            finished = true;
            image.removeEventListener('load', finish);
            image.removeEventListener('error', finish);
            clearTimeout(timeout);
            resolve();
          };
          const timeout = window.setTimeout(finish, 2000);
          image.addEventListener('load', finish, { once: true });
          image.addEventListener('error', finish, { once: true });
          if (image.complete) finish();
        });
      }
      try { await image.decode(); } catch {}
    }));
    await new Promise<void>((resolve) => requestAnimationFrame(() => requestAnimationFrame(() => resolve())));
  });
}
"""
    replace_exact(root, 'tests/browser.spec.ts', old, new, 'bounded image-settle race fix')

    browser = root / 'tests/browser.spec.ts'
    text = browser.read_text(encoding='utf-8')
    checks = {
        'boundedImageWait': 'window.setTimeout(finish, 2000)' in text,
        'lateCompletionRecheck': 'if (image.complete) finish();' in text,
        'eventCleanup': "image.removeEventListener('load', finish);" in text,
        'layoutStabilizationPreserved': 'requestAnimationFrame(() => requestAnimationFrame' in text,
    }
    if not all(checks.values()):
        raise SystemExit(json.dumps({'passed': False, 'checks': checks}, indent=2))

    print(json.dumps({
        'passed': True,
        'reason': 'Prevent a load/error race from hanging the browser matrix while retaining bounded image decode and layout stabilization.',
        'changedFiles': [{'path': 'tests/browser.spec.ts', 'bytes': browser.stat().st_size, 'sha256': sha256(browser)}],
        'checks': checks,
    }, indent=2))


if __name__ == '__main__':
    main()
