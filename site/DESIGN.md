# Forge Website Design System

## 0. Research Log
- Embedded refs: shortlisted opencode.ai, warp.md, voltagent.md → picked opencode.ai (developer-native dark terminal aesthetic) + taste-skill (execution discipline)
- No lazyweb (skipped): site content is product-identity-driven

## 1. Atmosphere & Identity

A warm terminal workshop. Not a cold IDE — a forge with ember glow. The signature is the orange accent against layered dark surfaces, like hot metal against a dark anvil. Surfaces separate by depth rather than borders; the accent is used only for interaction and emphasis, never decoration.

## 2. Color

### Palette

| Role | Token | Value | Usage |
|------|-------|-------|-------|
| Surface/canvas | --surface-canvas | #10100f | Page background |
| Surface/primary | --surface-primary | #151513 | Main content areas |
| Surface/elevated | --surface-elevated | #24221e | Cards, code blocks |
| Surface/rail | --surface-rail | #1c1b18 | Side notes, asides |
| Text/primary | --text-primary | #f1eadf | Headlines, body |
| Text/secondary | --text-secondary | #aaa397 | Captions, muted |
| Text/muted | --text-muted | #6f6a61 | Disabled, footnotes |
| Border/default | --border-default | #35312b | Dividers, outlines |
| Accent/primary | --accent-primary | #e06c3b | Links, CTAs, interactive |
| Accent/hover | --accent-hover | #f08a54 | Hover states |
| Status/success | --status-success | #87a96b | Positive indicators |
| Status/warning | --status-warning | #d5a94f | Cautions |
| Status/error | --status-error | #d9685f | Errors |
| Status/info | --status-info | #6f9fba | Informational |

### Rules
- Accent primary is used ONLY for links, buttons, and interactive focus.
- No raw hex values outside this table.
- All text on dark surfaces meets WCAG AA contrast.

## 3. Typography

### Scale

| Level | Size | Weight | Line Height | Usage |
|-------|------|--------|-------------|-------|
| Display | 3rem / 48px | 700 | 1.1 | Hero headline |
| H1 | 2rem / 32px | 700 | 1.2 | Section headers |
| H2 | 1.5rem / 24px | 600 | 1.3 | Subsection headers |
| H3 | 1.125rem / 18px | 600 | 1.4 | Card titles |
| Body | 1rem / 16px | 400 | 1.6 | Paragraphs |
| Body/sm | 0.875rem / 14px | 400 | 1.5 | Secondary text |
| Caption | 0.75rem / 12px | 500 | 1.4 | Labels, metadata |
| Mono | 0.875rem / 14px | 400 | 1.5 | Code, commands |

### Font Stack
- Primary: Geist, system-ui, -apple-system, sans-serif
- Mono: JetBrains Mono, Fira Code, ui-monospace, monospace

### Rules
- Max 2 font families.
- Body text never below 14px.

## 4. Spacing & Layout

### Base Unit: 4px

| Token | Value | Usage |
|-------|-------|-------|
| --space-1 | 4px | Tight |
| --space-2 | 8px | Compact |
| --space-3 | 12px | Default internal |
| --space-4 | 16px | Standard |
| --space-6 | 24px | Generous |
| --space-8 | 32px | Section gap |
| --space-12 | 48px | Major section break |
| --space-16 | 64px | Page rhythm |
| --space-24 | 96px | Hero spacing |

### Grid
- Max content width: 960px
- Single-column primary layout
- Breakpoints: 375 (mobile), 768 (tablet), 1024 (desktop)

## 5. Components

### Button (Primary)
- Background: var(--accent-primary), Text: var(--text-primary)
- Padding: 12px 24px, Radius: 4px
- Hover: var(--accent-hover), Focus: 2px outline
- States: default, hover, focus, active, disabled

### Code Block
- Background: var(--surface-elevated), Border: 1px solid var(--border-default)
- Padding: 16px, Radius: 4px, Font: Mono stack
- Inline code uses same background without border

### Section
- Max width 960px, centered
- Padding: var(--space-24) var(--space-4)
- Alternates surface tones or borders for separation

### Skip Link
- Positioned off-screen, revealed on focus
- White on accent-primary background

## 6. Motion

| Type | Duration | Easing | Usage |
|------|----------|--------|-------|
| Micro | 100ms | ease-out | Button press |
| Standard | 200ms | ease-in-out | Link hover, tab switch |
| Reveal | 400ms | ease-out | Section entry |

### Rules
- Only animate transform and opacity.
- Respect prefers-reduced-motion: disable all non-essential motion.
- No perpetual animation, no scroll-jacking.

## 7. Depth

Strategy: tonal-shift with borders. Surfaces use progressively lighter shades of the warm dark palette. No shadows. Section separation uses background shifts or a single 1px border line.

## 8. Accessibility Constraints & Accepted Debt

### Constraints
- WCAG 2.2 AA: contrast floor 4.5:1 body, 3:1 large text
- Visible focus ring on every interactive element
- Full keyboard reachability
- Skip-to-content link
- Landmarks: header, main, nav
- prefers-reduced-motion respected

### Accepted Debt
| Item | Location | Why accepted | Owner / Exit |
|------|----------|--------------|--------------|
| No client-side routing | site/ | Single-page site, no SPA needed | Permanent |
| No light mode theme | site/ | Terminal-native identity is dark-first | Until user requests light theme |
