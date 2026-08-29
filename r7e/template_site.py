from __future__ import annotations

from textwrap import dedent


def d(value: str) -> str:
    return dedent(value).lstrip("\n")


def site_files(versions: dict[str, str], node_version: str, npm_version: str) -> dict[str, str]:
    package_json = {
        "name": "david-anderle-bearing-production-reference",
        "version": "0.0.0-r7e",
        "private": True,
        "type": "module",
        "description": "Production-reference static Astro implementation of the approved Bearing identity system.",
        "packageManager": f"npm@{npm_version}",
        "engines": {"node": node_version, "npm": npm_version},
        "scripts": {
            "check": "astro check",
            "validate:content": "node scripts/validate-content.mjs",
            "select:portrait": "node scripts/select-portrait-source.mjs ..",
            "images": "node scripts/process-images.mjs",
            "build": "npm run validate:content && npm run images && astro build",
            "build:astro": "astro build",
            "verify:source": "node scripts/verify-source.mjs",
            "verify:dist": "node scripts/verify-dist.mjs dist",
            "generate:scale": "node scripts/generate-scale-fixtures.mjs 500",
            "verify:scale": "node scripts/verify-scale.mjs",
            "clear:scale": "node scripts/clear-scale-fixtures.mjs",
            "test:browser": "playwright test",
            "test:lighthouse": "node scripts/run-lighthouse.mjs",
            "test:wrangler-preview": "node scripts/test-wrangler-preview.mjs",
            "verify:reproducibility": "node scripts/verify-reproducibility.mjs",
            "finalize:evidence": "node scripts/finalize-evidence.mjs",
            "package:r7e": "python3 scripts/package_r7e.py"
        },
        "devDependencies": {
            "@astrojs/check": versions["@astrojs/check"],
            "@axe-core/playwright": versions["@axe-core/playwright"],
            "@playwright/test": versions["@playwright/test"],
            "astro": versions["astro"],
            "gray-matter": versions["gray-matter"],
            "lighthouse": versions["lighthouse"],
            "parse5": versions["parse5"],
            "sharp": versions["sharp"],
            "typescript": versions["typescript"],
            "wrangler": versions["wrangler"]
        }
    }

    import json
    files: dict[str, str] = {
        "package.json": json.dumps(package_json, indent=2) + "\n",
        ".node-version": node_version + "\n",
        ".npmrc": "engine-strict=true\nfund=false\naudit=false\n",
        ".editorconfig": d("""
            root = true

            [*]
            charset = utf-8
            end_of_line = lf
            insert_final_newline = true
            indent_style = space
            indent_size = 2
            trim_trailing_whitespace = true

            [*.py]
            indent_size = 4
        """),
        ".gitignore": d("""
            node_modules/
            .astro/
            dist/
            dist-scale/
            evidence/
            R7E_PACKAGE/
            R7E_OUTPUT/
            playwright-report/
            test-results/
            src/content/scale/*.md
        """),
        "astro.config.mjs": d("""
            import { defineConfig } from 'astro/config';

            export default defineConfig({
              site: 'https://davidanderle.com',
              output: 'static',
              trailingSlash: 'always',
              compressHTML: true,
              outDir: process.env.R7E_OUT_DIR || './dist',
              build: {
                format: 'directory',
                inlineStylesheets: 'never'
              }
            });
        """),
        "tsconfig.json": d("""
            {
              "extends": "astro/tsconfigs/strict",
              "compilerOptions": {
                "noUncheckedIndexedAccess": true,
                "exactOptionalPropertyTypes": true,
                "verbatimModuleSyntax": true
              }
            }
        """),
        "wrangler.jsonc": d("""
            {
              "$schema": "./node_modules/wrangler/config-schema.json",
              "name": "david-anderle-bearing",
              "compatibility_date": "2026-08-29",
              "assets": {
                "directory": "./dist",
                "not_found_handling": "404-page",
                "html_handling": "auto-trailing-slash"
              }
            }
        """),
        "playwright.config.ts": d("""
            import { defineConfig, devices } from '@playwright/test';

            export default defineConfig({
              testDir: './tests',
              outputDir: './evidence/browser/test-results',
              fullyParallel: false,
              workers: 1,
              retries: 0,
              timeout: 45_000,
              expect: { timeout: 8_000 },
              reporter: [
                ['line'],
                ['json', { outputFile: './evidence/browser/playwright-report.json' }],
                ['html', { outputFolder: './evidence/browser/html-report', open: 'never' }]
              ],
              use: {
                baseURL: 'http://127.0.0.1:4321',
                trace: 'retain-on-failure',
                screenshot: 'only-on-failure',
                video: 'off'
              },
              webServer: {
                command: 'python3 -m http.server 4321 --bind 127.0.0.1 --directory dist',
                url: 'http://127.0.0.1:4321/',
                reuseExistingServer: false,
                timeout: 30_000,
                stdout: 'pipe',
                stderr: 'pipe'
              },
              projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }]
            });
        """),
        "README.md": d("""
            # Bearing production reference

            This directory is a real static Astro repository built for the R7E evidence-production stage of davidanderle.com.

            It is not a release certificate. `R7E_EVIDENCE_INDEX.json` records native observations and leaves every final disposition open for independent R7F review.

            ## Architecture

            Astro static output, typed content collections, canonical Markdown and JSON, explicit cross-record validation, authored CSS, no global hydration, no executable JavaScript on ordinary routes, one route-local standards-based Web Component, local Sharp processing, GitHub Actions and Cloudflare Workers Static Assets in assets-only mode.

            ## Reproduce

            Use the exact Node and npm versions recorded in `.node-version`, `package.json` and `R7E_TOOLCHAIN_RESOLUTION.json`.

            ```sh
            npm ci
            npm run check
            npm run build
            npm run verify:dist
            ```

            The complete R7E workflow and raw command records are included in the packaged evidence directory.
        """),
        "SECURITY.md": d("""
            # Security model

            The production output is static. No origin application code, database, authentication layer or user-submitted form handler is part of this reference build.

            Security headers are defined in `public/_headers`. Cloudflare deployment is configured as Workers Static Assets without a Worker script. Dependency and dry-run observations are evidence inputs, not security certification.
        """),
        "public/_headers": d("""
            /*
              Content-Security-Policy: default-src 'self'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'; img-src 'self' data:; font-src 'self'; style-src 'self'; script-src 'self'; connect-src 'self'; object-src 'none'; upgrade-insecure-requests
              Cross-Origin-Opener-Policy: same-origin
              Permissions-Policy: camera=(), microphone=(), geolocation=(), payment=(), usb=(), browsing-topics=()
              Referrer-Policy: strict-origin-when-cross-origin
              X-Content-Type-Options: nosniff
              X-Frame-Options: DENY

            /_astro/*
              Cache-Control: public, max-age=31536000, immutable

            /media/*
              Cache-Control: public, max-age=31536000, immutable

            /*.html
              Cache-Control: public, max-age=0, must-revalidate
        """),
        "public/_redirects": d("""
            /projects /work/ 301
            /research /work/ 301
            /notes /writing/ 301
        """),
        "public/robots.txt": d("""
            User-agent: *
            Allow: /
            Disallow: /scale/
            Sitemap: https://davidanderle.com/sitemap.xml
        """),
        "public/favicon.svg": d("""
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" role="img" aria-label="DA">
              <rect width="64" height="64" rx="12" fill="#171a1c"/>
              <circle cx="32" cy="32" r="18" fill="none" stroke="#d96f3d" stroke-width="5"/>
              <circle cx="32" cy="32" r="5" fill="#f2eee5"/>
              <path d="M32 4v10M32 50v10M4 32h10M50 32h10" stroke="#f2eee5" stroke-width="3"/>
            </svg>
        """),
        "src/env.d.ts": "/// <reference types=\"astro/client\" />\n",
        "src/content.config.ts": d("""
            import { defineCollection, z } from 'astro:content';
            import { file, glob } from 'astro/loaders';

            const maturity = z.enum(['working-prototype', 'research-in-progress', 'private-system', 'published-note']);
            const authorship = z.enum(['solo', 'contributor', 'collaborative']);
            const material = z.enum(['graphite', 'oxide', 'paper']);

            const projects = defineCollection({
              loader: glob({ base: './src/content/projects', pattern: '**/*.{md,mdx}' }),
              schema: z.object({
                title: z.string().min(3),
                slug: z.string().regex(/^[a-z0-9-]+$/),
                summary: z.string().min(40),
                publishedAt: z.coerce.date(),
                year: z.number().int().min(2020).max(2035),
                role: z.string().min(5),
                maturity,
                authorship,
                access: z.enum(['public', 'private', 'restricted']),
                material,
                featured: z.boolean(),
                sortOrder: z.number().int(),
                evidence: z.array(z.object({ label: z.string(), value: z.string() })).min(2),
                links: z.array(z.object({ label: z.string(), href: z.string().url() })),
                relatedNotes: z.array(z.string())
              })
            });

            const notes = defineCollection({
              loader: glob({ base: './src/content/notes', pattern: '**/*.{md,mdx}' }),
              schema: z.object({
                title: z.string().min(3),
                slug: z.string().regex(/^[a-z0-9-]+$/),
                summary: z.string().min(35),
                publishedAt: z.coerce.date(),
                year: z.number().int().min(2020).max(2035),
                status: z.enum(['working-note', 'technical-note']),
                material,
                relatedProjects: z.array(z.string())
              })
            });

            const experience = defineCollection({
              loader: file('./src/content/data/experience.json'),
              schema: z.object({
                id: z.string(),
                organization: z.string(),
                role: z.string(),
                location: z.string(),
                start: z.string(),
                end: z.string(),
                prominence: z.enum(['primary', 'secondary']),
                summary: z.string()
              })
            });

            const education = defineCollection({
              loader: file('./src/content/data/education.json'),
              schema: z.object({
                id: z.string(),
                institution: z.string(),
                programme: z.string(),
                startYear: z.number().int(),
                endYear: z.number().int(),
                status: z.enum(['current', 'completed']),
                prominence: z.enum(['primary', 'secondary']),
                summary: z.string()
              })
            });

            const scale = defineCollection({
              loader: glob({ base: './src/content/scale', pattern: '**/*.md' }),
              schema: z.object({
                title: z.string(),
                slug: z.string().regex(/^scale-[0-9]{4}$/),
                year: z.number().int().min(2017).max(2026),
                sequence: z.number().int().min(1).max(500),
                material,
                summary: z.string().min(30)
              })
            });

            export const collections = { projects, notes, experience, education, scale };
        """),
        "src/data/site.json": d("""
            {
              "name": "David Anderle",
              "descriptor": "Informatics student building quantitative research and risk systems.",
              "location": "Prague, Czechia",
              "email": "david@davidanderle.com",
              "github": "https://github.com/davidanderle1",
              "site": "https://davidanderle.com"
            }
        """),
        "src/data/content-provenance.json": d("""
            {
              "authorityOrder": ["R4", "R5", "R6C", "R6D", "current official documentation", "R7", "old prototype"],
              "contentPolicy": "Only claims supported by the supplied authority packages or David Anderle's existing public project records are represented.",
              "photographyPolicy": "The compact portrait is enabled only when a 320 x 320 candidate source is found and processed without enlargement. Exact R5 identity provenance remains an independent R7F comparison unless a matching authority hash is present.",
              "researchBoundary": "Research-in-progress and prototype records are never labelled completed publications or production systems."
            }
        """),
        "src/content/data/education.json": d("""
            [
              {
                "id": "czu-informatics",
                "institution": "Czech University of Life Sciences Prague, Faculty of Economics and Management",
                "programme": "BSc Informatics",
                "startYear": 2024,
                "endYear": 2027,
                "status": "current",
                "prominence": "primary",
                "summary": "Current bachelor's study in informatics, with emphasis on programming, algorithms, data work and systems thinking."
              },
              {
                "id": "uw-madison-exchange",
                "institution": "University of Wisconsin–Madison",
                "programme": "Exchange study in finance, economics and financial modelling",
                "startYear": 2025,
                "endYear": 2026,
                "status": "completed",
                "prominence": "secondary",
                "summary": "A completed exchange year that broadened the finance and economics context behind the technical work."
              }
            ]
        """),
        "src/content/data/experience.json": d("""
            [
              {
                "id": "independent-quantitative-work",
                "organization": "Independent research and engineering",
                "role": "Student researcher and builder",
                "location": "Prague, Czechia",
                "start": "2025-01",
                "end": "present",
                "prominence": "primary",
                "summary": "Building bounded research prototypes, data pipelines and risk-oriented tooling while documenting limits and evidence."
              },
              {
                "id": "uw-context",
                "organization": "University of Wisconsin–Madison",
                "role": "Exchange student",
                "location": "Madison, Wisconsin",
                "start": "2025-08",
                "end": "2026-07",
                "prominence": "secondary",
                "summary": "Completed academic exchange; retained as historical context rather than the centre of the identity system."
              }
            ]
        """),
        "src/content/projects/research-workspace.md": d("""
            ---
            title: Quantitative research workspace
            slug: research-workspace
            summary: A private, versioned workspace for market data, portfolio-risk analysis, research experiments and controlled execution interfaces.
            publishedAt: 2026-07-31
            year: 2026
            role: System designer and primary implementer
            maturity: private-system
            authorship: solo
            access: private
            material: graphite
            featured: true
            sortOrder: 1
            evidence:
              - label: Recorded version
                value: v0.5.0-rc.1
              - label: Core stack
                value: Python, FastAPI, PostgreSQL, Parquet and DuckDB
              - label: Boundary
                value: Research workspace, not an investment product
            links: []
            relatedNotes:
              - risk-before-optimization
            ---

            ## What exists

            The workspace separates research data, portfolio-risk calculations, scheduling and controlled execution interfaces. It is designed around explicit boundaries between exploration, validation and anything capable of touching a brokerage connection.

            ## Why it matters

            The useful evidence is not a claim of profitable trading. It is the engineering discipline: reproducible data paths, clear interfaces, controlled state and a record of what has and has not been validated.

            ## Current boundary

            The repository is private. The recorded release is a release candidate and should not be interpreted as a production trading platform or a verified source of returns.
        """),
        "src/content/projects/non-core-real-estate.md": d("""
            ---
            title: Non-core real-estate return research
            slug: non-core-real-estate
            summary: An empirical research extension examining how acquisition strategy and property lifecycle relate to non-core real-estate returns.
            publishedAt: 2026-06-18
            year: 2026
            role: Research contributor developing property-level follow-up analysis
            maturity: research-in-progress
            authorship: contributor
            access: restricted
            material: oxide
            featured: true
            sortOrder: 2
            evidence:
              - label: Research context
                value: Asset-level non-core real-estate data
              - label: Analytical direction
                value: Dispersion, lifecycle and risk-sensitive follow-up
              - label: Boundary
                value: Work in progress; no final independent paper claimed
            links: []
            relatedNotes:
              - evidence-before-conclusion
            ---

            ## Research question

            Aggregate return differences can hide wide property-level dispersion. The follow-up work asks where that dispersion comes from, how it changes across lifecycle stages and how conclusions move once risk and composition are treated explicitly.

            ## Contribution boundary

            This record describes a supervised research contribution and intended empirical extension. It does not present the underlying dataset as public, does not claim sole authorship and does not label unfinished analysis as a publication.

            ## Method direction

            The planned structure separates strategy at acquisition from lifecycle state, tests period sensitivity and reports distributions rather than relying on a single average-return ranking.
        """),
        "src/content/projects/merkle-poseidon.md": d("""
            ---
            title: Merkle–Poseidon threshold prototype
            slug: merkle-poseidon
            summary: A Rust and arkworks prototype for Poseidon commitments, Merkle membership and a bounded threshold-proof research path.
            publishedAt: 2026-05-06
            year: 2026
            role: Prototype implementer
            maturity: working-prototype
            authorship: solo
            access: public
            material: paper
            featured: true
            sortOrder: 3
            evidence:
              - label: Implemented
                value: Merkle tree, Poseidon demonstration, commitments and native checks
              - label: Not implemented
                value: Complete circuit and end-to-end zero-knowledge proof layer
              - label: Language
                value: Rust with arkworks
            links:
              - label: Public repository
                href: https://github.com/davidanderle1/merkle-poseidon
            relatedNotes:
              - prototypes-need-boundaries
            ---

            ## Implemented layer

            The repository contains the native data-structure and hashing path needed to reason about commitments and membership outside a circuit.

            ## Missing layer

            The circuit implementation and an end-to-end proof that the committed leaf values exceed a public threshold remain incomplete. The page preserves that limitation instead of turning a prototype into a finished cryptographic claim.

            ## Next technical step

            Define circuit constraints against the same Poseidon parameters, verify root consistency and then test the threshold statement with explicit fixtures before discussing performance.
        """),
        "src/content/notes/risk-before-optimization.md": d("""
            ---
            title: Risk before optimization
            slug: risk-before-optimization
            summary: A working note on why drawdown, liquidity, state control and failure modes belong before objective-function tuning.
            publishedAt: 2026-07-20
            year: 2026
            status: working-note
            material: graphite
            relatedProjects:
              - research-workspace
            ---

            Optimization can improve a model inside its assumptions while leaving the system exposed outside them. The first design questions are therefore about data failure, liquidity, position limits, recovery and observability. Only after those boundaries are explicit does tuning become meaningful.
        """),
        "src/content/notes/evidence-before-conclusion.md": d("""
            ---
            title: Evidence before conclusion
            slug: evidence-before-conclusion
            summary: A technical note on separating measured distributions, period effects and composition from a convenient aggregate narrative.
            publishedAt: 2026-06-25
            year: 2026
            status: technical-note
            material: oxide
            relatedProjects:
              - non-core-real-estate
            ---

            An average difference is a starting observation, not a causal conclusion. A credible extension should expose dispersion, sample composition, time dependence and uncertainty before it compresses the result into a ranking.
        """),
        "src/content/notes/prototypes-need-boundaries.md": d("""
            ---
            title: Prototypes need explicit boundaries
            slug: prototypes-need-boundaries
            summary: A working note on documenting the missing layer of a technical prototype as prominently as the implemented layer.
            publishedAt: 2026-05-12
            year: 2026
            status: working-note
            material: paper
            relatedProjects:
              - merkle-poseidon
            ---

            A prototype becomes misleading when the interface looks finished but the security or validation layer is absent. The record should name what runs, what is only sketched and what evidence would be required to move the maturity label.
        """),
        "src/content/scale/.gitkeep": "",
        "src/layouts/BaseLayout.astro": d("""
            ---
            import '../styles/global.css';
            import BearingHeader from '../components/BearingHeader.astro';
            import BearingFooter from '../components/BearingFooter.astro';
            import site from '../data/site.json';

            interface Props {
              title?: string;
              description?: string;
              material?: 'graphite' | 'oxide' | 'paper';
              noindex?: boolean;
            }

            const {
              title = site.name,
              description = site.descriptor,
              material = 'graphite',
              noindex = false
            } = Astro.props;
            const fullTitle = title === site.name ? title : `${title} | ${site.name}`;
            const canonical = new URL(Astro.url.pathname, site.site);
            ---
            <!doctype html>
            <html lang="en" data-material={material}>
              <head>
                <meta charset="UTF-8" />
                <meta name="viewport" content="width=device-width, initial-scale=1" />
                <meta name="description" content={description} />
                <meta name="theme-color" content="#171a1c" />
                {noindex && <meta name="robots" content="noindex,nofollow" />}
                <link rel="canonical" href={canonical} />
                <link rel="icon" href="/favicon.svg" type="image/svg+xml" />
                <title>{fullTitle}</title>
              </head>
              <body>
                <a class="skip-link" href="#main-content">Skip to content</a>
                <BearingHeader />
                <main id="main-content"><slot /></main>
                <BearingFooter />
              </body>
            </html>
        """),
        "src/components/BearingHeader.astro": d("""
            ---
            import site from '../data/site.json';
            const path = Astro.url.pathname;
            const links = [
              { href: '/work/', label: 'Work' },
              { href: '/writing/', label: 'Writing' },
              { href: '/archive/', label: 'Archive' },
              { href: '/about/', label: 'About' },
              { href: '/contact/', label: 'Contact' }
            ];
            ---
            <header class="site-header">
              <div class="bearing-strip" aria-hidden="true">
                <span>BEARING</span><span>50.0°N / 14.3°E</span><span>REFERENCE 07E</span>
              </div>
              <div class="header-inner">
                <a class="wordmark" href="/" aria-label={`${site.name}, home`}>
                  <span class="wordmark-mark" aria-hidden="true"><i></i></span>
                  <span>{site.name}</span>
                </a>
                <nav aria-label="Primary navigation">
                  <ul>
                    {links.map((link) => (
                      <li><a href={link.href} aria-current={path.startsWith(link.href) ? 'page' : undefined}>{link.label}</a></li>
                    ))}
                  </ul>
                </nav>
              </div>
            </header>
        """),
        "src/components/BearingFooter.astro": d("""
            ---
            import site from '../data/site.json';
            ---
            <footer class="site-footer">
              <div class="footer-inner">
                <p><strong>{site.name}</strong><br />Informatics · quantitative research · engineering</p>
                <p class="footer-coordinate">PRAGUE / 2026<br />STATIC REFERENCE BUILD</p>
                <p><a href={`mailto:${site.email}`}>{site.email}</a><br /><a href={site.github} rel="me">GitHub</a></p>
              </div>
            </footer>
        """),
        "src/components/EvidenceCard.astro": d("""
            ---
            import type { CollectionEntry } from 'astro:content';
            interface Props { project: CollectionEntry<'projects'>; compact?: boolean; }
            const { project, compact = false } = Astro.props;
            ---
            <article class:list={['evidence-card', `material-${project.data.material}`, { compact }]}>
              <div class="card-calibration" aria-hidden="true"><span></span><span></span><span></span></div>
              <p class="eyebrow">{project.data.year} · {project.data.maturity.replaceAll('-', ' ')}</p>
              <h3><a href={`/work/${project.data.slug}/`}>{project.data.title}</a></h3>
              <p>{project.data.summary}</p>
              <dl class="card-facts">
                <div><dt>Role</dt><dd>{project.data.role}</dd></div>
                <div><dt>Access</dt><dd>{project.data.access}</dd></div>
              </dl>
              <a class="text-link" href={`/work/${project.data.slug}/`}>Inspect evidence <span aria-hidden="true">→</span></a>
            </article>
        """),
        "src/components/Portrait.astro": d("""
            ---
            import fs from 'node:fs';
            import path from 'node:path';
            interface Props { forceNoPhoto?: boolean; }
            const { forceNoPhoto = false } = Astro.props;
            const imagePath = path.join(process.cwd(), 'public', 'media', 'portrait-256x320.webp');
            const present = !forceNoPhoto && fs.existsSync(imagePath);
            ---
            {present ? (
              <figure class="portrait compact-photo">
                <picture>
                  <source srcset="/media/portrait-256x320.avif" type="image/avif" />
                  <img src="/media/portrait-256x320.webp" width="256" height="320" alt="Portrait of David Anderle" loading="eager" decoding="async" />
                </picture>
                <figcaption>Compact portrait · source and processing provenance recorded in the R7E evidence package.</figcaption>
              </figure>
            ) : (
              <div class="portrait no-photo" role="img" aria-label="No-photo identity panel for David Anderle">
                <div class="no-photo-mark" aria-hidden="true"><span>DA</span></div>
                <p>DAVID ANDERLE</p>
                <small>NO-PHOTO COMPOSITION</small>
              </div>
            )}
        """),
        "src/components/ComparisonExplorer.astro": d("""
            <bearing-comparison class="comparison-explorer">
              <div class="comparison-controls" aria-label="Comparison emphasis">
                <button type="button" data-view="all" aria-pressed="true">All evidence</button>
                <button type="button" data-view="architecture" aria-pressed="false">Architecture</button>
                <button type="button" data-view="measurement" aria-pressed="false">Measurement</button>
              </div>
              <div class="comparison-grid">
                <article data-category="architecture"><p class="eyebrow">Architecture</p><h2>Static by construction</h2><p>Ordinary routes are complete HTML documents. There is no application shell and no site-wide client runtime.</p></article>
                <article data-category="measurement"><p class="eyebrow">Measurement</p><h2>Claims remain inspectable</h2><p>Native exit codes, logs, generated files, screenshots and hashes remain separate from the producer's narrative.</p></article>
                <article data-category="architecture"><p class="eyebrow">Architecture</p><h2>One bounded enhancement</h2><p>This page is the only route that loads executable JavaScript. Its baseline content remains visible when JavaScript is disabled.</p></article>
                <article data-category="measurement"><p class="eyebrow">Measurement</p><h2>R7F owns disposition</h2><p>R7E records observations. A separate audit decides whether those observations satisfy the release gates.</p></article>
              </div>
            </bearing-comparison>
            <script>
              class BearingComparison extends HTMLElement {
                connectedCallback() {
                  if (this.dataset.ready === 'true') return;
                  this.dataset.ready = 'true';
                  const buttons = Array.from(this.querySelectorAll('button[data-view]'));
                  const cards = Array.from(this.querySelectorAll('[data-category]'));
                  for (const button of buttons) {
                    button.addEventListener('click', () => {
                      const view = button.dataset.view || 'all';
                      for (const candidate of buttons) candidate.setAttribute('aria-pressed', String(candidate === button));
                      for (const card of cards) {
                        const active = view === 'all' || card.dataset.category === view;
                        card.toggleAttribute('data-deemphasized', !active);
                      }
                    });
                  }
                }
              }
              if (!customElements.get('bearing-comparison')) customElements.define('bearing-comparison', BearingComparison);
            </script>
        """),
        "src/pages/index.astro": d("""
            ---
            import { getCollection } from 'astro:content';
            import BaseLayout from '../layouts/BaseLayout.astro';
            import EvidenceCard from '../components/EvidenceCard.astro';
            import site from '../data/site.json';
            const projects = (await getCollection('projects')).sort((a, b) => a.data.sortOrder - b.data.sortOrder);
            ---
            <BaseLayout title={site.name} description={site.descriptor}>
              <section class="hero shell">
                <div class="hero-index" aria-hidden="true"><span>01</span><span>TRUE NORTH</span></div>
                <div class="hero-copy">
                  <p class="eyebrow">INFORMATICS · QUANTITATIVE RESEARCH · ENGINEERING</p>
                  <h1>David<br />Anderle</h1>
                  <p class="hero-deck">I build bounded research systems, empirical analyses and technical prototypes, then document what the evidence does and does not support.</p>
                  <div class="hero-actions"><a class="button" href="/work/">Examine the work</a><a class="text-link" href="/about/">Context and trajectory →</a></div>
                </div>
                <aside class="hero-bearing" aria-label="Current bearing">
                  <p class="eyebrow">CURRENT BEARING</p>
                  <strong>Evidence before assertion.</strong>
                  <p>Prague-based informatics student working at the intersection of code, data, risk and financial research.</p>
                  <div class="instrument" aria-hidden="true"><span class="instrument-ring"></span><span class="instrument-axis"></span><i></i></div>
                </aside>
              </section>

              <section id="selected-evidence" class="section shell evidence-section">
                <header class="section-heading"><p class="eyebrow">SELECTED EVIDENCE / 03 RECORDS</p><h2>Concrete work, early.</h2><p>Different materials for different kinds of evidence. No maturity label is implied beyond the one shown.</p></header>
                <div class="evidence-grid">{projects.map((project) => <EvidenceCard project={project} />)}</div>
              </section>

              <section class="section shell method-grid">
                <div><p class="eyebrow">OPERATING METHOD</p><h2>Build. Measure. Bound.</h2></div>
                <ol>
                  <li><span>01</span><div><strong>Define the claim</strong><p>Separate the useful question from the identity story around it.</p></div></li>
                  <li><span>02</span><div><strong>Preserve raw evidence</strong><p>Keep source, commands, logs and output independently inspectable.</p></div></li>
                  <li><span>03</span><div><strong>Name the missing layer</strong><p>A prototype or research direction stays labelled as such.</p></div></li>
                </ol>
              </section>

              <section id="trajectory" class="section shell trajectory">
                <div><p class="eyebrow">TRAJECTORY / SECONDARY CONTEXT</p><h2>From informatics toward quantitative finance.</h2></div>
                <div class="trajectory-copy"><p>Current study is a BSc in Informatics in Prague. A completed 2025–2026 exchange at the University of Wisconsin–Madison added finance, economics and financial-modelling context.</p><p>The long-term direction is rigorous quantitative work. The immediate standard is simpler: produce stronger evidence than the previous version.</p><a class="text-link" href="/about/">Read the full context →</a></div>
              </section>
            </BaseLayout>
        """),
        "src/pages/work/index.astro": d("""
            ---
            import { getCollection } from 'astro:content';
            import BaseLayout from '../../layouts/BaseLayout.astro';
            import EvidenceCard from '../../components/EvidenceCard.astro';
            const projects = (await getCollection('projects')).sort((a, b) => a.data.sortOrder - b.data.sortOrder);
            ---
            <BaseLayout title="Work" description="Selected quantitative research, engineering systems and bounded technical prototypes by David Anderle.">
              <section class="page-lead shell"><p class="eyebrow">WORK / EVIDENCE REGISTER</p><h1>Three records.<br />Three different boundaries.</h1><p>Each page separates implemented evidence, role, maturity and unresolved work.</p></section>
              <section class="section shell"><div class="evidence-grid">{projects.map((project) => <EvidenceCard project={project} />)}</div></section>
            </BaseLayout>
        """),
        "src/pages/work/[slug].astro": d("""
            ---
            import { getCollection, render, type CollectionEntry } from 'astro:content';
            import BaseLayout from '../../layouts/BaseLayout.astro';
            export async function getStaticPaths() {
              const projects = await getCollection('projects');
              return projects.map((project) => ({ params: { slug: project.data.slug }, props: { project } }));
            }
            const project = Astro.props.project as CollectionEntry<'projects'>;
            const { Content } = await render(project);
            ---
            <BaseLayout title={project.data.title} description={project.data.summary} material={project.data.material}>
              <article class:list={['project-record', `material-${project.data.material}`]}>
                <header class="record-head shell">
                  <div><p class="eyebrow">WORK / {project.data.year} / {project.data.maturity.replaceAll('-', ' ')}</p><h1>{project.data.title}</h1><p class="record-summary">{project.data.summary}</p></div>
                  <dl class="record-register">
                    <div><dt>Role</dt><dd>{project.data.role}</dd></div>
                    <div><dt>Authorship</dt><dd>{project.data.authorship}</dd></div>
                    <div><dt>Access</dt><dd>{project.data.access}</dd></div>
                    <div><dt>Maturity</dt><dd>{project.data.maturity.replaceAll('-', ' ')}</dd></div>
                  </dl>
                </header>
                <div class="record-body shell">
                  <aside><p class="eyebrow">RECORDED EVIDENCE</p><dl class="evidence-list">{project.data.evidence.map((item) => <div><dt>{item.label}</dt><dd>{item.value}</dd></div>)}</dl>{project.data.links.length > 0 && <div class="record-links">{project.data.links.map((link) => <a class="text-link" href={link.href} rel="external">{link.label} →</a>)}</div>}</aside>
                  <div class="prose"><Content /></div>
                </div>
                <footer class="record-foot shell"><a class="text-link" href="/work/">← Return to work register</a></footer>
              </article>
            </BaseLayout>
        """),
        "src/pages/writing/index.astro": d("""
            ---
            import { getCollection } from 'astro:content';
            import BaseLayout from '../../layouts/BaseLayout.astro';
            const notes = (await getCollection('notes')).sort((a, b) => b.data.publishedAt.valueOf() - a.data.publishedAt.valueOf());
            ---
            <BaseLayout title="Writing" description="Working and technical notes by David Anderle.">
              <section class="page-lead shell"><p class="eyebrow">WRITING / WORKING NOTES</p><h1>Notes that expose<br />the reasoning boundary.</h1><p>These are compact notes, not peer-reviewed papers.</p></section>
              <section class="section shell note-list">{notes.map((note, index) => <article><span>{String(index + 1).padStart(2, '0')}</span><div><p class="eyebrow">{note.data.status.replaceAll('-', ' ')} · {note.data.year}</p><h2><a href={`/writing/${note.data.slug}/`}>{note.data.title}</a></h2><p>{note.data.summary}</p></div></article>)}</section>
            </BaseLayout>
        """),
        "src/pages/writing/[slug].astro": d("""
            ---
            import { getCollection, render, type CollectionEntry } from 'astro:content';
            import BaseLayout from '../../layouts/BaseLayout.astro';
            export async function getStaticPaths() {
              const notes = await getCollection('notes');
              return notes.map((note) => ({ params: { slug: note.data.slug }, props: { note } }));
            }
            const note = Astro.props.note as CollectionEntry<'notes'>;
            const { Content } = await render(note);
            ---
            <BaseLayout title={note.data.title} description={note.data.summary} material={note.data.material}>
              <article class="note-record shell"><header><p class="eyebrow">{note.data.status.replaceAll('-', ' ')} / {note.data.year}</p><h1>{note.data.title}</h1><p>{note.data.summary}</p></header><div class="prose"><Content /></div><footer><a class="text-link" href="/writing/">← All notes</a></footer></article>
            </BaseLayout>
        """),
        "src/pages/archive/index.astro": d("""
            ---
            import { getCollection } from 'astro:content';
            import BaseLayout from '../../layouts/BaseLayout.astro';
            const projects = await getCollection('projects');
            const notes = await getCollection('notes');
            const years = [...new Set([...projects.map((x) => x.data.year), ...notes.map((x) => x.data.year)])].sort((a, b) => b - a);
            ---
            <BaseLayout title="Archive" description="Year-indexed archive of work and notes by David Anderle.">
              <section class="page-lead shell"><p class="eyebrow">ARCHIVE / YEAR INDEX</p><h1>A durable record,<br />not an infinite feed.</h1><p>Records are grouped by year. The same policy keeps large archives below 200 records per index page.</p></section>
              <section class="section shell year-index">{years.map((year) => <a href={`/archive/${year}/`}><span>{year}</span><strong>Open year</strong><i aria-hidden="true">→</i></a>)}</section>
            </BaseLayout>
        """),
        "src/pages/archive/[year].astro": d("""
            ---
            import { getCollection } from 'astro:content';
            import BaseLayout from '../../layouts/BaseLayout.astro';
            export async function getStaticPaths() {
              const projects = await getCollection('projects');
              const notes = await getCollection('notes');
              const years = [...new Set([...projects.map((x) => x.data.year), ...notes.map((x) => x.data.year)])];
              return years.map((year) => ({ params: { year: String(year) }, props: { year } }));
            }
            const year = Number(Astro.props.year);
            const projects = (await getCollection('projects')).filter((x) => x.data.year === year);
            const notes = (await getCollection('notes')).filter((x) => x.data.year === year);
            ---
            <BaseLayout title={`Archive ${year}`} description={`Work and writing records from ${year}.`}>
              <section class="page-lead shell"><p class="eyebrow">ARCHIVE / {year}</p><h1>{year}</h1><p>{projects.length + notes.length} records in this year.</p></section>
              <section class="section shell archive-records">
                {projects.map((item) => <a href={`/work/${item.data.slug}/`}><span>WORK</span><strong>{item.data.title}</strong><i>→</i></a>)}
                {notes.map((item) => <a href={`/writing/${item.data.slug}/`}><span>NOTE</span><strong>{item.data.title}</strong><i>→</i></a>)}
              </section>
            </BaseLayout>
        """),
        "src/pages/about/index.astro": d("""
            ---
            import { getCollection } from 'astro:content';
            import BaseLayout from '../../layouts/BaseLayout.astro';
            import Portrait from '../../components/Portrait.astro';
            const education = await getCollection('education');
            const primary = education.find((x) => x.data.prominence === 'primary');
            const secondary = education.filter((x) => x.data.prominence === 'secondary');
            ---
            <BaseLayout title="About" description="Background, current direction and working principles of David Anderle.">
              <section class="about-lead shell"><div><p class="eyebrow">ABOUT / CURRENT POSITION</p><h1>Technical foundation.<br />Financial direction.</h1><p class="hero-deck">I am an informatics student in Prague building the mathematical, software and empirical foundation for quantitative finance.</p></div><Portrait /></section>
              <section class="section shell about-grid"><div><p class="eyebrow">PRIMARY CONTEXT</p><h2>{primary?.data.programme}</h2><p>{primary?.data.summary}</p></div><div><p class="eyebrow">WORKING PRINCIPLES</p><ol><li>Do not turn an intention into evidence.</li><li>Keep risk and failure modes visible.</li><li>Prefer a smaller reproducible system to a larger opaque one.</li></ol></div></section>
              <section class="section shell secondary-context"><p class="eyebrow">SECONDARY HISTORICAL CONTEXT</p>{secondary.map((item) => <article><span>{item.data.startYear}–{item.data.endYear}</span><div><h2>{item.data.institution}</h2><p>{item.data.summary}</p></div></article>)}<a class="text-link" href="/about/no-photo/">Inspect complete no-photo composition →</a></section>
            </BaseLayout>
        """),
        "src/pages/about/no-photo.astro": d("""
            ---
            import BaseLayout from '../../layouts/BaseLayout.astro';
            import Portrait from '../../components/Portrait.astro';
            ---
            <BaseLayout title="About, no-photo composition" description="Complete no-photo identity composition for David Anderle.">
              <section class="about-lead shell"><div><p class="eyebrow">ABOUT / NO-PHOTO STATE</p><h1>Identity without<br />image dependence.</h1><p class="hero-deck">The information architecture and Bearing identity remain complete when no approved portrait is available.</p></div><Portrait forceNoPhoto={true} /></section>
              <section class="section shell about-grid"><div><p class="eyebrow">CURRENT</p><h2>BSc Informatics, Prague</h2><p>Programming, systems, data and quantitative foundations.</p></div><div><p class="eyebrow">DIRECTION</p><h2>Quantitative finance</h2><p>Research, risk systems and technically rigorous market work.</p></div></section>
            </BaseLayout>
        """),
        "src/pages/contact.astro": d("""
            ---
            import BaseLayout from '../layouts/BaseLayout.astro';
            import site from '../data/site.json';
            ---
            <BaseLayout title="Contact" description="Contact David Anderle about research, engineering and quantitative work.">
              <section class="contact-lead shell"><p class="eyebrow">CONTACT / DIRECT CHANNEL</p><h1>Start with the<br />actual question.</h1><p>Research collaboration, quantitative engineering and technically serious student opportunities.</p><a class="button" href={`mailto:${site.email}`}>{site.email}</a><a class="text-link" href={site.github} rel="me">GitHub →</a></section>
            </BaseLayout>
        """),
        "src/pages/visual-comparison.astro": d("""
            ---
            import BaseLayout from '../layouts/BaseLayout.astro';
            import ComparisonExplorer from '../components/ComparisonExplorer.astro';
            ---
            <BaseLayout title="Evidence comparison" description="The single bounded route-local enhancement in the Bearing reference build.">
              <section class="page-lead shell"><p class="eyebrow">BOUNDED ENHANCEMENT / ONE WEB COMPONENT</p><h1>Architecture and<br />measurement stay separate.</h1><p>All four evidence panels are present in static HTML. JavaScript only changes emphasis.</p></section>
              <section class="section shell"><ComparisonExplorer /></section>
            </BaseLayout>
        """),
        "src/pages/404.astro": d("""
            ---
            import BaseLayout from '../layouts/BaseLayout.astro';
            ---
            <BaseLayout title="Not found" description="The requested route was not found.">
              <section class="not-found shell" data-custom-404="bearing"><p class="eyebrow">404 / OFF BEARING</p><h1>This route does not exist.</h1><p>The archive remains intact. Return to a known reference point.</p><div><a class="button" href="/">Home</a><a class="text-link" href="/work/">Work register →</a></div></section>
            </BaseLayout>
        """),
        "src/pages/sitemap.xml.ts": d("""
            import type { APIRoute } from 'astro';
            import { getCollection } from 'astro:content';

            export const GET: APIRoute = async () => {
              const projects = await getCollection('projects');
              const notes = await getCollection('notes');
              const paths = ['/', '/work/', '/writing/', '/archive/', '/about/', '/about/no-photo/', '/contact/', '/visual-comparison/'];
              paths.push(...projects.map((x) => `/work/${x.data.slug}/`));
              paths.push(...notes.map((x) => `/writing/${x.data.slug}/`));
              const urls = paths.map((path) => `<url><loc>https://davidanderle.com${path}</loc></url>`).join('');
              return new Response(`<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">${urls}</urlset>`, { headers: { 'Content-Type': 'application/xml; charset=utf-8' } });
            };
        """),
        "src/pages/scale/index.astro": d("""
            ---
            import { getCollection } from 'astro:content';
            import BaseLayout from '../../layouts/BaseLayout.astro';
            const enabled = process.env.R7E_SCALE === '1';
            const records = enabled ? await getCollection('scale') : [];
            const years = [...new Set(records.map((x) => x.data.year))].sort((a, b) => b - a);
            ---
            <BaseLayout title="Scale fixture" description="R7E generated scale fixture." noindex={true}>
              <section class="page-lead shell"><p class="eyebrow">R7E SCALE FIXTURE</p><h1>{records.length} validated records.</h1><p>This route exists only as an empirical build-scale target.</p></section>
              <section class="section shell year-index">{years.map((year) => <a href={`/scale/archive/${year}/`}><span>{year}</span><strong>Open generated year</strong><i>→</i></a>)}</section>
            </BaseLayout>
        """),
        "src/pages/scale/[slug].astro": d("""
            ---
            import { getCollection, render, type CollectionEntry } from 'astro:content';
            import BaseLayout from '../../layouts/BaseLayout.astro';
            export async function getStaticPaths() {
              if (process.env.R7E_SCALE !== '1') return [];
              const records = await getCollection('scale');
              return records.map((record) => ({ params: { slug: record.data.slug }, props: { record } }));
            }
            const record = Astro.props.record as CollectionEntry<'scale'>;
            const { Content } = await render(record);
            ---
            <BaseLayout title={record.data.title} description={record.data.summary} material={record.data.material} noindex={true}>
              <article class="note-record shell"><header><p class="eyebrow">SCALE / {record.data.sequence} / {record.data.year}</p><h1>{record.data.title}</h1><p>{record.data.summary}</p></header><div class="prose"><Content /></div></article>
            </BaseLayout>
        """),
        "src/pages/scale/archive/[year].astro": d("""
            ---
            import { getCollection } from 'astro:content';
            import BaseLayout from '../../../layouts/BaseLayout.astro';
            export async function getStaticPaths() {
              if (process.env.R7E_SCALE !== '1') return [];
              const records = await getCollection('scale');
              const years = [...new Set(records.map((x) => x.data.year))];
              return years.map((year) => ({ params: { year: String(year) }, props: { year } }));
            }
            const year = Number(Astro.props.year);
            const records = (await getCollection('scale')).filter((x) => x.data.year === year).sort((a, b) => a.data.sequence - b.data.sequence);
            ---
            <BaseLayout title={`Scale archive ${year}`} description={`Generated scale records for ${year}.`} noindex={true}>
              <section class="page-lead shell"><p class="eyebrow">SCALE ARCHIVE / {year}</p><h1>{records.length} records.</h1><p>The generated policy keeps each yearly index below 200 records.</p></section>
              <section class="section shell archive-records">{records.map((item) => <a href={`/scale/${item.data.slug}/`}><span>{String(item.data.sequence).padStart(4, '0')}</span><strong>{item.data.title}</strong><i>→</i></a>)}</section>
            </BaseLayout>
        """),
        "tests/bearing.spec.ts": d("""
            import { test, expect, chromium, type Page } from '@playwright/test';
            import AxeBuilder from '@axe-core/playwright';
            import fs from 'node:fs/promises';
            import path from 'node:path';

            const ordinary = ['/', '/work/', '/work/research-workspace/', '/work/non-core-real-estate/', '/work/merkle-poseidon/', '/writing/', '/archive/', '/about/', '/about/no-photo/', '/contact/'];
            const evidenceDir = path.resolve('evidence/browser');

            async function measure(page: Page, route: string, viewport: string) {
              const data = await page.evaluate(() => ({
                href: location.href,
                title: document.title,
                innerWidth: window.innerWidth,
                scrollWidth: document.documentElement.scrollWidth,
                bodyTextCharacters: document.body.innerText.length,
                executableScripts: Array.from(document.scripts).filter((node) => !node.type || node.type === 'module' || /javascript/i.test(node.type)).length,
                headings: Array.from(document.querySelectorAll('h1,h2')).map((node) => node.textContent?.trim())
              }));
              await fs.mkdir(path.join(evidenceDir, 'measurements'), { recursive: true });
              const safe = route === '/' ? 'home' : route.replaceAll('/', '-').replace(/^-|-$/g, '');
              await fs.writeFile(path.join(evidenceDir, 'measurements', `${safe}-${viewport}.json`), JSON.stringify(data, null, 2));
              expect(data.scrollWidth).toBeLessThanOrEqual(data.innerWidth);
              expect(data.bodyTextCharacters).toBeGreaterThan(250);
            }

            for (const config of [
              { name: 'desktop-1440', width: 1440, height: 1000 },
              { name: 'mobile-390', width: 390, height: 844 },
              { name: 'mobile-320', width: 320, height: 568 }
            ]) {
              test(`homepage composition ${config.name}`, async ({ page }) => {
                await page.setViewportSize({ width: config.width, height: config.height });
                await page.goto('/');
                await expect(page.locator('h1')).toContainText('David');
                await expect(page.locator('#selected-evidence')).toBeVisible();
                await measure(page, '/', config.name);
                await fs.mkdir(path.join(evidenceDir, 'screenshots'), { recursive: true });
                await page.screenshot({ path: path.join(evidenceDir, 'screenshots', `home-${config.name}.png`), fullPage: true });
              });
            }

            for (const config of [
              { name: 'desktop-1440', width: 1440, height: 1000 },
              { name: 'mobile-390', width: 390, height: 844 },
              { name: 'mobile-320', width: 320, height: 568 }
            ]) {
              test(`deep project composition ${config.name}`, async ({ page }) => {
                await page.setViewportSize({ width: config.width, height: config.height });
                await page.goto('/work/non-core-real-estate/');
                await expect(page.locator('.record-register')).toBeVisible();
                await measure(page, '/work/non-core-real-estate/', config.name);
                await fs.mkdir(path.join(evidenceDir, 'screenshots'), { recursive: true });
                await page.screenshot({ path: path.join(evidenceDir, 'screenshots', `project-oxide-${config.name}.png`), fullPage: true });
              });
            }

            test('ordinary routes remain complete with JavaScript disabled', async ({ browser }) => {
              const context = await browser.newContext({ javaScriptEnabled: false, viewport: { width: 390, height: 844 } });
              const page = await context.newPage();
              const rows = [];
              for (const route of ordinary) {
                const response = await page.goto(route);
                expect(response?.status()).toBe(200);
                const h1 = (await page.locator('h1').first().textContent())?.trim();
                const bodyLength = (await page.locator('body').innerText()).length;
                const scripts = await page.locator('script').count();
                expect(h1).toBeTruthy();
                expect(bodyLength).toBeGreaterThan(250);
                expect(scripts).toBe(0);
                rows.push({ route, status: response?.status(), h1, bodyLength, scripts });
              }
              await fs.writeFile(path.join(evidenceDir, 'no-js-routes.json'), JSON.stringify(rows, null, 2));
              await context.close();
            });

            test('single route-local Web Component is progressive enhancement', async ({ page, browser }) => {
              await page.goto('/visual-comparison/');
              await expect(page.locator('bearing-comparison')).toHaveAttribute('data-ready', 'true');
              await page.getByRole('button', { name: 'Architecture' }).click();
              await expect(page.locator('[data-category="measurement"]').first()).toHaveAttribute('data-deemphasized', '');
              const context = await browser.newContext({ javaScriptEnabled: false });
              const staticPage = await context.newPage();
              await staticPage.goto('/visual-comparison/');
              await expect(staticPage.locator('[data-category]')).toHaveCount(4);
              await context.close();
            });

            test('axe serious and critical findings are absent on representative routes', async ({ page }) => {
              const routes = ['/', '/work/non-core-real-estate/', '/about/no-photo/', '/visual-comparison/'];
              const reports = [];
              for (const route of routes) {
                await page.goto(route);
                const result = await new AxeBuilder({ page }).analyze();
                const blocking = result.violations.filter((item) => item.impact === 'serious' || item.impact === 'critical');
                reports.push({ route, violations: result.violations, blocking });
                expect(blocking).toEqual([]);
              }
              await fs.writeFile(path.join(evidenceDir, 'axe-representative.json'), JSON.stringify(reports, null, 2));
            });

            test('compact-photo and no-photo states are both structurally complete', async ({ page }) => {
              await page.goto('/about/');
              await expect(page.locator('.portrait')).toBeVisible();
              await page.screenshot({ path: path.join(evidenceDir, 'screenshots', 'about-compact-photo-or-fallback-390.png'), fullPage: true });
              await page.goto('/about/no-photo/');
              await expect(page.locator('.no-photo')).toBeVisible();
              await page.screenshot({ path: path.join(evidenceDir, 'screenshots', 'about-no-photo-390.png'), fullPage: true });
            });

            test('custom 404 output contains the Bearing marker', async ({ page }) => {
              const response = await page.goto('/404.html');
              expect(response?.status()).toBe(200);
              await expect(page.locator('[data-custom-404="bearing"]')).toBeVisible();
              await page.screenshot({ path: path.join(evidenceDir, 'screenshots', 'custom-404.png'), fullPage: true });
            });
        """),
    }

    files["src/styles/global.css"] = d("""
        :root {
          --ink: #171a1c;
          --ink-soft: #34393c;
          --paper: #f2eee5;
          --paper-deep: #e5dfd2;
          --line: rgba(23, 26, 28, .20);
          --line-strong: rgba(23, 26, 28, .55);
          --signal: #c85f32;
          --signal-dark: #87391e;
          --graphite: #303538;
          --oxide: #a64927;
          --white: #fffdf8;
          --max: 1240px;
          --gutter: clamp(1rem, 3vw, 3rem);
          --serif: Iowan Old Style, Baskerville, Times New Roman, serif;
          --sans: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
          --mono: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
        }
        * { box-sizing: border-box; }
        html { background: var(--paper); color: var(--ink); font-family: var(--sans); scroll-behavior: smooth; }
        body { margin: 0; min-width: 320px; background: radial-gradient(circle at 84% 8%, rgba(200,95,50,.08), transparent 26rem), var(--paper); line-height: 1.55; }
        body::before { content: ""; position: fixed; inset: 0; pointer-events: none; opacity: .2; background-image: linear-gradient(rgba(23,26,28,.035) 1px, transparent 1px), linear-gradient(90deg, rgba(23,26,28,.035) 1px, transparent 1px); background-size: 32px 32px; z-index: -1; }
        a { color: inherit; text-underline-offset: .2em; }
        a:hover { text-decoration-thickness: .14em; }
        img { display: block; max-width: 100%; height: auto; }
        button, a { -webkit-tap-highlight-color: transparent; }
        :focus-visible { outline: 3px solid var(--signal); outline-offset: 4px; }
        .skip-link { position: fixed; top: .5rem; left: .5rem; transform: translateY(-160%); background: var(--ink); color: var(--paper); padding: .75rem 1rem; z-index: 100; }
        .skip-link:focus { transform: none; }
        .shell { width: min(calc(100% - 2 * var(--gutter)), var(--max)); margin-inline: auto; }
        .eyebrow { margin: 0 0 1rem; font: 700 .69rem/1.3 var(--mono); letter-spacing: .12em; text-transform: uppercase; color: var(--signal-dark); }
        h1, h2, h3, p { text-wrap: pretty; }
        h1, h2, h3 { margin: 0; line-height: .98; letter-spacing: -.045em; }
        h1 { font-family: var(--serif); font-size: clamp(3.4rem, 8vw, 8.5rem); font-weight: 500; }
        h2 { font-family: var(--serif); font-size: clamp(2.2rem, 4.3vw, 4.7rem); font-weight: 500; }
        h3 { font-family: var(--serif); font-size: clamp(1.65rem, 2.3vw, 2.65rem); font-weight: 500; }
        .bearing-strip { min-height: 2rem; padding: .45rem var(--gutter); display: grid; grid-template-columns: 1fr auto 1fr; gap: 1rem; align-items: center; background: var(--ink); color: var(--paper); font: 600 .62rem/1 var(--mono); letter-spacing: .12em; }
        .bearing-strip span:last-child { text-align: right; }
        .site-header { border-bottom: 1px solid var(--line-strong); }
        .header-inner { width: min(calc(100% - 2 * var(--gutter)), var(--max)); min-height: 5.75rem; margin-inline: auto; display: flex; align-items: center; justify-content: space-between; gap: 2rem; }
        .wordmark { display: inline-flex; gap: .8rem; align-items: center; text-decoration: none; font-weight: 800; letter-spacing: -.025em; }
        .wordmark-mark { width: 1.7rem; height: 1.7rem; border: 2px solid var(--ink); border-radius: 50%; display: grid; place-items: center; position: relative; }
        .wordmark-mark::before, .wordmark-mark::after { content: ""; position: absolute; background: var(--ink); }
        .wordmark-mark::before { width: 2.2rem; height: 1px; }
        .wordmark-mark::after { width: 1px; height: 2.2rem; }
        .wordmark-mark i { width: .35rem; height: .35rem; border-radius: 50%; background: var(--signal); z-index: 1; }
        nav ul { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: .35rem 1.4rem; list-style: none; margin: 0; padding: 0; font: 650 .77rem/1 var(--mono); text-transform: uppercase; letter-spacing: .06em; }
        nav a { text-decoration: none; padding: .6rem 0; border-bottom: 2px solid transparent; }
        nav a[aria-current="page"], nav a:hover { border-color: var(--signal); }
        .hero { min-height: 44rem; display: grid; grid-template-columns: 5rem minmax(0, 1.55fr) minmax(18rem, .65fr); gap: clamp(1.5rem, 4vw, 5rem); align-items: stretch; border-bottom: 1px solid var(--line-strong); }
        .hero-index { border-inline: 1px solid var(--line); display: flex; writing-mode: vertical-rl; justify-content: space-between; align-items: center; padding: 2rem 1rem; font: 650 .65rem/1 var(--mono); letter-spacing: .12em; }
        .hero-copy { padding: clamp(5rem, 9vw, 8rem) 0 4rem; }
        .hero-copy h1 { max-width: 8ch; }
        .hero-deck { max-width: 46rem; margin: 2rem 0 0; font: 400 clamp(1.15rem, 1.8vw, 1.55rem)/1.48 var(--sans); color: var(--ink-soft); }
        .hero-actions { display: flex; flex-wrap: wrap; gap: 1.5rem 2rem; align-items: center; margin-top: 2.5rem; }
        .button { display: inline-flex; min-height: 3rem; align-items: center; justify-content: center; padding: .75rem 1.1rem; background: var(--ink); color: var(--paper); font: 750 .76rem/1 var(--mono); letter-spacing: .05em; text-transform: uppercase; text-decoration: none; border: 1px solid var(--ink); }
        .button:hover { background: var(--signal-dark); border-color: var(--signal-dark); }
        .text-link { font: 700 .78rem/1.3 var(--mono); letter-spacing: .035em; text-transform: uppercase; }
        .hero-bearing { border-left: 1px solid var(--line); padding: clamp(5rem, 9vw, 8rem) 0 4rem clamp(1.5rem, 3vw, 3rem); }
        .hero-bearing strong { display: block; max-width: 12ch; font: 500 clamp(2rem, 3.2vw, 3.4rem)/1 var(--serif); letter-spacing: -.04em; }
        .hero-bearing > p:not(.eyebrow) { max-width: 23rem; color: var(--ink-soft); }
        .instrument { position: relative; width: min(100%, 18rem); aspect-ratio: 1; margin-top: 3rem; border: 1px solid var(--line-strong); border-radius: 50%; }
        .instrument::before, .instrument::after, .instrument-axis::before, .instrument-axis::after { content: ""; position: absolute; background: var(--line-strong); }
        .instrument::before { width: 120%; height: 1px; left: -10%; top: 50%; }
        .instrument::after { width: 1px; height: 120%; top: -10%; left: 50%; }
        .instrument-ring { position: absolute; inset: 18%; border: 1px solid var(--line); border-radius: 50%; }
        .instrument-axis::before { width: 1px; height: 82%; left: 50%; top: 9%; transform: rotate(37deg); transform-origin: center; background: var(--signal); }
        .instrument i { position: absolute; width: .8rem; height: .8rem; border-radius: 50%; background: var(--ink); inset: calc(50% - .4rem); }
        .section { padding-block: clamp(5rem, 9vw, 9rem); border-bottom: 1px solid var(--line-strong); }
        .section-heading { display: grid; grid-template-columns: 1fr 1fr; gap: 1.5rem 4rem; margin-bottom: 3.5rem; }
        .section-heading .eyebrow { grid-column: 1 / -1; }
        .section-heading > p:last-child { max-width: 34rem; align-self: end; color: var(--ink-soft); }
        .evidence-grid { display: grid; grid-template-columns: repeat(3, 1fr); border-top: 1px solid var(--line-strong); border-left: 1px solid var(--line-strong); }
        .evidence-card { min-width: 0; padding: clamp(1.4rem, 2.5vw, 2.25rem); min-height: 36rem; display: flex; flex-direction: column; border-right: 1px solid var(--line-strong); border-bottom: 1px solid var(--line-strong); position: relative; overflow: hidden; }
        .evidence-card::after { content: ""; position: absolute; width: 12rem; height: 12rem; border: 1px solid currentColor; border-radius: 50%; opacity: .09; right: -5rem; top: -5rem; }
        .evidence-card.material-graphite { background: var(--graphite); color: var(--white); }
        .evidence-card.material-graphite .eyebrow, .material-graphite .eyebrow { color: #ef976e; }
        .evidence-card.material-oxide { background: var(--oxide); color: var(--white); }
        .evidence-card.material-oxide .eyebrow, .material-oxide .eyebrow { color: #ffe0cf; }
        .evidence-card.material-paper { background: var(--white); }
        .card-calibration { display: flex; gap: .3rem; margin-bottom: 3rem; }
        .card-calibration span { width: .6rem; height: .6rem; border: 1px solid currentColor; border-radius: 50%; }
        .card-calibration span:first-child { background: currentColor; }
        .evidence-card h3 a { text-decoration: none; }
        .evidence-card > p:not(.eyebrow) { margin: 1.5rem 0; opacity: .85; }
        .card-facts { margin: auto 0 2rem; border-top: 1px solid currentColor; }
        .card-facts div { display: grid; grid-template-columns: 5rem 1fr; gap: 1rem; padding: .75rem 0; border-bottom: 1px solid currentColor; }
        .card-facts dt { font: 650 .65rem/1.4 var(--mono); text-transform: uppercase; }
        .card-facts dd { margin: 0; font-size: .86rem; }
        .method-grid, .trajectory, .about-grid { display: grid; grid-template-columns: .8fr 1.2fr; gap: clamp(3rem, 8vw, 8rem); }
        .method-grid ol { list-style: none; margin: 0; padding: 0; border-top: 1px solid var(--line-strong); }
        .method-grid li { display: grid; grid-template-columns: 4rem 1fr; gap: 1.5rem; padding: 1.3rem 0; border-bottom: 1px solid var(--line-strong); }
        .method-grid li > span { font: 700 .7rem var(--mono); color: var(--signal-dark); }
        .method-grid strong { font-family: var(--serif); font-size: 1.5rem; font-weight: 500; }
        .method-grid p { margin: .4rem 0 0; color: var(--ink-soft); }
        .trajectory-copy { columns: 2; column-gap: 2.5rem; }
        .trajectory-copy .text-link { display: inline-block; margin-top: 1rem; }
        .page-lead { padding: clamp(5rem, 10vw, 9rem) 0 clamp(4rem, 7vw, 7rem); display: grid; grid-template-columns: 1fr .72fr; gap: 2rem 5rem; border-bottom: 1px solid var(--line-strong); }
        .page-lead .eyebrow { grid-column: 1 / -1; }
        .page-lead > p:last-child { max-width: 30rem; align-self: end; font-size: 1.15rem; color: var(--ink-soft); }
        .record-head { padding: clamp(5rem, 9vw, 8rem) 0 4rem; display: grid; grid-template-columns: 1.25fr .75fr; gap: 4rem; }
        .record-summary { max-width: 50rem; font-size: 1.25rem; color: var(--ink-soft); }
        .record-register { margin: 0; border-top: 2px solid var(--ink); align-self: end; }
        .record-register div, .evidence-list div { display: grid; grid-template-columns: 7rem 1fr; gap: 1rem; padding: .85rem 0; border-bottom: 1px solid var(--line-strong); }
        .record-register dt, .evidence-list dt { font: 650 .66rem/1.4 var(--mono); text-transform: uppercase; letter-spacing: .04em; }
        .record-register dd, .evidence-list dd { margin: 0; }
        .record-body { padding-block: 5rem 7rem; display: grid; grid-template-columns: .72fr 1.28fr; gap: clamp(3rem, 8vw, 8rem); border-top: 1px solid var(--line-strong); }
        .evidence-list { margin: 0; }
        .record-links { display: grid; gap: 1rem; margin-top: 2rem; }
        .prose { max-width: 47rem; font-family: var(--serif); font-size: clamp(1.15rem, 1.7vw, 1.35rem); line-height: 1.65; }
        .prose h2 { margin: 3rem 0 1rem; font-size: clamp(2rem, 3vw, 3.2rem); }
        .prose h2:first-child { margin-top: 0; }
        .record-foot { padding-block: 2rem 4rem; }
        html[data-material="graphite"] .project-record .record-head, html[data-material="graphite"] .project-record .record-body { background: linear-gradient(90deg, rgba(48,53,56,.08), transparent); }
        html[data-material="oxide"] .project-record .record-head { box-shadow: inset 0 .45rem 0 var(--oxide); }
        html[data-material="paper"] .project-record .record-head { background: var(--white); }
        .note-list { display: grid; gap: 0; }
        .note-list article { display: grid; grid-template-columns: 4rem 1fr; gap: 2rem; padding: 2.25rem 0; border-top: 1px solid var(--line-strong); }
        .note-list article:last-child { border-bottom: 1px solid var(--line-strong); }
        .note-list article > span { font: 700 .72rem var(--mono); color: var(--signal-dark); }
        .note-list h2 { font-size: clamp(2rem, 3.4vw, 3.4rem); }
        .note-list h2 a { text-decoration: none; }
        .note-list p:last-child { max-width: 50rem; color: var(--ink-soft); }
        .note-record { padding-block: clamp(5rem, 10vw, 9rem); max-width: 60rem; }
        .note-record header { padding-bottom: 3rem; border-bottom: 1px solid var(--line-strong); }
        .note-record header > p:last-child { font-size: 1.2rem; color: var(--ink-soft); }
        .note-record .prose { margin: 4rem 0; }
        .year-index { display: grid; grid-template-columns: repeat(3, 1fr); gap: 1px; background: var(--line-strong); padding-block: 1px; }
        .year-index a { min-height: 14rem; padding: 1.5rem; background: var(--paper); display: grid; text-decoration: none; }
        .year-index span { font: 500 4rem/1 var(--serif); }
        .year-index strong { align-self: end; font: 700 .75rem var(--mono); text-transform: uppercase; }
        .year-index i { justify-self: end; font-style: normal; }
        .archive-records { display: grid; }
        .archive-records a { display: grid; grid-template-columns: 6rem 1fr auto; gap: 1.5rem; align-items: center; padding: 1.2rem 0; border-top: 1px solid var(--line-strong); text-decoration: none; }
        .archive-records a:last-child { border-bottom: 1px solid var(--line-strong); }
        .archive-records span { font: 700 .67rem var(--mono); color: var(--signal-dark); }
        .archive-records strong { font-family: var(--serif); font-size: 1.5rem; font-weight: 500; }
        .archive-records i { font-style: normal; }
        .about-lead { padding: clamp(5rem, 9vw, 8rem) 0; display: grid; grid-template-columns: 1fr 20rem; gap: clamp(3rem, 8vw, 8rem); align-items: end; border-bottom: 1px solid var(--line-strong); }
        .portrait { margin: 0; }
        .portrait img { width: 256px; height: 320px; object-fit: cover; border: 1px solid var(--line-strong); filter: saturate(.78) contrast(1.03); }
        .portrait figcaption { margin-top: .75rem; max-width: 16rem; font: .62rem/1.45 var(--mono); color: var(--ink-soft); }
        .no-photo { width: 256px; min-height: 320px; border: 1px solid var(--line-strong); padding: 1.25rem; display: flex; flex-direction: column; justify-content: space-between; background: var(--ink); color: var(--paper); }
        .no-photo-mark { flex: 1; display: grid; place-items: center; background: repeating-linear-gradient(45deg, transparent 0 12px, rgba(242,238,229,.08) 12px 13px); }
        .no-photo-mark span { width: 7rem; height: 7rem; display: grid; place-items: center; border: 1px solid var(--paper); border-radius: 50%; font: 500 2rem var(--serif); }
        .no-photo p, .no-photo small { margin: 0; font-family: var(--mono); }
        .about-grid ol { margin: 0; padding-left: 1.2rem; }
        .about-grid li { padding: .6rem 0; border-bottom: 1px solid var(--line); }
        .secondary-context article { display: grid; grid-template-columns: 8rem 1fr; gap: 2rem; padding: 2rem 0; border-top: 1px solid var(--line-strong); }
        .secondary-context article span { font: 700 .7rem var(--mono); }
        .secondary-context article h2 { font-size: 2.2rem; }
        .contact-lead, .not-found { min-height: 65vh; padding-block: clamp(6rem, 13vw, 12rem); }
        .contact-lead > p:not(.eyebrow), .not-found > p:not(.eyebrow) { max-width: 42rem; font-size: 1.2rem; color: var(--ink-soft); }
        .contact-lead .button, .not-found .button { margin: 2rem 1.5rem 0 0; }
        .comparison-controls { display: flex; flex-wrap: wrap; gap: .5rem; margin-bottom: 2rem; }
        .comparison-controls button { border: 1px solid var(--ink); background: transparent; padding: .75rem 1rem; font: 700 .7rem var(--mono); text-transform: uppercase; cursor: pointer; }
        .comparison-controls button[aria-pressed="true"] { background: var(--ink); color: var(--paper); }
        .comparison-grid { display: grid; grid-template-columns: 1fr 1fr; border-top: 1px solid var(--line-strong); border-left: 1px solid var(--line-strong); }
        .comparison-grid article { min-height: 18rem; padding: 2rem; border-right: 1px solid var(--line-strong); border-bottom: 1px solid var(--line-strong); transition: opacity .18s ease; }
        .comparison-grid article[data-deemphasized] { opacity: .28; }
        .comparison-grid h2 { font-size: clamp(2rem, 3.5vw, 3.5rem); }
        .site-footer { background: var(--ink); color: var(--paper); }
        .footer-inner { width: min(calc(100% - 2 * var(--gutter)), var(--max)); margin-inline: auto; padding: 3rem 0; display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 2rem; font-size: .8rem; }
        .footer-inner p { margin: 0; }
        .footer-inner p:last-child { text-align: right; }
        .footer-coordinate { text-align: center; font-family: var(--mono); color: #bbb6aa; }

        @media (max-width: 900px) {
          .hero { grid-template-columns: 3rem 1fr; }
          .hero-bearing { grid-column: 2; border-left: 0; border-top: 1px solid var(--line); padding: 3rem 0 4rem; display: grid; grid-template-columns: 1fr 15rem; gap: 2rem; }
          .instrument { grid-column: 2; grid-row: 1 / span 3; margin: 0; }
          .evidence-grid { grid-template-columns: 1fr; }
          .evidence-card { min-height: 27rem; }
          .section-heading, .page-lead, .record-head, .record-body, .method-grid, .trajectory, .about-grid { grid-template-columns: 1fr; }
          .trajectory-copy { columns: 1; }
          .about-lead { grid-template-columns: 1fr 16rem; }
          .year-index { grid-template-columns: 1fr 1fr; }
        }

        /* Dedicated 390 px composition: not a scaled desktop layout. */
        @media (max-width: 410px) and (min-width: 351px) {
          :root { --gutter: 1rem; }
          body::before { background-size: 24px 24px; }
          .bearing-strip { grid-template-columns: 1fr auto; min-height: 1.75rem; font-size: .55rem; }
          .bearing-strip span:nth-child(2) { display: none; }
          .header-inner { min-height: 7.2rem; align-items: flex-start; padding-block: 1rem; flex-direction: column; gap: .8rem; }
          nav { width: 100%; overflow-x: auto; padding-bottom: .25rem; }
          nav ul { width: max-content; justify-content: flex-start; gap: 1.1rem; }
          .hero { min-height: auto; display: block; border-bottom: 0; }
          .hero-index { writing-mode: horizontal-tb; border: 0; border-bottom: 1px solid var(--line); flex-direction: row; padding: .7rem 0; }
          .hero-copy { padding: 3.8rem 0 3rem; }
          .hero-copy h1 { font-size: 4.75rem; line-height: .88; }
          .hero-deck { font-size: 1.08rem; }
          .hero-actions { align-items: flex-start; flex-direction: column; }
          .hero-bearing { display: block; padding: 2.5rem 0; border-top: 1px solid var(--line-strong); }
          .hero-bearing strong { font-size: 2.35rem; }
          .instrument { width: 12rem; margin: 2.5rem auto 0; }
          .section { padding-block: 4.5rem; }
          .section-heading { margin-bottom: 2rem; }
          .evidence-grid { border-left: 0; }
          .evidence-card { margin-inline: 0; min-height: 29rem; border-left: 1px solid var(--line-strong); }
          .page-lead { padding: 4rem 0; }
          .page-lead h1 { font-size: 3.75rem; }
          .record-head { padding: 4rem 0 3rem; gap: 2.5rem; }
          .record-head h1 { font-size: 3.8rem; }
          .record-register div, .evidence-list div { grid-template-columns: 5.5rem 1fr; }
          .record-body { padding-block: 3rem 5rem; gap: 3rem; }
          .about-lead { grid-template-columns: 1fr; padding: 4rem 0; }
          .portrait, .no-photo { justify-self: start; }
          .year-index { grid-template-columns: 1fr; }
          .comparison-grid { grid-template-columns: 1fr; }
          .footer-inner { grid-template-columns: 1fr; }
          .footer-coordinate, .footer-inner p:last-child { text-align: left; }
        }

        /* Dedicated 320 px composition: tighter hierarchy, preserved identity. */
        @media (max-width: 350px) {
          :root { --gutter: .75rem; }
          body { min-width: 0; }
          .bearing-strip { display: flex; justify-content: space-between; padding-inline: .75rem; font-size: .5rem; }
          .bearing-strip span:nth-child(2) { display: none; }
          .header-inner { min-height: auto; padding: .9rem 0 1rem; flex-direction: column; align-items: flex-start; gap: .9rem; }
          .wordmark { font-size: .92rem; }
          nav { width: 100%; overflow-x: auto; }
          nav ul { width: max-content; justify-content: flex-start; gap: .85rem; font-size: .64rem; }
          .hero { display: block; min-height: auto; }
          .hero-index { writing-mode: horizontal-tb; border-inline: 0; border-bottom: 1px solid var(--line); padding: .65rem 0; }
          .hero-copy { padding: 3rem 0 2.5rem; }
          .hero-copy h1 { font-size: 4rem; line-height: .87; }
          .hero-deck { font-size: 1rem; line-height: 1.5; }
          .hero-actions { flex-direction: column; align-items: stretch; gap: 1.2rem; }
          .button { width: 100%; }
          .hero-bearing { display: block; padding: 2.2rem 0 3rem; border-left: 0; border-top: 1px solid var(--line-strong); }
          .hero-bearing strong { font-size: 2rem; }
          .instrument { width: 10rem; margin: 2rem auto 0; }
          h2 { font-size: 2.45rem; }
          .section { padding-block: 3.75rem; }
          .section-heading { margin-bottom: 1.7rem; }
          .evidence-grid { border-left: 0; }
          .evidence-card { min-height: 27rem; padding: 1.25rem; border-left: 1px solid var(--line-strong); }
          .card-facts div { grid-template-columns: 4rem 1fr; }
          .method-grid li { grid-template-columns: 2.5rem 1fr; gap: .75rem; }
          .page-lead { padding: 3.5rem 0; }
          .page-lead h1, .record-head h1 { font-size: 3.25rem; }
          .record-head { padding: 3.5rem 0 2.5rem; gap: 2rem; }
          .record-register div, .evidence-list div { grid-template-columns: 4.7rem 1fr; gap: .65rem; }
          .record-body { padding-block: 2.75rem 4.5rem; gap: 2.75rem; }
          .prose { font-size: 1.08rem; }
          .note-list article { grid-template-columns: 2rem 1fr; gap: .75rem; }
          .about-lead { grid-template-columns: 1fr; padding: 3.5rem 0; }
          .portrait img, .no-photo { width: 100%; max-width: 256px; }
          .year-index, .comparison-grid { grid-template-columns: 1fr; }
          .archive-records a { grid-template-columns: 3.5rem 1fr auto; gap: .6rem; }
          .secondary-context article { grid-template-columns: 1fr; gap: .5rem; }
          .footer-inner { grid-template-columns: 1fr; padding: 2.5rem 0; }
          .footer-coordinate, .footer-inner p:last-child { text-align: left; }
        }

        @media (prefers-reduced-motion: reduce) {
          *, *::before, *::after { scroll-behavior: auto !important; animation-duration: .01ms !important; animation-iteration-count: 1 !important; transition-duration: .01ms !important; }
        }

        @media print {
          .bearing-strip, nav, .site-footer, .hero-actions { display: none; }
          body { background: white; color: black; }
          body::before { display: none; }
          a { text-decoration: none; }
        }
    """)
    return files
