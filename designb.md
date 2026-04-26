# Design Basis

Diese Datei ist die zentrale Stelle fuer UI-Farben, Abstaende und visuelle Tokens.

## So nutzt du sie

- Aendere nur die Werte im CSS-Block zwischen den Markern.
- Starte danach `npm run dev` oder `npm run build` im `frontend`-Ordner.
- Das Script `sync:design` aktualisiert automatisch `frontend/src/styles/design-tokens.css`.

<!-- DESIGN_TOKENS_START -->

```css
:root {
  --primary: #6e51b8;
  --primary-container: #8a70cc;
  --on-primary: #ffffff;
  --on-primary-container: #ffffff;
  --primary-fixed: #7c5ec0;
  --primary-fixed-dim: #5d419f;
  --inverse-primary: #b8a3e0;
  --secondary: #8a7fa8;
  --secondary-container: #ebe6f3;
  --on-secondary: #ffffff;
  --on-secondary-container: #2a2438;
  --secondary-fixed: #9d92ba;
  --secondary-fixed-dim: #786d96;
  --tertiary: #b8a5dd;
  --tertiary-container: #f2ecfa;
  --on-tertiary: #ffffff;
  --on-tertiary-container: #2d2440;
  --tertiary-fixed: #c4b4e3;
  --tertiary-fixed-dim: #a591ce;
  --error: #d97a85;
  --error-container: #f8dde0;
  --on-error: #ffffff;
  --on-error-container: #481b22;
  --background: #ffffff;
  --on-background: #1f1d24;
  --surface: #ffffff;
  --surface-dim: #f7f5fb;
  --surface-bright: #ffffff;
  --surface-container-lowest: #ffffff;
  --surface-container-low: #fbf9fe;
  --surface-container: #f6f3fb;
  --surface-container-high: #f0ecf7;
  --surface-container-highest: #e8e2f2;
  --surface-variant: #ece8f3;
  --on-surface: #1f1d24;
  --on-surface-variant: #5d556e;
  --surface-tint: #6e51b8;
  --inverse-surface: #2a2438;
  --inverse-on-surface: #f7f5fb;
  --outline: #b5adc4;
  --outline-variant: #ddd6e8;

  --text-placeholder: rgba(93, 85, 110, 0.5);
  --shadow-focus-primary: 0 0 0 3px rgba(110, 81, 184, 0.22);

  --border-muted: rgba(60, 50, 80, 0.08);
  --border-muted-strong: rgba(60, 50, 80, 0.16);
  --border-weak: rgba(60, 50, 80, 0.22);
  --border-weaker: rgba(60, 50, 80, 0.16);
  --border-faint: rgba(60, 50, 80, 0.12);
  --border-faintest: rgba(60, 50, 80, 0.08);

  --bg-hover-ghost: rgba(110, 81, 184, 0.06);
  --bg-error-soft: rgba(217, 122, 133, 0.1);
  --border-error-soft: rgba(217, 122, 133, 0.28);
  --bg-success-soft: rgba(155, 192, 168, 0.12);
  --border-success-soft: rgba(155, 192, 168, 0.3);
  --bg-warning-soft: rgba(229, 192, 128, 0.14);
  --border-warning-soft: rgba(229, 192, 128, 0.3);

  --kg-accent-bg: rgba(110, 81, 184, 0.12);
  --kg-accent-border: rgba(110, 81, 184, 0.32);
  --kg-tag-bg: rgba(110, 81, 184, 0.08);
  --kg-tag-border: rgba(110, 81, 184, 0.22);
  --kg-tag-text: #5d419f;
  --kg-tag-neutral-text: #5d556e;

  --network-bg-start: #ffffff;
  --network-bg-end: #ffffff;
  --network-line: rgba(60, 50, 80, 0.18);
  --network-line-active: rgba(110, 81, 184, 0.9);
  --network-line-soft: rgba(110, 81, 184, 0.4);
  --network-node-bg: #ffffff;
  --network-node-outline: rgba(60, 50, 80, 0.18);
  --network-node-active-border: rgba(110, 81, 184, 0.6);
  --network-node-active-glow: 0 0 0 4px rgba(110, 81, 184, 0.2);
  --network-node-materials-border: rgba(138, 112, 204, 0.55);
  --network-node-validation-border: rgba(155, 192, 168, 0.55);
  --network-message-success-border: rgba(155, 192, 168, 0.4);
  --network-message-warn-border: rgba(217, 122, 133, 0.4);
  --network-message-info-border: rgba(110, 81, 184, 0.4);

  --progress-empty-bar: #ece8f3;

  --unit: 4px;
  --gutter: 16px;
  --margin: 24px;
  --container-max: 1440px;
  --sidebar-width: 256px;
  --header-height: 64px;
}
```

<!-- DESIGN_TOKENS_END -->
