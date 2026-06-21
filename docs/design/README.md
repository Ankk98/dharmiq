# Dharmiq — Design System (v0.3, FINALIZED)

This folder is the **single source of truth** for Dharmiq's visual design. Hand these three artifacts to an
implementing agent and it has everything it needs:

| Artifact | What it is |
|----------|-----------|
| [`dharmiq-design-demo.html`](./dharmiq-design-demo.html) | **The canonical, pixel-accurate spec.** A self-contained, runnable mock of the whole app (chat, document viewer, documents/upload, settings, auth) in the finalized theme, with every flow and micro-interaction animating. Open it in a browser. When this README and the demo disagree, **the demo wins**. |
| [`tokens.json`](./tokens.json) | Portable design tokens (colors, type, spacing, radius, motion) → CSS variables → Flutter `ThemeData`. |
| `README.md` (this file) | The written principles, exact values, component specs, and a step-by-step implementation guide for our actual stack. |
| [`explorations/`](./explorations/) | Earlier theme/variant studies (preview, variants, showcase). **Reference only — not shipped.** |

> The demo is a static HTML/CSS/JS prototype. It is **not** meant to be copied into the codebase verbatim.
> Re-implement its look and behavior using our real stack (React 19 + Tailwind v4 + shadcn + assistant-ui), driven by `tokens.json`.

---

## 0. The locked configuration

After iterating across three themes and many variants, **v0.3 ships exactly one configuration**:

```
Theme:        Ashoka          (calm navy primary, India-green accent)
Default mode: Light           (Dark fully supported)
Glow:         Soft
UI font:      Inter           (variable)
Display font: Fraunces        (variable, optical sizing — headings & wordmark)
Mono font:    Geist Mono      (citations refs, counts, code)
Hindi font:   Noto Sans Devanagari
Type scale:   XL / 4K         (base 15px × 1.22)
Hindi size:   Comfortable     (× 1.08, line-height 1.9)
Cursor:       System
Wallpaper:    Aurora          (slow, subtle, behind content)
```

`archival` and `gazette` and the variant matrix remain in `tokens.json` and `explorations/` for posterity, but
**do not build them**. Build Ashoka, light + dark.

---

## 1. Design principles

Dharmiq is **not a chatbot** — it is a *grounded legal information system*. The UI must earn trust before it shows
personality. Every choice below serves **trust, traceability, and source fidelity** over flash.

1. **Less is more.** Border-first surfaces, generous whitespace, one accent used sparingly. If a flourish doesn't aid
   comprehension or trust, remove it.
2. **The source is the product.** Citations, quotes, and the document viewer are first-class — never an afterthought.
   "Law says" and "Your document says" are *visually distinct* so users always know what grounds a claim.
3. **Honesty in motion.** Animation communicates real state (a step running, a stream arriving, a doc attaching) —
   never decoration for its own sake. Everything respects `prefers-reduced-motion`.
4. **Readability over filling pixels.** Reading legal text demands a constrained measure (~66–72 characters). We keep a
   centered reading column even on 4K and put the freed space to work *on demand* (the document viewer slides into it).
5. **Calm, premium restraint.** The bar is Posthog / Sentry / Stripe / Linear: quiet surfaces, crisp hairlines, refined
   type, deliberate spacing. Trustworthy, not toy-like.
6. **One system, two platforms.** Tokens drive web today and Flutter later. Keep values portable; avoid web-only hacks
   in token definitions.
7. **Accessible by default.** WCAG AA contrast, visible focus rings, keyboard-navigable, honest live-region semantics
   for streaming.

---

## 2. Foundations

### 2.1 Color — Ashoka

All values below are the **finalized** Ashoka palette (they match the demo and `tokens.json`). Map them to our shadcn
variable names in `frontend/src/index.css` (see §5).

**Light (default)**

| Role | Token | Hex |
|------|-------|-----|
| App background | `background` | `#F8FAFC` |
| App background (alt) | `background2` | `#EEF2F7` |
| Surface (cards, sidebar) | `surface` | `#FFFFFF` |
| Raised (answer card, composer field) | `surfaceRaised` | `#FFFFFF` |
| Hover | `hover` | `#F1F5F9` |
| Text | `foreground` | `#0F172A` |
| Muted text | `mutedForeground` | `#5B6678` |
| Faint text | `faint` | `#94A3B8` |
| **Primary** (brand navy) | `primary` | `#1E3A5F` |
| Primary foreground | `primaryForeground` | `#FFFFFF` |
| Primary muted (soft fills) | `primaryMuted` | `#E8EEF4` |
| **Accent** (India green) | `accent` | `#0E8C3F` |
| Accent muted | `accentMuted` | `#E6F4EC` |
| **Law citation** border/text | `citationLaw` | `#1E3A5F` |
| Law citation background | `citationLawBackground` | `#F1F5F9` |
| **Your-document citation** border/text | `citationDoc` | `#0E7C66` |
| Doc citation background | `citationDocBackground` | `#E6F3F0` |
| Border (hairline) | `border` | `#E4E8EF` |
| Border subtle | `borderSubtle` | `#EEF2F7` |
| Focus ring | `ring` | `#94A3B8` |
| Success | `success` | `#0E8C3F` |
| Warning (disclaimer) | `warning` | `#B25A00` |
| Danger | `danger` | `#C0392B` |

Light shadow: `0 1px 2px rgba(15,23,42,0.05), 0 8px 24px rgba(15,23,42,0.05)`. Soft glow in light ≈ none (`0 0 0 0 transparent`).

**Dark** — near-neutral charcoal with a faint cool cast (not saturated navy). Built on *elevation*, not tint.

| Role | Token | Hex |
|------|-------|-----|
| App background | `background` | `#0A0B0D` |
| App background (alt) | `background2` | `#0C0E11` |
| Surface | `surface` | `#121419` |
| Raised | `surfaceRaised` | `#181B21` |
| Hover | `hover` | `#1F232A` |
| Text | `foreground` | `#E8EAEE` |
| Muted text | `mutedForeground` | `#969BA6` |
| Faint text | `faint` | `#5F636E` |
| Primary (sky) | `primary` | `#6FA3DE` |
| Primary foreground | `primaryForeground` | `#0A0B0D` |
| Primary muted | `primaryMuted` | `#171B22` |
| Accent | `accent` | `#56C28C` |
| Accent muted | `accentMuted` | `#13201A` |
| Law citation | `citationLaw` | `#86AEDC` |
| Law citation bg | `citationLawBackground` | `#121519` |
| Doc citation | `citationDoc` | `#5BC9A7` |
| Doc citation bg | `citationDocBackground` | `#10201B` |
| Border | `border` | `rgba(255,255,255,0.07)` |
| Border subtle | `borderSubtle` | `rgba(255,255,255,0.045)` |
| Ring | `ring` | `rgba(111,163,222,0.55)` |
| Warning | `warning` | `#D6A84D` |
| Danger | `danger` | `#E8806E` |

Dark soft glow: `0 0 11px rgba(111,163,222,0.16)`. Dark card top-edge highlight: `inset 0 1px 0 rgba(255,255,255,0.045)`.
Dark shadow: `0 1px 2px rgba(0,0,0,0.4), 0 12px 40px rgba(0,0,0,0.35)`.

**Color usage rules**
- Primary is for: brand mark, active nav, user bubble, links, primary buttons, "running" step, focus.
- Accent (green) is **sparse**: the live/"grounded" dot, success states, "verified" markers. Never large fills.
- Hairline borders define surfaces in **both** modes; in dark, prefer border + elevation + the inset top highlight
  over heavier shadows.

### 2.2 Typography

| Use | Family | Notes |
|-----|--------|-------|
| UI / body | **Inter** (variable) | weights 400/500/600 |
| Display / headings / wordmark | **Fraunces** (variable, `opsz`) | weights 400/500/600; optical sizing for crisp 4K |
| Citation refs, counts, code, doc viewer | **Geist Mono** | tabular feel; use `font-variant-numeric: tabular-nums` for counts/section numbers |
| Hindi (all roles) | **Noto Sans Devanagari** | leads the stack when `lang=hi`; **never letter-space** Devanagari |

**Scale — XL (4K).** Base font size = `15px × 1.22 ≈ 18.3px` on the app root. Component sizes are relative `em`s off that
base (see demo). Use fluid `clamp()` for top-level headings so they scale between mobile and 4K. Variable fonts +
`opsz` keep text crisp on high-DPI without looking heavy on cheap phones.

**Reading measure.** The chat column is capped at **`min(72ch, 100%)`, centered**. This is intentional and load-bearing
for readability — do not stretch answers full-bleed on wide screens.

### 2.3 Hindi (Devanagari)

Devanagari needs more vertical room and a touch more size than Latin at the same point size.

- Size multiplier **× 1.08** ("Comfortable") on top of the XL scale when `lang=hi`.
- `line-height: 1.9` for answer paragraphs, user bubbles, and citations.
- **Never** apply `letter-spacing` or `text-transform: uppercase` to Devanagari (it breaks conjuncts/ligatures). Citation
  labels that are uppercase+tracked in English must reset to `none`/`normal` in Hindi.
- The whole UI (nav, settings, auth) localizes, not just answers. In the demo this is `data-en`/`data-hi`; in the app use
  the real i18n layer.

### 2.4 Spacing, radius, motion

- **Spacing** on a 4px grid (see `tokens.json` → `spacing`).
- **Radius:** sm `6px`, md `8px`, lg `12px`, xl `16px`, full `9999px`. Cards/panels lg–xl; chips/pills full; bubbles ~14px.
- **Motion** (`tokens.json` → `motion`):
  - durations: instant `100ms`, fast `150ms`, normal `220ms`, slow `380ms`.
  - easing: default `cubic-bezier(0.22,1,0.36,1)`, enter `cubic-bezier(0.16,1,0.3,1)`, spring `cubic-bezier(0.34,1.56,0.64,1)` (chips/pop only).
  - **Always** gate non-essential animation behind `@media (prefers-reduced-motion: reduce)`.

### 2.5 Wallpaper, glow, cursor

- **Aurora wallpaper:** very low-opacity radial gradients in the primary hue, behind content, animating slowly
  (~22s, translate+scale). Sits on app background and the auth screen. Disabled under reduced-motion.
- **Soft glow:** a faint colored shadow on primary elements (brand mark, active nav indicator, send button, running
  step). Barely visible in light; gentle in dark. Never a neon halo.
- **Cursor:** system default (we evaluated custom cursors and chose not to ship them).

---

## 3. Layout & responsive

**Desktop app shell** is a 3-column grid:

```
┌──────────┬─────────────────────────┬──────────────────┐
│ Sidebar  │  Main (topnav + page)   │  Doc viewer      │
│ ~250px   │  1fr                    │  (0, opens 50/50)│
│ collapse │                         │  resizable       │
│  → 70px  │                         │                  │
└──────────┴─────────────────────────┴──────────────────┘
```

- **Sidebar** (`~250px`, collapsible to `70px`): wordmark, nav (Chat / Documents / Settings), New chat, user footer
  (avatar + name + logout). Active nav has a primary left-edge indicator + soft fill.
- **Main**: sticky top nav (breadcrumb + "grounded" chip + Concise/Detailed toggle), then the routed page.
- **Doc viewer** (right column): width `0` when closed; opening a citation animates it to a **50/50 split of the
  available space** (`calc((100% - sidebar)/2)`), and it is **drag-resizable** (min 300px doc / 360px chat; double-click
  divider resets to 50/50).

**Mobile** (`≤ ~420px` / when targeting phones):
- Sidebar → top **app bar** (hamburger + wordmark + avatar) and a bottom **tab bar** (Chat / Docs / Settings / Account).
- Doc viewer becomes a **full-screen overlay** that slides in from the right (no resizer).
- Reading column is full width (minus padding).

Must look right from a **cheap phone up to a 4K monitor** — verify both extremes.

---

## 4. Components & flows (spec)

> All of these are demonstrated, animated, in `dharmiq-design-demo.html`. Use it as the visual reference for each item.

### 4.1 Chat thread
- **User message:** primary-filled bubble, right-aligned, asymmetric radius (`14px 14px 5px 14px`), max-width ~82%.
- **Attachment = part of the thread.** When a document is attached/detached, render a **centered system pill** inline in
  the timeline (paperclip + "Attached document: `<name>`"), matching the existing `SystemEventMessage`. This is *in
  addition to* the session attachment chips and the composer paperclip — attaching is a thread event, not just a sidebar
  state.
- **Message entry:** subtle fade + 7px rise, staggered per message (respect reduced-motion).

### 4.2 Inline agent progress (concise / detailed / debug)
- Appears as a card in the thread *above* the answer while the pipeline runs.
- Mirrors the real graph: **Understanding your question → Searching the law → Ranking the best sources → Checking the
  answer → Writing the answer** (clarifier → retrieve+merge → rerank → validator → finalizer).
- States per step: pending (faint dot), **running** (primary pulsing dot + label), done (accent dot). A live timer.
- **Concise** (default): friendly labels only. **Detailed**: adds agent id + counts (e.g. `corpus+uploads · 11 chunks`,
  `rerank · top 8`, `validator · claims n/m`) on the right in mono. **Debug**: admin-only; never exposed to regular users
  (server strips it). Toggle lives in the top nav and in Settings; persist `concise|detailed` (localStorage / prefs).

### 4.3 Streamed answer with citations
- Streaming is **replay of the already-validated answer** (no second model call) — type it in token-by-token with a
  blinking caret. Loop/replay must be cancellable (don't double-write on re-render).
- **Structured sections** (Fraunces sub-headings): Summary → What the law says → What your document says → How this
  applies → Practical next steps → Assumptions (if any) → Disclaimer.
- **Citations:** inline `[n]` markers (mono, superscript, clickable) + block citations:
  - **"Law says · verified"** — primary left border, `citationLawBackground`.
  - **"Your document says"** — teal (`citationDoc`) left border, `citationDocBackground`.
  - Each shows the quoted text + a mono ref (e.g. `Consumer Protection Act, 2019 · § 2(9)`). Clicking a citation or an
    `[n]` opens the document viewer to that source with the quoted span highlighted.
- **Message actions** (icon row): copy, 👍, 👎, regenerate. Hover/active states; subtle.
- **Disclaimer** appended once at the end (warning-bordered, muted): general information, not advice.

### 4.4 Critical answer states
- **Refusal on weak retrieval:** a contained card — "I can't answer this reliably" + reason + suggestion pills
  (Rephrase / Attach a document). Warning tone, not error-red.
- **Clarifying question** (up to 3 rounds): a card with a "why this helps" line, the question, quick-reply chips, and an
  **"Answer with what you have"** skip (dashed). 

### 4.5 Composer & attachments
- Rounded field (raised surface) with a **paperclip** (attach) and a disabled **mic** (voice = roadmap), plus a primary
  **Send** button. Focus state: primary border + soft focus ring.
- Session attachment chips render above the composer (full pill, paperclip + filename + detach ✕), and uploads picker is
  reachable from the paperclip.

### 4.6 Document viewer panel
- Header: document title + section subtitle + close. Body: monospaced source lines; the **quoted span is highlighted**
  with a primary left-bar and a gentle pulse. Footer note. 50/50 + resizable on desktop, full-screen overlay on mobile
  (see §3).

### 4.7 Documents page (library + upload pipeline)
- Dropzone (PDF / DOCX / Markdown / images-OCR, ≤ 20MB) with hover affordance.
- File list cards. **Processing pipeline** shown as chips that advance: **Uploaded → Parsed → Chunking → Embedding →
  Ready**, with a progress bar and a status label (Processing → Ready). Ready files show chunk count.
- Uploads land in the **library**; user must **explicitly "Attach to chat"** (button toggles to "Attached"). This matches
  the product rule: corpus is always searched; uploads only when attached.

### 4.8 Settings
- Cards: **Answer progress** (Concise / Detailed / Debug·admin tier), **Appearance & language** (Light/Dark, EN/हिं),
  **Privacy & data** (save-history switch, export JSON, delete account — danger), **Account** (profile + log out).
- The Light/Dark and EN/हिं controls here mirror (and drive) the same global state.

### 4.9 Auth (login / signup / logout)
- Centered card over the aurora background, brand mark + tagline, fields, primary CTA, alt link to switch login↔signup,
  and a footer reminder ("general legal information — not legal advice"). Card entrance: gentle spring pop. Logout returns
  to login.

### 4.10 Micro-interaction catalog
Spinner, thinking dots, skeleton shimmer (loading), toast (e.g. "Document attached"), error/retry card (shake-in,
reconnecting copy), step pulse, chip pop-in, nav active slide, button press scale, citation hover nudge, field focus ring,
doc-line highlight pulse, aurora drift. All subtle; all reduced-motion aware.

### 4.11 Default avatar
No text initials. Use the subtle, professional inline-SVG silhouette from the demo (figure + attire on a `primaryMuted`
disc), themable via `currentColor`.

---

## 5. Implementation guide (our stack)

Current stack: **React 19 + Vite + Tailwind v4 + shadcn + assistant-ui**, fonts via fontsource. Theme variables live in
`frontend/src/index.css` (shadcn-style OKLCH `--background/--foreground/--primary/...` in `:root` and `.dark`).

### 5.1 Tokens → CSS variables
1. Replace the placeholder OKLCH values in `:root` and `.dark` with the **Ashoka** hex values from §2.1, mapped to the
   existing shadcn variable names:
   - `--background, --foreground, --card, --card-foreground, --popover*, --primary, --primary-foreground, --secondary*,
     --muted, --muted-foreground, --accent, --accent-foreground, --border, --input, --ring, --destructive`, and the
     `--sidebar*` set.
   - Map: surface→`--card`/`--popover`/`--sidebar`; raised→answer/composer surfaces; hover→`--accent`(as hover fill) or a
     dedicated `--hover`; `primaryMuted`→soft primary fills.
2. **Add custom variables** Tailwind doesn't ship: `--citation-law`, `--citation-law-bg`, `--citation-doc`,
   `--citation-doc-bg`, `--glow`, `--card-highlight`, `--wp-accent` (rgb triplet for the aurora). Expose via
   `@theme inline` so you can use `bg-*`/`border-*` utilities, or apply directly.
3. Drive dark mode with the existing `.dark` class variant (already configured: `@custom-variant dark`).
4. Hex is fine in Tailwind v4; you don't have to convert to OKLCH (keep whichever is easier to maintain, but keep it
   consistent).

### 5.2 Fonts
- Add **Inter** and **Fraunces** (and **Noto Sans Devanagari**) — prefer `@fontsource-variable/*` (Geist Mono is already
  available via fontsource). Set `--font-sans: Inter`, add `--font-display: Fraunces`, `--font-mono: 'Geist Mono'`.
- Apply Fraunces to headings (`--font-heading`) and the wordmark; Inter everywhere else; Geist Mono to citation refs,
  counts, and the doc viewer.
- For Hindi, switch the active UI stack to lead with Noto Sans Devanagari and apply the §2.3 size/line-height rules.

### 5.3 Where each piece lives (map demo → real components)

| Demo piece | Real file(s) to touch |
|------------|----------------------|
| Theme tokens, light/dark, fonts | `frontend/src/index.css` |
| App shell / 3-column layout, sidebar, doc panel | `frontend/src/pages/ChatPage.tsx` |
| User bubble, **in-thread attach system pill**, message actions, composer + paperclip | `frontend/src/components/assistant-ui/thread.tsx` |
| Inline `[n]` citations, **Law says / Your document says** blockquotes, links | `frontend/src/components/assistant-ui/markdown-text.tsx`, `frontend/src/lib/citations.ts` |
| Concise / Detailed / Debug progress | `frontend/src/components/chat/MessageProgress.tsx` |
| Document viewer → **resizable 50/50 side panel** (currently a full-page route) | `frontend/src/pages/DocumentViewerPage.tsx` + `ChatPage.tsx` (host the panel beside the thread; keep the route for deep-links/mobile) |
| Session attachment chips + attach picker | `frontend/src/components/uploads/SessionAttachments.tsx` |
| Upload library + **processing pipeline** UI | `frontend/src/components/uploads/UploadLibrary.tsx` |
| Default avatar SVG | shared avatar component (replace initials) |
| Settings, Auth pages | corresponding route/page components (create/restyle to match demo) |

> Notable behavior change from today: the document viewer should be reachable **inline as a resizable side panel beside
> the chat** (per the demo), in addition to the existing `/docs/:id` route used for deep links and mobile full-screen.

### 5.4 Flutter (future)
`tokens.json` maps cleanly to `ThemeData`: colors → `ColorScheme`, type → `TextTheme` (bundle Inter/Fraunces/Noto via
`google_fonts` or assets; map `opsz`/`wght` through `TextStyle.fontVariations`), radius/spacing → constants, motion →
`Duration` + `Curve`. Keep the same semantic names so web and app stay in lockstep.

---

## 6. Acceptance checklist

An implementation matches this design when:

- [ ] Ashoka light + dark match §2.1; dark uses elevation + hairline + inset top-highlight (no muddy navy tint).
- [ ] Inter (UI), Fraunces (display/headings/wordmark), Geist Mono (refs/counts) load and render; 4K-crisp, fine on phones.
- [ ] Chat column is centered `min(72ch,100%)`; not full-bleed on wide screens.
- [ ] Inline progress shows concise by default with a working Detailed toggle; debug never reaches non-admins.
- [ ] Answer streams (replay) with structured sections; `[n]` + **Law says** vs **Your document says** are visually distinct.
- [ ] Clicking a citation opens the document viewer with the quoted span highlighted.
- [ ] Doc viewer opens 50/50 and is drag-resizable on desktop; full-screen overlay on mobile.
- [ ] Attaching a document appears as an **in-thread system pill** (plus session chips); uploads require explicit attach.
- [ ] Documents page shows the Uploaded→Parsed→Chunking→Embedding→Ready pipeline.
- [ ] Settings + Login/Signup/Logout match the demo; appearance/language controls drive global state.
- [ ] Refusal and clarifying-question states are implemented.
- [ ] Hindi: full UI localizes, Devanagari sized/led per §2.3, no letter-spacing on conjuncts.
- [ ] Mobile shell (app bar + bottom tabs) and desktop shell both verified.
- [ ] All motion respects `prefers-reduced-motion`; AA contrast and visible focus throughout.

---

*Finalized for v0.3. Questions or proposed changes to the system should update `tokens.json` + this README + the demo
together so the three never drift.*
