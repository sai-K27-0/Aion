# Desktop app auto-updater (Tauri)

The desktop app uses `tauri-plugin-updater` to check for updates from GitHub Releases and prompt the user to install.

## Configuration

1. **Signing keys (required for updates)**  
   Generate a key pair and set the public key in `desktop/src-tauri/tauri.conf.json`:

   ```bash
   cd desktop && npm run tauri signer generate -- -w ~/.tauri/aion.key
   ```

   Copy the contents of the generated `.pub` file into `plugins.updater.pubkey` in `tauri.conf.json` (as a string).

2. **Build with signing**  
   When building (locally or in CI), set the private key so Tauri can create `.sig` files:

   - Windows: `$env:TAURI_SIGNING_PRIVATE_KEY = "content or path of private key"`
   - macOS/Linux: `export TAURI_SIGNING_PRIVATE_KEY="content or path of private key"`

   Then run `npm run tauri build` as usual. The build will produce `.sig` files next to the installers.

3. **Endpoint**  
   The config points to:

   `https://github.com/aion-app/aion/releases/latest/download/latest.json`

   Replace `aion-app/aion` with your GitHub `owner/repo` if different. The app will request this URL to see if an update is available.

4. **`latest.json` on each release**  
   For each release, the updater expects a file named `latest.json` in the release assets. Its format:

   ```json
   {
     "version": "0.2.0",
     "notes": "Release notes",
     "pub_date": "2024-01-15T12:00:00Z",
     "platforms": {
       "windows-x86_64": {
         "signature": "<contents of .msi.sig or .exe.sig>",
         "url": "https://github.com/owner/repo/releases/download/v0.2.0/Aion_0.2.0_x64_en-US.msi"
       },
       "darwin-aarch64": {
         "signature": "<contents of .app.tar.gz.sig>",
         "url": "https://github.com/owner/repo/releases/download/v0.2.0/Aion_0.2.0_aarch64.app.tar.gz"
       }
     }
   }
   ```

   You can add a step to your release workflow that generates `latest.json` from the built artifacts and uploads it to the release.

## In-app behavior

- **Settings → Check for updates**: Runs the update check. If an update is found, the app downloads and installs it, then restarts.
- Updates are verified using the configured public key; do not share or commit the private key.
