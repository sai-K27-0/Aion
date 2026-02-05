# Aion Desktop Build Instructions

## Prerequisites

1. **Node.js** (v18+) - https://nodejs.org
2. **Rust** - https://rustup.rs
3. **Platform-specific dependencies** (see below)

## Install Dependencies

```bash
cd desktop
npm install
```

## Development

```bash
# Start development server with hot reload
npm run tauri:dev
```

## Building for Windows

### Requirements
- Windows 10/11
- Visual Studio 2022 Build Tools with C++ workload

### Build
```bash
npm run tauri:build:windows
```

Output: `src-tauri/target/release/bundle/msi/Aion_0.1.0_x64_en-US.msi`

## Building for macOS

### Requirements
- macOS 10.15+ (Catalina or later)
- Xcode Command Line Tools: `xcode-select --install`
- (Optional) Apple Developer account for code signing

### Build Options

**Universal Binary (Intel + Apple Silicon):**
```bash
# Add both targets first
rustup target add x86_64-apple-darwin
rustup target add aarch64-apple-darwin

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

Output: `src-tauri/target/release/bundle/dmg/Aion_0.1.0_x64.dmg`

### Code Signing (Optional)

To sign your app for distribution:

1. Get an Apple Developer account
2. Create a Developer ID certificate
3. Update `tauri.conf.json`:
```json
"macOS": {
    "signingIdentity": "Developer ID Application: Your Name (XXXXXXXXXX)"
}
```

## Building for Linux

### Requirements
- Ubuntu/Debian: `sudo apt install libwebkit2gtk-4.0-dev build-essential curl wget libssl-dev libgtk-3-dev libayatana-appindicator3-dev librsvg2-dev`
- Fedora: `sudo dnf install webkit2gtk4.0-devel openssl-devel curl wget libappindicator-gtk3 librsvg2-devel`

### Build
```bash
npm run tauri:build:linux
```

Output: 
- AppImage: `src-tauri/target/release/bundle/appimage/aion_0.1.0_amd64.AppImage`
- Deb: `src-tauri/target/release/bundle/deb/aion_0.1.0_amd64.deb`

## Cross-Compilation Notes

Tauri apps must be built on the target platform. For CI/CD:
- Use GitHub Actions with `macos-latest`, `windows-latest`, and `ubuntu-latest` runners
- Consider using `tauri-action` for automated builds

## Server Configuration

The desktop app connects to the Aion server. Configure the server URL in:

1. **Development**: Edit `CONFIG.API_BASE` in `src/main.js`
2. **Production**: The app will auto-discover the server on the local network or allow manual entry

## Offline Mode

The app works offline with:
- Local IndexedDB storage for all data
- Automatic sync when server is available
- Conflict resolution for simultaneous edits

## Security

### Device Authentication
Each device is registered with the server and receives a unique token:
1. On first launch, the app generates a unique device ID
2. The device registers with the server at `POST /api/v1/devices/register`
3. The server returns a token valid for 30 days
4. The token is stored securely and included in all sync requests
5. Tokens can be refreshed or revoked if compromised

### Data Encryption (Optional)
For additional security on mobile devices:
- **Android**: Use AndroidKeystore for token storage
- **iOS**: Use iOS Keychain for token storage
- **Desktop**: Use OS keychain (Windows Credential Manager, macOS Keychain)

### SQLite Encryption (Production)
For production deployments requiring encrypted local storage:
1. Replace `better-sqlite3` with `sql.js` + encryption
2. Or use SQLCipher-compatible libraries
3. Store encryption key in OS secure storage

## Troubleshooting

### Windows: "VCRUNTIME140.dll not found"
Install the Visual C++ Redistributable: https://aka.ms/vs/17/release/vc_redist.x64.exe

### macOS: "App is damaged and can't be opened"
Run: `xattr -cr /Applications/Aion.app`

### Linux: AppImage won't run
Make executable: `chmod +x Aion_*.AppImage`
