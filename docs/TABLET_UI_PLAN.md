# Android tablet UI plan – touch-first design

This doc asks questions and outlines ideas so we can shape the Tab S10 FE+ experience before changing code.

## Implemented (from your answers: mix, mostly landscape, everything, same as desktop, two-handed, everything in the orb)

- **Orb hub:** First rail destination is “Orb” – grid of 8 large tiles (Tasks, Mind Map, Pomodoro, Stats, Habits, Calendar, AI Chat, Settings). Same entry points as desktop radial menu.
- **Extended rail:** 9 destinations, extended rail (140dp), larger icons (26px), haptic on destination tap.
- **Quick capture FAB:** Opens bottom sheet with New task, New note, Voice note (placeholder). Navigates to Tasks or Mind Map when chosen.
- **Touch-friendly lists:** Task tiles min height 56dp, 32px checkbox; pull-to-refresh on Tasks (including empty state) and Mind Map block tree. Block tree rows min 52dp, 28px expand icon, 16pt text, selection haptic.
- **Split view:** Mind Map keeps master-detail on wide screens; sync indicator in rail trailing.
- **Placeholders:** Pomodoro, Statistics, Habits views (match desktop; wired to rail).
- **Forms:** Settings uses full-width list tiles with larger padding and 26px icons. Future edit forms should use full-width fields and a sticky “Save” bar at bottom.

---

## Questions for you

### 1. Primary use on the Tab

- **A)** Mostly **tasks, to-dos, quick notes** (quick capture, check off, minimal editing)
- **B)** **View and sync** – see what you created on PC, light edits
- **C)** **Full work** – blocks, mind map, chat, calendar, same scope as desktop
- **D)** **Mixed** – different use in different situations (e.g. tasks in portrait, mind map in landscape)

Your answer will drive whether we simplify the tablet UI or keep feature parity with desktop.

---

### 2. Orientation

- **A)** Mostly **landscape** (horizontal) – e.g. on a desk or stand
- **B)** Mostly **portrait** (vertical) – held in hand
- **C)** **Both** – you switch often

This affects navigation (rail vs bottom bar), list vs grid layouts, and split vs single pane.

---

### 3. Input preference

- **A)** **Touch only** – tap, swipe, long-press; minimal typing
- **B)** **Keyboard often** – on-screen or physical; longer text entry
- **C)** **Voice matters** – dictation / voice commands for notes and tasks

We can prioritize big tap targets and gestures, or make room for keyboard and voice.

---

### 4. Relationship to desktop

- **A)** **Same data, different UI** – tablet UI rethought for touch (different layout/navigation, same features)
- **B)** **Simplified** – fewer features, focused on tasks/notes/sync
- **C)** **Parallel to desktop** – as close to desktop as possible, mainly bigger touch targets

This sets the bar for how much we redesign vs adapt.

---

### 5. One-handed vs two-handed

- Do you often use the Tab **one-handed** (e.g. walking) or **two-handed** (e.g. on lap/desk)?

One-handed use suggests: bottom or thumb-zone actions, fewer top-right controls, swipe navigation.

---

### 6. Must-have on Tab

What **must** work well on the Tab from day one?

Examples: quick add task, view today’s list, sync status, open a block, AI chat, calendar view.  
List your top 3–5 and we can design around them.

---

## Ideas for a touch-stream tablet UI

### Navigation

- **Tablet (e.g. 10"+):** Keep a **side rail** (like now) but make it **wider and easier to tap** (e.g. 72–80 dp), with optional labels. Consider a **collapsible rail** (icon-only → expand) to free space.
- **Portrait:** Switch to a **bottom nav bar** (like phone) so thumb can reach everything; or a **bottom sheet** that slides up with main sections.
- **Gesture:** **Swipe from left edge** to open/close the rail or main menu so power users don’t need to tap a hamburger.

### Lists and cards

- **Touch-friendly rows:** Min height ~48–56 dp per row; padding so taps don’t feel cramped.
- **Cards** for tasks/blocks: **Swipe left** = complete (or archive), **Swipe right** = pin or open. **Long-press** = context menu (edit, delete, move).
- **Pull-to-refresh** on main lists (you have sync; this fits “refresh” mentally).
- **Infinite scroll or “Load more”** instead of tiny scrollbars; avoid precision scrolling.

### Mind map / blocks on tablet

- **Pinch-zoom and pan** for the mind map canvas (touch-first).
- **Tap a node** to select; **double-tap** to edit title inline or open detail.
- **Drag nodes** to reorder or reparent; **long-press** to add child or open menu.
- On smaller tablets, consider a **list view of blocks** with expand/collapse instead of a full canvas.

### Quick capture

- **FAB (Floating Action Button)** or a **persistent “+”** in a thumb-friendly zone (e.g. bottom-right) for “Add task” or “New note”.
- **Tap FAB** → bottom sheet or small dialog: “Task”, “Note”, “Quick note” with **large buttons** and optional voice.
- Optional: **widget or shortcut** that opens the app straight into “Add task” or “Add note”.

### Forms and editing

- **One column** on tablet for forms (no cramped side-by-side); **full-width** fields.
- **Large tap targets** for checkboxes, chips, and buttons (min 44–48 dp).
- **Sticky “Save” / “Done”** at bottom so it’s always reachable after scrolling.
- **Optional voice:** Mic button next to text fields for dictation.

### Split view (existing idea, refined)

- **Master–detail:** List on left (e.g. tasks or blocks), detail on right. **Tap row** = show detail in right pane (no new screen).
- **Resizable divider** (drag) so you can favor list or detail.
- In **portrait**, show either list or detail; **tap back** or swipe to switch (no tiny split).

### Sync and status

- **Sync indicator** always visible (e.g. in app bar or rail) – icon + “Synced” / “Syncing…” / “Offline”.
- **Tap indicator** → brief toast or bottom sheet: “Last synced 2 min ago” and **“Sync now”** button.
- Optional: **Banner** when offline: “You’re offline. Changes will sync when back online.”

### Theming and density

- **Support system font size** (accessibility); avoid fixed small text.
- **Optional “Tablet density”** in settings: slightly larger text and spacing for arm’s-length use.
- Reuse your **dark theme**; ensure contrast for touch targets (focus states).

### Performance and feel

- **Skeleton loaders** or placeholders while data loads so the UI doesn’t jump.
- **Haptic feedback** (light tap) on key actions (complete task, open panel) so touch feels responsive.
- **Animations** short and subtle (e.g. 200–300 ms) so the app feels smooth, not slow.

---

## Suggested next steps (after you answer)

1. **Lock in** your answers to the questions above (and any extra “must-haves”).
2. **Prioritize** which ideas to implement first (e.g. navigation + quick capture + task list).
3. **Define** a small set of tablet-specific screens/flows (e.g. “Tablet task list”, “Tablet block list”, “Quick add”).
4. **Implement** in the existing Flutter app (reuse `TabletHomeScreen` and add new layouts/components as needed).

---

## Current state (for reference)

- **Router:** `shortestSide >= 600` → tablet gets `TabletHomeScreen`, else phone gets `HomeScreen`.
- **Tablet UI today:** `TabletHomeScreen` with `NavigationRail` (Dashboard, Tasks, Mind Map, Calendar, Chat, Settings), sync indicator, and content areas. Layout is a starting point; we can evolve it for touch and orientation.

Once you answer the questions and pick which ideas you want first, we can turn this into a concrete implementation plan (screens, components, and tasks) and then execute.
