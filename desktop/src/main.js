/**
 * AION - Complete Productivity App
 * Features: Mind Map, Tasks, Pomodoro, Habits, Calendar, Stats, AI Chat
 * With Offline-First Multi-Device Sync
 */

import { initLocalDb, getLocalDb } from './services/local_db.js';
import { initSyncService, getSyncService } from './services/sync.js';

const CONFIG = {
  // Default API URL - can be overridden by user settings
  get API_BASE() {
    // Check localStorage for custom server URL first
    const customUrl = localStorage.getItem('aion_server_url');
    if (customUrl) {
      return customUrl;
    }
    return 'http://localhost:8000/api/v1';
  },
  get API_BASE_SETTABLE() {
    // For setting the URL programmatically
    return localStorage.getItem('aion_server_url') || 'http://localhost:8000/api/v1';
  },
  set API_BASE_SETTABLE(value) {
    if (value) {
      localStorage.setItem('aion_server_url', value);
    } else {
      localStorage.removeItem('aion_server_url');
    }
  },
  STORAGE_KEY: 'aion_complete_v1',
};

// Sync state
let syncService = null;
let localDb = null;
let isOnline = navigator.onLine;

const STATUSES = {
  not_started: { label: 'Not Started', color: '#a78bfa' },
  in_progress: { label: 'In Progress', color: '#fbbf24' },
  on_hold: { label: 'On Hold', color: '#fb923c' },
  completed: { label: 'Completed', color: '#34d399' },
};

const ICONS = ['📝', '✅', '📁', '💡', '⭐', '❤️', '💻', '📚', '🎯', '📅', '⏰', '🚀', '🔥', '💪', '🧠', '🎨', '🔧', '📊'];

// ============================================================================
// State
// ============================================================================

const state = {
  menuOpen: false,
  aiInputOpen: false,
  focusMinimized: false,
  focusSection: 'calendar',  // calendar, todos
  focusTimerExpanded: false,
  orbCentered: false,
  orbClickTimer: null,
  openSections: { timer: false, calendar: true, todos: false },
  miniCalDate: new Date(),
  // Multi-panel system
  openPanels: new Set(),  // Track which panels are open
  panelPositions: {},     // Store panel positions { panelId: { x, y } }
  draggingPanel: null,    // Currently dragging panel
  dragPanelOffset: { x: 0, y: 0 },
  allPanelsHidden: false, // Master toggle for hiding all
  profiles: [],
  currentProfile: null,
  currentFocus: null,
  theme: 'sky',
  blocks: [],
  currentBlock: null,
  newBlockParent: null,
  contextBlock: null,
  contextTask: null,  // Currently right-clicked task { task, blockId }
  dragging: null,
  dragOffset: { x: 0, y: 0 },
  calendarDate: new Date(),
  selectedDate: null,
  calendarTasks: [],
  taskFilter: 'all',
  taskSort: 'block',  // Sort by: block, priority, status, date, created
  taskSearchQuery: '',  // Search within tasks panel
  selectedTasks: [],  // For bulk operations: [{taskId, blockId}]
  habits: [],
  habitDate: new Date(),
  habitChecks: {},
  stats: { completed: 0, pomodoros: 0, focusMinutes: 0, streak: 0, daily: {} },
  timer: { running: false, seconds: 0, interval: null },
  pomodoro: {
    mode: 'work',
    running: false,
    seconds: 25 * 60,
    interval: null,
    sessions: 0,
    totalMinutes: 0,
    workDuration: 25,
    shortBreak: 5,
    longBreak: 15,
    currentTask: '',
  },
  searchQuery: '',
};

// ============================================================================
// Persistence
// ============================================================================

function load() {
  try {
    const data = JSON.parse(localStorage.getItem(CONFIG.STORAGE_KEY) || '{}');
    state.profiles = data.profiles?.length ? data.profiles : [{ id: '1', name: 'Default' }];
    state.currentProfile = data.currentProfile || state.profiles[0];
    state.currentFocus = data.currentFocus || null;
    state.theme = data.theme || 'sky';
    state.blocks = data.blocks?.length ? data.blocks : defaultBlocks();
    state.calendarTasks = data.calendarTasks || [];
    state.habits = data.habits || [];
    state.habitChecks = data.habitChecks || {};
    state.stats = data.stats || { completed: 0, pomodoros: 0, focusMinutes: 0, streak: 0, daily: {} };
    state.pomodoro.workDuration = data.pomodoroSettings?.work || 25;
    state.pomodoro.shortBreak = data.pomodoroSettings?.short || 5;
    state.pomodoro.longBreak = data.pomodoroSettings?.long || 15;
  } catch (e) {
    console.error('Load error:', e);
    state.profiles = [{ id: '1', name: 'Default' }];
    state.currentProfile = state.profiles[0];
    state.blocks = defaultBlocks();
  }
}

function save() {
  localStorage.setItem(CONFIG.STORAGE_KEY, JSON.stringify({
    profiles: state.profiles,
    currentProfile: state.currentProfile,
    currentFocus: state.currentFocus,
    theme: state.theme,
    blocks: state.blocks,
    calendarTasks: state.calendarTasks,
    habits: state.habits,
    habitChecks: state.habitChecks,
    stats: state.stats,
    pomodoroSettings: { work: state.pomodoro.workDuration, short: state.pomodoro.shortBreak, long: state.pomodoro.longBreak },
  }));
}

function defaultBlocks() {
  return [
    { id: 'root', name: 'My Projects', type: 'project', icon: '📁', notes: 'Welcome to Aion! Right-click blocks for options.', todos: [], dateStart: '', dateEnd: '', x: 60, y: 60, children: ['work', 'personal'] },
    { id: 'work', name: 'Work', type: 'task', icon: '💼', notes: '', todos: [{ id: 't1', text: 'Complete project', status: 'in_progress', priority: 'high', date: '', tags: ['urgent'] }], dateStart: '', dateEnd: '', x: 280, y: 30, parentId: 'root', children: [] },
    { id: 'personal', name: 'Personal', type: 'idea', icon: '🌟', notes: '', todos: [{ id: 't2', text: 'Learn something new', status: 'not_started', priority: 'medium', date: '', tags: ['growth'] }], dateStart: '', dateEnd: '', x: 280, y: 140, parentId: 'root', children: [] },
  ];
}

// ============================================================================
// Elements
// ============================================================================

const $ = id => document.getElementById(id);
let els = {};

function initEls() {
  els = {
    orb: $('orb'), radialMenu: $('radial-menu'),
    btnMindmap: $('btn-mindmap'), btnTasks: $('btn-tasks'), btnPomodoro: $('btn-pomodoro'),
    btnStats: $('btn-stats'), btnHabits: $('btn-habits'), btnCalendar: $('btn-calendar'),
    btnChat: $('btn-chat'), btnSettings: $('btn-settings'),
    profileBadge: $('profile-badge'), profileNameBadge: $('profile-name-badge'),
    profileDropdown: $('profile-dropdown'), profileList: $('profile-list'), btnNewProfile: $('btn-new-profile'),
    searchBar: $('search-bar'), searchInput: $('search-input'), searchResults: $('search-results'),
    focusPanel: $('focus-panel'), focusTextDisplay: $('focus-text-display'), focusInput: $('focus-input'),
    miniTimer: $('mini-timer'), miniStart: $('focus-timer-start'), miniPause: $('focus-timer-pause'), miniReset: $('focus-timer-reset'),
    todayTasksDone: $('today-tasks-done'), todayTasksTotal: $('today-tasks-total'), progressFill: $('progress-fill'),
    btnQuickTask: $('btn-quick-task'), btnQuickSearch: $('btn-quick-search'), btnQuickHelp: $('btn-quick-help'),
    pomodoroPanel: $('pomodoro-panel'), btnClosePomodoro: $('btn-close-pomodoro'),
    pomoTime: $('pomo-time'), pomoProgress: $('pomo-progress'),
    pomoStart: $('pomo-start'), pomoPause: $('pomo-pause'), pomoReset: $('pomo-reset'),
    pomoSessions: $('pomo-sessions'), pomoTotalTime: $('pomo-total-time'), pomoTaskSelect: $('pomo-task-select'),
    statsPanel: $('stats-panel'), btnCloseStats: $('btn-close-stats'),
    statCompleted: $('stat-completed'), statPomodoros: $('stat-pomodoros'),
    statFocusTime: $('stat-focus-time'), statStreak: $('stat-streak'), activityChart: $('activity-chart'),
    habitsPanel: $('habits-panel'), btnCloseHabits: $('btn-close-habits'), btnAddHabit: $('btn-add-habit'),
    habitsDateLabel: $('habits-date-label'), habitsList: $('habits-list'), habitStreakCount: $('habit-streak-count'),
    habitPrevDay: $('habit-prev-day'), habitNextDay: $('habit-next-day'),
    calendarPanel: $('calendar-panel'), btnCloseCalendar: $('btn-close-calendar'),
    calendarMonth: $('calendar-month'), calendarGrid: $('calendar-grid'),
    dayTaskList: $('day-task-list'), selectedDateLabel: $('selected-date-label'),
    btnPrevMonth: $('btn-prev-month'), btnNextMonth: $('btn-next-month'), btnAddCalTask: $('btn-add-cal-task'),
    tasksPanel: $('tasks-panel'), btnCloseTasks: $('btn-close-tasks'), allTasksList: $('all-tasks-list'),
    btnAddGlobalTask: $('btn-add-global-task'), taskSortSelect: $('task-sort-select'),
    taskSearchInput: $('task-search-input'), bulkActionsBar: $('bulk-actions-bar'),
    selectedCount: $('selected-count'), bulkStatusBtn: $('bulk-status-btn'),
    bulkMoveBtn: $('bulk-move-btn'), bulkDeleteBtn: $('bulk-delete-btn'), bulkCancelBtn: $('bulk-cancel-btn'),
    taskContextMenu: $('task-context-menu'), ctxTaskEdit: $('ctx-task-edit'),
    ctxTaskStatus: $('ctx-task-status'), ctxTaskPriority: $('ctx-task-priority'),
    ctxTaskMove: $('ctx-task-move'), ctxTaskDuplicate: $('ctx-task-duplicate'),
    ctxTaskComplete: $('ctx-task-complete'), ctxTaskDelete: $('ctx-task-delete'),
    statusSubmenu: $('status-submenu'), prioritySubmenu: $('priority-submenu'),
    globalTaskPopup: $('global-task-popup'), globalTaskText: $('global-task-text'),
    globalTaskBlock: $('global-task-block'), globalTaskPriority: $('global-task-priority'),
    globalTaskStatus: $('global-task-status'), globalTaskDate: $('global-task-date'),
    globalTaskTags: $('global-task-tags'), btnSaveGlobalTask: $('btn-save-global-task'),
    btnCancelGlobalTask: $('btn-cancel-global-task'),
    editTaskPopup: $('edit-task-popup'), editTaskText: $('edit-task-text'),
    editTaskPriority: $('edit-task-priority'), editTaskStatus: $('edit-task-status'),
    editTaskDate: $('edit-task-date'), editTaskTags: $('edit-task-tags'),
    btnSaveEditTask: $('btn-save-edit-task'), btnCancelEditTask: $('btn-cancel-edit-task'),
    moveTaskPopup: $('move-task-popup'), moveTaskBlock: $('move-task-block'),
    btnConfirmMoveTask: $('btn-confirm-move-task'), btnCancelMoveTask: $('btn-cancel-move-task'),
    chatBox: $('chat-box'), btnCloseChat: $('btn-close-chat'),
    chatMessages: $('chat-messages'), chatInput: $('chat-input'), btnSend: $('btn-send'),
    mindmapView: $('mindmap-view'), btnCloseMindmap: $('btn-close-mindmap'), btnAddBlock: $('btn-add-block'),
    connectionsSvg: $('connections-svg'), blocksLayer: $('blocks-layer'),
    contextMenu: $('block-context-menu'), ctxOpen: $('ctx-open'), ctxRename: $('ctx-rename'),
    ctxIcon: $('ctx-icon'), ctxSubblock: $('ctx-subblock'), ctxDelete: $('ctx-delete'),
    blockEditor: $('block-editor'), btnBack: $('btn-back'), blockIconBtn: $('block-icon-btn'),
    blockTitle: $('block-title'), btnCloseEditor: $('btn-close-editor'),
    blockDate: $('block-date'), blockDateEnd: $('block-date-end'),
    timerValue: $('timer-value'), btnTimerStart: $('btn-timer-start'),
    btnTimerPause: $('btn-timer-pause'), btnTimerReset: $('btn-timer-reset'),
    blockNotes: $('block-notes'), todoList: $('todo-list'), btnAddTodo: $('btn-add-todo'),
    subblocksList: $('subblocks-list'), btnAddSubblock: $('btn-add-subblock'),
    settingsPanel: $('settings-panel'), btnCloseSettings: $('btn-close-settings'),
    serverUrlInput: $('server-url-input'), btnSaveServerUrl: $('btn-save-server-url'), btnResetServerUrl: $('btn-reset-server-url'), syncStatusIndicator: $('sync-status-indicator'),
    pomoWorkDuration: $('pomo-work-duration'), pomoShortBreak: $('pomo-short-break'), pomoLongBreak: $('pomo-long-break'),
    btnExport: $('btn-export'), btnImport: $('btn-import'), btnClearData: $('btn-clear-data'), importFile: $('import-file'),
    profilePopup: $('profile-popup'), profileNameInput: $('profile-name-input'),
    btnSaveProfile: $('btn-save-profile'), btnDeleteProfile: $('btn-delete-profile'),
    blockPopup: $('block-popup'), newBlockName: $('new-block-name'),
    btnCreateBlock: $('btn-create-block'), btnCancelBlock: $('btn-cancel-block'),
    renamePopup: $('rename-popup'), renameInput: $('rename-input'),
    btnSaveRename: $('btn-save-rename'), btnCancelRename: $('btn-cancel-rename'),
    iconPopup: $('icon-popup'), iconGrid: $('icon-grid'), btnCancelIcon: $('btn-cancel-icon'),
    todoPopup: $('todo-popup'), todoText: $('todo-text'), todoPriority: $('todo-priority'),
    todoStatus: $('todo-status'), todoDate: $('todo-date'), todoTags: $('todo-tags'),
    btnSaveTodo: $('btn-save-todo'), btnCancelTodo: $('btn-cancel-todo'),
    quickAddPopup: $('quick-add-popup'), quickTaskText: $('quick-task-text'), quickTaskBlock: $('quick-task-block'),
    btnSaveQuick: $('btn-save-quick'), btnCancelQuick: $('btn-cancel-quick'),
    habitPopup: $('habit-popup'), habitName: $('habit-name'), habitIcon: $('habit-icon'), habitFreq: $('habit-freq'),
    btnSaveHabit: $('btn-save-habit'), btnCancelHabit: $('btn-cancel-habit'),
    calTaskPopup: $('cal-task-popup'), calTaskTitle: $('cal-task-title'),
    calTaskStart: $('cal-task-start'), calTaskEnd: $('cal-task-end'), calTaskStatus: $('cal-task-status'),
    btnSaveCalTask: $('btn-save-cal-task'), btnCancelCalTask: $('btn-cancel-cal-task'),
    shortcutsPopup: $('shortcuts-popup'), btnCloseShortcuts: $('btn-close-shortcuts'),
    toast: $('toast'), notification: $('notification'), notifClose: $('notif-close'),
    // AI Input/Output
    aiInputBar: $('ai-input-bar'), aiInput: $('ai-input'), aiSendBtn: $('ai-send-btn'),
    aiCloseBtn: $('ai-close-btn'), aiOutputBox: $('ai-output-box'), aiOutputClose: $('ai-output-close'),
    aiThinking: $('ai-thinking'), aiResponse: $('ai-response'),
    // Focus Panel
    focusMinimized: $('focus-minimized'), focusExpanded: $('focus-expanded'),
    focusExpandBtn: $('focus-expand-btn'), focusMinimizeBtn: $('focus-minimize-btn'),
    focusCalendarSection: $('focus-calendar-section'),
    focusTodosSection: $('focus-todos-section'),
    miniCalPrev: $('mini-cal-prev'), miniCalNext: $('mini-cal-next'), miniCalMonth: $('mini-cal-month'),
    miniCalGrid: $('mini-cal-grid'), miniCalTaskList: $('mini-cal-task-list'),
    miniTodoList: $('mini-todo-list'), miniAddTodo: $('mini-add-todo'),
    // Focus Profile
    focusProfile: $('focus-profile'), focusProfileName: $('focus-profile-name'),
    focusProfileBtn: $('focus-profile-btn'),
    // Collapsible Timer Section
    focusTimerContent: $('focus-timer-content'), focusTimerTime: $('focus-timer-time'),
    focusTimerModeLabel: $('focus-timer-mode-label'), focusTimerProgress: $('focus-timer-progress'),
    focusTimerStart: $('focus-timer-start'), focusTimerPause: $('focus-timer-pause'),
    focusTimerReset: $('focus-timer-reset'), focusTimerSessions: $('focus-timer-sessions'),
    timerStatusBadge: $('timer-status-badge'),
    // Orb Overlay
    orbOverlay: $('orb-overlay'), orbContainer: $('orb-container'),
    // Floating Timer
    floatingTimer: $('floating-timer'), closeFloatingTimer: $('close-floating-timer'),
    floatTimerTime: $('float-timer-time'), floatTimerMode: $('float-timer-mode'),
    floatTimerBar: $('float-timer-bar'), floatTimerStart: $('float-timer-start'),
    floatTimerPause: $('float-timer-pause'), floatTimerReset: $('float-timer-reset'),
    floatSessions: $('float-sessions'), floatTotalTime: $('float-total-time'),
  };
}

// ============================================================================
// Utilities
// ============================================================================

function toast(msg) {
  if (!els.toast) return;
  els.toast.textContent = msg;
  els.toast.classList.remove('hidden');
  setTimeout(() => {
    if (els.toast) els.toast.classList.add('hidden');
  }, 2000);
}

function showNotification(title, message, icon = '🔔') {
  const notification = $('notification');
  if (!notification) return; // Guard against missing element

  const titleEl = notification.querySelector('.notif-title');
  const messageEl = notification.querySelector('.notif-message');
  const iconEl = notification.querySelector('.notif-icon');

  if (titleEl) titleEl.textContent = title;
  if (messageEl) messageEl.textContent = message;
  if (iconEl) iconEl.textContent = icon;

  notification.classList.remove('hidden');
  setTimeout(() => notification.classList.add('hidden'), 5000);
}

function escHtml(s) { const d = document.createElement('div'); d.textContent = s; return d.innerHTML; }
function formatTime(sec) { const m = Math.floor(sec / 60); const s = sec % 60; return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`; }
function formatTimeFull(sec) { const h = Math.floor(sec / 3600); const m = Math.floor((sec % 3600) / 60); const s = sec % 60; return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`; }
function formatDate(d) { return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }); }
function dateStr(d) { return d.toISOString().split('T')[0]; }
function today() { return dateStr(new Date()); }
function dateInRange(date, start, end) { if (!start) return false; if (!end) return date === start; return date >= start && date <= end; }

// ============================================================================
// Theme
// ============================================================================

function applyTheme(theme) {
  state.theme = theme;
  document.body.setAttribute('data-theme', theme);
  document.querySelectorAll('.theme-option').forEach(o => o.classList.toggle('active', o.dataset.theme === theme));
  save();
}

// ============================================================================
// Menu / Radial Menu (accessed via right-click on orb)
// ============================================================================

function toggleMenu() {
  state.menuOpen = !state.menuOpen;
  if (els.orb) els.orb.classList.toggle('active', state.menuOpen);
  if (els.radialMenu) els.radialMenu.classList.toggle('hidden', !state.menuOpen);
}

function closeMenu() {
  state.menuOpen = false;
  els.orb.classList.remove('active');
  els.radialMenu.classList.add('hidden');
}

function closeAllPanels() {
  const panels = [
    els.mindmapView, els.blockEditor, els.chatBox, els.tasksPanel,
    els.calendarPanel, els.pomodoroPanel, els.statsPanel, els.habitsPanel,
    els.settingsPanel, els.searchBar, els.searchResults
  ];
  panels.forEach(panel => {
    if (panel) panel.classList.add('hidden');
  });
}

// ============================================================================
// AI Input/Output (Orb click behavior)
// ============================================================================

function toggleAiInput() {
  state.aiInputOpen = !state.aiInputOpen;
  if (els.orb) els.orb.classList.toggle('active', state.aiInputOpen);
  if (els.aiInputBar) els.aiInputBar.classList.toggle('hidden', !state.aiInputOpen);
  if (state.aiInputOpen) {
    if (els.aiInput) {
      els.aiInput.value = '';
      els.aiInput.focus();
    }
    // Close radial menu if open
    closeMenu();
    // Undock output box when opening input
    if (els.aiOutputBox) els.aiOutputBox.classList.remove('docked');
  }
}

function closeAiInput() {
  state.aiInputOpen = false;
  els.orb.classList.remove('active');
  els.aiInputBar.classList.add('hidden');
}

function closeAiOutput() {
  els.aiOutputBox.classList.add('hidden');
  els.aiOutputBox.classList.remove('docked');
}

function dockAiOutput() {
  // Move AI output to bottom-left corner
  if (els.aiOutputBox && !els.aiOutputBox.classList.contains('hidden')) {
    els.aiOutputBox.classList.add('docked');
  }
}

// ============================================================================
// AI Command System - Smart Assistant
// ============================================================================

async function sendAiQuery() {
  const text = els.aiInput.value.trim();
  if (!text) return;

  // Show output box with thinking animation
  els.aiOutputBox.classList.remove('hidden');
  els.aiThinking.classList.remove('hidden');
  els.aiResponse.innerHTML = '';
  els.aiInput.value = '';

  // Process command locally first
  const result = await processAiCommand(text);

  els.aiThinking.classList.add('hidden');
  els.aiResponse.innerHTML = result.html;

  // Execute any actions
  if (result.actions) {
    for (const action of result.actions) {
      await executeAiAction(action);
    }
  }
}

async function processAiCommand(input) {
  const lower = input.toLowerCase();

  // Study/Exam related commands
  if (lower.includes('study') || lower.includes('exam') || lower.includes('learn') || lower.includes('prepare')) {
    return handleStudyRequest(input);
  }

  // Create block commands
  if (lower.includes('create block') || lower.includes('new block') || lower.includes('make block') || lower.includes('add block')) {
    return handleCreateBlock(input);
  }

  // Create task commands
  if (lower.includes('create task') || lower.includes('new task') || lower.includes('add task') || lower.includes('remind me')) {
    return handleCreateTask(input);
  }

  // Timer commands
  if (lower.includes('start timer') || lower.includes('set timer') || lower.includes('pomodoro') || lower.includes('focus for')) {
    return handleTimerCommand(input);
  }

  // Open panel commands
  if (lower.includes('open') || lower.includes('show') || lower.includes('go to')) {
    return handleOpenCommand(input);
  }

  // Timetable/Schedule commands
  if (lower.includes('timetable') || lower.includes('schedule') || lower.includes('plan my')) {
    return handleTimetableRequest(input);
  }

  // Help command
  if (lower.includes('help') || lower.includes('what can you do')) {
    return getHelpResponse();
  }

  // Theme command
  if (lower.includes('theme') || lower.includes('color')) {
    return handleThemeCommand(input);
  }

  // Default - try Ollama first for real AI; fallback to help message
  return await getOllamaResponse(input);
}

function handleStudyRequest(input) {
  const lower = input.toLowerCase();

  // Extract subject/topic
  let subject = 'General';
  const subjectMatch = input.match(/(?:study|learn|prepare for|exam in|test on)\s+(.+?)(?:\s+for|\s+in|\s+exam|$)/i);
  if (subjectMatch) subject = subjectMatch[1].trim();

  // Create study block
  const blockId = 'block-' + Date.now();
  const studyBlock = {
    id: blockId,
    name: `📚 Study: ${subject}`,
    icon: '📚',
    type: 'Study Plan',
    x: 200 + Math.random() * 100,
    y: 150 + Math.random() * 100,
    notes: generateStudyNotes(subject),
    todos: generateStudyTasks(subject),
    createdAt: new Date().toISOString(),
  };

  state.blocks.push(studyBlock);
  save();

  const studyGuide = generateStudyGuide(subject);

  return {
    html: `
      <div class="ai-success">
        <h3>📚 Study Plan Created!</h3>
        <p>I've created a comprehensive study plan for <strong>${subject}</strong>.</p>
        ${studyGuide}
        <div class="ai-actions-done">
          <span class="action-badge">✅ Created study block</span>
          <span class="action-badge">✅ Added ${studyBlock.todos.length} tasks</span>
          <span class="action-badge">✅ Generated study guide</span>
        </div>
      </div>
    `,
    actions: [
      { type: 'openBlock', blockId },
      { type: 'startTimer', duration: 25 },
      { type: 'toast', message: 'Study session ready! Timer set for 25 minutes.' }
    ]
  };
}

function generateStudyNotes(subject) {
  return `# Study Plan: ${subject}

## Goals
- Understand key concepts
- Practice with examples
- Review and consolidate

## Resources
- Textbooks and notes
- Online resources
- Practice problems

## Schedule
- Morning: Theory review
- Afternoon: Practice problems
- Evening: Revision

## Tips
- Take regular breaks (Pomodoro technique)
- Active recall over passive reading
- Teach concepts to others
`;
}

function generateStudyTasks(subject) {
  const tasks = [
    { text: `📖 Review ${subject} fundamentals`, priority: 'high', status: 'not_started' },
    { text: `📝 Create summary notes`, priority: 'high', status: 'not_started' },
    { text: `💡 Identify key concepts`, priority: 'medium', status: 'not_started' },
    { text: `📋 Practice problems - Set 1`, priority: 'high', status: 'not_started' },
    { text: `📋 Practice problems - Set 2`, priority: 'medium', status: 'not_started' },
    { text: `🔄 Review mistakes`, priority: 'medium', status: 'not_started' },
    { text: `🎯 Mock test/self-assessment`, priority: 'high', status: 'not_started' },
    { text: `📚 Final revision`, priority: 'high', status: 'not_started' },
  ];

  return tasks.map((t, i) => ({
    id: 'task-' + Date.now() + '-' + i,
    ...t,
    date: getDateOffset(i),
    tags: ['study', subject.toLowerCase()],
  }));
}

function getDateOffset(days) {
  const d = new Date();
  d.setDate(d.getDate() + days);
  return d.toISOString().split('T')[0];
}

function generateStudyGuide(subject) {
  return `
    <div class="study-guide">
      <h4>📋 Study Strategy</h4>
      <ol>
        <li><strong>Understand</strong> - Read and comprehend the material</li>
        <li><strong>Organize</strong> - Create mind maps and summaries</li>
        <li><strong>Practice</strong> - Solve problems and exercises</li>
        <li><strong>Review</strong> - Use spaced repetition</li>
        <li><strong>Test</strong> - Self-assess your knowledge</li>
      </ol>
      <h4>⏱️ Recommended Schedule</h4>
      <ul>
        <li>25 min study + 5 min break (Pomodoro)</li>
        <li>After 4 sessions, take a 15-30 min break</li>
        <li>Review material before sleep</li>
      </ul>
    </div>
  `;
}

function handleCreateBlock(input) {
  const nameMatch = input.match(/(?:called?|named?|for)\s+["']?([^"']+)["']?/i) ||
    input.match(/block\s+["']?([^"']+)["']?/i);
  const name = nameMatch ? nameMatch[1].trim() : 'New Block';

  const blockId = 'block-' + Date.now();
  const block = {
    id: blockId,
    name: name,
    icon: '📦',
    type: 'general',
    x: 200 + Math.random() * 200,
    y: 150 + Math.random() * 150,
    notes: '',
    todos: [],
    createdAt: new Date().toISOString(),
  };

  state.blocks.push(block);
  save();

  return {
    html: `
      <div class="ai-success">
        <h3>✅ Block Created!</h3>
        <p>Created new block: <strong>${name}</strong></p>
        <p>Opening the Mind Map now...</p>
      </div>
    `,
    actions: [
      { type: 'openPanel', panel: 'mindmap' },
      { type: 'toast', message: `Block "${name}" created!` }
    ]
  };
}

function handleCreateTask(input) {
  const taskMatch = input.match(/(?:task|remind me to|add)\s+["']?(.+?)["']?(?:\s+(?:to|in|for)|$)/i);
  let taskText = taskMatch ? taskMatch[1].trim() : input.replace(/create task|new task|add task|remind me/gi, '').trim();

  if (!taskText) taskText = 'New task';

  // Find or create a block for the task
  let targetBlock = state.blocks.find(b => b.name.toLowerCase().includes('task') || b.type === 'general');
  if (!targetBlock && state.blocks.length > 0) {
    targetBlock = state.blocks[0];
  }

  if (!targetBlock) {
    targetBlock = {
      id: 'block-' + Date.now(),
      name: '📋 Tasks',
      icon: '📋',
      type: 'general',
      x: 200,
      y: 150,
      notes: '',
      todos: [],
      createdAt: new Date().toISOString(),
    };
    state.blocks.push(targetBlock);
  }

  const task = {
    id: 'task-' + Date.now(),
    text: taskText,
    priority: 'medium',
    status: 'not_started',
    date: today(),
    tags: [],
  };

  if (!targetBlock.todos) targetBlock.todos = [];
  targetBlock.todos.push(task);
  save();

  return {
    html: `
      <div class="ai-success">
        <h3>✅ Task Added!</h3>
        <p>Added task: <strong>${taskText}</strong></p>
        <p>Added to: ${targetBlock.name}</p>
      </div>
    `,
    actions: [
      { type: 'openPanel', panel: 'tasks' },
      { type: 'toast', message: 'Task added!' }
    ]
  };
}

function handleTimerCommand(input) {
  const durationMatch = input.match(/(\d+)\s*(?:min|minutes?|m)/i);
  const duration = durationMatch ? parseInt(durationMatch[1]) : 25;

  return {
    html: `
      <div class="ai-success">
        <h3>⏱️ Timer Set!</h3>
        <p>Starting a <strong>${duration} minute</strong> focus session.</p>
        <p>Stay focused! I'll notify you when it's time for a break.</p>
      </div>
    `,
    actions: [
      { type: 'setTimer', duration },
      { type: 'startTimer' },
      { type: 'openPanel', panel: 'floating-timer' }
    ]
  };
}

function handleOpenCommand(input) {
  const lower = input.toLowerCase();
  let panel = null;
  let panelName = '';

  if (lower.includes('mind') || lower.includes('map') || lower.includes('block')) {
    panel = 'mindmap'; panelName = 'Mind Map';
  } else if (lower.includes('task')) {
    panel = 'tasks'; panelName = 'Tasks';
  } else if (lower.includes('timer') || lower.includes('pomodoro')) {
    panel = 'floating-timer'; panelName = 'Timer';
  } else if (lower.includes('stat')) {
    panel = 'stats'; panelName = 'Statistics';
  } else if (lower.includes('habit')) {
    panel = 'habits'; panelName = 'Habits';
  } else if (lower.includes('calendar') || lower.includes('date')) {
    panel = 'calendar'; panelName = 'Calendar';
  } else if (lower.includes('setting')) {
    panel = 'settings'; panelName = 'Settings';
  }

  if (panel) {
    return {
      html: `<div class="ai-success"><h3>📂 Opening ${panelName}</h3></div>`,
      actions: [{ type: 'openPanel', panel }]
    };
  }

  return {
    html: `<p>I'm not sure which panel you want to open. Try: mind map, tasks, timer, stats, habits, calendar, or settings.</p>`
  };
}

function handleTimetableRequest(input) {
  const days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];
  const activities = [
    { time: '06:00 - 07:00', activity: '🌅 Wake up, Exercise' },
    { time: '07:00 - 08:00', activity: '🍳 Breakfast, Get ready' },
    { time: '08:00 - 10:00', activity: '📚 Study Session 1' },
    { time: '10:00 - 10:30', activity: '☕ Break' },
    { time: '10:30 - 12:30', activity: '📚 Study Session 2' },
    { time: '12:30 - 14:00', activity: '🍽️ Lunch & Rest' },
    { time: '14:00 - 16:00', activity: '📚 Study Session 3' },
    { time: '16:00 - 16:30', activity: '☕ Break' },
    { time: '16:30 - 18:30', activity: '📋 Practice/Review' },
    { time: '18:30 - 19:30', activity: '🍽️ Dinner' },
    { time: '19:30 - 21:00', activity: '📖 Light Review' },
    { time: '21:00 - 22:00', activity: '🎮 Relaxation' },
    { time: '22:00', activity: '😴 Sleep' },
  ];

  // Create timetable block
  const blockId = 'block-' + Date.now();
  const timetableBlock = {
    id: blockId,
    name: '📅 Weekly Timetable',
    icon: '📅',
    type: 'Schedule',
    x: 250,
    y: 150,
    notes: activities.map(a => `${a.time}: ${a.activity}`).join('\n'),
    todos: activities.slice(2, 8).map((a, i) => ({
      id: 'task-tt-' + Date.now() + '-' + i,
      text: a.activity.replace(/^[^\s]+\s/, ''),
      priority: 'medium',
      status: 'not_started',
      date: today(),
      tags: ['routine'],
    })),
    createdAt: new Date().toISOString(),
  };

  state.blocks.push(timetableBlock);
  save();

  return {
    html: `
      <div class="ai-success">
        <h3>📅 Timetable Created!</h3>
        <div class="timetable-preview">
          ${activities.slice(0, 6).map(a => `<div class="tt-row"><span class="tt-time">${a.time}</span><span class="tt-act">${a.activity}</span></div>`).join('')}
          <p class="tt-more">...and more</p>
        </div>
        <div class="ai-actions-done">
          <span class="action-badge">✅ Created schedule block</span>
          <span class="action-badge">✅ Added daily tasks</span>
        </div>
      </div>
    `,
    actions: [
      { type: 'openBlock', blockId },
      { type: 'toast', message: 'Timetable created!' }
    ]
  };
}

function handleThemeCommand(input) {
  const lower = input.toLowerCase();
  let theme = null;

  if (lower.includes('sky') || lower.includes('blue')) theme = 'sky';
  else if (lower.includes('forest') || lower.includes('green')) theme = 'forest';
  else if (lower.includes('sunset') || lower.includes('orange')) theme = 'sunset';
  else if (lower.includes('ocean') || lower.includes('deep blue')) theme = 'ocean';
  else if (lower.includes('lavender') || lower.includes('purple')) theme = 'lavender';
  else if (lower.includes('rose') || lower.includes('pink')) theme = 'rose';

  if (theme) {
    return {
      html: `<div class="ai-success"><h3>🎨 Theme Changed!</h3><p>Switched to <strong>${theme}</strong> theme.</p></div>`,
      actions: [{ type: 'setTheme', theme }]
    };
  }

  return {
    html: `
      <div class="ai-info">
        <h3>🎨 Available Themes</h3>
        <p>Say "change theme to [name]":</p>
        <ul>
          <li><strong>Sky</strong> - Light blue</li>
          <li><strong>Forest</strong> - Green</li>
          <li><strong>Sunset</strong> - Orange</li>
          <li><strong>Ocean</strong> - Deep blue</li>
          <li><strong>Lavender</strong> - Purple</li>
          <li><strong>Rose</strong> - Pink</li>
        </ul>
      </div>
    `
  };
}

function getHelpResponse() {
  return {
    html: `
      <div class="ai-help">
        <h3>🤖 What I Can Do</h3>
        <div class="help-section">
          <h4>📚 Study Help</h4>
          <p>"I need to study for math exam"</p>
          <p>"Help me prepare for biology test"</p>
        </div>
        <div class="help-section">
          <h4>📦 Create Things</h4>
          <p>"Create a block called Project X"</p>
          <p>"Add task: finish homework"</p>
        </div>
        <div class="help-section">
          <h4>⏱️ Timer</h4>
          <p>"Start 25 minute timer"</p>
          <p>"Pomodoro session"</p>
        </div>
        <div class="help-section">
          <h4>📅 Schedule</h4>
          <p>"Create a timetable"</p>
          <p>"Plan my week"</p>
        </div>
        <div class="help-section">
          <h4>🎨 Appearance</h4>
          <p>"Change theme to forest"</p>
        </div>
        <div class="help-section">
          <h4>📂 Navigation</h4>
          <p>"Open mind map"</p>
          <p>"Show tasks"</p>
        </div>
      </div>
    `
  };
}

async function getOllamaResponse(input) {
  const model = (typeof currentAiModel !== 'undefined' ? currentAiModel : null) ||
    document.getElementById('ai-model-select')?.value || 'llama3.2';
  try {
    const { invoke } = window.__TAURI__.core;
    const text = await invoke('ollama_generate', {
      prompt: input,
      model: model || 'llama3.2',
    });
    if (!text || !text.trim()) return getSmartResponse(input);
    return { html: `<div class="ai-info">${formatAiResponse(text)}</div>` };
  } catch (e) {
    console.warn('Ollama not available:', e);
    return getSmartResponse(input);
  }
}

function getSmartResponse(input) {
  return {
    html: `
      <div class="ai-info">
        <p>I understand you said: "<em>${escHtml(input)}</em>"</p>
        <p>Ollama isn't running or didn't respond. I can also help with:</p>
        <ul>
          <li>📚 <strong>Study plans</strong> - "I need to study for [subject]"</li>
          <li>📦 <strong>Create blocks</strong> - "Create block called [name]"</li>
          <li>✅ <strong>Add tasks</strong> - "Add task: [description]"</li>
          <li>⏱️ <strong>Set timers</strong> - "Start 25 minute timer"</li>
          <li>📅 <strong>Make schedules</strong> - "Create a timetable"</li>
          <li>🎨 <strong>Change theme</strong> - "Theme [color]"</li>
        </ul>
        <p>Start <strong>Ollama</strong> (e.g. <code>ollama serve</code>) and try again for AI replies.</p>
      </div>
    `
  };
}

async function executeAiAction(action) {
  switch (action.type) {
    case 'openPanel':
      if (action.panel === 'mindmap') openMindmap();
      else if (action.panel === 'tasks') openTasks();
      else if (action.panel === 'floating-timer') openFloatingTimer();
      else if (action.panel === 'stats') openStats();
      else if (action.panel === 'habits') openHabits();
      else if (action.panel === 'calendar') openCalendar();
      else if (action.panel === 'settings') openSettings();
      break;
    case 'openBlock':
      openBlockEditor(action.blockId);
      break;
    case 'setTimer':
      state.pomodoro.workDuration = action.duration;
      state.pomodoro.seconds = action.duration * 60;
      updatePomodoroUI();
      break;
    case 'startTimer':
      setTimeout(() => startPomodoro(), 500);
      break;
    case 'setTheme':
      applyTheme(action.theme);
      break;
    case 'toast':
      toast(action.message);
      break;
  }

  // Small delay between actions
  await new Promise(r => setTimeout(r, 300));
}

function formatAiResponse(text) {
  // Simple markdown-like formatting
  return text
    .split('\n\n').map(p => `<p>${escHtml(p)}</p>`).join('')
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.*?)\*/g, '<em>$1</em>');
}

// ============================================================================
// Focus Panel
// ============================================================================

function toggleFocusPanel() {
  state.focusMinimized = !state.focusMinimized;
  updateFocusPanelState();
}

function minimizeFocusPanel() {
  state.focusMinimized = true;
  updateFocusPanelState();
}

function expandFocusPanel() {
  state.focusMinimized = false;
  updateFocusPanelState();
}

function updateFocusPanelState() {
  if (state.focusMinimized) {
    els.focusMinimized.classList.remove('hidden');
    els.focusExpanded.classList.add('hidden');
  } else {
    els.focusMinimized.classList.add('hidden');
    els.focusExpanded.classList.remove('hidden');
  }
}

function switchFocusSection(section) {
  state.focusSection = section;

  // Open the corresponding collapsible section and close others
  const sectionMap = { timer: 'timer', calendar: 'calendar', todos: 'todos' };
  if (sectionMap[section]) {
    state.openSections[section] = true;
    updateCollapsibleSections();
  }

  // Render content
  if (section === 'timer') updateFocusTimerBar();
  if (section === 'calendar') renderMiniCalendar();
  if (section === 'todos') renderMiniTodos();
}

// ============================================================================
// Mini Calendar (in Focus Panel)
// ============================================================================

function renderMiniCalendar() {
  const d = state.miniCalDate;
  const year = d.getFullYear();
  const month = d.getMonth();
  const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

  if (els.miniCalMonth) els.miniCalMonth.textContent = `${months[month]} ${year}`;

  const firstDay = new Date(year, month, 1).getDay();
  const daysInMonth = new Date(year, month + 1, 0).getDate();
  const prevDays = new Date(year, month, 0).getDate();
  const todayStr = today();

  // Get tasks for this month
  const allTasks = [...state.calendarTasks];
  state.blocks.forEach(b => (b.todos || []).filter(t => t.date).forEach(t => allTasks.push({ ...t, start: t.date, end: t.date })));

  let html = '';
  // Previous month days
  for (let i = firstDay - 1; i >= 0; i--) {
    html += `<div class="mini-cal-day other-month">${prevDays - i}</div>`;
  }

  // Current month days
  for (let day = 1; day <= daysInMonth; day++) {
    const ds = `${year}-${String(month + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
    const isToday = ds === todayStr;
    const hasTask = allTasks.some(t => dateInRange(ds, t.start || t.date, t.end || t.date));
    let cls = 'mini-cal-day';
    if (isToday) cls += ' today';
    if (hasTask) cls += ' has-task';
    html += `<div class="${cls}" data-date="${ds}">${day}</div>`;
  }

  if (els.miniCalGrid) els.miniCalGrid.innerHTML = html;

  // Render today's tasks
  renderMiniCalTasks();
}

function renderMiniCalTasks() {
  const todayStr = today();
  const allTasks = [];
  state.blocks.forEach(b => (b.todos || []).filter(t => t.date === todayStr).forEach(t =>
    allTasks.push({ ...t, blockName: b.name })
  ));
  state.calendarTasks.filter(t => dateInRange(todayStr, t.start, t.end)).forEach(t => allTasks.push(t));

  if (els.miniCalTaskList) {
    if (allTasks.length === 0) {
      els.miniCalTaskList.innerHTML = '<div class="mini-cal-task" style="opacity: 0.5;">No tasks today</div>';
    } else {
      els.miniCalTaskList.innerHTML = allTasks.slice(0, 3).map(t =>
        `<div class="mini-cal-task">${escHtml(t.text || t.title)}</div>`
      ).join('');
    }
  }
}

// ============================================================================
// Mini To-Do List (in Focus Panel)
// ============================================================================

function renderMiniTodos() {
  // Get all uncompleted tasks
  const todos = [];
  state.blocks.forEach(b => (b.todos || [])
    .filter(t => t.status !== 'completed')
    .slice(0, 3)
    .forEach(t => todos.push({ ...t, blockId: b.id, blockName: b.name }))
  );

  if (els.miniTodoList) {
    if (todos.length === 0) {
      els.miniTodoList.innerHTML = '<div class="mini-todos-empty">No pending tasks</div>';
    } else {
      els.miniTodoList.innerHTML = todos.slice(0, 5).map(t => `
        <div class="mini-todo-item" data-block="${t.blockId}" data-todo="${t.id}">
          <div class="mini-todo-check ${t.status === 'completed' ? 'done' : ''}" data-block="${t.blockId}" data-todo="${t.id}">
            ${t.status === 'completed' ? '✓' : ''}
          </div>
          <span class="mini-todo-text ${t.status === 'completed' ? 'done' : ''}">${escHtml(t.text)}</span>
        </div>
      `).join('');
    }
  }
}

// Event delegation handler for mini todo list (attached once during init)
function initMiniTodoEvents() {
  if (!els.miniTodoList) return;

  els.miniTodoList.addEventListener('click', e => {
    const check = e.target.closest('.mini-todo-check');
    if (check) {
      e.stopPropagation();
      const blockId = check.dataset.block;
      const todoId = check.dataset.todo;
      toggleMiniTodo(todoId, blockId);
      return;
    }

    const item = e.target.closest('.mini-todo-item');
    if (item) {
      openBlockEditor(item.dataset.block);
    }
  });
}

function toggleMiniTodo(todoId, blockId) {
  const block = state.blocks.find(b => b.id === blockId);
  if (!block) return;
  const todo = (block.todos || []).find(t => t.id === todoId);
  if (!todo) return;

  const wasCompleted = todo.status === 'completed';
  todo.status = wasCompleted ? 'not_started' : 'completed';

  if (!wasCompleted) {
    updateTodayStats();
    const t = today();
    if (!state.stats.daily[t]) state.stats.daily[t] = { completed: 0, pomodoros: 0, focusMinutes: 0 };
    state.stats.daily[t].completed++;
    state.stats.completed++;
  }

  save();
  renderMiniTodos();
  updateTodayProgress();
}

// ============================================================================
// Floating Panels & Multi-Window System
// ============================================================================

function openFloatingPanel(panelId) {
  const panel = document.getElementById(panelId);
  if (!panel) return;

  panel.classList.remove('hidden');
  state.openPanels.add(panelId);

  // Restore position if saved
  if (state.panelPositions[panelId]) {
    panel.style.left = state.panelPositions[panelId].x + 'px';
    panel.style.top = state.panelPositions[panelId].y + 'px';
    panel.style.right = 'auto';
  }

  // Bring to front
  bringPanelToFront(panel);
}

function closeFloatingPanel(panelId) {
  const panel = document.getElementById(panelId);
  if (!panel) return;

  panel.classList.add('hidden');
  state.openPanels.delete(panelId);
}

function toggleFloatingPanel(panelId) {
  const panel = document.getElementById(panelId);
  if (!panel) return;

  if (panel.classList.contains('hidden')) {
    openFloatingPanel(panelId);
  } else {
    closeFloatingPanel(panelId);
  }
}

function bringPanelToFront(panel) {
  // Set z-index higher than others
  document.querySelectorAll('.floating-panel, .panel-view').forEach(p => {
    p.style.zIndex = p === panel ? '850' : '800';
  });
}

// Panel Dragging
function initPanelDrag(e) {
  const header = e.target.closest('[data-drag]');
  if (!header) return;

  const panelId = header.dataset.drag;
  const panel = document.getElementById(panelId);
  if (!panel) return;

  e.preventDefault();
  state.draggingPanel = panel;

  const rect = panel.getBoundingClientRect();
  state.dragPanelOffset = {
    x: e.clientX - rect.left,
    y: e.clientY - rect.top
  };

  bringPanelToFront(panel);
  panel.style.transition = 'none';
}

function handlePanelDrag(e) {
  if (!state.draggingPanel) return;

  const x = Math.max(0, Math.min(window.innerWidth - 100, e.clientX - state.dragPanelOffset.x));
  const y = Math.max(0, Math.min(window.innerHeight - 50, e.clientY - state.dragPanelOffset.y));

  state.draggingPanel.style.left = x + 'px';
  state.draggingPanel.style.top = y + 'px';
  state.draggingPanel.style.right = 'auto';
}

function endPanelDrag() {
  if (!state.draggingPanel) return;

  // Save position
  const rect = state.draggingPanel.getBoundingClientRect();
  state.panelPositions[state.draggingPanel.id] = { x: rect.left, y: rect.top };

  state.draggingPanel.style.transition = '';
  state.draggingPanel = null;
}

// ============================================================================
// Click-Through Mode (Ghost Mode)
// ============================================================================

let clickThroughEnabled = false;

async function toggleClickThroughMode() {
  clickThroughEnabled = !clickThroughEnabled;

  const toggle = document.getElementById('click-through-toggle');

  if (clickThroughEnabled) {
    // Enable click-through mode
    document.body.classList.add('click-through-mode');
    if (toggle) toggle.classList.add('active');
    toast('Ghost mode enabled - click through to windows below');

    // Tell Tauri to enable click-through and set window to ignore cursor (clicks pass through)
    try {
      const { invoke } = window.__TAURI__.core;
      await invoke('set_click_through', { enabled: true });
      const w = window.__TAURI__.webviewWindow.getCurrentWebviewWindow();
      await w.setIgnoreCursorEvents(true);
      toast('Ghost mode on — press Alt+G to turn off');
    } catch (e) {
      console.log('Tauri invoke not available:', e);
    }
  } else {
    // Disable click-through mode and re-enable cursor events on window
    try {
      const w = window.__TAURI__.webviewWindow?.getCurrentWebviewWindow?.();
      if (w) await w.setIgnoreCursorEvents(false);
      const { invoke } = window.__TAURI__.core;
      await invoke('set_click_through', { enabled: false });
    } catch (e) {
      console.log('Tauri invoke not available:', e);
    }
    document.body.classList.remove('click-through-mode');
    if (toggle) toggle.classList.remove('active');
    toast('Ghost mode disabled');
  }
}

// ============================================================================
// Floating Timer
// ============================================================================

function openFloatingTimer() {
  openFloatingPanel('floating-timer');
  updateFloatingTimer();
}

function closeFloatingTimerPanel() {
  closeFloatingPanel('floating-timer');
}

function updateFloatingTimer() {
  if (els.floatTimerTime) els.floatTimerTime.textContent = formatTime(state.pomodoro.seconds);

  const modeLabels = { work: 'Work', short: 'Short Break', long: 'Long Break' };
  if (els.floatTimerMode) els.floatTimerMode.textContent = modeLabels[state.pomodoro.mode] || 'Work';

  // Update progress bar
  const total = state.pomodoro.mode === 'work' ? state.pomodoro.workDuration * 60
    : state.pomodoro.mode === 'short' ? state.pomodoro.shortBreak * 60 : state.pomodoro.longBreak * 60;
  const percent = (state.pomodoro.seconds / total) * 100;
  if (els.floatTimerBar) els.floatTimerBar.style.width = percent + '%';

  if (els.floatSessions) els.floatSessions.textContent = state.pomodoro.sessions;
  const h = Math.floor(state.pomodoro.totalMinutes / 60);
  const m = state.pomodoro.totalMinutes % 60;
  if (els.floatTotalTime) els.floatTotalTime.textContent = `${h}h ${m}m`;

  // Update button visibility
  if (state.pomodoro.running) {
    if (els.floatTimerStart) els.floatTimerStart.classList.add('hidden');
    if (els.floatTimerPause) els.floatTimerPause.classList.remove('hidden');
  } else {
    if (els.floatTimerStart) els.floatTimerStart.classList.remove('hidden');
    if (els.floatTimerPause) els.floatTimerPause.classList.add('hidden');
  }
}

// ============================================================================
// Master Panel Toggle (Hide/Show All)
// ============================================================================

function toggleAllPanelsVisibility() {
  state.allPanelsHidden = !state.allPanelsHidden;

  const allPanels = [
    'mindmap-view', 'block-editor', 'tasks-panel', 'calendar-panel',
    'pomodoro-panel', 'stats-panel', 'habits-panel', 'settings-panel',
    'floating-timer', 'chat-box', 'focus-panel'
  ];

  allPanels.forEach(id => {
    const panel = document.getElementById(id);
    if (panel) {
      if (state.allPanelsHidden) {
        panel.dataset.wasVisible = !panel.classList.contains('hidden');
        panel.classList.add('hidden');
      } else {
        if (panel.dataset.wasVisible === 'true') {
          panel.classList.remove('hidden');
        }
      }
    }
  });

  // Also hide/show AI input
  if (state.allPanelsHidden) {
    if (els.aiInputBar) {
      els.aiInputBar.dataset.wasVisible = !els.aiInputBar.classList.contains('hidden');
      els.aiInputBar.classList.add('hidden');
    }
    if (els.aiOutputBox) {
      els.aiOutputBox.dataset.wasVisible = !els.aiOutputBox.classList.contains('hidden');
      els.aiOutputBox.classList.add('hidden');
    }
  } else {
    if (els.aiInputBar?.dataset.wasVisible === 'true') els.aiInputBar.classList.remove('hidden');
    if (els.aiOutputBox?.dataset.wasVisible === 'true') els.aiOutputBox.classList.remove('hidden');
  }

  toast(state.allPanelsHidden ? 'All panels hidden (Press ~ to show)' : 'Panels restored');
}

function closeAllOpenPanels() {
  const allPanels = [
    'mindmap-view', 'block-editor', 'tasks-panel', 'calendar-panel',
    'pomodoro-panel', 'stats-panel', 'habits-panel', 'settings-panel',
    'floating-timer', 'chat-box'
  ];

  allPanels.forEach(id => {
    const panel = document.getElementById(id);
    if (panel) panel.classList.add('hidden');
  });

  state.openPanels.clear();
  closeAiInput();
  closeAiOutput();
  closeMenu();
  closeSearch();
}

// ============================================================================
// Search
// ============================================================================

function openSearch() {
  closeMenu();
  els.searchBar.classList.remove('hidden');
  els.searchInput.value = '';
  els.searchInput.focus();
  els.searchResults.classList.add('hidden');
}

function closeSearch() {
  els.searchBar.classList.add('hidden');
  els.searchResults.classList.add('hidden');
}

function performSearch(query) {
  if (!query.trim()) { els.searchResults.classList.add('hidden'); return; }

  const q = query.toLowerCase();
  const results = [];

  state.blocks.forEach(b => {
    if (b.name.toLowerCase().includes(q) || b.notes?.toLowerCase().includes(q)) {
      results.push({ type: 'block', id: b.id, title: b.name, icon: b.icon, subtitle: b.type });
    }
    (b.todos || []).forEach(t => {
      if (t.text.toLowerCase().includes(q)) {
        results.push({ type: 'task', blockId: b.id, id: t.id, title: t.text, icon: '✅', subtitle: `in ${b.name}` });
      }
    });
  });

  state.habits.forEach(h => {
    if (h.name.toLowerCase().includes(q)) {
      results.push({ type: 'habit', id: h.id, title: h.name, icon: h.icon, subtitle: 'Habit' });
    }
  });

  if (results.length === 0) {
    els.searchResults.innerHTML = '<div class="search-empty">No results found</div>';
  } else {
    els.searchResults.innerHTML = results.slice(0, 10).map(r => `
      <div class="search-result" data-type="${r.type}" data-id="${r.id}" data-block="${r.blockId || ''}">
        <span class="search-result-icon">${r.icon}</span>
        <span class="search-result-text">${escHtml(r.title)}</span>
        <span class="search-result-type">${r.subtitle}</span>
      </div>
    `).join('');
  }

  els.searchResults.classList.remove('hidden');
}

// ============================================================================
// Profile
// ============================================================================

function updateProfileBadge() {
  if (state.currentProfile) {
    if (els.profileNameBadge) els.profileNameBadge.textContent = state.currentProfile.name;
    if (els.focusProfileName) els.focusProfileName.textContent = state.currentProfile.name;
  }
}

function renderProfiles() {
  els.profileList.innerHTML = state.profiles.map(p => `
    <button class="dropdown-item ${p.id === state.currentProfile?.id ? 'active' : ''}" data-id="${p.id}">${escHtml(p.name)}</button>
  `).join('');
}

function switchProfile(id) {
  state.currentProfile = state.profiles.find(p => p.id === id) || state.currentProfile;
  save(); updateProfileBadge();
  els.profileDropdown.classList.add('hidden');
  toast(`Switched to ${state.currentProfile.name}`);
}

let editProfileId = null;
function openProfilePopup(id = null) {
  editProfileId = id;
  const p = id ? state.profiles.find(x => x.id === id) : null;
  els.profileNameInput.value = p?.name || '';
  els.btnDeleteProfile.classList.toggle('hidden', !p);
  els.profilePopup.classList.remove('hidden');
  els.profileNameInput.focus();
}

function saveProfile() {
  const name = els.profileNameInput.value.trim();
  if (!name) return;
  if (editProfileId) { const p = state.profiles.find(x => x.id === editProfileId); if (p) p.name = name; }
  else { state.profiles.push({ id: Date.now().toString(), name }); }
  save(); renderProfiles(); updateProfileBadge();
  els.profilePopup.classList.add('hidden');
  toast('Profile saved');
}

function deleteProfile() {
  if (!editProfileId) return;
  state.profiles = state.profiles.filter(p => p.id !== editProfileId);
  if (state.currentProfile?.id === editProfileId) state.currentProfile = state.profiles[0];
  save(); renderProfiles(); updateProfileBadge();
  els.profilePopup.classList.add('hidden');
}

// ============================================================================
// Focus
// ============================================================================

function updateFocusDisplay() {
  els.focusTextDisplay.textContent = state.currentFocus || 'Click to set...';
  els.focusTextDisplay.classList.toggle('active', !!state.currentFocus);
}

function startFocusEdit() {
  els.focusTextDisplay.classList.add('hidden');
  els.focusInput.classList.remove('hidden');
  els.focusInput.value = state.currentFocus || '';
  els.focusInput.focus();
}

function saveFocus() {
  state.currentFocus = els.focusInput.value.trim() || null;
  save();
  els.focusInput.classList.add('hidden');
  els.focusTextDisplay.classList.remove('hidden');
  updateFocusDisplay();
}

// ============================================================================
// Pomodoro
// ============================================================================

function updateMiniTimer() {
  if (els.miniTimer) els.miniTimer.textContent = formatTime(state.pomodoro.seconds);
  // Update mode indicator
  const modeLabels = { work: 'Work', short: 'Short Break', long: 'Long Break' };
  const modeLabelsFull = { work: 'Work Session', short: 'Short Break', long: 'Long Break' };
  if (els.miniMode) {
    els.miniMode.textContent = modeLabels[state.pomodoro.mode] || 'Work';
  }
  // Update sessions count
  if (els.miniSessions) els.miniSessions.textContent = state.pomodoro.sessions;

  // Update focus timer bar (minimized)
  updateFocusTimerBar();
}

function updateFocusTimerBar() {
  const modeLabelsFull = { work: 'Work Session', short: 'Short Break', long: 'Long Break' };

  // Update collapsible timer section
  if (els.focusTimerTime) els.focusTimerTime.textContent = formatTime(state.pomodoro.seconds);
  if (els.focusTimerModeLabel) els.focusTimerModeLabel.textContent = modeLabelsFull[state.pomodoro.mode] || 'Work Session';
  if (els.focusTimerSessions) els.focusTimerSessions.textContent = state.pomodoro.sessions;

  // Update progress bar
  if (els.focusTimerProgress) {
    const total = state.pomodoro.mode === 'work' ? state.pomodoro.workDuration * 60
      : state.pomodoro.mode === 'short' ? state.pomodoro.shortBreak * 60 : state.pomodoro.longBreak * 60;
    const progress = ((total - state.pomodoro.seconds) / total) * 100;
    els.focusTimerProgress.style.width = progress + '%';
  }

  // Update start/pause button visibility
  if (els.focusTimerStart && els.focusTimerPause) {
    els.focusTimerStart.classList.toggle('hidden', state.pomodoro.running);
    els.focusTimerPause.classList.toggle('hidden', !state.pomodoro.running);
  }

  // Update running status badge
  if (els.timerStatusBadge) {
    els.timerStatusBadge.classList.toggle('hidden', !state.pomodoro.running);
  }

  // Update mode buttons
  document.querySelectorAll('.mode-select-btn').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.mode === state.pomodoro.mode);
  });
}

// Toggle collapsible sections
function toggleCollapsibleSection(section) {
  state.openSections[section] = !state.openSections[section];
  updateCollapsibleSections();
}

function updateCollapsibleSections() {
  document.querySelectorAll('.focus-collapsible').forEach(el => {
    const section = el.dataset.section;
    el.classList.toggle('open', state.openSections[section]);
  });
}

// Orb centered mode
function centerOrb() {
  state.orbCentered = true;
  if (els.orbContainer) els.orbContainer.classList.add('centered');
  if (els.radialMenu) els.radialMenu.classList.add('centered');
  if (els.orbOverlay) els.orbOverlay.classList.add('visible');
  els.radialMenu.classList.remove('hidden');
}

function uncenterOrb() {
  state.orbCentered = false;
  state.menuOpen = false;
  if (els.orbContainer) els.orbContainer.classList.remove('centered');
  if (els.radialMenu) els.radialMenu.classList.remove('centered');
  if (els.orbOverlay) els.orbOverlay.classList.remove('visible');
  if (els.radialMenu) els.radialMenu.classList.add('hidden');
  if (els.orb) els.orb.classList.remove('active');
}

function updatePomodoroUI() {
  if (els.pomoTime) els.pomoTime.textContent = formatTime(state.pomodoro.seconds);
  const total = state.pomodoro.mode === 'work' ? state.pomodoro.workDuration * 60
    : state.pomodoro.mode === 'short' ? state.pomodoro.shortBreak * 60 : state.pomodoro.longBreak * 60;
  const progress = ((total - state.pomodoro.seconds) / total) * 283;
  if (els.pomoProgress) els.pomoProgress.style.strokeDashoffset = 283 - progress;
  if (els.pomoSessions) els.pomoSessions.textContent = state.pomodoro.sessions;
  const h = Math.floor(state.pomodoro.totalMinutes / 60);
  const m = state.pomodoro.totalMinutes % 60;
  if (els.pomoTotalTime) els.pomoTotalTime.textContent = `${h}h ${m}m`;
  updateMiniTimer();
  updateFloatingTimer();
}

function startPomodoro() {
  if (state.pomodoro.running) return;
  state.pomodoro.running = true;
  els.pomoStart.classList.add('hidden'); els.pomoPause.classList.remove('hidden');
  els.miniStart.classList.add('hidden'); els.miniPause.classList.remove('hidden');

  state.pomodoro.interval = setInterval(() => {
    state.pomodoro.seconds--;
    if (state.pomodoro.seconds <= 0) {
      clearInterval(state.pomodoro.interval);
      state.pomodoro.running = false;

      if (state.pomodoro.mode === 'work') {
        state.pomodoro.sessions++;
        state.pomodoro.totalMinutes += state.pomodoro.workDuration;
        state.stats.pomodoros++;
        state.stats.focusMinutes += state.pomodoro.workDuration;
        updateTodayStats();
        showNotification('Pomodoro Complete!', 'Time for a break', '🍅');
        state.pomodoro.mode = state.pomodoro.sessions % 4 === 0 ? 'long' : 'short';
      } else {
        showNotification('Break Over!', 'Ready to focus?', '💪');
        state.pomodoro.mode = 'work';
      }

      resetPomodoroTimer();
      save();
    }
    updatePomodoroUI();
  }, 1000);
}

function pausePomodoro() {
  state.pomodoro.running = false;
  clearInterval(state.pomodoro.interval);
  els.pomoStart.classList.remove('hidden'); els.pomoPause.classList.add('hidden');
  els.miniStart.classList.remove('hidden'); els.miniPause.classList.add('hidden');
}

function resetPomodoroTimer() {
  pausePomodoro();
  const durations = { work: state.pomodoro.workDuration, short: state.pomodoro.shortBreak, long: state.pomodoro.longBreak };
  state.pomodoro.seconds = durations[state.pomodoro.mode] * 60;
  updatePomodoroUI();
}

function setPomoMode(mode) {
  pausePomodoro();
  state.pomodoro.mode = mode;
  document.querySelectorAll('.pomo-tab').forEach(t => t.classList.toggle('active', t.dataset.mode === mode));
  resetPomodoroTimer();
}

function populatePomoTasks() {
  const tasks = [];
  state.blocks.forEach(b => {
    (b.todos || []).filter(t => t.status !== 'completed').forEach(t => {
      tasks.push({ id: t.id, text: t.text, block: b.name });
    });
  });
  els.pomoTaskSelect.innerHTML = '<option value="">Select a task...</option>' +
    tasks.map(t => `<option value="${t.id}">${escHtml(t.text)} (${escHtml(t.block)})</option>`).join('');
}

function openPomodoro() {
  closeMenu();
  populatePomoTasks();
  els.pomodoroPanel.classList.remove('hidden');
  state.openPanels.add('pomodoro-panel');
  bringPanelToFront(els.pomodoroPanel);
}

// ============================================================================
// Statistics
// ============================================================================

function updateTodayStats() {
  const t = today();
  if (!state.stats.daily[t]) state.stats.daily[t] = { completed: 0, pomodoros: 0, focusMinutes: 0 };
}

function calculateStats(period) {
  let completed = 0, pomodoros = 0, focusMinutes = 0;
  const now = new Date();
  const dates = [];

  if (period === 'today') {
    dates.push(today());
  } else if (period === 'week') {
    for (let i = 6; i >= 0; i--) {
      const d = new Date(now); d.setDate(d.getDate() - i);
      dates.push(dateStr(d));
    }
  } else {
    for (let i = 29; i >= 0; i--) {
      const d = new Date(now); d.setDate(d.getDate() - i);
      dates.push(dateStr(d));
    }
  }

  dates.forEach(d => {
    const daily = state.stats.daily[d];
    if (daily) {
      completed += daily.completed || 0;
      pomodoros += daily.pomodoros || 0;
      focusMinutes += daily.focusMinutes || 0;
    }
  });

  return { completed, pomodoros, focusMinutes };
}

function renderStats(period = 'today') {
  const s = calculateStats(period);
  els.statCompleted.textContent = s.completed;
  els.statPomodoros.textContent = s.pomodoros;
  els.statFocusTime.textContent = `${Math.floor(s.focusMinutes / 60)}h`;
  els.statStreak.textContent = calculateStreak();

  // Activity chart (last 7 days)
  const now = new Date();
  let maxVal = 1;
  const days = [];
  for (let i = 6; i >= 0; i--) {
    const d = new Date(now); d.setDate(d.getDate() - i);
    const daily = state.stats.daily[dateStr(d)] || {};
    const val = (daily.completed || 0) + (daily.pomodoros || 0);
    days.push(val);
    if (val > maxVal) maxVal = val;
  }

  els.activityChart.innerHTML = days.map(v => `<div class="chart-bar" style="height: ${(v / maxVal) * 100}%"></div>`).join('');
}

function calculateStreak() {
  let streak = 0;
  const now = new Date();
  for (let i = 0; i < 365; i++) {
    const d = new Date(now); d.setDate(d.getDate() - i);
    const daily = state.stats.daily[dateStr(d)];
    if (daily && (daily.completed > 0 || daily.pomodoros > 0)) streak++;
    else if (i > 0) break;
  }
  return streak;
}

function openStats() {
  closeMenu();
  renderStats('today');
  els.statsPanel.classList.remove('hidden');
  state.openPanels.add('stats-panel');
  bringPanelToFront(els.statsPanel);
}

// ============================================================================
// Habits
// ============================================================================

function renderHabits() {
  const d = dateStr(state.habitDate);
  const isToday = d === today();
  els.habitsDateLabel.textContent = isToday ? 'Today' : formatDate(state.habitDate);

  if (state.habits.length === 0) {
    els.habitsList.innerHTML = '<div class="habits-empty">No habits yet. Click + Add Habit to start.</div>';
    return;
  }

  const checks = state.habitChecks[d] || {};
  els.habitsList.innerHTML = state.habits.map(h => `
    <div class="habit-item" data-id="${h.id}">
      <div class="habit-check ${checks[h.id] ? 'done' : ''}" data-habit="${h.id}">${checks[h.id] ? '✓' : ''}</div>
      <span class="habit-icon">${h.icon}</span>
      <span class="habit-name">${escHtml(h.name)}</span>
      <span class="habit-streak">${getHabitStreak(h.id)} 🔥</span>
    </div>
  `).join('');

  els.habitStreakCount.textContent = calculateHabitStreak();
}

function getHabitStreak(habitId) {
  let streak = 0;
  const now = new Date();
  for (let i = 0; i < 365; i++) {
    const d = new Date(now); d.setDate(d.getDate() - i);
    const checks = state.habitChecks[dateStr(d)] || {};
    if (checks[habitId]) streak++;
    else if (i > 0) break;
  }
  return streak;
}

function calculateHabitStreak() {
  if (state.habits.length === 0) return 0;
  let streak = 0;
  const now = new Date();
  for (let i = 0; i < 365; i++) {
    const d = new Date(now); d.setDate(d.getDate() - i);
    const checks = state.habitChecks[dateStr(d)] || {};
    const allDone = state.habits.every(h => checks[h.id]);
    if (allDone) streak++;
    else if (i > 0) break;
  }
  return streak;
}

function toggleHabit(habitId) {
  const d = dateStr(state.habitDate);
  if (!state.habitChecks[d]) state.habitChecks[d] = {};
  state.habitChecks[d][habitId] = !state.habitChecks[d][habitId];
  save();
  renderHabits();
}

function openHabits() {
  closeMenu();
  state.habitDate = new Date();
  renderHabits();
  els.habitsPanel.classList.remove('hidden');
  state.openPanels.add('habits-panel');
  bringPanelToFront(els.habitsPanel);
}

function openHabitPopup() {
  els.habitName.value = '';
  els.habitIcon.value = '💪';
  els.habitFreq.value = 'daily';
  els.habitPopup.classList.remove('hidden');
  els.habitName.focus();
}

function saveHabit() {
  const name = els.habitName.value.trim();
  if (!name) return;
  state.habits.push({ id: 'h_' + Date.now(), name, icon: els.habitIcon.value, freq: els.habitFreq.value });
  save();
  renderHabits();
  els.habitPopup.classList.add('hidden');
  toast('Habit added');
}

// ============================================================================
// Calendar
// ============================================================================

function openCalendar() {
  closeMenu();
  state.selectedDate = today();
  renderCalendar();
  els.calendarPanel.classList.remove('hidden');
  state.openPanels.add('calendar-panel');
  bringPanelToFront(els.calendarPanel);
}

function renderCalendar() {
  const d = state.calendarDate;
  const year = d.getFullYear();
  const month = d.getMonth();
  const months = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
  els.calendarMonth.textContent = `${months[month]} ${year}`;

  const firstDay = new Date(year, month, 1).getDay();
  const daysInMonth = new Date(year, month + 1, 0).getDate();
  const prevDays = new Date(year, month, 0).getDate();
  const todayStr = today();

  const allTasks = [...state.calendarTasks];
  state.blocks.forEach(b => (b.todos || []).filter(t => t.date).forEach(t => allTasks.push({ ...t, start: t.date, end: t.date })));

  let html = '';
  for (let i = firstDay - 1; i >= 0; i--) html += `<div class="cal-day other-month">${prevDays - i}</div>`;

  for (let day = 1; day <= daysInMonth; day++) {
    const ds = `${year}-${String(month + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
    const isToday = ds === todayStr;
    const isSelected = ds === state.selectedDate;
    const hasTask = allTasks.some(t => dateInRange(ds, t.start || t.date, t.end || t.date));
    let cls = 'cal-day';
    if (isToday) cls += ' today';
    if (isSelected) cls += ' selected';
    if (hasTask) cls += ' has-task';
    html += `<div class="${cls}" data-date="${ds}">${day}</div>`;
  }

  els.calendarGrid.innerHTML = html;
  renderDayTasks();
}

function renderDayTasks() {
  if (!state.selectedDate) { els.dayTaskList.innerHTML = '<div class="day-empty">Select a day</div>'; return; }

  els.selectedDateLabel.textContent = formatDate(new Date(state.selectedDate + 'T12:00:00'));

  const allTasks = [...state.calendarTasks];
  state.blocks.forEach(b => (b.todos || []).filter(t => t.date).forEach(t => allTasks.push({ ...t, start: t.date, end: t.date, blockName: b.name })));

  const dayTasks = allTasks.filter(t => dateInRange(state.selectedDate, t.start || t.date, t.end || t.date));

  if (dayTasks.length === 0) {
    els.dayTaskList.innerHTML = '<div class="day-empty">No tasks</div>';
    return;
  }

  els.dayTaskList.innerHTML = dayTasks.map(t => `
    <div class="day-task-item status-${t.status || 'not_started'}">
      <div>${escHtml(t.title || t.text)}</div>
    </div>
  `).join('');
}

function openCalTaskPopup() {
  els.calTaskTitle.value = '';
  els.calTaskStart.value = state.selectedDate || today();
  els.calTaskEnd.value = '';
  els.calTaskStatus.value = 'not_started';
  els.calTaskPopup.classList.remove('hidden');
  els.calTaskTitle.focus();
}

function saveCalTask() {
  const title = els.calTaskTitle.value.trim();
  if (!title) return;
  state.calendarTasks.push({
    id: 'ct_' + Date.now(), title,
    start: els.calTaskStart.value || state.selectedDate,
    end: els.calTaskEnd.value || els.calTaskStart.value,
    status: els.calTaskStatus.value,
  });
  save();
  renderCalendar();
  els.calTaskPopup.classList.add('hidden');
  toast('Task added');
}

// ============================================================================
// All Tasks
// ============================================================================

function openTasks() {
  closeMenu();
  state.taskFilter = 'all';
  state.taskSearchQuery = '';
  state.selectedTasks = [];
  if (els.taskSearchInput) els.taskSearchInput.value = '';
  if (els.taskSortSelect) els.taskSortSelect.value = state.taskSort;
  document.querySelectorAll('.status-tab').forEach(t => t.classList.toggle('active', t.dataset.status === 'all'));
  updateBulkActionsBar();
  renderAllTasks();
  els.tasksPanel.classList.remove('hidden');
  state.openPanels.add('tasks-panel');
  bringPanelToFront(els.tasksPanel);
}

function getDueDateStatus(dateStr) {
  if (!dateStr) return null;
  const today = new Date(); today.setHours(0, 0, 0, 0);
  const dueDate = new Date(dateStr + 'T00:00:00');
  const diffDays = Math.floor((dueDate - today) / (1000 * 60 * 60 * 24));
  if (diffDays < 0) return 'overdue';
  if (diffDays === 0) return 'due-today';
  if (diffDays <= 7) return 'due-week';
  return null;
}

function sortTasks(todos) {
  const priorityOrder = { high: 0, medium: 1, low: 2, none: 3 };
  const statusOrder = { in_progress: 0, not_started: 1, on_hold: 2, completed: 3 };

  return [...todos].sort((a, b) => {
    switch (state.taskSort) {
      case 'priority':
        return (priorityOrder[a.priority || 'none'] || 3) - (priorityOrder[b.priority || 'none'] || 3);
      case 'status':
        return (statusOrder[a.status || 'not_started'] || 1) - (statusOrder[b.status || 'not_started'] || 1);
      case 'date':
        if (!a.date && !b.date) return 0;
        if (!a.date) return 1;
        if (!b.date) return -1;
        return a.date.localeCompare(b.date);
      case 'created':
        return (a.id || '').localeCompare(b.id || '');
      default: // block
        return 0;
    }
  });
}

function renderAllTasks() {
  let todos = [];
  state.blocks.forEach(b => (b.todos || []).forEach(t => todos.push({ ...t, blockId: b.id, blockName: b.name, blockIcon: b.icon })));

  // Apply status filter
  let filtered = state.taskFilter === 'all' ? todos : todos.filter(t => (t.status || 'not_started') === state.taskFilter);

  // Apply search filter
  if (state.taskSearchQuery) {
    const q = state.taskSearchQuery.toLowerCase();
    filtered = filtered.filter(t =>
      t.text.toLowerCase().includes(q) ||
      (t.tags || []).some(tag => tag.toLowerCase().includes(q)) ||
      t.blockName.toLowerCase().includes(q)
    );
  }

  // Apply sorting
  filtered = sortTasks(filtered);

  if (filtered.length === 0) {
    els.allTasksList.innerHTML = '<div class="tasks-empty">No tasks found</div>';
    return;
  }

  // Group by block if sorting by block
  if (state.taskSort === 'block') {
    const groups = {};
    filtered.forEach(t => {
      if (!groups[t.blockId]) groups[t.blockId] = { name: t.blockName, icon: t.blockIcon, todos: [] };
      groups[t.blockId].todos.push(t);
    });

    let html = '';
    Object.entries(groups).forEach(([blockId, group]) => {
      html += `<div class="task-group">
        <div class="task-group-header">
          <span>${group.icon}</span>
          <span class="task-group-name">${escHtml(group.name)}</span>
          <span class="task-group-count">${group.todos.length}</span>
        </div>
        ${group.todos.map(t => renderTaskItem(t, blockId)).join('')}
      </div>`;
    });
    els.allTasksList.innerHTML = html;
  } else {
    // Flat list for other sort modes
    els.allTasksList.innerHTML = filtered.map(t => renderTaskItem(t, t.blockId)).join('');
  }

  // Add event listeners for task items
  initTaskItemEvents();
}

function renderTaskItem(t, blockId) {
  const dueStatus = getDueDateStatus(t.date);
  const isSelected = state.selectedTasks.some(s => s.taskId === t.id && s.blockId === blockId);

  let dueBadge = '';
  if (dueStatus === 'overdue') dueBadge = '<span class="due-badge overdue">Overdue</span>';
  else if (dueStatus === 'due-today') dueBadge = '<span class="due-badge due-today">Due Today</span>';
  else if (dueStatus === 'due-week') dueBadge = '<span class="due-badge due-week">This Week</span>';

  return `
    <div class="global-task-item ${dueStatus || ''}" data-block="${blockId}" data-todo="${t.id}">
      <div class="task-checkbox ${isSelected ? 'checked' : ''}" data-block="${blockId}" data-todo="${t.id}"></div>
      <div class="task-status-dot ${t.status || 'not_started'}"></div>
      <div class="global-task-info">
        <div class="global-task-text ${t.status === 'completed' ? 'done' : ''}">
          ${escHtml(t.text)}
          ${t.priority && t.priority !== 'none' ? `<span class="priority-badge">${t.priority === 'high' ? '🔴' : t.priority === 'medium' ? '🟡' : '🟢'}</span>` : ''}
          ${dueBadge}
            </div>
        <div class="global-task-meta">
          ${t.date ? `<span class="todo-date">${t.date}</span>` : ''}
          ${t.tags?.length ? t.tags.map(tag => `<span class="todo-tag">${escHtml(tag)}</span>`).join('') : ''}
          ${state.taskSort !== 'block' ? `<span class="task-block-name">${t.blockIcon} ${escHtml(t.blockName)}</span>` : ''}
            </div>
            </div>
      <span class="status-badge ${t.status || 'not_started'}" data-block="${blockId}" data-todo="${t.id}">${STATUSES[t.status || 'not_started']?.label}</span>
        </div>
    `;
}

// Event delegation for all tasks list - attach once during init
function initTaskListEventDelegation() {
  if (!els.allTasksList) return;

  // Handle all clicks via event delegation
  els.allTasksList.addEventListener('click', e => {
    // Checkbox click for bulk selection
    const checkbox = e.target.closest('.task-checkbox');
    if (checkbox) {
      e.stopPropagation();
      const blockId = checkbox.dataset.block;
      const taskId = checkbox.dataset.todo;
      toggleTaskSelection(taskId, blockId);
      return;
    }

    // Status badge click for quick toggle
    const badge = e.target.closest('.status-badge');
    if (badge) {
      e.stopPropagation();
      const blockId = badge.dataset.block;
      const taskId = badge.dataset.todo;
      cycleTaskStatus(taskId, blockId);
      return;
    }

    // Click on task item to open block editor
    const item = e.target.closest('.global-task-item');
    if (item) {
      openBlockEditor(item.dataset.block);
    }
  });

  // Context menu via event delegation
  els.allTasksList.addEventListener('contextmenu', e => {
    const item = e.target.closest('.global-task-item');
    if (item) {
      e.preventDefault();
      const blockId = item.dataset.block;
      const taskId = item.dataset.todo;
      showTaskContextMenu(e, taskId, blockId);
    }
  });
}

// Deprecated - now uses event delegation (initTaskListEventDelegation)
function initTaskItemEvents() {
  // No longer adds event listeners - handled by event delegation
}

function toggleTaskSelection(taskId, blockId) {
  const index = state.selectedTasks.findIndex(s => s.taskId === taskId && s.blockId === blockId);
  if (index > -1) {
    state.selectedTasks.splice(index, 1);
  } else {
    state.selectedTasks.push({ taskId, blockId });
  }
  updateBulkActionsBar();
  renderAllTasks();
}

function updateBulkActionsBar() {
  if (state.selectedTasks.length > 0) {
    els.bulkActionsBar.classList.remove('hidden');
    els.selectedCount.textContent = `${state.selectedTasks.length} selected`;
  } else {
    els.bulkActionsBar.classList.add('hidden');
  }
}

function clearTaskSelection() {
  state.selectedTasks = [];
  updateBulkActionsBar();
  renderAllTasks();
}

function cycleTaskStatus(taskId, blockId) {
  const block = state.blocks.find(b => b.id === blockId);
  if (!block) return;
  const task = (block.todos || []).find(t => t.id === taskId);
  if (!task) return;

  const statusCycle = ['not_started', 'in_progress', 'completed'];
  const currentIndex = statusCycle.indexOf(task.status || 'not_started');
  task.status = statusCycle[(currentIndex + 1) % statusCycle.length];

  if (task.status === 'completed') {
    updateTodayStats();
    const t = today();
    if (!state.stats.daily[t]) state.stats.daily[t] = { completed: 0, pomodoros: 0, focusMinutes: 0 };
    state.stats.daily[t].completed++;
    state.stats.completed++;
  }

  save();
  renderAllTasks();
  updateTodayProgress();
  toast(`Status: ${STATUSES[task.status].label}`);
}

// ============================================================================
// Task Context Menu
// ============================================================================

function showTaskContextMenu(e, taskId, blockId) {
  const block = state.blocks.find(b => b.id === blockId);
  if (!block) return;
  const task = (block.todos || []).find(t => t.id === taskId);
  if (!task) return;

  state.contextTask = { task, blockId, taskId };

  els.taskContextMenu.style.left = `${e.clientX}px`;
  els.taskContextMenu.style.top = `${e.clientY}px`;
  els.taskContextMenu.classList.remove('hidden');
}

function hideTaskContextMenu() {
  els.taskContextMenu.classList.add('hidden');
  state.contextTask = null;
}

function editTaskFromContext() {
  if (!state.contextTask) return;
  const { task } = state.contextTask;

  els.editTaskText.value = task.text;
  els.editTaskPriority.value = task.priority || 'none';
  els.editTaskStatus.value = task.status || 'not_started';
  els.editTaskDate.value = task.date || '';
  els.editTaskTags.value = (task.tags || []).join(', ');

  els.editTaskPopup.classList.remove('hidden');
  els.editTaskText.focus();
  hideTaskContextMenu();
}

function saveEditedTask() {
  if (!state.contextTask) return;
  const { task, blockId } = state.contextTask;
  const block = state.blocks.find(b => b.id === blockId);
  if (!block) return;

  const todoIndex = block.todos.findIndex(t => t.id === task.id);
  if (todoIndex === -1) return;

  block.todos[todoIndex] = {
    ...task,
    text: els.editTaskText.value.trim() || task.text,
    priority: els.editTaskPriority.value,
    status: els.editTaskStatus.value,
    date: els.editTaskDate.value,
    tags: els.editTaskTags.value.split(',').map(t => t.trim()).filter(t => t),
  };

  save();
  renderAllTasks();
  updateTodayProgress();
  els.editTaskPopup.classList.add('hidden');
  state.contextTask = null;
  toast('Task updated');
}

function changeTaskStatusFromContext(status) {
  if (!state.contextTask) return;
  const { blockId, taskId } = state.contextTask;
  const block = state.blocks.find(b => b.id === blockId);
  if (!block) return;

  const task = block.todos.find(t => t.id === taskId);
  if (!task) return;

  const wasCompleted = task.status === 'completed';
  task.status = status;

  if (status === 'completed' && !wasCompleted) {
    updateTodayStats();
    const t = today();
    if (!state.stats.daily[t]) state.stats.daily[t] = { completed: 0, pomodoros: 0, focusMinutes: 0 };
    state.stats.daily[t].completed++;
    state.stats.completed++;
  }

  save();
  renderAllTasks();
  updateTodayProgress();
  hideTaskContextMenu();
  toast(`Status: ${STATUSES[status].label}`);
}

function changeTaskPriorityFromContext(priority) {
  if (!state.contextTask) return;
  const { blockId, taskId } = state.contextTask;
  const block = state.blocks.find(b => b.id === blockId);
  if (!block) return;

  const task = block.todos.find(t => t.id === taskId);
  if (task) {
    task.priority = priority;
    save();
    renderAllTasks();
    hideTaskContextMenu();
    toast('Priority updated');
  }
}

function openMoveTaskPopup() {
  if (!state.contextTask) return;

  els.moveTaskBlock.innerHTML = state.blocks
    .filter(b => b.id !== state.contextTask.blockId)
    .map(b => `<option value="${b.id}">${b.icon} ${escHtml(b.name)}</option>`)
    .join('');

  els.moveTaskPopup.classList.remove('hidden');
  hideTaskContextMenu();
}

function moveTaskToBlock() {
  if (!state.contextTask) return;
  const { blockId: sourceBlockId, taskId } = state.contextTask;
  const targetBlockId = els.moveTaskBlock.value;

  if (!targetBlockId) return;

  const sourceBlock = state.blocks.find(b => b.id === sourceBlockId);
  const targetBlock = state.blocks.find(b => b.id === targetBlockId);

  if (!sourceBlock || !targetBlock) return;

  const taskIndex = sourceBlock.todos.findIndex(t => t.id === taskId);
  if (taskIndex === -1) return;

  const [task] = sourceBlock.todos.splice(taskIndex, 1);
  targetBlock.todos = targetBlock.todos || [];
  targetBlock.todos.push(task);

  save();
  renderAllTasks();
  els.moveTaskPopup.classList.add('hidden');
  state.contextTask = null;
  toast(`Moved to ${targetBlock.name}`);
}

function duplicateTaskFromContext() {
  if (!state.contextTask) return;
  const { task, blockId } = state.contextTask;
  const block = state.blocks.find(b => b.id === blockId);
  if (!block) return;

  const newTask = {
    ...task,
    id: 'todo_' + Date.now(),
    text: task.text + ' (copy)',
    status: 'not_started',
  };

  block.todos.push(newTask);
  save();
  renderAllTasks();
  updateTodayProgress();
  hideTaskContextMenu();
  toast('Task duplicated');
}

function toggleCompleteFromContext() {
  if (!state.contextTask) return;
  const { blockId, taskId } = state.contextTask;
  cycleTaskStatus(taskId, blockId);
  hideTaskContextMenu();
}

function deleteTaskFromContext() {
  if (!state.contextTask) return;
  const { blockId, taskId } = state.contextTask;
  const block = state.blocks.find(b => b.id === blockId);
  if (!block) return;

  block.todos = block.todos.filter(t => t.id !== taskId);
  save();
  renderAllTasks();
  updateTodayProgress();
  hideTaskContextMenu();
  toast('Task deleted');
}

// ============================================================================
// Global Task Creation (from All Tasks panel)
// ============================================================================

function openGlobalTaskPopup() {
  els.globalTaskText.value = '';
  els.globalTaskBlock.innerHTML = '<option value="">Select block...</option>' +
    state.blocks.map(b => `<option value="${b.id}">${b.icon} ${escHtml(b.name)}</option>`).join('');
  els.globalTaskPriority.value = 'none';
  els.globalTaskStatus.value = 'not_started';
  els.globalTaskDate.value = '';
  els.globalTaskTags.value = '';
  els.globalTaskPopup.classList.remove('hidden');
  els.globalTaskText.focus();
}

function saveGlobalTask() {
  const text = els.globalTaskText.value.trim();
  const blockId = els.globalTaskBlock.value;

  if (!text) { toast('Please enter task description'); return; }
  if (!blockId) { toast('Please select a block'); return; }

  const block = state.blocks.find(b => b.id === blockId);
  if (!block) return;

  const tags = els.globalTaskTags.value.split(',').map(t => t.trim()).filter(t => t);

  block.todos = block.todos || [];
  block.todos.push({
    id: 'todo_' + Date.now(),
    text,
    status: els.globalTaskStatus.value,
    priority: els.globalTaskPriority.value,
    date: els.globalTaskDate.value,
    tags,
  });

  save();
  renderAllTasks();
  updateTodayProgress();
  els.globalTaskPopup.classList.add('hidden');
  toast('Task added');
}

// ============================================================================
// Bulk Task Operations
// ============================================================================

function bulkChangeStatus(status) {
  state.selectedTasks.forEach(({ taskId, blockId }) => {
    const block = state.blocks.find(b => b.id === blockId);
    if (!block) return;
    const task = block.todos.find(t => t.id === taskId);
    if (task) task.status = status;
  });

  save();
  clearTaskSelection();
  updateTodayProgress();
  toast(`Updated ${state.selectedTasks.length} tasks`);
}

function bulkMoveTasks() {
  if (state.selectedTasks.length === 0) return;

  els.moveTaskBlock.innerHTML = state.blocks
    .map(b => `<option value="${b.id}">${b.icon} ${escHtml(b.name)}</option>`)
    .join('');

  // Store that this is a bulk move
  state.contextTask = { bulk: true };
  els.moveTaskPopup.classList.remove('hidden');
}

function bulkMoveTasksConfirm() {
  if (!state.contextTask?.bulk) return;

  const targetBlockId = els.moveTaskBlock.value;
  const targetBlock = state.blocks.find(b => b.id === targetBlockId);
  if (!targetBlock) return;

  targetBlock.todos = targetBlock.todos || [];

  state.selectedTasks.forEach(({ taskId, blockId }) => {
    if (blockId === targetBlockId) return; // Skip if same block
    const sourceBlock = state.blocks.find(b => b.id === blockId);
    if (!sourceBlock) return;

    const taskIndex = sourceBlock.todos.findIndex(t => t.id === taskId);
    if (taskIndex === -1) return;

    const [task] = sourceBlock.todos.splice(taskIndex, 1);
    targetBlock.todos.push(task);
  });

  save();
  els.moveTaskPopup.classList.add('hidden');
  clearTaskSelection();
  toast(`Moved tasks to ${targetBlock.name}`);
}

function bulkDeleteTasks() {
  if (!confirm(`Delete ${state.selectedTasks.length} tasks?`)) return;

  state.selectedTasks.forEach(({ taskId, blockId }) => {
    const block = state.blocks.find(b => b.id === blockId);
    if (block) {
      block.todos = block.todos.filter(t => t.id !== taskId);
    }
  });

  save();
  clearTaskSelection();
  updateTodayProgress();
  toast('Tasks deleted');
}

// ============================================================================
// Today Progress
// ============================================================================

function updateTodayProgress() {
  let done = 0, total = 0;
  state.blocks.forEach(b => (b.todos || []).forEach(t => { total++; if (t.status === 'completed') done++; }));
  els.todayTasksDone.textContent = done;
  els.todayTasksTotal.textContent = total;
  els.progressFill.style.width = total > 0 ? `${(done / total) * 100}%` : '0%';
}

// ============================================================================
// Mind Map
// ============================================================================

function toggleMindmapFullscreen() {
  const panel = document.getElementById('mindmap-view');
  if (panel) {
    panel.classList.toggle('fullscreen');
    const btn = document.getElementById('btn-fullscreen');
    if (btn) {
      btn.textContent = panel.classList.contains('fullscreen') ? '⇱' : '⛶';
    }
  }
}

function openMindmap() {
  closeMenu();
  if (!els.mindmapView) {
    console.error('Mindmap view element not found');
    return;
  }
  els.mindmapView.classList.remove('hidden');
  state.openPanels.add('mindmap-view');
  bringPanelToFront(els.mindmapView);
  renderMindmap();
}

function renderMindmap() {
  console.log('Rendering mindmap, blocks:', state.blocks.length);

  // Guard against missing elements
  if (!els.blocksLayer) {
    console.error('Blocks layer element not found');
    return;
  }

  if (!state.blocks || state.blocks.length === 0) {
    els.blocksLayer.innerHTML = '<div style="padding:20px;color:var(--text-muted);">No blocks yet. Click "+ Add Block" to create one.</div>';
    return;
  }

  // Ensure each block has required properties
  const validBlocks = state.blocks.map(b => ({
    id: b.id || 'block-' + Date.now(),
    name: b.name || 'Untitled',
    type: b.type || 'note',
    icon: b.icon || '📝',
    x: typeof b.x === 'number' ? b.x : 100,
    y: typeof b.y === 'number' ? b.y : 100,
    children: b.children || [],
    todos: b.todos || [],
    parentId: b.parentId || null
  }));

  els.blocksLayer.innerHTML = validBlocks.map(b => `
    <div class="block-node" data-id="${b.id}" style="left:${b.x}px;top:${b.y}px">
      <div class="node-header">
        <span class="node-icon">${b.icon}</span>
        <span class="node-name">${escHtml(b.name)}</span>
      </div>
      <div class="node-meta">${b.type}</div>
      <div class="node-badges">
        ${b.children?.length ? `<span class="node-badge">📦 ${b.children.length}</span>` : ''}
        ${b.todos?.length ? `<span class="node-badge">✅ ${b.todos.filter(t => t.status !== 'completed').length}/${b.todos.length}</span>` : ''}
      </div>
    </div>
  `).join('');

  renderConnections();
  initBlockEvents();
  console.log('Mindmap rendered successfully, blocks:', validBlocks.length);
}

function renderConnections() {
  let paths = '';
  state.blocks.forEach(b => {
    if (b.parentId) {
      const parent = state.blocks.find(p => p.id === b.parentId);
      if (parent) {
        const x1 = parent.x + 85, y1 = parent.y + 35, x2 = b.x, y2 = b.y + 35;
        const mx = (x1 + x2) / 2;
        paths += `<path d="M${x1},${y1} C${mx},${y1} ${mx},${y2} ${x2},${y2}"/>`;
      }
    }
  });
  els.connectionsSvg.innerHTML = paths;
}

// Event delegation for blocks layer - attach once during init
function initBlockEventDelegation() {
  if (!els.blocksLayer) return;

  els.blocksLayer.addEventListener('mousedown', e => {
    const node = e.target.closest('.block-node');
    if (!node || e.button !== 0) return;

    const block = state.blocks.find(b => b.id === node.dataset.id);
    if (!block) return;

    state.dragging = block;
    state.dragOffset = { x: e.clientX - block.x, y: e.clientY - block.y };
    node.classList.add('dragging');
    e.preventDefault();
  });

  els.blocksLayer.addEventListener('contextmenu', e => {
    const node = e.target.closest('.block-node');
    if (!node) return;

    e.preventDefault();
    state.contextBlock = state.blocks.find(b => b.id === node.dataset.id);
    if (els.contextMenu) {
      els.contextMenu.style.left = `${e.clientX}px`;
      els.contextMenu.style.top = `${e.clientY}px`;
      els.contextMenu.classList.remove('hidden');
    }
  });

  els.blocksLayer.addEventListener('dblclick', e => {
    const node = e.target.closest('.block-node');
    if (node) {
      openBlockEditor(node.dataset.id);
    }
  });
}

// Deprecated - now uses event delegation (initBlockEventDelegation)
function initBlockEvents() {
  // No longer adds event listeners - handled by event delegation
}

function handleMouseMove(e) {
  if (!state.dragging) return;
  state.dragging.x = Math.max(10, e.clientX - state.dragOffset.x);
  state.dragging.y = Math.max(10, e.clientY - state.dragOffset.y);
  const node = els.blocksLayer.querySelector(`[data-id="${state.dragging.id}"]`);
  if (node) { node.style.left = `${state.dragging.x}px`; node.style.top = `${state.dragging.y}px`; }
  renderConnections();
}

function handleMouseUp() {
  if (state.dragging) {
    const node = els.blocksLayer.querySelector(`[data-id="${state.dragging.id}"]`);
    if (node) node.classList.remove('dragging');
    state.dragging = null;
    save();
  }
}

function hideContextMenu() { els.contextMenu.classList.add('hidden'); state.contextBlock = null; }

// ============================================================================
// Block Actions
// ============================================================================

function openBlockPopup(parentId = null) {
  state.newBlockParent = parentId;
  els.newBlockName.value = '';
  document.querySelectorAll('.type-opt').forEach(b => b.classList.toggle('selected', b.dataset.type === 'note'));
  els.blockPopup.classList.remove('hidden');
  els.newBlockName.focus();
}

function createBlock() {
  const name = els.newBlockName.value.trim();
  if (!name) return;
  const type = document.querySelector('.type-opt.selected')?.dataset.type || 'note';
  const icons = { note: '📝', task: '✅', project: '📁', idea: '💡' };

  // Position new blocks in a spread pattern across the screen
  let x = 100 + (state.blocks.length * 50) % 600;
  let y = 100 + Math.floor(state.blocks.length / 3) * 120;

  // If creating as child of another block
  if (state.newBlockParent) {
    const parent = state.blocks.find(b => b.id === state.newBlockParent);
    if (parent) {
      const siblings = state.blocks.filter(b => b.parentId === state.newBlockParent);
      x = parent.x + 200; y = parent.y + (siblings.length * 80);
    }
  }

  const newBlock = { id: Date.now().toString(), name, type, icon: icons[type], notes: '', todos: [], dateStart: '', dateEnd: '', x, y, parentId: state.newBlockParent || null, children: [] };

  if (state.newBlockParent) {
    const parent = state.blocks.find(b => b.id === state.newBlockParent);
    if (parent) { parent.children = parent.children || []; parent.children.push(newBlock.id); }
  }

  state.blocks.push(newBlock);
  save();
  els.blockPopup.classList.add('hidden');
  if (!els.mindmapView.classList.contains('hidden')) renderMindmap();
  else if (!els.blockEditor.classList.contains('hidden')) renderSubblocks();

  // Sync with calendar and todos
  syncBlocksToCalendarAndTodos();

  toast('Block created');
}

function openRenamePopup() {
  if (!state.contextBlock) return;
  els.renameInput.value = state.contextBlock.name;
  els.renamePopup.classList.remove('hidden');
  els.renameInput.focus();
  hideContextMenu();
}

function saveRename() {
  if (!state.contextBlock || !els.renameInput.value.trim()) return;
  state.contextBlock.name = els.renameInput.value.trim();
  save(); renderMindmap();
  els.renamePopup.classList.add('hidden');
  toast('Renamed');
}

function openIconPopup() {
  if (!state.contextBlock) return;
  els.iconGrid.innerHTML = ICONS.map(icon => `<button class="icon-option" data-icon="${icon}">${icon}</button>`).join('');
  els.iconPopup.classList.remove('hidden');
  hideContextMenu();
}

function selectIcon(icon) {
  if (!state.contextBlock) return;
  state.contextBlock.icon = icon;
  save(); renderMindmap();
  if (state.currentBlock?.id === state.contextBlock.id) els.blockIconBtn.textContent = icon;
  els.iconPopup.classList.add('hidden');
  toast('Icon changed');
}

function deleteBlock() {
  if (!state.contextBlock) {
    console.error('No block selected for deletion');
    return;
  }

  const id = state.contextBlock.id;
  console.log('Deleting block:', id);

  // Find and update parent
  const parent = state.blocks.find(b => b.children?.includes(id));
  if (parent) {
    parent.children = parent.children.filter(c => c !== id);
  }

  // Recursive function to remove block and its children
  function removeWithChildren(blockId) {
    const block = state.blocks.find(b => b.id === blockId);
    if (block?.children) {
      block.children.forEach(removeWithChildren);
    }
    state.blocks = state.blocks.filter(b => b.id !== blockId);
  }

  removeWithChildren(id);

  // Save and re-render
  save();

  // Check if mindmap is visible and re-render
  if (els.mindmapView && !els.mindmapView.classList.contains('hidden')) {
    renderMindmap();
  }

  // Sync with calendar and todos after deletion
  syncBlocksToCalendarAndTodos();

  hideContextMenu();
  toast('Block deleted');
}

// ============================================================================
// Block/Task Sync with Calendar and Todos
// ============================================================================

function syncBlocksToCalendarAndTodos() {
  console.log('Syncing blocks to calendar and todos...');

  // Update calendar view if open
  if (els.calendarPanel && !els.calendarPanel.classList.contains('hidden')) {
    renderCalendar();
  }

  // Update tasks view if open
  if (els.tasksPanel && !els.tasksPanel.classList.contains('hidden')) {
    renderAllTasks();
  }

  // Update mini calendar and todos in focus panel
  if (state.focusSection === 'calendar') {
    renderMiniCalendar();
  }
  if (state.focusSection === 'todos') {
    renderMiniTodos();
  }

  // Update today's progress
  updateTodayProgress();

  console.log('Sync complete');
}

// ============================================================================
// Block Editor
// ============================================================================

function openBlockEditor(blockId) {
  const block = state.blocks.find(b => b.id === blockId);
  if (!block) return;
  state.currentBlock = block;
  stopTimer();

  els.blockIconBtn.textContent = block.icon;
  els.blockTitle.value = block.name;
  els.blockDate.value = block.dateStart || '';
  els.blockDateEnd.value = block.dateEnd || '';
  els.blockNotes.innerHTML = block.notes || '';
  state.timer.seconds = 0;
  updateTimerDisplay();

  renderTodos();
  renderSubblocks();

  closeAllPanels();
  els.blockEditor.classList.remove('hidden');
}

function saveCurrentBlock() {
  if (!state.currentBlock) return;
  state.currentBlock.name = els.blockTitle.value.trim() || 'Untitled';
  state.currentBlock.notes = els.blockNotes.innerHTML;
  state.currentBlock.dateStart = els.blockDate.value;
  state.currentBlock.dateEnd = els.blockDateEnd.value;
  save();
}

function closeEditor() {
  saveCurrentBlock(); stopTimer();
  state.currentBlock = null;
  els.blockEditor.classList.add('hidden');
  openMindmap();
}

function updateTimerDisplay() { els.timerValue.textContent = formatTimeFull(state.timer.seconds); }

function startTimer() {
  if (state.timer.running) return;
  state.timer.running = true;
  els.btnTimerStart.classList.add('hidden'); els.btnTimerPause.classList.remove('hidden');
  state.timer.interval = setInterval(() => { state.timer.seconds++; updateTimerDisplay(); }, 1000);
}

function pauseTimer() {
  state.timer.running = false;
  clearInterval(state.timer.interval);
  els.btnTimerPause.classList.add('hidden'); els.btnTimerStart.classList.remove('hidden');
}

function stopTimer() { pauseTimer(); state.timer.seconds = 0; updateTimerDisplay(); }

function renderTodos() {
  const todos = state.currentBlock?.todos || [];
  if (todos.length === 0) {
    els.todoList.innerHTML = '<div class="todo-empty">No to-dos yet</div>';
    return;
  }

  els.todoList.innerHTML = todos.map(t => `
    <div class="todo-item" data-id="${t.id}">
      <div class="todo-checkbox ${t.status === 'completed' ? 'checked' : ''}" data-todo="${t.id}">${t.status === 'completed' ? '✓' : ''}</div>
      <div class="todo-content">
        <div class="todo-text ${t.status === 'completed' ? 'done' : ''}">${escHtml(t.text)}${t.priority && t.priority !== 'none' ? ` ${t.priority === 'high' ? '🔴' : t.priority === 'medium' ? '🟡' : '🟢'}` : ''}</div>
        <div class="todo-meta">
          <span class="status-badge ${t.status || 'not_started'}">${STATUSES[t.status || 'not_started']?.label}</span>
          ${t.date ? `<span class="todo-date">${t.date}</span>` : ''}
          ${t.tags?.map(tag => `<span class="todo-tag">${escHtml(tag)}</span>`).join('') || ''}
            </div>
            </div>
            </div>
  `).join('');
}

function toggleTodoStatus(todoId) {
  if (!state.currentBlock) return;
  const todo = state.currentBlock.todos.find(t => t.id === todoId);
  if (todo) {
    const wasCompleted = todo.status === 'completed';
    todo.status = wasCompleted ? 'not_started' : 'completed';
    if (!wasCompleted) {
      updateTodayStats();
      const t = today();
      if (!state.stats.daily[t]) state.stats.daily[t] = { completed: 0, pomodoros: 0, focusMinutes: 0 };
      state.stats.daily[t].completed++;
      state.stats.completed++;
    }
    save(); renderTodos(); updateTodayProgress();
  }
}

function openTodoPopup() {
  els.todoText.value = '';
  els.todoPriority.value = 'none';
  els.todoStatus.value = 'not_started';
  els.todoDate.value = '';
  els.todoTags.value = '';
  els.todoPopup.classList.remove('hidden');
  els.todoText.focus();
}

function saveTodo() {
  const text = els.todoText.value.trim();
  if (!text || !state.currentBlock) return;
  const tags = els.todoTags.value.split(',').map(t => t.trim()).filter(t => t);
  state.currentBlock.todos.push({
    id: 'todo_' + Date.now(), text,
    status: els.todoStatus.value,
    priority: els.todoPriority.value,
    date: els.todoDate.value,
    tags,
  });
  save(); renderTodos(); updateTodayProgress();
  els.todoPopup.classList.add('hidden');
  toast('To-do added');
}

function renderSubblocks() {
  if (!state.currentBlock) return;
  const children = state.blocks.filter(b => b.parentId === state.currentBlock.id);
  if (children.length === 0) {
    els.subblocksList.innerHTML = '<div class="subblock-empty">No sub-blocks</div>';
    return;
  }
  els.subblocksList.innerHTML = children.map(c => `
    <div class="subblock-item" data-id="${c.id}">
      <span class="subblock-icon">${c.icon}</span>
      <span class="subblock-name">${escHtml(c.name)}</span>
      <span class="subblock-arrow">→</span>
            </div>
  `).join('');
}

// ============================================================================
// Quick Add
// ============================================================================

function openQuickAdd() {
  els.quickTaskText.value = '';
  els.quickTaskBlock.innerHTML = '<option value="">Select block...</option>' +
    state.blocks.map(b => `<option value="${b.id}">${b.icon} ${escHtml(b.name)}</option>`).join('');
  els.quickAddPopup.classList.remove('hidden');
  els.quickTaskText.focus();
}

function saveQuickTask() {
  const text = els.quickTaskText.value.trim();
  const blockId = els.quickTaskBlock.value;
  if (!text || !blockId) return;

  const block = state.blocks.find(b => b.id === blockId);
  if (block) {
    block.todos = block.todos || [];
    block.todos.push({ id: 'todo_' + Date.now(), text, status: 'not_started', priority: 'none', date: '', tags: [] });
    save();
    updateTodayProgress();
    toast('Task added');
  }
  els.quickAddPopup.classList.add('hidden');
}

// ============================================================================
// AI System - Chat, Actions, WebSocket
// ============================================================================

const chatHistory = [];
let aiWebSocket = null;
let aiModels = [];
let currentAiModel = 'llama3.2';

// AI Action Handlers - Execute actions triggered by AI
const aiActionHandlers = {
  create_block: (params) => {
    const name = params.name || 'New Block';
    const type = params.type || 'note';
    const icons = { note: '📝', task: '✅', project: '📁', idea: '💡' };
    const x = Math.max(...state.blocks.map(b => b.x), 0) + 200;
    const newBlock = {
      id: Date.now().toString(),
      name,
      type,
      icon: icons[type] || '📝',
      notes: params.notes || '',
      todos: [],
      dateStart: '',
      dateEnd: '',
      x,
      y: 60,
      parentId: params.parent_id || null,
      children: [],
    };
    state.blocks.push(newBlock);
    save();
    if (!els.mindmapView.classList.contains('hidden')) renderMindmap();
    toast(`Created: ${name}`);
  },

  create_task: (params) => {
    const text = params.text || 'New Task';
    const blockId = params.block_id;

    if (blockId) {
      const block = state.blocks.find(b => b.id === blockId);
      if (block) {
        block.todos = block.todos || [];
        block.todos.push({
          id: 'todo_' + Date.now(),
          text,
          status: params.status || 'not_started',
          priority: params.priority || 'none',
          date: params.due_date || '',
          tags: params.tags || [],
        });
        save();
      }
    } else {
      // Add to first block or create general task
      const firstBlock = state.blocks[0];
      if (firstBlock) {
        firstBlock.todos = firstBlock.todos || [];
        firstBlock.todos.push({
          id: 'todo_' + Date.now(),
          text,
          status: params.status || 'not_started',
          priority: params.priority || 'none',
          date: params.due_date || '',
          tags: [],
        });
        save();
      }
    }
    updateTodayProgress();
    toast(`Task added: ${text}`);
  },

  start_timer: (params) => {
    const minutes = parseInt(params.minutes) || 25;
    state.pomodoro.seconds = minutes * 60;
    state.pomodoro.mode = 'work';
    startPomodoro();
    toast(`Timer started: ${minutes} min`);
  },

  start_pomodoro: (params) => {
    const mode = params.mode || 'work';
    setPomoMode(mode);
    startPomodoro();
    toast(`Pomodoro started: ${mode}`);
  },

  stop_timer: () => {
    pausePomodoro();
    toast('Timer stopped');
  },

  open_panel: (params) => {
    const panel = params.panel?.toLowerCase();
    const panelMap = {
      mindmap: openMindmap,
      tasks: openTasks,
      calendar: openCalendar,
      pomodoro: openFloatingTimer,
      stats: openStats,
      habits: openHabits,
      chat: openChat,
      settings: openSettings,
    };
    if (panelMap[panel]) {
      panelMap[panel]();
      toast(`Opened: ${panel}`);
    }
  },

  change_theme: (params) => {
    const theme = params.theme?.toLowerCase();
    if (theme) {
      applyTheme(theme);
      toast(`Theme: ${theme}`);
    }
  },

  set_focus: (params) => {
    state.currentFocus = params.text || null;
    save();
    updateFocusDisplay();
    toast(`Focus: ${params.text}`);
  },

  show_notification: (params) => {
    showNotification(params.title, params.message, params.icon || '🔔');
  },

  open_browser: (params) => {
    const url = params.url;
    if (url) {
      window.open(url.startsWith('http') ? url : 'https://' + url, '_blank');
      toast(`Opening: ${url}`);
      if (params.instructions) {
        chatHistory.push({ role: 'assistant', content: params.instructions });
        renderChat();
      }
    }
  },

  add_calendar_event: (params) => {
    state.calendarTasks.push({
      id: 'ct_' + Date.now(),
      title: params.title,
      start: params.start,
      end: params.end || params.start,
      status: params.status || 'not_started',
    });
    save();
    if (!els.calendarPanel.classList.contains('hidden')) renderCalendar();
    toast(`Calendar: ${params.title}`);
  },

  create_habit: (params) => {
    state.habits.push({
      id: 'h_' + Date.now(),
      name: params.name,
      icon: params.icon || '🎯',
      freq: params.frequency || 'daily',
    });
    save();
    if (!els.habitsPanel.classList.contains('hidden')) renderHabits();
    toast(`Habit: ${params.name}`);
  },

  start_study_session: (params) => {
    const topic = params.topic || 'Study';
    const duration = parseInt(params.duration) || 25;

    // Set focus
    state.currentFocus = `Studying: ${topic}`;
    save();
    updateFocusDisplay();

    // Start timer
    state.pomodoro.seconds = duration * 60;
    state.pomodoro.mode = 'work';
    startPomodoro();

    toast(`Study session: ${topic} (${duration} min)`);
    showNotification('Study Session Started', `Focus on: ${topic} for ${duration} minutes`, '📚');
  },
};

// Execute actions from AI
function executeAiActions(actions) {
  if (!actions || !Array.isArray(actions)) return;

  actions.forEach(action => {
    const handler = aiActionHandlers[action.type];
    if (handler) {
      try {
        handler(action.params || {});
      } catch (e) {
        console.error('Action error:', action.type, e);
      }
    }
  });
}

// WebSocket Connection
function connectAiWebSocket() {
  if (aiWebSocket && aiWebSocket.readyState === WebSocket.OPEN) return;

  try {
    const wsUrl = CONFIG.API_BASE.replace('http', 'ws') + '/ai/ws';
    aiWebSocket = new WebSocket(wsUrl);

    aiWebSocket.onopen = () => {
      console.log('AI WebSocket connected');
    };

    aiWebSocket.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);

        if (data.type === 'chunk') {
          // Streaming response
          const lastMsg = chatHistory[chatHistory.length - 1];
          if (lastMsg && lastMsg.role === 'assistant' && lastMsg.streaming) {
            lastMsg.content += data.content;
            renderChat();
          }
        } else if (data.type === 'complete') {
          // Response complete
          const lastMsg = chatHistory[chatHistory.length - 1];
          if (lastMsg && lastMsg.streaming) {
            lastMsg.content = data.response;
            lastMsg.streaming = false;
          }
          renderChat();

          // Execute any actions
          if (data.actions) {
            executeAiActions(data.actions);
          }
        } else if (data.type === 'action_result') {
          if (data.frontend_action) {
            executeAiActions([data.frontend_action]);
          }
        }
      } catch (e) {
        console.error('WS message error:', e);
      }
    };

    aiWebSocket.onclose = () => {
      console.log('AI WebSocket closed');
      // Reconnect after delay
      setTimeout(connectAiWebSocket, 5000);
    };

    aiWebSocket.onerror = (e) => {
      console.error('AI WebSocket error:', e);
    };
  } catch (e) {
    console.error('WebSocket connection failed:', e);
  }
}

// Send via WebSocket if available, fallback to HTTP
async function sendChatMessage(text) {
  if (aiWebSocket && aiWebSocket.readyState === WebSocket.OPEN) {
    // Add streaming placeholder
    chatHistory.push({ role: 'assistant', content: '', streaming: true });
    renderChat();

    aiWebSocket.send(JSON.stringify({
      type: 'chat',
      message: text,
      user_id: 'default',
      stream: true,
    }));
  } else {
    // Fallback to HTTP smart chat
    try {
      const res = await fetch(`${CONFIG.API_BASE}/ai/chat/smart`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: text,
          user_id: 'default',
          execute_actions: true,
        }),
      });

      if (res.ok) {
        const data = await res.json();
        chatHistory.push({ role: 'assistant', content: data.response || 'No response' });

        // Execute frontend actions
        if (data.frontend_actions) {
          executeAiActions(data.frontend_actions);
        }
      } else {
        chatHistory.push({ role: 'assistant', content: 'Error getting response.' });
      }
    } catch (e) {
      chatHistory.push({ role: 'assistant', content: 'Connection error. Make sure the backend is running.' });
    }
    renderChat();
  }
}

// Load available AI models
async function loadAiModels() {
  try {
    const res = await fetch(`${CONFIG.API_BASE}/ai/models`);
    if (res.ok) {
      const data = await res.json();
      aiModels = data.models || [];
      currentAiModel = data.current_model || 'llama3.2';
      updateModelSelector();
    }
  } catch (e) {
    console.log('Could not load AI models');
  }
}

// Update model selector UI
function updateModelSelector() {
  const selector = document.getElementById('ai-model-select');
  if (selector && aiModels.length > 0) {
    selector.innerHTML = aiModels.map(m =>
      `<option value="${m.name}" ${m.name === currentAiModel ? 'selected' : ''}>${m.name} (${m.size || '?'})</option>`
    ).join('');
  }
}

// Switch AI model
async function switchAiModel(modelName) {
  try {
    const res = await fetch(`${CONFIG.API_BASE}/ai/models/switch`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ model_name: modelName }),
    });

    if (res.ok) {
      const data = await res.json();
      currentAiModel = data.current_model;
      toast(`Model: ${currentAiModel}`);
    }
  } catch (e) {
    toast('Failed to switch model');
  }
}

function openChat() {
  closeMenu();
  if (els.chatBox.classList.contains('hidden')) {
    els.chatBox.classList.remove('hidden');
    state.openPanels.add('chat-box');
    bringPanelToFront(els.chatBox);
    connectAiWebSocket();
  } else {
    els.chatBox.classList.add('hidden');
    state.openPanels.delete('chat-box');
  }
}

function renderChat() {
  if (!els.chatMessages) return;
  els.chatMessages.innerHTML = chatHistory.map(m => {
    const streamingClass = m.streaming ? ' streaming' : '';
    return `<div class="chat-msg ${m.role}${streamingClass}">${escHtml(m.content)}${m.streaming ? '<span class="typing-indicator">...</span>' : ''}</div>`;
  }).join('');
  els.chatMessages.scrollTop = els.chatMessages.scrollHeight;
}

async function sendChat() {
  if (!els.chatInput) return;
  const text = els.chatInput.value.trim();
  if (!text) return;
  chatHistory.push({ role: 'user', content: text });
  els.chatInput.value = '';
  renderChat();

  await sendChatMessage(text);
}

// ============================================================================
// Voice Interaction
// ============================================================================

let mediaRecorder = null;
let audioChunks = [];
let isRecording = false;
let voiceEnabled = true;

// Check if browser supports voice
function checkVoiceSupport() {
  return !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia());
}

// Start voice recording
async function startVoiceRecording() {
  if (!checkVoiceSupport()) {
    toast('Voice not supported in this browser');
    return;
  }

  try {
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        echoCancellation: true,
        noiseSuppression: true,
        sampleRate: 16000,
      }
    });

    mediaRecorder = new MediaRecorder(stream, {
      mimeType: 'audio/webm;codecs=opus'
    });

    audioChunks = [];

    mediaRecorder.ondataavailable = (e) => {
      if (e.data.size > 0) {
        audioChunks.push(e.data);
      }
    };

    mediaRecorder.onstop = async () => {
      stream.getTracks().forEach(track => track.stop());

      if (audioChunks.length > 0) {
        const audioBlob = new Blob(audioChunks, { type: 'audio/webm' });
        await processVoiceCommand(audioBlob);
      }
    };

    mediaRecorder.start(100); // Collect data every 100ms
    isRecording = true;

    // Update UI
    const voiceBtn = document.getElementById('btn-voice');
    const voiceIndicator = document.getElementById('voice-indicator');
    if (voiceBtn) voiceBtn.classList.add('recording');
    if (voiceIndicator) voiceIndicator.classList.remove('hidden');

  } catch (e) {
    console.error('Voice recording error:', e);
    toast('Could not access microphone');
  }
}

// Stop voice recording
function stopVoiceRecording() {
  if (mediaRecorder && isRecording) {
    mediaRecorder.stop();
    isRecording = false;

    // Update UI
    const voiceBtn = document.getElementById('btn-voice');
    const voiceIndicator = document.getElementById('voice-indicator');
    if (voiceBtn) voiceBtn.classList.remove('recording');
    if (voiceIndicator) voiceIndicator.classList.add('hidden');
  }
}

// Process voice command
async function processVoiceCommand(audioBlob) {
  const voiceIndicator = document.getElementById('voice-indicator');
  const voiceText = voiceIndicator?.querySelector('.voice-text');

  if (voiceText) voiceText.textContent = 'Processing...';
  if (voiceIndicator) voiceIndicator.classList.remove('hidden');

  try {
    // Convert blob to base64
    const reader = new FileReader();
    const audioBase64 = await new Promise((resolve, reject) => {
      reader.onloadend = () => resolve(reader.result.split(',')[1]);
      reader.onerror = reject;
      reader.readAsDataURL(audioBlob);
    });

    // Send to voice command endpoint
    const res = await fetch(`${CONFIG.API_BASE}/voice/command`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        audio_base64: audioBase64,
        user_id: 'default',
        execute_actions: true,
      }),
    });

    if (res.ok) {
      const data = await res.json();

      if (data.success) {
        // Add to chat history
        if (data.user_text) {
          chatHistory.push({ role: 'user', content: data.user_text });
        }
        if (data.ai_response) {
          chatHistory.push({ role: 'assistant', content: data.ai_response });
        }
        renderChat();

        // Play audio response
        if (data.audio_base64 && voiceEnabled) {
          playAudioResponse(data.audio_base64);
        }

        // Show actions executed
        if (data.actions_executed > 0) {
          toast(`Executed ${data.actions_executed} action(s)`);
        }
      } else {
        toast(data.error || 'Voice command failed');
      }
    } else {
      toast('Voice processing error');
    }
  } catch (e) {
    console.error('Voice command error:', e);
    toast('Voice command failed');
  } finally {
    if (voiceIndicator) voiceIndicator.classList.add('hidden');
  }
}

// Play audio response
function playAudioResponse(base64Audio) {
  try {
    const audio = new Audio(`data:audio/mp3;base64,${base64Audio}`);
    audio.play().catch(e => console.log('Audio autoplay blocked:', e));
  } catch (e) {
    console.error('Audio playback error:', e);
  }
}

// Text-to-speech for any message
async function speakText(text) {
  try {
    const res = await fetch(`${CONFIG.API_BASE}/voice/tts/speak?text=${encodeURIComponent(text)}&voice=guy`);

    if (res.ok) {
      const audioBlob = await res.blob();
      const audioUrl = URL.createObjectURL(audioBlob);
      const audio = new Audio(audioUrl);
      audio.play();
    }
  } catch (e) {
    console.error('TTS error:', e);
  }
}

// Toggle voice on/off
function toggleVoice() {
  voiceEnabled = !voiceEnabled;
  toast(voiceEnabled ? 'Voice enabled' : 'Voice disabled');
}

// Study assistance
async function createStudyPlan(subject, topics, examDate) {
  try {
    const res = await fetch(`${CONFIG.API_BASE}/ai/study/plan`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        subject,
        topics: topics ? topics.split(',').map(t => t.trim()) : null,
        exam_date: examDate,
        daily_hours: 2,
      }),
    });

    if (res.ok) {
      const data = await res.json();

      // Add blocks
      if (data.blocks) {
        data.blocks.forEach(block => {
          const existing = state.blocks.find(b => b.id === block.id);
          if (!existing) {
            state.blocks.push({
              ...block,
              x: 100 + state.blocks.length * 50,
              y: 100,
            });
          }
        });
      }

      // Add calendar tasks
      if (data.calendar_tasks) {
        data.calendar_tasks.forEach(task => {
          state.calendarTasks.push({
            id: 'ct_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9),
            ...task,
          });
        });
      }

      save();
      toast(`Study plan created: ${subject}`);
      showNotification('Study Plan Ready', `Created plan for ${subject} with ${data.plan?.topics?.length || 0} topics`, '📚');

      return data;
    }
  } catch (e) {
    toast('Failed to create study plan');
  }
  return null;
}

async function getTopicExplanation(topic) {
  try {
    const res = await fetch(`${CONFIG.API_BASE}/ai/study/explain?topic=${encodeURIComponent(topic)}&depth=medium`, {
      method: 'POST',
    });

    if (res.ok) {
      const data = await res.json();
      return data.explanation;
    }
  } catch (e) {
    console.error('Failed to get explanation');
  }
  return null;
}

// ============================================================================
// Settings
// ============================================================================

function openSettings() {
  closeMenu();
  els.pomoWorkDuration.value = state.pomodoro.workDuration;
  els.pomoShortBreak.value = state.pomodoro.shortBreak;
  els.pomoLongBreak.value = state.pomodoro.longBreak;
  // Populate server URL field
  if (els.serverUrlInput) {
    els.serverUrlInput.value = CONFIG.API_BASE;
  }
  if (els.syncStatusIndicator) {
    els.syncStatusIndicator.textContent = isOnline ? 'Online' : 'Offline';
    els.syncStatusIndicator.style.color = isOnline ? '#34d399' : '#f87171';
  }
  els.settingsPanel.classList.remove('hidden');
  state.openPanels.add('settings-panel');
  bringPanelToFront(els.settingsPanel);
}

function saveSettings() {
  state.pomodoro.workDuration = parseInt(els.pomoWorkDuration.value);
  state.pomodoro.shortBreak = parseInt(els.pomoShortBreak.value);
  state.pomodoro.longBreak = parseInt(els.pomoLongBreak.value);
  save();
  toast('Settings saved');
}

function exportData() {
  const data = localStorage.getItem(CONFIG.STORAGE_KEY);
  const blob = new Blob([data], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = 'aion-backup.json';
  a.click();
  toast('Data exported');
}

function importData(file) {
  const reader = new FileReader();
  reader.onload = e => {
    try {
      const data = JSON.parse(e.target.result);
      localStorage.setItem(CONFIG.STORAGE_KEY, JSON.stringify(data));
      location.reload();
    } catch (err) {
      toast('Invalid file');
    }
  };
  reader.readAsText(file);
}

function clearData() {
  if (confirm('Clear all data? This cannot be undone.')) {
    localStorage.removeItem(CONFIG.STORAGE_KEY);
    location.reload();
  }
}

// ============================================================================
// Events
// ============================================================================

function initEvents() {
  // Orb - Single click: AI input, Double click: Center with radial menu
  els.orb.addEventListener('click', e => {
    if (state.orbCentered) {
      // If already centered, clicking orb does nothing (use menu or overlay to close)
      return;
    }

    if (state.orbClickTimer) {
      // Double click detected
      clearTimeout(state.orbClickTimer);
      state.orbClickTimer = null;
      centerOrb();
    } else {
      // Start single click timer
      state.orbClickTimer = setTimeout(() => {
        state.orbClickTimer = null;
        toggleAiInput();
      }, 250);
    }
  });

  // Click on overlay to close centered orb
  if (els.orbOverlay) els.orbOverlay.addEventListener('click', uncenterOrb);

  // AI Input/Output
  if (els.aiSendBtn) els.aiSendBtn.addEventListener('click', sendAiQuery);
  if (els.aiCloseBtn) els.aiCloseBtn.addEventListener('click', closeAiInput);
  if (els.aiInput) els.aiInput.addEventListener('keydown', e => { if (e.key === 'Enter') sendAiQuery(); });
  if (els.aiOutputClose) els.aiOutputClose.addEventListener('click', closeAiOutput);

  // Voice button - hold to record
  const voiceBtn = document.getElementById('btn-voice');
  if (voiceBtn) {
    voiceBtn.addEventListener('mousedown', startVoiceRecording);
    voiceBtn.addEventListener('mouseup', stopVoiceRecording);
    voiceBtn.addEventListener('mouseleave', stopVoiceRecording);
    // Touch support
    voiceBtn.addEventListener('touchstart', (e) => { e.preventDefault(); startVoiceRecording(); });
    voiceBtn.addEventListener('touchend', stopVoiceRecording);
  }

  // Radial Menu buttons - close centered mode when selecting
  if (els.btnMindmap) els.btnMindmap.addEventListener('click', () => { uncenterOrb(); closeMenu(); openMindmap(); });
  if (els.btnTasks) els.btnTasks.addEventListener('click', () => { uncenterOrb(); closeMenu(); openTasks(); });
  if (els.btnPomodoro) els.btnPomodoro.addEventListener('click', () => { uncenterOrb(); closeMenu(); openFloatingTimer(); });
  if (els.btnStats) els.btnStats.addEventListener('click', () => { uncenterOrb(); closeMenu(); openStats(); });
  if (els.btnHabits) els.btnHabits.addEventListener('click', () => { uncenterOrb(); closeMenu(); openHabits(); });
  if (els.btnCalendar) els.btnCalendar.addEventListener('click', () => { uncenterOrb(); closeMenu(); openCalendar(); });
  if (els.btnChat) els.btnChat.addEventListener('click', () => { uncenterOrb(); closeMenu(); toggleAiInput(); });
  if (els.btnSettings) els.btnSettings.addEventListener('click', () => { uncenterOrb(); closeMenu(); openSettings(); });

  // Focus Panel
  if (els.focusExpandBtn) els.focusExpandBtn.addEventListener('click', expandFocusPanel);
  if (els.focusMinimizeBtn) els.focusMinimizeBtn.addEventListener('click', minimizeFocusPanel);

  // Collapsible Sections (Timer, Calendar, To-Do)
  document.querySelectorAll('.collapsible-header').forEach(header => {
    header.addEventListener('click', e => {
      // Don't toggle if clicking the add button
      if (e.target.closest('.mini-add-btn-inline')) return;
      const section = header.dataset.toggle;
      if (section) toggleCollapsibleSection(section);
    });
  });

  // Mini Calendar Navigation
  if (els.miniCalPrev) els.miniCalPrev.addEventListener('click', e => {
    e.stopPropagation();
    state.miniCalDate.setMonth(state.miniCalDate.getMonth() - 1);
    renderMiniCalendar();
  });
  if (els.miniCalNext) els.miniCalNext.addEventListener('click', e => {
    e.stopPropagation();
    state.miniCalDate.setMonth(state.miniCalDate.getMonth() + 1);
    renderMiniCalendar();
  });

  // Mini Add Todo
  if (els.miniAddTodo) els.miniAddTodo.addEventListener('click', e => { e.stopPropagation(); openQuickAdd(); });

  // Profile (legacy badge - hidden, kept for compatibility)
  if (els.profileBadge) els.profileBadge.addEventListener('click', () => { renderProfiles(); els.profileDropdown.classList.toggle('hidden'); });
  els.profileList.addEventListener('click', e => { const item = e.target.closest('.dropdown-item'); if (item) switchProfile(item.dataset.id); });
  els.btnNewProfile.addEventListener('click', () => { els.profileDropdown.classList.add('hidden'); openProfilePopup(); });
  els.btnSaveProfile.addEventListener('click', saveProfile);
  els.btnDeleteProfile.addEventListener('click', deleteProfile);

  // Focus Profile (new location)
  if (els.focusProfile) els.focusProfile.addEventListener('click', () => { renderProfiles(); els.profileDropdown.classList.toggle('hidden'); });

  // Focus Timer Controls
  if (els.focusTimerStart) els.focusTimerStart.addEventListener('click', e => { e.stopPropagation(); startPomodoro(); });
  if (els.focusTimerPause) els.focusTimerPause.addEventListener('click', e => { e.stopPropagation(); pausePomodoro(); });
  if (els.focusTimerReset) els.focusTimerReset.addEventListener('click', e => { e.stopPropagation(); resetPomodoroTimer(); });

  // Timer Mode Buttons
  document.querySelectorAll('.mode-select-btn').forEach(btn => {
    btn.addEventListener('click', e => {
      e.stopPropagation();
      const mode = btn.dataset.mode;
      if (mode && !state.pomodoro.running) {
        state.pomodoro.mode = mode;
        state.pomodoro.seconds = mode === 'work' ? state.pomodoro.workDuration * 60
          : mode === 'short' ? state.pomodoro.shortBreak * 60 : state.pomodoro.longBreak * 60;
        updatePomodoroUI();
      }
    });
  });

  // Search
  els.btnQuickSearch.addEventListener('click', openSearch);
  els.searchInput.addEventListener('input', e => performSearch(e.target.value));
  els.searchResults.addEventListener('click', e => {
    const item = e.target.closest('.search-result');
    if (item) {
      closeSearch();
      if (item.dataset.type === 'block') openBlockEditor(item.dataset.id);
      else if (item.dataset.type === 'task') openBlockEditor(item.dataset.block);
      else if (item.dataset.type === 'habit') openHabits();
    }
  });

  // Focus
  els.focusTextDisplay.addEventListener('click', startFocusEdit);
  els.focusInput.addEventListener('blur', saveFocus);
  els.focusInput.addEventListener('keydown', e => { if (e.key === 'Enter') saveFocus(); });

  // Mini Pomodoro
  els.miniStart.addEventListener('click', startPomodoro);
  els.miniPause.addEventListener('click', pausePomodoro);
  els.miniReset.addEventListener('click', resetPomodoroTimer);

  // Quick Actions
  els.btnQuickTask.addEventListener('click', openQuickAdd);
  els.btnQuickHelp.addEventListener('click', () => els.shortcutsPopup.classList.remove('hidden'));

  // Pomodoro Panel
  els.btnClosePomodoro.addEventListener('click', () => els.pomodoroPanel.classList.add('hidden'));
  els.pomoStart.addEventListener('click', startPomodoro);
  els.pomoPause.addEventListener('click', pausePomodoro);
  els.pomoReset.addEventListener('click', resetPomodoroTimer);
  document.querySelectorAll('.pomo-tab').forEach(t => t.addEventListener('click', () => setPomoMode(t.dataset.mode)));

  // Stats
  els.btnCloseStats.addEventListener('click', () => els.statsPanel.classList.add('hidden'));
  document.querySelectorAll('.period-btn').forEach(b => {
    b.addEventListener('click', () => {
      document.querySelectorAll('.period-btn').forEach(x => x.classList.remove('active'));
      b.classList.add('active');
      renderStats(b.dataset.period);
    });
  });

  // Habits
  els.btnCloseHabits.addEventListener('click', () => els.habitsPanel.classList.add('hidden'));
  els.btnAddHabit.addEventListener('click', openHabitPopup);
  els.habitPrevDay.addEventListener('click', () => { state.habitDate.setDate(state.habitDate.getDate() - 1); renderHabits(); });
  els.habitNextDay.addEventListener('click', () => { state.habitDate.setDate(state.habitDate.getDate() + 1); renderHabits(); });
  els.habitsList.addEventListener('click', e => {
    const check = e.target.closest('.habit-check');
    if (check) toggleHabit(check.dataset.habit);
  });
  els.btnSaveHabit.addEventListener('click', saveHabit);
  els.btnCancelHabit.addEventListener('click', () => els.habitPopup.classList.add('hidden'));

  // Calendar
  els.btnCloseCalendar.addEventListener('click', () => els.calendarPanel.classList.add('hidden'));
  els.btnPrevMonth.addEventListener('click', () => { state.calendarDate.setMonth(state.calendarDate.getMonth() - 1); renderCalendar(); });
  els.btnNextMonth.addEventListener('click', () => { state.calendarDate.setMonth(state.calendarDate.getMonth() + 1); renderCalendar(); });
  els.calendarGrid.addEventListener('click', e => {
    const day = e.target.closest('.cal-day');
    if (day?.dataset.date) { state.selectedDate = day.dataset.date; renderCalendar(); }
  });
  els.btnAddCalTask.addEventListener('click', openCalTaskPopup);
  els.btnSaveCalTask.addEventListener('click', saveCalTask);
  els.btnCancelCalTask.addEventListener('click', () => els.calTaskPopup.classList.add('hidden'));

  // Tasks Panel
  els.btnCloseTasks.addEventListener('click', () => { clearTaskSelection(); els.tasksPanel.classList.add('hidden'); });
  document.querySelectorAll('.status-tab').forEach(t => {
    t.addEventListener('click', () => {
      state.taskFilter = t.dataset.status;
      document.querySelectorAll('.status-tab').forEach(x => x.classList.toggle('active', x.dataset.status === state.taskFilter));
      renderAllTasks();
    });
  });

  // Task Panel New Features
  if (els.btnAddGlobalTask) els.btnAddGlobalTask.addEventListener('click', openGlobalTaskPopup);
  if (els.taskSortSelect) els.taskSortSelect.addEventListener('change', e => { state.taskSort = e.target.value; renderAllTasks(); });
  if (els.taskSearchInput) els.taskSearchInput.addEventListener('input', e => { state.taskSearchQuery = e.target.value; renderAllTasks(); });

  // Bulk Actions
  if (els.bulkStatusBtn) els.bulkStatusBtn.addEventListener('click', () => {
    const status = prompt('Enter status (not_started, in_progress, on_hold, completed):');
    if (status && STATUSES[status]) bulkChangeStatus(status);
  });
  if (els.bulkMoveBtn) els.bulkMoveBtn.addEventListener('click', bulkMoveTasks);
  if (els.bulkDeleteBtn) els.bulkDeleteBtn.addEventListener('click', bulkDeleteTasks);
  if (els.bulkCancelBtn) els.bulkCancelBtn.addEventListener('click', clearTaskSelection);

  // Task Context Menu
  if (els.ctxTaskEdit) els.ctxTaskEdit.addEventListener('click', editTaskFromContext);
  if (els.ctxTaskMove) els.ctxTaskMove.addEventListener('click', openMoveTaskPopup);
  if (els.ctxTaskDuplicate) els.ctxTaskDuplicate.addEventListener('click', duplicateTaskFromContext);
  if (els.ctxTaskComplete) els.ctxTaskComplete.addEventListener('click', toggleCompleteFromContext);
  if (els.ctxTaskDelete) els.ctxTaskDelete.addEventListener('click', deleteTaskFromContext);

  // Status submenu
  if (els.statusSubmenu) {
    els.statusSubmenu.querySelectorAll('.ctx-item').forEach(item => {
      item.addEventListener('click', () => changeTaskStatusFromContext(item.dataset.status));
    });
  }

  // Priority submenu
  if (els.prioritySubmenu) {
    els.prioritySubmenu.querySelectorAll('.ctx-item').forEach(item => {
      item.addEventListener('click', () => changeTaskPriorityFromContext(item.dataset.priority));
    });
  }

  // Global Task Popup
  if (els.btnSaveGlobalTask) els.btnSaveGlobalTask.addEventListener('click', saveGlobalTask);
  if (els.btnCancelGlobalTask) els.btnCancelGlobalTask.addEventListener('click', () => els.globalTaskPopup.classList.add('hidden'));
  if (els.globalTaskText) els.globalTaskText.addEventListener('keydown', e => { if (e.key === 'Enter') saveGlobalTask(); });

  // Edit Task Popup
  if (els.btnSaveEditTask) els.btnSaveEditTask.addEventListener('click', saveEditedTask);
  if (els.btnCancelEditTask) els.btnCancelEditTask.addEventListener('click', () => { els.editTaskPopup.classList.add('hidden'); state.contextTask = null; });

  // Move Task Popup
  if (els.btnConfirmMoveTask) els.btnConfirmMoveTask.addEventListener('click', () => {
    if (state.contextTask?.bulk) bulkMoveTasksConfirm();
    else moveTaskToBlock();
  });
  if (els.btnCancelMoveTask) els.btnCancelMoveTask.addEventListener('click', () => { els.moveTaskPopup.classList.add('hidden'); state.contextTask = null; });

  // Chat
  els.btnCloseChat.addEventListener('click', () => els.chatBox.classList.add('hidden'));
  els.btnSend.addEventListener('click', sendChat);
  els.chatInput.addEventListener('keydown', e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendChat(); } });

  // Mind Map
  els.btnCloseMindmap.addEventListener('click', () => els.mindmapView.classList.add('hidden'));
  els.btnAddBlock.addEventListener('click', () => openBlockPopup(null));

  // Fullscreen toggle for mind map
  const btnFullscreen = document.getElementById('btn-fullscreen');
  if (btnFullscreen) {
    btnFullscreen.addEventListener('click', toggleMindmapFullscreen);
  }
  els.ctxOpen.addEventListener('click', () => { if (state.contextBlock) openBlockEditor(state.contextBlock.id); hideContextMenu(); });
  els.ctxRename.addEventListener('click', openRenamePopup);
  els.ctxIcon.addEventListener('click', openIconPopup);
  els.ctxSubblock.addEventListener('click', () => { if (state.contextBlock) openBlockPopup(state.contextBlock.id); hideContextMenu(); });
  els.ctxDelete.addEventListener('click', deleteBlock);

  // Block popup
  document.querySelectorAll('.type-opt').forEach(b => {
    b.addEventListener('click', () => { document.querySelectorAll('.type-opt').forEach(x => x.classList.remove('selected')); b.classList.add('selected'); });
  });
  els.btnCreateBlock.addEventListener('click', createBlock);
  els.btnCancelBlock.addEventListener('click', () => els.blockPopup.classList.add('hidden'));
  els.newBlockName.addEventListener('keydown', e => { if (e.key === 'Enter') createBlock(); });

  // Rename
  els.btnSaveRename.addEventListener('click', saveRename);
  els.btnCancelRename.addEventListener('click', () => els.renamePopup.classList.add('hidden'));
  els.renameInput.addEventListener('keydown', e => { if (e.key === 'Enter') saveRename(); });

  // Icon
  els.iconGrid.addEventListener('click', e => { const opt = e.target.closest('.icon-option'); if (opt) selectIcon(opt.dataset.icon); });
  els.btnCancelIcon.addEventListener('click', () => els.iconPopup.classList.add('hidden'));

  // Block Editor
  els.btnBack.addEventListener('click', closeEditor);
  els.btnCloseEditor.addEventListener('click', () => { saveCurrentBlock(); stopTimer(); closeAllPanels(); });
  els.blockTitle.addEventListener('input', saveCurrentBlock);
  els.blockNotes.addEventListener('input', saveCurrentBlock);
  els.blockDate.addEventListener('change', saveCurrentBlock);
  els.blockDateEnd.addEventListener('change', saveCurrentBlock);
  els.blockIconBtn.addEventListener('click', () => { state.contextBlock = state.currentBlock; openIconPopup(); });
  els.btnTimerStart.addEventListener('click', startTimer);
  els.btnTimerPause.addEventListener('click', pauseTimer);
  els.btnTimerReset.addEventListener('click', stopTimer);
  els.btnAddTodo.addEventListener('click', openTodoPopup);
  els.todoList.addEventListener('click', e => { const check = e.target.closest('.todo-checkbox'); if (check) toggleTodoStatus(check.dataset.todo); });
  els.btnSaveTodo.addEventListener('click', saveTodo);
  els.btnCancelTodo.addEventListener('click', () => els.todoPopup.classList.add('hidden'));
  els.todoText.addEventListener('keydown', e => { if (e.key === 'Enter') saveTodo(); });
  els.btnAddSubblock.addEventListener('click', () => { if (state.currentBlock) openBlockPopup(state.currentBlock.id); });
  els.subblocksList.addEventListener('click', e => { const item = e.target.closest('.subblock-item'); if (item) { saveCurrentBlock(); openBlockEditor(item.dataset.id); } });

  // Quick Add
  els.btnSaveQuick.addEventListener('click', saveQuickTask);
  els.btnCancelQuick.addEventListener('click', () => els.quickAddPopup.classList.add('hidden'));
  els.quickTaskText.addEventListener('keydown', e => { if (e.key === 'Enter') saveQuickTask(); });

  // Settings
  els.btnCloseSettings.addEventListener('click', () => els.settingsPanel.classList.add('hidden'));
  document.querySelectorAll('.theme-option').forEach(o => o.addEventListener('click', () => applyTheme(o.dataset.theme)));
  els.pomoWorkDuration.addEventListener('change', saveSettings);
  els.pomoShortBreak.addEventListener('change', saveSettings);
  els.pomoLongBreak.addEventListener('change', saveSettings);
  els.btnExport.addEventListener('click', exportData);
  els.btnImport.addEventListener('click', () => els.importFile.click());
  els.importFile.addEventListener('change', e => { if (e.target.files[0]) importData(e.target.files[0]); });
  els.btnClearData.addEventListener('click', clearData);

  // Server URL settings
  if (els.btnSaveServerUrl) {
    els.btnSaveServerUrl.addEventListener('click', async () => {
      const url = els.serverUrlInput?.value?.trim();
      if (!url) return toast('Please enter a server URL');
      CONFIG.API_BASE_SETTABLE = url;
      toast('Server URL saved. Reconnecting...');
      // Re-initialize sync with new URL
      try {
        if (syncService) {
          syncService.serverUrl = url.replace('/api/v1', '');
          await syncService.sync();
        }
        if (els.syncStatusIndicator) {
          els.syncStatusIndicator.textContent = 'Connected';
          els.syncStatusIndicator.style.color = '#34d399';
        }
        toast('Connected to server');
      } catch (e) {
        if (els.syncStatusIndicator) {
          els.syncStatusIndicator.textContent = 'Failed';
          els.syncStatusIndicator.style.color = '#f87171';
        }
        toast('Could not connect: ' + (e?.message || e));
      }
    });
  }
  if (els.btnResetServerUrl) {
    els.btnResetServerUrl.addEventListener('click', () => {
      CONFIG.API_BASE_SETTABLE = null;
      if (els.serverUrlInput) els.serverUrlInput.value = CONFIG.API_BASE;
      toast('Server URL reset to default (localhost:8000)');
    });
  }

  // Check for updates (Tauri updater plugin)
  const btnCheckUpdates = document.getElementById('btn-check-updates');
  const updateStatusEl = document.getElementById('update-status');
  if (btnCheckUpdates) {
    btnCheckUpdates.addEventListener('click', async () => {
      if (!window.__TAURI__) return;
      try {
        if (updateStatusEl) updateStatusEl.textContent = 'Checking...';
        const { check } = await import('@tauri-apps/plugin-updater');
        const update = await check();
        if (updateStatusEl) updateStatusEl.textContent = '';
        if (update) {
          showToast(`Update ${update.version} available. Downloading...`);
          await update.downloadAndInstall();
          showToast('Update installed. Restarting...');
          const { relaunch } = await import('@tauri-apps/plugin-process');
          await relaunch();
        } else {
          showToast('You are on the latest version.');
        }
      } catch (e) {
        console.warn('Update check failed:', e);
        if (updateStatusEl) updateStatusEl.textContent = '';
        showToast(e?.message || 'Update check failed');
      }
    });
  }

  // Shortcuts
  els.btnCloseShortcuts.addEventListener('click', () => els.shortcutsPopup.classList.add('hidden'));

  // Notification
  els.notifClose.addEventListener('click', () => $('notification').classList.add('hidden'));

  // Floating Timer
  if (els.closeFloatingTimer) els.closeFloatingTimer.addEventListener('click', closeFloatingTimerPanel);
  if (els.floatTimerStart) els.floatTimerStart.addEventListener('click', startPomodoro);
  if (els.floatTimerPause) els.floatTimerPause.addEventListener('click', pausePomodoro);
  if (els.floatTimerReset) els.floatTimerReset.addEventListener('click', resetPomodoroTimer);

  // Click-Through Toggle (Ghost Mode)
  const clickThroughToggle = document.getElementById('click-through-toggle');
  if (clickThroughToggle) {
    clickThroughToggle.addEventListener('click', toggleClickThroughMode);
  }
  // Alt+G global shortcut: sync with backend and toggle ghost mode (so user can turn off when window is click-through)
  if (window.__TAURI__?.event?.listen) {
    window.__TAURI__.event.listen('toggle-ghost', async () => {
      try {
        const { invoke } = window.__TAURI__.core;
        const enabled = await invoke('get_click_through_state');
        const toggle = document.getElementById('click-through-toggle');
        if (enabled) {
          clickThroughEnabled = false;
          const w = window.__TAURI__.webviewWindow?.getCurrentWebviewWindow?.();
          if (w) await w.setIgnoreCursorEvents(false);
          await invoke('set_click_through', { enabled: false });
          document.body.classList.remove('click-through-mode');
          if (toggle) toggle.classList.remove('active');
          toast('Ghost mode disabled');
        } else {
          clickThroughEnabled = true;
          document.body.classList.add('click-through-mode');
          if (toggle) toggle.classList.add('active');
          await invoke('set_click_through', { enabled: true });
          const w = window.__TAURI__.webviewWindow.getCurrentWebviewWindow();
          await w.setIgnoreCursorEvents(true);
          toast('Ghost mode on — press Alt+G to turn off');
        }
      } catch (e) {
        console.warn('Toggle ghost:', e);
      }
    });
  }

  // Panel Dragging
  document.addEventListener('mousedown', e => {
    const header = e.target.closest('[data-drag]');
    if (header) initPanelDrag(e);
  });

  // Mouse
  document.addEventListener('mousemove', e => {
    handleMouseMove(e);
    handlePanelDrag(e);
  });
  document.addEventListener('mouseup', e => {
    handleMouseUp(e);
    endPanelDrag();
  });

  // Click outside
  document.addEventListener('click', e => {
    if (!els.orb.contains(e.target) && !els.radialMenu.contains(e.target)) closeMenu();
    if (!els.profileDropdown.contains(e.target) && !els.profileBadge.contains(e.target)) els.profileDropdown.classList.add('hidden');
    if (!els.contextMenu.contains(e.target)) hideContextMenu();
    if (els.taskContextMenu && !els.taskContextMenu.contains(e.target)) hideTaskContextMenu();
    if (!els.searchBar.contains(e.target) && !els.searchResults.contains(e.target) && !els.btnQuickSearch.contains(e.target)) closeSearch();

    // Dock AI output when clicking outside it (but not when clicking AI input)
    if (els.aiOutputBox && !els.aiOutputBox.classList.contains('hidden') &&
      !els.aiOutputBox.contains(e.target) &&
      !els.aiInputBar?.contains(e.target) &&
      !els.orb.contains(e.target)) {
      dockAiOutput();
    }

    // Close AI input when clicking outside
    if (state.aiInputOpen && !els.aiInputBar?.contains(e.target) && !els.orb.contains(e.target)) {
      closeAiInput();
    }
  });

  // Bring panel to front when clicked
  document.addEventListener('mousedown', e => {
    const panel = e.target.closest('.floating-panel, .panel-view');
    if (panel) bringPanelToFront(panel);
  });

  // Keyboard Shortcuts
  document.addEventListener('keydown', e => {
    const target = e.target;
    const isInput = target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.contentEditable === 'true';

    // Global shortcuts: backtick/~ hides overlay to system tray (use Alt+Space to show again)
    if (e.key === '`' || e.key === '~') {
      e.preventDefault();
      if (window.__TAURI__?.core?.invoke) {
        window.__TAURI__.core.invoke('minimize_to_tray').then(() => {
          toast('Overlay hidden to tray — press Alt+Space to show again');
        }).catch(() => toggleAllPanelsVisibility());
      } else {
        toggleAllPanelsVisibility();
      }
      return;
    }
    if (e.altKey && e.code === 'Space') { e.preventDefault(); toggleMenu(); return; }
    if (e.ctrlKey && e.key === 'k') { e.preventDefault(); openSearch(); return; }
    if (e.ctrlKey && e.key === 'n') { e.preventDefault(); openQuickAdd(); return; }
    if (e.ctrlKey && e.key === '/') { e.preventDefault(); toggleAiInput(); return; }

    // Escape - close things progressively
    if (e.key === 'Escape') {
      if (state.aiInputOpen) { closeAiInput(); closeAiOutput(); return; }
      if (state.menuOpen) { closeMenu(); return; }
      if (state.currentPanel) { closeAllOpenPanels(); return; }
      closeMenu(); closeSearch(); hideContextMenu();
      document.querySelectorAll('.popup').forEach(p => p.classList.add('hidden'));
      return;
    }

    // Letter shortcuts (only when not in input)
    if (!isInput) {
      switch (e.key.toLowerCase()) {
        case 'm': openMindmap(); break;
        case 't': openTasks(); break;
        case 'p': openFloatingTimer(); break;
        case 's': openStats(); break;
        case 'h': openHabits(); break;
        case 'c': openCalendar(); break;
        case 'a': toggleAiInput(); break;
        case 'f': els.focusTextDisplay?.click(); break;
        case 'q': closeAllOpenPanels(); break;
        case '?': els.shortcutsPopup.classList.remove('hidden'); break;
        case '1': switchFocusSection('timer'); break;
        case '2': switchFocusSection('calendar'); break;
        case '3': switchFocusSection('todos'); break;
        // Timer controls
        case ' ':
          e.preventDefault();
          state.pomodoro.running ? pausePomodoro() : startPomodoro();
          break;
        case 'r':
          if (e.shiftKey) resetPomodoroTimer();
          break;
      }
    }
  });
}

// ============================================================================
// Init
// ============================================================================

async function init() {
  initEls();
  load();
  initEvents();
  applyTheme(state.theme);
  updateProfileBadge();
  updateFocusDisplay();
  updateMiniTimer();
  updatePomodoroUI();
  updateTodayProgress();
  updateTodayStats();

  // Initialize focus panel
  updateFocusPanelState();
  updateCollapsibleSections();
  renderMiniCalendar();
  initMiniTodoEvents(); // Event delegation for mini todos (attach once)
  initTaskListEventDelegation(); // Event delegation for all tasks list (attach once)
  initBlockEventDelegation(); // Event delegation for mindmap blocks (attach once)
  renderMiniTodos();

  // Initialize AI system
  loadAiModels();
  connectAiWebSocket();

  // Model selector event
  const modelSelect = document.getElementById('ai-model-select');
  if (modelSelect) {
    modelSelect.addEventListener('change', (e) => switchAiModel(e.target.value));
  }

  // Initialize offline-first sync system
  await initOfflineSync();

  // Smooth overlay fade-in when app is ready
  requestAnimationFrame(() => {
    requestAnimationFrame(() => document.body.classList.add('overlay-ready'));
  });

  console.log('Aion Complete v2 with AI and Offline Sync ready');
}

// ============================================================================
// Offline-First Sync System
// ============================================================================

async function initOfflineSync() {
  try {
    // Initialize local database
    localDb = await initLocalDb();
    console.log('[Sync] Local database initialized');

    // Initialize sync service
    syncService = await initSyncService(CONFIG.API_BASE.replace('/api/v1', ''));

    // Listen to sync events (with null check)
    if (syncService && typeof syncService.addListener === 'function') {
      syncService.addListener(handleSyncEvent);
    } else {
      console.warn('[Sync] Sync service not available or invalid');
    }

    // Update UI
    updateSyncStatusUI();

    // Listen for online/offline
    window.addEventListener('online', handleOnlineStatusChange);
    window.addEventListener('offline', handleOnlineStatusChange);

    // Sync on close: when user closes the window or quits (Cmd+Q on macOS),
    // run one final sync then exit the app process.
    if (window.__TAURI__?.event?.listen && syncService) {
      let isClosing = false;
      window.__TAURI__.event.listen('sync-before-close', async () => {
        if (isClosing) return; // prevent re-entrant calls
        isClosing = true;
        const SYNC_CLOSE_TIMEOUT_MS = 5000;
        try {
          const syncPromise = syncService.sync();
          const timeoutPromise = new Promise((_, reject) =>
            setTimeout(() => reject(new Error('timeout')), SYNC_CLOSE_TIMEOUT_MS)
          );
          await Promise.race([syncPromise, timeoutPromise]);
        } catch (e) {
          console.warn('[Sync] Sync before close:', e?.message || e);
        }
        try {
          const { invoke } = window.__TAURI__.core;
          await invoke('exit_app');
        } catch (err) {
          console.warn('[Sync] exit_app:', err);
        }
      });
    }

    console.log('[Sync] Offline sync system initialized');
  } catch (error) {
    console.error('[Sync] Failed to initialize:', error);
  }
}

function handleSyncEvent(event, data) {
  console.log('[Sync Event]', event, data);

  switch (event) {
    case 'sync_start':
      updateSyncStatusUI('syncing', 'Syncing...');
      break;
    case 'sync_complete':
      updateSyncStatusUI('synced', `Synced (↑${data.pushed} ↓${data.pulled})`);
      // Reload data if server had changes
      if (data.pulled > 0) {
        loadFromLocalDb();
      }
      break;
    case 'sync_error':
      updateSyncStatusUI('error', 'Sync failed');
      break;
    case 'conflicts':
      showToast(`${data.conflicts.length} sync conflict(s) detected`);
      break;
    case 'online':
      updateSyncStatusUI('synced', 'Online');
      break;
    case 'offline':
      updateSyncStatusUI('offline', 'Offline');
      break;
  }
}

function handleOnlineStatusChange() {
  isOnline = navigator.onLine;
  updateSyncStatusUI(isOnline ? 'synced' : 'offline', isOnline ? 'Online' : 'Offline');
}

function updateSyncStatusUI(status = 'synced', text = 'Synced') {
  const statusEl = document.getElementById('sync-status');
  if (!statusEl) return;

  statusEl.classList.remove('hidden', 'syncing', 'synced', 'error', 'offline');
  statusEl.classList.add(status);

  const textEl = statusEl.querySelector('.sync-text');
  if (textEl) textEl.textContent = text;

  // Show pending count if any
  if (localDb) {
    localDb.getPendingChanges().then(pending => {
      let pendingEl = statusEl.querySelector('.sync-pending');
      if (pending.length > 0) {
        if (!pendingEl) {
          pendingEl = document.createElement('span');
          pendingEl.className = 'sync-pending';
          statusEl.appendChild(pendingEl);
        }
        pendingEl.textContent = pending.length;
      } else if (pendingEl) {
        pendingEl.remove();
      }
    });
  }
}

async function loadFromLocalDb() {
  if (!localDb) return;

  try {
    const blocks = await localDb.getBlocks();
    if (blocks.length > 0) {
      // Convert local DB format to app state format
      state.blocks = blocks.map(b => ({
        ...b,
        children: b.children || [],
        todos: b.todos || [],
      }));
      save();
      renderMindMap();
      renderMiniTodos();
      showToast('Data synced from server');
    }
  } catch (error) {
    console.error('[Sync] Failed to load from local DB:', error);
  }
}

async function saveToLocalDb(block) {
  if (!localDb) return;

  try {
    await localDb.saveBlock({
      ...block,
      updated_at: new Date().toISOString(),
    });
  } catch (error) {
    console.error('[Sync] Failed to save to local DB:', error);
  }
}

// Force sync button handler
function forceSync() {
  if (syncService) {
    syncService.forceSync();
  }
}

document.addEventListener('DOMContentLoaded', init);
