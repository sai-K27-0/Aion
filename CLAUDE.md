# Aion - Claude Code Instructions

This file documents the plan for optimizing the GUI, improving UI/UX, and fixing bugs in the Aion desktop application.

## Project Overview

Aion is a Tauri desktop app (transparent overlay) with:
- `desktop/src/main.js` — 4337-line core JS app
- `desktop/index.html` — 51KB single-page HTML
- `desktop/src/styles/overlay.css` — Main styles (~1300 lines)
- `desktop/src/styles/main.css` — Glassmorphism chat styles
- `desktop/src/styles/calendar.css` — Calendar styles

## Bug Fixes

### CRITICAL Bug 1: `showToast` is undefined
`showToast()` called at lines 3964, 3966, 3970, 3975, 4251, 4310 but never defined.
Only `toast()` exists. Crashes on update check / sync / data reload.
**Fix:** Add alias `const showToast = toast;` after `toast()` definition (line 289).

### CRITICAL Bug 2: `renderMindMap` vs `renderMindmap` case mismatch
Line 4308 calls `renderMindMap()` (capital M) but function is `renderMindmap()` (lowercase m, line 2510).
Crashes when server sync pulls data.
**Fix:** Change `renderMindMap()` to `renderMindmap()` on line 4308.

### CRITICAL Bug 3: Backtick shortcut fires in text inputs
Lines 4077-4087: backtick/~ handler runs BEFORE the `isInput` check.
Typing backtick in any input field minimizes the app to tray.
**Fix:** Add `if (isInput) return;` guard before the backtick handler.

### CRITICAL Bug 4: `sendAiQuery` has no error handling
Lines 395-417: `await processAiCommand(text)` not wrapped in try-catch.
If it throws, the loading spinner stays forever.
**Fix:** Wrap in try-catch, hide spinner and show error message on failure.

### Bug 5: Audio player uses polling instead of onended event
audio_player.js lines 49-58: 100ms setInterval polls for playback end.
**Fix:** Use `source.onended` Web Audio API event instead.

### Bug 6: Duplicate online/offline listeners
main.js lines 4202-4203 adds listeners that duplicate SyncService's own (sync.js:30-31).
**Fix:** Remove the duplicate listeners from initOfflineSync().

## UI/UX Improvements

1. **AI response text overflow** — Add `overflow-wrap: break-word` to `#ai-response`
2. **Scrollbar visibility** — Increase thumb opacity from 0.2 to 0.3 (hover: 0.5)
3. **Chat textarea auto-grow** — Add JS auto-resize on input event
4. **Context menu viewport bounds** — Clamp position to window dimensions
5. **Timer display text shifting** — Add `font-variant-numeric: tabular-nums`
6. **Calendar grid responsive** — Change 60px to `clamp(40px, 8vw, 60px)`
7. **Remove dead orbit.css** — 780-line unreferenced legacy stylesheet

## Performance Optimizations

1. **Debounce save()** — 300ms debounce on block title/notes input listeners
2. **Throttle renderConnections** — Use requestAnimationFrame during drag
3. **Remove duplicate event listeners** — Online/offline registered twice
