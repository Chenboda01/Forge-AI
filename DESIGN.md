# Forge Terminal Design System

## 1. Atmosphere & Identity

Forge is a focused workshop: dark iron surfaces, quiet warm text, and a restrained
ember accent used only where attention or action is required. Its signature is a
continuous full-height status rail on the right, visually anchored from the top edge
to the bottom edge while the conversation moves independently beside it.

## 2. Color

### Palette

| Role | Token | Value | Usage |
|---|---|---|---|
| Canvas | `surface-canvas` | `#10100f` | Application background |
| Conversation | `surface-main` | `#151513` | Conversation and composer |
| Sidebar | `surface-rail` | `#1c1b18` | Fixed status rail |
| Elevated | `surface-elevated` | `#24221e` | Focused input and approval surfaces |
| Text primary | `text-primary` | `#f1eadf` | User and assistant content |
| Text secondary | `text-secondary` | `#aaa397` | Metadata and supporting values |
| Text muted | `text-muted` | `#6f6a61` | Hints and inactive information |
| Divider | `border-subtle` | `#35312b` | Structural separation only |
| Ember | `accent-primary` | `#e06c3b` | Focus, current activity, Forge identity |
| Ember bright | `accent-active` | `#f08a54` | Active and focused state |
| Success | `status-success` | `#87a96b` | Completed activity |
| Warning | `status-warning` | `#d5a94f` | Context pressure and cautions |
| Error | `status-error` | `#d9685f` | Failures and destructive actions |
| Info | `status-info` | `#6f9fba` | Tool activity and neutral notices |

### Rules

- The rail is separated by one divider and a tonal shift, never by a floating card.
- Ember is reserved for focus, identity, and current activity.
- Status colors communicate runtime meaning and are never decorative.
- New colors must be declared here before use in Textual CSS.

## 3. Typography

Textual inherits the terminal's monospace face. Hierarchy comes from weight, case,
color, and spacing rather than unavailable font-size changes.

| Level | Treatment | Usage |
|---|---|---|
| Product | Bold, ember | Forge mark |
| Section | Bold, primary | Sidebar section headings |
| Speaker | Bold, primary or ember | Conversation authors |
| Body | Regular, primary | Messages and command output |
| Metadata | Regular, secondary | Model, cost, tokens, directory |
| Hint | Dim, muted | Composer hint and inactive values |

Labels use sentence case. Numeric values use the terminal's tabular monospace cells.

## 4. Spacing & Layout

Textual spacing uses terminal cells rather than pixels. The base unit is one cell.

| Token | Value | Usage |
|---|---|---|
| `space-1` | 1 cell | Inline separation and compact gaps |
| `space-2` | 2 cells | Panel padding and section separation |
| `space-3` | 3 cells | Generous empty-state breathing room |

The app is a fixed full-screen shell. The main region owns roughly 75-80% of width;
the right rail owns 20-25%, with a 24-cell minimum and 32-cell preferred width.
The conversation viewport is the only vertical scroll owner. The rail and composer
remain fixed. At widths below 72 cells, the rail hides so the primary interaction
remains usable; status stays available through `/status`.

## 5. Components

### Conversation stream

- **Structure**: vertical scroll containing message blocks and activity records.
- **Variants**: user, Forge, tool, notice, error.
- **Spacing**: `space-1` within a message and `space-2` between messages.
- **States**: empty welcome, active generation, populated, error.
- **Accessibility**: chronological DOM order; plain ASCII labels; selectable text.
- **Motion**: none; new content scrolls into view only when appended.
- **Layout**: stack; owns vertical scrolling.

### Composer

- **Structure**: one labeled input at the bottom of the main column.
- **Variants**: ready, busy, disabled.
- **Spacing**: `space-1` vertical and `space-2` horizontal padding.
- **States**: default, focus, history navigation, submitted, disabled, error.
- **Accessibility**: keyboard-first; Enter submits; Up and Down navigate submitted input;
  visible focus treatment.
- **Motion**: none.
- **Layout**: fixed final row of the main-column shell.

### Activity progress

- **Structure**: compact phase label and horizontal activity bar immediately above the composer.
- **Variants**: ready, indeterminate primary-agent work, indeterminate subagent work, done, error.
- **Spacing**: `space-1` horizontal padding.
- **States**: ready, waiting for provider, running tool, reducing context, complete, failed.
- **Accessibility**: the current phase is always written as text; no fabricated percentage is shown.
- **Motion**: Textual's indeterminate progress animation runs only while duration is unknowable;
  completion switches to a full static bar. No decorative animation.
- **Layout**: fixed penultimate row of the main-column shell.

### Status rail

- **Structure**: product mark, session, context, cost, MCP, todo, model, directory,
  and version sections with flexible space before environment metadata.
- **Variants**: full and compact-content.
- **Spacing**: `space-2` padding and section gaps.
- **States**: zero usage, normal usage, context warning, long-value truncation.
- **Accessibility**: labels precede values; status is not conveyed by color alone.
- **Motion**: none.
- **Layout**: fixed right column; never participates in conversation scrolling.

### Approval dialog

- **Structure**: requested tool, exact arguments, approve and deny actions.
- **Variants**: write and command approval.
- **Spacing**: `space-2` padding.
- **States**: focused action, approved, denied.
- **Accessibility**: deny is the default; keyboard actions are explicit.
- **Motion**: none.
- **Layout**: centered modal over the shell.

## 6. Motion & Interaction

The terminal interface uses no decorative animation. The activity bar's indeterminate
motion communicates an active operation whose duration cannot be measured; it stops
immediately on completion. Focus changes and new activity are immediate. Input is
disabled while one model request is running to prevent overlapping writes. `Ctrl+C`
cancels or exits according to Textual lifecycle; two Escape presses request a safe
interrupt, five Escape presses within one 1.25-second sequence exit, and `Ctrl+Q` exits
explicitly.

## 7. Depth & Surface

The depth strategy is tonal shift plus structural dividers. The canvas, conversation,
rail, elevated input, and modal use progressively lighter iron tones. There are no
shadows, simulated glow, nested panel borders, or rounded card stacks.

## 8. Accessibility Constraints & Accepted Debt

### Constraints

- Every action is keyboard reachable and has a visible focused state.
- The UI remains understandable without color, Nerd Fonts, Unicode icons, or motion.
- Primary text targets at least WCAG AA contrast against its surface.
- Long paths and model identifiers truncate or wrap without moving the rail.
- At narrow widths, primary conversation and input take precedence over the rail.

### Accepted Debt

| Item | Location | Why accepted | Owner / Exit |
|---|---|---|---|
| Terminal screen readers vary by emulator | Entire TUI | Textual accessibility support depends on terminal capabilities | Reassess with supported-terminal matrix |
