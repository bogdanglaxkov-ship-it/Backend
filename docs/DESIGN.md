---
name: TenderAI Design System
source: Stitch project 15198750396004684153 — "TenderAI Procurement Dashboard"
exported: 2026-07-07
screens: 7 (6 UI screens + 1 design-system reference instance)
---

# TenderAI Design System

Exported from Stitch project `15198750396004684153`. The project contains **7 instances** total: **6 functional UI screens** and **1 design-system reference instance** (a canvas artifact that documents the tokens below, not a product screen).

> **Note — two theme variants exist in this project.** The project's *active* theme (used to render the 6 screens) is a **dark mint/teal** palette (primary `#46F6BB` / `#00D9A0`). A separate saved design-system asset in the same project (`assets/820c54fc78284c0c9f64d9daf7efb170`, v2) documents an **earlier dark slate/grey** variant (primary `#707775`, pure black `#000000` base). Both are documented below; **treat the mint/teal variant as canonical** since it's what the live screens use.

## Brand & Style

"Precision Minimalism" — a high-stakes professional tool where clarity, speed of information processing, and technical reliability are paramount. Strictly flat: no shadows, no gradients, no blur/transparency. Depth comes from tonal layering and 1px borders only ("blueprint" feel). Emotional target: calm focus and surgical precision, letting dense procurement data and AI insights take center stage.

## Screens (7 instances)

| # | Title (RU) | English | Type | Size |
|---|---|---|---|---|
| 1 | Мои лоты | My Lots | UI screen | 2560×2048 |
| 2 | AI чат | AI Chat | UI screen | 2560×2048 |
| 3 | Лоты | Lots | UI screen | 2560×2048 |
| 4 | Регионы | Regions | UI screen | 2560×2048 |
| 5 | Анализ заказчика | Customer Analysis | UI screen | 2560×2048 |
| 6 | Обзор рынка | Market Overview | UI screen | 2560×2048 |
| 7 | *(design-system instance)* | Design System Reference | Non-UI asset | 960×540 |

All 6 UI screens share one global sidebar navigation: Dashboard, Tenders, Analytics, Contracts, Compliance, Settings, plus Support/Logout — confirmed from screen content (dark mode toggle, notifications, admin avatar, "Add New Tender" primary action, search + filters, status-column layout: Корзина / В анализе / В работе / Завершено / Архив).

---

## Colors — Active Theme (mint/teal, canonical)

| Token | Hex | Usage |
|---|---|---|
| `primary` | `#46F6BB` | Primary actions, active states |
| `primary-container` | `#00D9A0` | Success states, active progress, primary buttons |
| `on-primary` | `#003827` | Text on primary |
| `on-primary-container` | `#005940` | Text on primary-container |
| `secondary` | `#FFB955` | Warnings, pending / mid-priority items ("Amber") |
| `secondary-container` | `#DC9100` | |
| `on-secondary` | `#452B00` | |
| `tertiary` | `#D5D9FF` | Data highlights, links, neutral info ("Info blue" family) |
| `tertiary-container` | `#B1BBFF` | |
| `error` | `#FFB4AB` | Deadlines, risk, destructive actions |
| `error-container` | `#93000A` | |
| `background` / `surface` | `#0D1511` | Base canvas |
| `surface-dim` | `#0D1511` | |
| `surface-bright` | `#333B36` | |
| `surface-container-lowest` | `#08100C` | Deepest recess |
| `surface-container-low` | `#151D19` | |
| `surface-container` | `#19211D` | Default card/container |
| `surface-container-high` | `#242C27` | |
| `surface-container-highest` | `#2E3732` | |
| `on-surface` | `#DCE5DE` | Primary text |
| `on-surface-variant` | `#BACAC0` | Secondary/muted text |
| `outline` | `#85948B` | Emphasized borders |
| `outline-variant` | `#3B4A42` | Standard 1px borders / dividers |
| `inverse-surface` | `#DCE5DE` | |
| `inverse-on-surface` | `#2A322E` | |
| `inverse-primary` | `#006C4E` | |

**Functional accent semantics:**
- **Primary — Mint `#00D9A0`**: success, active progress, primary buttons. Signifies growth/health.
- **Secondary — Amber `#F5A623`/`#FFB955`**: warnings, pending, mid-priority.
- **Critical — Red `#E5484D`** (error family `#FFB4AB`/`#93000A`): deadlines, risk, destructive actions.
- **Info — Blue `#4F6BFF`** (tertiary family `#D5D9FF`/`#B1BBFF`): data highlights, links, neutral callouts.
- **Neutrals**: background hierarchy runs from deepest `#08100C` → cards `#19211D`/`#151D19` → sidebar-level surfaces, replacing shadows with tonal steps.

### Colors — Saved Design-System Asset (slate/grey variant, v2)

| Token | Hex | Usage |
|---|---|---|
| `primary` | `#C1C8C5` | |
| `primary-container` | `#707775` | "Slate" — structural actions, active nav, primary buttons |
| `secondary` / `secondary-container` | `#FFB955` / `#DC9100` | Amber — same semantic as canonical |
| `tertiary` | `#C6C6C7` (base white `#FFFFFF` per style guide) | High-contrast highlights |
| `error` / `error-container` | `#FFB4AB` / `#93000A` | Same as canonical |
| `background` / `surface` | `#131313` (style guide references pure `#000000` base) | |
| `surface-container` | `#1F1F1F` | Cards |
| `surface-container-low` | `#1B1B1B` | Sidebar |
| `outline-variant` | `#434846` (style guide: `#1F1F1F` border) | |
| `on-surface` | `#E2E2E2` | |

---

## Typography

Font family: **Inter** throughout (headline, body, and label all use Inter).

| Style | Size | Weight | Line height | Letter spacing |
|---|---|---|---|---|
| `headline-xl` | 32px | 600 | 40px | -0.02em |
| `headline-lg` | 24px | 600 | 32px | -0.01em |
| `headline-md` | 20px | 500 | 28px | — |
| `body-lg` | 16px | 400 | 24px | — |
| `body-md` | 14px | 400 | 20px | — |
| `label-sm` | 12px | 700 | 16px | 0.05em |

- **Headers**: pure white / `on-surface`, tight letter-spacing, dense professional look.
- **Body text**: muted grey (`on-surface-variant` / `#9CA3AF`-ish) so primary data points stand out.
- **Labels**: uppercase small-caps for metadata, category headers, form labels — visually separates "system instructions" from "user data."
- **Mobile scaling**: headline sizes scale down ~15% on mobile; body text stays fixed at 14–16px for legibility.

## Layout & Spacing

- Base unit: **4px**; all spacing is a multiple of this.
- Container padding: **24px**; gutter: **16px**; stack gap (vertical rhythm between blocks): **12px**.
- **Desktop**: 12-column fluid grid, 16px gutters, 24px fixed margins.
- **Sidebar**: fixed **260px** width, persistent navigation anchor, distinct surface level from content.
- **Mobile**: grid collapses to 1 column; sidebar becomes a bottom nav bar or full-screen overlay.

## Shape / Radius

| Token | Value |
|---|---|
| `radius-sm` | 0.25rem (4px) |
| `radius-DEFAULT` | 0.5rem (8px) |
| `radius-md` | 0.75rem (12px) |
| `radius-lg` | 1rem (16px) |
| `radius-xl` | 1.5rem (24px) |
| `radius-full` | 9999px (pills/avatars) |

Standard containers (cards, buttons, inputs) use a **~10px radius** in the canonical theme (0.5rem/8px `DEFAULT` in the token scale — style guide text says 10px, token value says 8px; treat 8px as the literal token, 10px as the rounded style-guide description of the same family). Tags/badges reuse the same radius for a unified language.

## Elevation & Depth

No shadows, blurs, or transparency anywhere — depth = tonal layering + 1px outline borders only.

| Level | Canonical (mint) | Slate variant | Role |
|---|---|---|---|
| 0 — Base | `#0D1511` (style guide ref: `#0A0A0A`) | `#131313` (style guide ref: `#000000`) | Primary canvas |
| 1 — Nav/Sidebar | `#151D19` (style guide ref: `#161616`) | `#1B1B1B` | Global controls |
| 2 — Containers/Cards | `#19211D` (style guide ref: `#121212`) | `#1F1F1F` | Data grouping, interactive modules |
| Borders | `outline-variant` (style guide ref: `#1F1F1F`) | systematic border token | 1px solid on every interactive/containing element |

- **Active/selected state**: 2px stroke of the primary accent color (no shape change, no shadow).
- **Dividers**: 1px lines using the border/outline-variant color.

## Components

- **Buttons**
  - Primary: solid primary-container color (mint `#00D9A0` / slate `#707775`) with contrasting text (black in mint variant, white in slate variant).
  - Secondary: ghost style, 1px `outline-variant` border, `on-surface` text.
  - No hover-lift; hover state = 10% opacity white overlay.
- **Cards**: `surface-container` background, 1px `outline-variant` border, ~8–10px radius. Header area separated from body by a 1px horizontal divider.
- **Input fields**: base-canvas background, 1px `outline-variant` border. On focus, border switches to the Info/tertiary blue (`#4F6BFF`) in the canonical theme, or white/slate in the alt variant.
- **Chips / badges**: background at 10% opacity of the accent color, solid 1px border of the same accent color, uppercase small-caps text (`label-sm`).
- **Lists**: rows separated by 1px borders; active/selected row gets a left-edge 4px accent border.
- **Data visuals (charts)**: use primary, secondary, and tertiary/info colors exclusively against the `surface-container` card background; gridlines match the border color exactly — no extra chart-specific palette.
- **Navigation sidebar** (observed across all 6 screens): fixed-width, icon+label items — Dashboard, Tenders, Analytics, Contracts, Compliance, Settings — with Support/Logout pinned separately.
- **Header bar** (observed): dark-mode toggle, notification bell, admin avatar, primary "Add New Tender" CTA button.
- **Status-column board** (observed on lot-listing screens): named columns — Корзина (Cart) / В анализе (Under Analysis) / В работе (In Progress) / Завершено (Completed) / Архив (Archive) — each card shows ID, title, price (₽), НМЦК label, company logo, and an AI-scoring badge; drag targets present ("Перетащите сюда").
