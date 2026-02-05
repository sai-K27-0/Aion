# Aion Desktop Client

Transparent AI overlay for Windows, macOS, and Linux.

## 🌟 Features

- **Transparent Overlay** - Glassmorphism UI that floats above your work
- **Screen Understanding** - AI analyzes what you're looking at
- **Global Hotkeys** - Quick access from anywhere
- **System Tray** - Background operation with quick actions
- **Real-time Sync** - Connected to all your devices

## 🚀 Quick Start

### Prerequisites

- Node.js 18+
- Rust 1.70+
- Ollama (for local AI)

### Development

```bash
cd desktop

# Install dependencies
npm install

# Run in development mode
npm run tauri dev
```

### Build

```bash
# Build for production
npm run tauri build
```

## ⌨️ Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| `Alt + Space` | Toggle overlay |
| `Alt + Shift + S` | Capture screen |
| `Escape` | Close/cancel |

## 🎨 UI Modes

1. **Minimal** - Floating action button (default)
2. **Chat** - Expanded chat panel
3. **Hidden** - Completely hidden, use hotkey to show

## 📁 Project Structure

```
desktop/
├── src/
│   ├── main.js           # Frontend JavaScript
│   └── styles/
│       └── main.css      # Glassmorphism styles
├── src-tauri/
│   ├── src/
│   │   └── main.rs       # Rust backend (screen capture)
│   ├── Cargo.toml        # Rust dependencies
│   └── tauri.conf.json   # Tauri configuration
├── index.html            # Main HTML
├── package.json          # Node dependencies
└── vite.config.js        # Vite configuration
```

## 🔧 Configuration

Edit `src-tauri/tauri.conf.json` to customize:

- Window size and position
- Global shortcuts
- System tray behavior
- Security permissions

## 📝 License

MIT License
