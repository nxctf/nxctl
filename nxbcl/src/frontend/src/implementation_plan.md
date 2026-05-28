# NXBCL Launcher — Premium UI Refactor

Redesign the NXBCL Launcher frontend from its current text-heavy, cramped layout into a clean, premium infrastructure-style dashboard inspired by **Vercel**, **Railway**, and **Cloudflare**.

## Problem Analysis

The current UI has these issues:
- **Too much text** — verbose labels like "Active Challenge Registry", "POLLING CONTAINER STATE...", "SYSTEM INTEGRITY: SECURE"
- **Cluttered layout** — small font sizes (9px–10px), overly-uppercase labels everywhere, no visual breathing room
- **Too many borders/cards** — nesting borders-within-borders creates visual noise
- **Inconsistent hierarchy** — everything screams for attention equally (uppercase, bold, monospace)
- **Footer is filler** — "SYSTEM INTEGRITY: SECURE" adds nothing
- **Sidebar is sparse but noisy** — mixes navigation with hardcoded metadata that has no value to the user (DB ENGINE, WORKSPACE)

## Design Philosophy

Drawing from Vercel/Railway/Cloudflare patterns:

| Principle | What it means |
|---|---|
| **Less is more** | Fewer labels, larger whitespace, let data breathe |
| **Hierarchy through spacing** | Use size + space instead of uppercase/bold everywhere |
| **Muted until active** | Default state is calm; active/danger states pop |
| **Progressive disclosure** | Show details on demand (hover, expand), not all at once |
| **Functional typography** | 13–14px body, 11–12px labels. Kill the 9px text. |

---

## Proposed Changes

### Design System

#### [MODIFY] [styles.css](file:///e:/9_org/nxctf/nxctl/nxbcl/frontend/src/styles.css)

- Refine color palette: slightly lighter surfaces for better depth perception (avoid pure `#020617`)
- Add Google Fonts import (Inter + JetBrains Mono) to `index.html`
- Increase minimum font sizes — kill all `text-[9px]` and `text-[10px]`, use `text-xs` (12px) minimum
- Add subtle hover-lift transition utility
- Add a smooth `slide-in` animation for sidebar transitions
- Add subtle glow utility for active states

---

### Shell / Layout

#### [MODIFY] [App.vue](file:///e:/9_org/nxctf/nxctl/nxbcl/frontend/src/App.vue)

**Sidebar redesign:**
- Remove "Registry" section (WORKSPACE, DB ENGINE) — adds zero user value
- Clean brand header: simpler, less gradient, more like Vercel's wordmark style
- Navigation items: larger hit targets (py-2.5 → py-3), proper 14px text size
- RPC node status in sidebar: cleaner card with subtle dot indicator, no border-in-border
- API indicator at bottom: simpler, less verbose
- Remove version number (or make it hover-only)

**Top header redesign:**
- Simplify breadcrumb — just page title, no "Infrastructure /" prefix
- RPC dropdown: maintain functionality, clean up padding and typography
- Add subtle bottom-shadow instead of hard border

**Footer:**
- Remove "SYSTEM INTEGRITY: SECURE" filler
- Either remove footer entirely or reduce to single-line version text

**Overall:**
- All logic (`ref`, `onMounted`, handlers) preserved exactly as-is
- Only template + class changes

---

### Challenge List Page

#### [MODIFY] [ChallengeList.vue](file:///e:/9_org/nxctf/nxctl/nxbcl/frontend/src/views/ChallengeList.vue)

- Simpler page header: "Challenges" as clean h1, count badge to the right, subtitle removed or shortened
- Challenge cards: 
  - Less uppercase text, larger titles (text-sm instead of text-xs)
  - Better whitespace inside cards (p-5 → p-6)
  - Category badge: pill-style, muted color until hover
  - Remove "Deploy Instance" text — the whole card is clickable, arrow is enough
  - Description: slightly larger text, better line height
- Loading state: simpler spinner without verbose "POLLING CONTAINER STATE..."
- Empty state: cleaner, less verbose
- Error state: cleaner alert without emoji

---

### Challenge Launcher Page

#### [MODIFY] [ChallengeLauncher.vue](file:///e:/9_org/nxctf/nxctl/nxbcl/frontend/src/views/ChallengeLauncher.vue)

- **Hero section**: Keep title + category + description + specs. Clean up typography sizes. Remove redundant "ID:" prefix text — show ID in breadcrumb instead
- **Controls column**: 
  - Cleaner button styles — remove emoji prefixes (⚡, ✔️, 📋, ➕, 🔄)
  - Use Tailwind SVG icons or simple text instead
  - Group primary vs secondary actions more clearly
  - Better disabled states
- **Terminal panel**: 
  - Keep the real-time log functionality
  - Remove "TTY: ACTIVE" chrome — just show clean log output
  - Remove the purple pulse animation on the entire container
  - Better monospace rendering
- **Instance data grid**: 
  - Clean label typography (remove uppercase tracking-widest pattern)
  - Use inline labels next to values instead of stacked
  - Larger copy buttons with better hover
- **Solver env block**: Keep as-is, just clean up label typography

---

### Components

#### [MODIFY] [CopyField.vue](file:///e:/9_org/nxctf/nxctl/nxbcl/frontend/src/components/CopyField.vue)

- Remove the label from inside this component (labels should be in parent)
- Slightly larger text (text-xs → text-sm for values)
- Better copy button with tooltip feedback

#### [MODIFY] [index.html](file:///e:/9_org/nxctf/nxctl/nxbcl/frontend/index.html)

- Add Google Fonts link for Inter and JetBrains Mono
- Add proper meta description

---

## What Will NOT Change

- All `<script setup>` logic in every file — zero modifications
- API calls, types, router, pow solver
- Event handlers (launch, handleCheck, handleExtend, etc.)
- State management (refs, computed properties)
- RPC control dropdown behavior
- Terminal log functionality
- Copy-to-clipboard functionality

---

## Verification Plan

### Manual Verification
- Run `npm run dev` and visually verify:
  1. Challenges list loads and cards render cleanly
  2. Challenge detail page loads with hero, controls, and terminal
  3. RPC dropdown opens/closes
  4. Copy buttons work
  5. All navigation works
  6. Responsive layout at mobile/tablet widths
- Build check: `npm run build` succeeds without errors
