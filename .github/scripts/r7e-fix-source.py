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

# Keep the full factual H1 while allowing a concise, human-authored metadata title.
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
    '<BaseLayout title={record.data.title} metaTitle={record.data.title.split(\':\')[0]} canonicalPath={record.data.route} description={record.data.summary}>',
    'writing concise metadata title',
)

print('Applied audited R7E corrections: optional href, module-scoped VCE component, runtime audit semantics, unique contribution IDs, concise metadata title.')
