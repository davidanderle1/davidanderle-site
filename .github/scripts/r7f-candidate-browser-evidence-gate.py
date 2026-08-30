#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

EXPECTED_ROUTES = [
    ('home', '/', 'David Anderle'),
    ('work', '/work/', 'Work.'),
    ('merkle', '/work/merkle-poseidon/', 'Merkle Commitments with Poseidon in Rust'),
    ('vce', '/work/volatility-cascade-engine/', 'Volatility Cascade Engine'),
    ('writing', '/writing/', 'Writing.'),
    ('article', '/writing/protecting-retail-investors/', 'Protecting Retail Investors: A Framework for Transparency and Risk Controls in High-Volatility Trading'),
    ('archive', '/archive/', 'Record.'),
    ('about', '/about/', 'Current context.'),
    ('about-no-photo', '/about/no-photo/', 'David Anderle.'),
    ('cv', '/cv/', 'Facts.'),
    ('contact', '/contact/', 'Contact.'),
    ('privacy', '/privacy/', 'Privacy.'),
    ('security', '/security/', 'Security.'),
    ('404', '/404.html', 'Off route.'),
]


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding='utf-8'))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def screenshot_path(tmp_root: Path, declared: str) -> Path:
    marker = '.r7e-tmp/'
    relative = declared.split(marker, 1)[1] if marker in declared else declared.lstrip('./')
    return tmp_root / relative


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('tmp_root', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    tmp = args.tmp_root.resolve()
    no_js_path = tmp / 'no-js-route-evidence.json'
    enhancement_path = tmp / 'vce-enhancement-evidence.json'
    browser_path = tmp / 'playwright' / 'browser-results.json'
    checks: dict[str, bool] = {
        'present:no-js-route-evidence': no_js_path.is_file(),
        'present:vce-enhancement-evidence': enhancement_path.is_file(),
        'present:browser-results': browser_path.is_file(),
    }
    metrics: dict[str, object] = {}
    failures: list[dict[str, object]] = []

    if all(checks.values()):
        no_js = load(no_js_path)
        enhancement = load(enhancement_path)
        browser = load(browser_path)
        routes = no_js.get('routes') if isinstance(no_js.get('routes'), list) else []
        route_rows = [(row.get('name'), row.get('url'), row.get('heading')) for row in routes]
        checks.update({
            'no-js:designation': no_js.get('designation') == 'NO_JAVASCRIPT_ROUTE_EVIDENCE',
            'no-js:passed': no_js.get('passed') is True,
            'no-js:disabled': no_js.get('javaScriptEnabled') is False,
            'no-js:route-count': no_js.get('routeCount') == len(EXPECTED_ROUTES) == len(routes),
            'no-js:exact-route-headings': route_rows == EXPECTED_ROUTES,
            'no-js:statuses': all(row.get('responseStatus') == 200 for row in routes),
            'no-js:final-paths': all(row.get('finalPathname') == row.get('url') for row in routes),
            'no-js:substantive-main': all(isinstance(row.get('mainTextCharacters'), int) and row['mainTextCharacters'] > 20 for row in routes),
            'no-js:ordinary-zero-script-requests': all(row.get('scriptRequestCount') == 0 for row in routes if row.get('name') != 'vce'),
        })
        vce = no_js.get('vce') if isinstance(no_js.get('vce'), dict) else {}
        no_js_shot = screenshot_path(tmp, str(vce.get('screenshotPath', '')))
        checks.update({
            'no-js-vce:four-panels': vce.get('panelCount') == 4,
            'no-js-vce:four-visible': vce.get('visiblePanelCount') == 4,
            'no-js-vce:status': vce.get('status') == 'Static sequence: all steps visible.',
            'no-js-vce:screenshot-present': no_js_shot.is_file(),
            'no-js-vce:screenshot-hash': no_js_shot.is_file() and sha256(no_js_shot) == vce.get('screenshotSha256'),
        })
        enhancement_shot = screenshot_path(tmp, str(enhancement.get('screenshotPath', '')))
        script_request = str(enhancement.get('scriptRequest') or '')
        checks.update({
            'enhancement:designation': enhancement.get('designation') == 'VCE_ROUTE_LOCAL_ENHANCEMENT_EVIDENCE',
            'enhancement:passed': enhancement.get('passed') is True,
            'enhancement:ready': enhancement.get('componentReady') == 'true',
            'enhancement:four-buttons': enhancement.get('buttonCount') == 4,
            'enhancement:four-panels': enhancement.get('panelCount') == 4,
            'enhancement:home-selection': enhancement.get('selectedIndexAfterHome') == 0,
            'enhancement:one-visible-after-home': enhancement.get('visiblePanelCountAfterHome') == 1,
            'enhancement:home-status': enhancement.get('statusAfterHome') == 'Showing Initial loss. Essential content remains available without JavaScript.',
            'enhancement:hashed-route-script': bool(re.search(r'/assets/js/vce-sequence\.[a-f0-9]+\.js(?:\?|$)', script_request)),
            'enhancement:screenshot-price-impact': enhancement.get('screenshotSelectedIndex') == 3,
            'enhancement:screenshot-present': enhancement_shot.is_file(),
            'enhancement:screenshot-hash': enhancement_shot.is_file() and sha256(enhancement_shot) == enhancement.get('screenshotSha256'),
        })
        suites = browser.get('suites') if isinstance(browser.get('suites'), list) else []
        stats = browser.get('stats') if isinstance(browser.get('stats'), dict) else {}
        checks.update({
            'browser:forty-two-expected': stats.get('expected') == 42,
            'browser:no-unexpected': stats.get('unexpected') == 0,
            'browser:no-flaky': stats.get('flaky') == 0,
            'browser:suites-present': len(suites) > 0,
        })
        screenshots = sorted((tmp / 'screenshots').glob('*.png'))
        checks['screenshots:at-least-41'] = len(screenshots) >= 41
        metrics = {
            'routeCount': len(routes),
            'screenshotCount': len(screenshots),
            'browserExpected': stats.get('expected'),
            'browserUnexpected': stats.get('unexpected'),
            'noJsVceScreenshot': str(no_js_shot),
            'enhancedVceScreenshot': str(enhancement_shot),
        }
    else:
        failures.append({'code': 'MISSING_EVIDENCE', 'checks': checks})

    failed_checks = [name for name, passed in checks.items() if not passed]
    result = {
        'designation': 'R7F_V4_CANDIDATE_BROWSER_EVIDENCE_GATE',
        'passed': not failed_checks and not failures,
        'tmpRoot': str(tmp),
        'checks': checks,
        'failedChecks': failed_checks,
        'metrics': metrics,
        'failures': failures,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, indent=2))
    if not result['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
