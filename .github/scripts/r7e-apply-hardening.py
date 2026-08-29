#!/usr/bin/env python3
from __future__ import annotations

import contextlib
import io
import json
import runpy
import sys
from pathlib import Path


def replace_exact(path: Path, old: str, new: str, label: str) -> None:
    text = path.read_text(encoding='utf-8')
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'{label}: expected one source block in {path}, found {count}')
    path.write_text(text.replace(old, new), encoding='utf-8')


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit('usage: r7e-apply-hardening.py <candidate-root>')

    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        runpy.run_path(str(Path(__file__).with_name('r7e-install-overlay.py')), run_name='__main__')

    installer_result = json.loads(output.getvalue())
    candidate = Path(sys.argv[1]).resolve()
    browser_test = candidate / 'tests/browser.spec.ts'

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
    const images = Array.from(document.images).filter((image) => {
      const style = getComputedStyle(image);
      const rect = image.getBoundingClientRect();
      return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0 && rect.bottom >= 0 && rect.top <= innerHeight * 2;
    });
    await Promise.allSettled(images.map(async (image) => {
      if (!image.complete) {
        await Promise.race([
          new Promise<void>((resolve) => {
            const done = () => resolve();
            image.addEventListener('load', done, { once: true });
            image.addEventListener('error', done, { once: true });
            if (image.complete) resolve();
          }),
          new Promise<void>((resolve) => setTimeout(resolve, 2000)),
        ]);
      }
      if (image.complete) {
        try { await image.decode(); } catch {}
      }
    }));
    await new Promise<void>((resolve) => requestAnimationFrame(() => requestAnimationFrame(() => resolve())));
  });
}
"""

    replace_exact(browser_test, old, new, 'bounded browser image settling')
    installer_result['postOverlayCorrections'] = {
        'boundedImageSettling': True,
        'reason': 'Do not deadlock on hidden or intentionally lazy images; visible near-viewport images retain a bounded load/decode wait.',
        'file': 'tests/browser.spec.ts',
    }
    print(json.dumps(installer_result, indent=2))


if __name__ == '__main__':
    main()
