#!/usr/bin/env python3
from pathlib import Path
import sys

root = Path(sys.argv[1] if len(sys.argv) > 1 else 'candidate')


def replace_exact(rel: str, old: str, new: str, label: str) -> None:
    path = root / rel
    text = path.read_text()
    if old not in text:
        raise SystemExit(f'{label}: expected source pattern not found in {rel}')
    path.write_text(text.replace(old, new))

# TypeScript exactOptionalPropertyTypes: omit optional href rather than materializing undefined.
replace_exact(
    'src/pages/index.astro',
    "...milestones.slice(0, 3).map((item) => ({ date: item.data.date, title: item.data.title, context: item.data.description, href: item.data.workRecordId ? '/work/volatility-cascade-engine/' : undefined })),",
    "...milestones.slice(0, 3).map((item) => ({ date: item.data.date, title: item.data.title, context: item.data.description, ...(item.data.workRecordId ? { href: '/work/volatility-cascade-engine/' } : {}) })),",
    'homepage optional href',
)

# Route-local Web Component must be module-scoped and not retain an unread private field.
vce = root / 'src/scripts/vce-sequence.ts'
text = vce.read_text().replace('  private active = 0;\n', '').replace('    this.active = index;\n', '')
if 'export {};' not in text:
    text += '\nexport {};\n'
vce.write_text(text)

# Dist audit must reject external runtime assets, not legitimate absolute canonical/OG metadata URLs.
replace_exact(
    'scripts/inspect-dist.mjs',
    "if (/<(?:script|link)[^>]+(?:src|href)=[\"']https?:\\/\\//i.test(text)) findings.push({code:'EXTERNAL_RUNTIME_ASSET',file:rel});",
    "if (/<script[^>]+src=[\"']https?:\\/\\//i.test(text) || /<link[^>]+rel=[\"']stylesheet[\"'][^>]+href=[\"']https?:\\/\\//i.test(text) || /<link[^>]+href=[\"']https?:\\/\\/[^\"']+[\"'][^>]+rel=[\"']stylesheet[\"']/i.test(text)) findings.push({code:'EXTERNAL_RUNTIME_ASSET',file:rel});",
    'runtime asset audit',
)

# Markdown generates #contribution for the project body, so the role boundary component needs its own ID.
replace_exact(
    'src/components/RoleContribution.astro',
    '<section class="boundary-grid" id="contribution" aria-labelledby="contribution-title">',
    '<section class="boundary-grid" id="role-boundary" aria-labelledby="contribution-title">',
    'duplicate contribution id',
)

# Keep the full factual H1 while allowing a concise metadata title.
replace_exact(
    'src/components/HeadMetadata.astro',
    "interface Props { title?: string; description?: string; canonicalPath?: string; noindex?: boolean; }\nconst { title, description = site.description, canonicalPath = '/', noindex = false } = Astro.props;\nconst fullTitle = title ? `${title} | ${site.name}` : `${site.name} | Technical work and public record`;",
    "interface Props { title?: string; metaTitle?: string; description?: string; canonicalPath?: string; noindex?: boolean; }\nconst { title, metaTitle, description = site.description, canonicalPath = '/', noindex = false } = Astro.props;\nconst effectiveTitle = metaTitle ?? title;\nconst fullTitle = effectiveTitle ? `${effectiveTitle} | ${site.name}` : `${site.name} | Technical work and public record`;",
    'metadata title support',
)
replace_exact(
    'src/layouts/BaseLayout.astro',
    'interface Props { title?: string; description?: string; canonicalPath?: string; noindex?: boolean; }',
    'interface Props { title?: string; metaTitle?: string; description?: string; canonicalPath?: string; noindex?: boolean; }',
    'base layout metadata title support',
)
replace_exact(
    'src/pages/writing/[slug].astro',
    '<BaseLayout title={record.data.title} canonicalPath={record.data.route} description={record.data.summary}>',
    '<BaseLayout title={record.data.title} metaTitle={record.data.title.split(\':\', 1)[0] ?? record.data.title} canonicalPath={record.data.route} description={record.data.summary}>',
    'writing concise metadata title',
)

# Narrow-screen resilience: large technical headings and metadata must wrap inside their own boxes.
# This deliberately fixes intrinsic sizing rather than hiding document overflow.
replace_exact(
    'src/styles/project.css',
    '.project-hero h1 { margin: .3rem 0 1.5rem; font-size: clamp(3.1rem, 8vw, 8.2rem); line-height: .82; letter-spacing: -.072em; max-width: 11ch; text-wrap: balance; }',
    '.project-hero h1 { margin: .3rem 0 1.5rem; font-size: clamp(3.1rem, 8vw, 8.2rem); line-height: .82; letter-spacing: -.072em; max-width: 11ch; text-wrap: balance; overflow-wrap: anywhere; }',
    'project title narrow reflow',
)
replace_exact(
    'src/styles/project.css',
    '.project-facts div { padding-top: 1rem; border-top: 1px solid var(--line); }\n.project-facts dt { margin-bottom: .4rem; }',
    '.project-facts div { min-inline-size: 0; padding-top: 1rem; border-top: 1px solid var(--line); }\n.project-facts dt { margin-bottom: .4rem; }\n.project-facts dd { overflow-wrap: anywhere; }',
    'project metadata narrow reflow',
)
replace_exact(
    'src/styles/project.css',
    '.boundary-grid > div:last-child { color: var(--ink-soft); font-size: 1.1rem; }',
    '.boundary-grid > * { min-inline-size: 0; }\n.boundary-grid > div:last-child { color: var(--ink-soft); font-size: 1.1rem; overflow-wrap: anywhere; }',
    'boundary grid intrinsic sizing',
)
replace_exact(
    'src/styles/project.css',
    '.evidence-links a { display: grid; grid-template-columns: 9rem 1fr auto; gap: 1rem; align-items: center; min-height: 4.2rem; text-decoration: none; }',
    '.evidence-links a { display: grid; grid-template-columns: 9rem minmax(0, 1fr) auto; gap: 1rem; align-items: center; min-height: 4.2rem; text-decoration: none; }\n.evidence-links a > * { min-inline-size: 0; overflow-wrap: anywhere; }',
    'evidence link intrinsic sizing',
)
replace_exact(
    'src/styles/project.css',
    '.provenance-block dl { display: grid; grid-template-columns: repeat(3,1fr); gap: 1rem; margin: 0; }',
    '.provenance-block dl { display: grid; grid-template-columns: repeat(3,minmax(0,1fr)); gap: 1rem; margin: 0; }\n.provenance-block dl > *, .provenance-block dd { min-inline-size: 0; overflow-wrap: anywhere; }',
    'provenance intrinsic sizing',
)

print('Applied audited R7E corrections: optional href, module-scoped VCE component, runtime audit semantics, unique contribution IDs, concise metadata title, and narrow project-text reflow.')
