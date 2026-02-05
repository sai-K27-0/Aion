# Building Aion Desktop for macOS

## Quick Start (Automated)

Run the setup script on your Mac:

```bash
cd desktop
chmod +x scripts/setup-mac.sh
./scripts/setup-mac.sh
```

Then build:

```bash
npm run tauri:build:macos
```

## Manual Setup

### Prerequisites

1. **Xcode Command Line Tools**
   ```bash
   xcode-select --install
   ```

2. **Rust**
   ```bash
   curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
   source ~/.cargo/env
   
   # Add targets for universal binary
   rustup target add aarch64-apple-darwin
   rustup target add x86_64-apple-darwin
   ```

3. **Node.js** (v18 or later)
   ```bash
   brew install node
   ```

4. **ImageMagick** (for icon generation)
   ```bash
   brew install imagemagick
   ```

### Generate Icons

```bash
cd src-tauri/icons
chmod +x generate-icons.sh
./generate-icons.sh
```

Or provide your own 512x512 PNG:
```bash
./generate-icons.sh /path/to/your-icon.png
```

### Install Dependencies

```bash
cd desktop
npm install
```

### Build

**Universal Binary (Intel + Apple Silicon):**
```bash
npm run tauri:build:macos
```

**Apple Silicon only:**
```bash
npm run tauri:build:macos-arm
```

**Intel only:**
```bash
npm run tauri:build:macos-intel
```

### Output

The built files will be in:
- **DMG**: `src-tauri/target/universal-apple-darwin/release/bundle/dmg/Aion_0.1.0_universal.dmg`
- **APP**: `src-tauri/target/universal-apple-darwin/release/bundle/macos/Aion.app`

## Development

Run in development mode with hot reload:

```bash
npm run tauri:dev
```

## Signing & Notarization (Optional)

For distribution outside the App Store, you'll need to:

1. Get an Apple Developer certificate
2. Set environment variables:
   ```bash
   export APPLE_SIGNING_IDENTITY="Developer ID Application: Your Name (TEAMID)"
   export APPLE_ID="your@email.com"
   export APPLE_PASSWORD="app-specific-password"
   export APPLE_TEAM_ID="TEAMID"
   ```

3. Update `tauri.conf.json`:
   ```json
   "macOS": {
     "signingIdentity": "Developer ID Application: Your Name (TEAMID)"
   }
   ```

## Troubleshooting

### "cargo: command not found"
```bash
source ~/.cargo/env
```

### Build fails with missing SDK
```bash
sudo xcode-select --switch /Applications/Xcode.app/Contents/Developer
```

### Universal build fails
Try building for a single architecture first:
```bash
npm run tauri:build:macos-arm  # For M1/M2/M3 Macs
npm run tauri:build:macos-intel  # For Intel Macs
```
