# Design system changelog

## v0.4 — Product on Ashoka (2026-06-22)

No design-system token changes. v0.4 ships product features on the existing Ashoka UI: real upload stages, document panel Parsed tab + quote highlight, privacy card, feedback thumbs. See [`docs/plans/v0.4/prd.md`](../plans/v0.4/prd.md).

## v0.3 — Ashoka (2026-06-21)

**Shipped configuration:** Ashoka theme, light default, soft glow, aurora wallpaper, Inter + Fraunces + Geist Mono + Noto Sans Devanagari, XL type scale.

### Artifacts

- Finalized `dharmiq-design-demo.html` as the pixel-accurate visual spec.
- Synced `tokens.json` ashoka light/dark palettes to match the demo (sidebar 250px, dark elevation tokens, `mutedForeground` corrections).
- Implemented in React frontend per [`docs/plans/v0.3.md`](../plans/v0.3.md).

### Not shipped (reference only)

- `archival` and `gazette` themes remain in `tokens.json` / `explorations/` but are not built.
- Hindi full UI translation, privacy settings, upload stage API, doc chunk highlight, and 👍/👎 feedback are deferred to v0.4.
