# Frontend Changes — Theme Toggle Button

Added a light/dark theme toggle to the Course Materials Assistant UI.

## Summary

A circular, icon-based toggle button now sits in the top-right corner of the
app. It switches between the existing dark theme and a new light theme, animates
smoothly between the two, persists the user's choice, and is fully keyboard
accessible.

## Files changed

### `frontend/index.html`
- Added a no-flash inline script in `<head>` that reads the saved theme from
  `localStorage` and sets `data-theme="light"` on `<html>` **before first paint**,
  so a returning light-mode user never sees a dark flash.
- Added the toggle button markup just inside `.container`:
  - A `<button id="themeToggle" class="theme-toggle">` positioned top-right.
  - Contains two inline SVGs — a **sun** icon and a **moon** icon — that
    cross-fade based on the active theme.
  - Accessibility: `type="button"`, `aria-label` (updated dynamically),
    `aria-pressed` state, and a `title` tooltip. SVGs are `aria-hidden="true"`.
- Bumped cache-busting query strings: `style.css?v=11 → v=12`,
  `script.js?v=9 → v=10`.

### `frontend/style.css`
- **Light theme variables:** Renamed the default `:root` block to "dark theme
  (default)" and added a `:root[data-theme="light"]` block overriding all color
  variables (background, surface, text, borders, shadow, focus ring, welcome
  colors) with light-mode values.
- **New `--code-bg` variable:** Replaced the two hard-coded
  `rgba(0,0,0,0.2)` code/`pre` backgrounds with `var(--code-bg)` so inline code
  and code blocks remain readable in light mode.
- **Smooth theme transition:** Added a shared
  `transition: background-color/color/border-color 0.3s ease` to all the
  color-bearing surfaces (body, sidebar, chat areas, inputs, messages, chips,
  buttons) so switching themes animates instead of snapping.
- **Toggle button styles:** Circular 44×44 button using the theme variables
  (`--surface`, `--border-color`, `--shadow`), with hover (lift + accent
  border), active, and `:focus-visible` (accent focus ring) states.
- **Animated icons:** Sun/moon SVGs are absolutely stacked and transition
  opacity + rotation/scale. Dark theme shows the moon; light theme
  (`:root[data-theme="light"]`) shows the sun — each icon rotates and scales as
  it fades in/out.
- **Reduced motion:** A `@media (prefers-reduced-motion: reduce)` block disables
  these transitions for users who request it.

### `frontend/script.js`
- Added `themeToggle` to the cached DOM element list.
- `initTheme()` runs on `DOMContentLoaded`, reading `localStorage` and applying
  the saved theme (defaults to dark).
- `applyTheme(theme)` toggles the `data-theme` attribute on `<html>` and keeps
  the button's `aria-pressed` and `aria-label` in sync with the current state.
- `toggleTheme()` flips the theme, persists the choice to `localStorage`, and
  re-applies it. Wired to the button's `click` event in `setupEventListeners()`.
- All `localStorage` access is wrapped in `try/catch` to stay functional where
  storage is unavailable.

## Design notes

- **Fits the existing aesthetic:** reuses the same CSS variables, border-radius,
  focus-ring, and hover-lift patterns already used by the send/new-chat buttons.
- **Icon-based:** sun (light) / moon (dark) line icons matching the existing
  stroke-based SVG style of the send button.
- **Smooth animation:** icons cross-fade with rotation/scale; the whole UI
  transitions its colors over 0.3s.
- **Accessible & keyboard navigable:** it's a native `<button>`, so it's in the
  tab order and Enter/Space activate it. Screen readers get a descriptive,
  state-aware `aria-label` plus `aria-pressed`; focus is clearly visible.
