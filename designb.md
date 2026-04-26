# Design Basis — Scientific Ultra-Light

Diese Datei ist die zentrale Stelle fuer UI-Farben, Abstaende und visuelle Tokens.

## So nutzt du sie

- Aendere nur die Werte im CSS-Block zwischen den Markern.
- Starte danach `npm run dev` oder `npm run build` im `frontend`-Ordner.
- Das Script `sync:design` aktualisiert automatisch `frontend/src/styles/design-tokens.css`.

## Brand & Style

The brand personality is rooted in objective precision and intellectual clarity. This design system evokes a sense of "clinical airiness"—it is sterile without being cold, and rigorous without being dense. It is designed for researchers, data scientists, and engineers who require a high-focus environment where the UI recedes to let data and observations take center stage.

The style is a pure expression of **Minimalism**, prioritizing negative space and a restricted palette. It utilizes structural alignment and subtle typographic hierarchy to guide the user. Every element is intentional; if a component does not serve a functional purpose in data interpretation, it is removed. The emotional response should be one of calm, focused efficiency.

## Colors

The palette is built on a pure white canvas (`#ffffff`) that acts as a neutral surface for long analytical sessions. Hierarchy is achieved through subtly tinted container layers (`#faf7fb` → `#e6e0e9`) rather than hue shifts, with a deep "lab violet" (`#4f378a`) serving as the sole interaction accent. A muted secondary slate (`#63597c`) carries supporting structure, while a restrained gold (`#765b00`) is reserved for knowledge-graph and validation cues. Text contrast is intentionally soft—deep warm grays instead of pure black—to maintain the airy atmosphere.

## Typography

Typography is systematic and utilitarian. **Inter** is used across all levels; hierarchy is achieved through size and tracking rather than aggressive weight changes. Headlines run light (300–500) with tighter letter spacing for an editorial feel. Body text is regular (400) at 14–16px with generous line height. Small labels use medium weight (500) and slight letter spacing to remain readable at small scales without breaking the light visual rhythm. Scientific data strings keep the standard font but maintain consistent character spacing.

## Layout & Spacing

The layout follows a Fixed Grid for centralized dashboards and a Fluid Grid for data-heavy analytical views, built on a strict 4px base unit. Whitespace is treated as a first-class citizen: page margins are generous (48px+) to prevent the interface from feeling cramped, and content modules are separated by large air gaps so the eye can rest between data sets.

## Elevation & Depth

This system eschews traditional shadows in favor of **Tonal Layers** and **Low-Contrast Outlines**. Depth is communicated through subtle shade stacking:

- **Level 0 (Base):** pure white surface (`#ffffff`).
- **Level 1 (Cards/Panels):** lightly tinted lavender containers (`#faf7fb` → `#f4eff5`) sitting above the white canvas.
- **Outlines:** thin (1px) borders in `outline-variant` (`#cbc4d2`).
- **Active State:** a faint, diffused violet glow at low opacity to indicate a "lifted" module.

The goal is a UI that feels flat and architectural, like a physical blueprint.

## Shapes

Shape language is disciplined and professional. Soft roundedness (`0.25rem`) is applied to primary UI elements like buttons, input fields, and small cards. Larger containers use `0.5rem` to soften the overall grid. Pill shapes and circles are reserved for status dots and avatars.

<!-- DESIGN_TOKENS_START -->

```css
:root {
  /* === Material 3 — Scientific Ultra-Light === */
  --primary: #4f378a;
  --primary-container: #6750a4;
  --on-primary: #ffffff;
  --on-primary-container: #e0d2ff;
  --primary-fixed: #e9ddff;
  --primary-fixed-dim: #cfbcff;
  --on-primary-fixed: #22005d;
  --on-primary-fixed-variant: #4f378a;
  --inverse-primary: #cfbcff;

  --secondary: #63597c;
  --secondary-container: #e1d4fd;
  --on-secondary: #ffffff;
  --on-secondary-container: #645a7d;
  --secondary-fixed: #e9ddff;
  --secondary-fixed-dim: #cdc0e9;
  --on-secondary-fixed: #1f1635;
  --on-secondary-fixed-variant: #4b4263;

  --tertiary: #765b00;
  --tertiary-container: #c9a74d;
  --on-tertiary: #ffffff;
  --on-tertiary-container: #503d00;
  --tertiary-fixed: #ffdf93;
  --tertiary-fixed-dim: #e7c365;
  --on-tertiary-fixed: #241a00;
  --on-tertiary-fixed-variant: #594400;

  --error: #ba1a1a;
  --error-container: #ffdad6;
  --on-error: #ffffff;
  --on-error-container: #93000a;

  --background: #ffffff;
  --on-background: #1d1b20;
  --surface: #ffffff;
  --surface-dim: #ece6ee;
  --surface-bright: #ffffff;
  --surface-container-lowest: #ffffff;
  --surface-container-low: #faf7fb;
  --surface-container: #f4eff5;
  --surface-container-high: #ece6ee;
  --surface-container-highest: #e6e0e9;
  --surface-variant: #ece6ee;
  --on-surface: #1d1b20;
  --on-surface-variant: #494551;
  --surface-tint: #6750a4;
  --inverse-surface: #322f35;
  --inverse-on-surface: #f5eff7;
  --outline: #7a7582;
  --outline-variant: #cbc4d2;

  /* === Custom interaction tokens === */
  --primary-hover: #3d2a6d;
  --text-placeholder: rgba(73, 69, 81, 0.5);
  --shadow-focus-primary: 0 0 0 3px rgba(79, 55, 138, 0.22);

  /* Borders are tonal layers built from on-surface (#1d1b20) */
  --border-muted: rgba(29, 27, 32, 0.06);
  --border-muted-strong: rgba(29, 27, 32, 0.12);
  --border-weak: rgba(29, 27, 32, 0.18);
  --border-weaker: rgba(29, 27, 32, 0.12);
  --border-faint: rgba(29, 27, 32, 0.08);
  --border-faintest: rgba(29, 27, 32, 0.05);

  /* Soft state backgrounds — monochromatic violet/slate, with red kept only for errors */
  --bg-hover-ghost: rgba(79, 55, 138, 0.06);
  --bg-error-soft: rgba(186, 26, 26, 0.1);
  --border-error-soft: rgba(186, 26, 26, 0.28);
  --bg-success-soft: rgba(99, 89, 124, 0.1);
  --border-success-soft: rgba(99, 89, 124, 0.3);
  --bg-warning-soft: rgba(118, 91, 0, 0.1);
  --border-warning-soft: rgba(118, 91, 0, 0.28);

  /* Knowledge Garden tags */
  --kg-accent-bg: rgba(79, 55, 138, 0.1);
  --kg-accent-border: rgba(79, 55, 138, 0.3);
  --kg-tag-bg: rgba(79, 55, 138, 0.08);
  --kg-tag-border: rgba(79, 55, 138, 0.22);
  --kg-tag-text: #4f378a;
  --kg-tag-neutral-text: #494551;

  /* Network graph */
  --network-bg-start: #ffffff;
  --network-bg-end: #ffffff;
  --network-line: rgba(29, 27, 32, 0.16);
  --network-line-active: rgba(79, 55, 138, 0.9);
  --network-line-soft: rgba(79, 55, 138, 0.4);
  --network-node-bg: #ffffff;
  --network-node-outline: rgba(29, 27, 32, 0.16);
  --network-node-active-border: rgba(79, 55, 138, 0.6);
  --network-node-active-glow: 0 0 0 4px rgba(79, 55, 138, 0.18);
  --network-node-materials-border: rgba(103, 80, 164, 0.55);
  --network-node-validation-border: rgba(99, 89, 124, 0.55);
  --network-message-success-border: rgba(99, 89, 124, 0.4);
  --network-message-warn-border: rgba(186, 26, 26, 0.4);
  --network-message-info-border: rgba(79, 55, 138, 0.4);

  --progress-empty-bar: #e6e0e9;

  /* === Shape tokens (border-radius scale) === */
  --rounded-sm: 0.125rem;
  --rounded: 0.25rem;
  --rounded-md: 0.375rem;
  --rounded-lg: 0.5rem;
  --rounded-xl: 0.75rem;
  --rounded-full: 9999px;

  /* === Layout & spacing — generous, airy, 4px-rhythm === */
  --unit: 4px;
  --gutter: 24px;
  --margin: 48px;
  --margin-page: 48px;
  --stack-xs: 4px;
  --stack-sm: 8px;
  --stack-md: 16px;
  --stack-lg: 32px;
  --stack-xl: 64px;
  --container-max: 1440px;
  --sidebar-width: 256px;
  --header-height: 64px;
}
```

<!-- DESIGN_TOKENS_END -->

## Components

### Buttons
Primary buttons use the deep `--primary` violet on white text. Hover transitions to `--primary-hover` (a slightly darker violet) so the action stays grounded but visibly responds. Secondary "ghost" buttons sit on a transparent or `surface-container-low` fill with a thin `outline-variant` border.

### Input Fields
Fields use a single-pixel `outline-variant` border on a `surface-container-lowest` (white) background. Focus replaces the border with `--primary` and adds a soft `--shadow-focus-primary` halo.

### Cards & Modules
Modules are flat white panels (`surface-container-lowest`) with no shadow, defined only by the light border. Titles use `font-label-caps` for a technical, tagged appearance.

### Chips & Tags
Chips have a `surface-container-high` background, no border, and `font-label-caps` text. They feel like labels, not buttons.

### Scientific Data Tables
Tables use the data-mono typography. Rows are separated by the thinnest possible horizontal lines (`border-faintest`). Avoid zebra-striping; use a subtle `--bg-hover-ghost` change on hover instead.

### Progress & Status
Status indicators use the violet accent for "active" and a simple gray for "inactive". Avoid green/red/yellow except for safety-critical alerts (`--error`), preferring a monochromatic violet scale for normal operation.
