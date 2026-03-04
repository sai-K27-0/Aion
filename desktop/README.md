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
# Build for production (current platform)
npm run tauri build
```

### Build on macOS

On your MacBook:

```bash
git clone <your-private-github-url>.git
cd desktop

# Install dependencies
npm install

# Install Tauri CLI if you don't have it yet
# (this also installs Rust components as needed)
npm run tauri -h || npm install --global @tauri-apps/cli

# Development (hot reload)
npm run tauri dev

# Production build (.app / .dmg under src-tauri/target/release/bundle)
npm run tauri build
```

You may need Xcode Command Line Tools installed first:

```bash
xcode-select --install
```

### Auto-updates & releases (macOS + GitHub)

To enable the built-in Tauri updater (for macOS and other platforms):

1. **Generate signing keys** on a secure machine (only keep the private key there):
   ```bash
   npm run tauri signer generate -- -w ~/.tauri/aion.key
   ```
   This prints a public key – copy that value.
2. **Set the public key** in `src-tauri/tauri.conf.json`:
   ```jsonc
   \"plugins\": {
     \"updater\": {
       \"pubkey\": \"REPLACE_WITH_TAURI_PUBLIC_KEY\",  // paste here
       \"endpoints\": [
         \"https://raw.githubusercontent.com/<your-user>/<your-updates-repo>/main/latest.json\"
       ]
     }
   }
   ```
3. **Prepare an updates feed repo** (can be public, while your main code repo is private):
   - Host `latest.json` and the `.app.tar.gz` / `.sig` files in that repo or on GitHub Pages.
   - Point the `endpoints` URL above to the raw `latest.json`.
4. **Release flow**:
   - Bump version in `package.json` / `tauri.conf.json`.
   - Run `npm run tauri build` on macOS with the signing key configured.
   - Upload the generated macOS bundle + signatures and update `latest.json` in the updates repo.
   - The app can then call the updater plugin to check/download/install new versions.

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
