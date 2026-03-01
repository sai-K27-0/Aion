# Run Aion on your Android Tab (Samsung Galaxy Tab S10 FE+)

Follow these steps to install and use Aion on your Tab S10 FE+ so it syncs with your Windows PC.

---

## 1. On your Windows PC

### 1.1 Start the backend

From a terminal on this PC:

```powershell
cd c:\projects\aion\backend
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Leave this running. Your Tab will connect to this PC over your Wi‑Fi.

### 1.2 Note your PC’s IP address

In PowerShell:

```powershell
ipconfig
```

Find the **IPv4 Address** for your Wi‑Fi adapter (e.g. `192.168.1.100`). The Tab will use:

**Server URL:** `http://YOUR_PC_IP:8000/api/v1`  
Example: `http://192.168.1.100:8000/api/v1`

(Use HTTPS and a self-signed cert only if you’ve already set that up; see `docs/HTTPS_AND_TLS_SETUP.md`.)

### 1.3 Create your account (first time only)

Sync requires login. Create one user from this PC:

```powershell
curl -X POST "http://localhost:8000/api/v1/auth/register" -H "Content-Type: application/json" -d "{\"username\":\"yourname\",\"email\":\"you@example.com\",\"password\":\"YourSecurePassword123\"}"
```

Use the same username/password on the Tab (and other devices) to log in.

---

## 2. Get the Aion Android APK

### Option A: From a GitHub release (after you’ve pushed a tag)

1. Push a version tag to trigger the build:
   ```powershell
   cd c:\projects\aion
   git tag v0.2.0
   git push origin v0.2.0
   ```
2. In GitHub: **Releases** → open the new release (e.g. `v0.2.0`).
3. Download the **ARM64** APK (for Tab S10 FE+):
   - Look for **Aion-Android-arm64-v8a** or a file like `app-production-arm64-v8a-release.apk`.
   - If there’s only a universal APK, use that.

### Option B: Build the APK on this PC

If you have Flutter installed:

```powershell
cd c:\projects\aion\mobile
flutter pub get
dart run build_runner build --delete-conflicting-outputs
flutter build apk --release --flavor production
```

APK path:  
`mobile\build\app\outputs\flutter-apk\app-production-release.apk`  
(or `app-production-arm64-v8a-release.apk` if you use `--split-per-abi`).

---

## 3. Install Aion on the Tab S10 FE+

1. Copy the APK to the Tab (USB, cloud, or download from GitHub on the Tab).
2. On the Tab, open the APK file and install. If asked, allow “Install from unknown sources” for your browser or file manager.
3. Open **Aion** from the app drawer.

---

## 4. Connect the Tab to your PC

1. **Connect to server**
   - On first launch you’ll see **“Connect to Aion”**.
   - Enter: `http://YOUR_PC_IP:8000/api/v1`  
     (replace `YOUR_PC_IP` with the IP from step 1.2).
   - Tap **Connect**. You should see “Connected to Aion server” and go to the home screen.

2. **Log in (required for sync)**
   - Sync (and device registration) now require login. If the app has a **Settings → Login** (or similar), enter the same username and password you used in step 1.3.
   - If there is no login screen yet, sync will fail with “unauthorized” until you add one or log in via another method. The backend expects `Authorization: Bearer <token>` on sync; the app stores tokens after login.

3. **Same Wi‑Fi**
   - The Tab and the PC must be on the same local network (same Wi‑Fi) when using `http://PC_IP:8000`.

---

## 5. Using the app on the Tab

- **Tasks, Blocks, Chat:** Use the bottom nav (Tasks, Blocks, Chat, Settings).
- **Sync:** Sync runs on open, when you leave the app, and about every 15 minutes. Tap the sync bar when it shows “Offline” or “Sync error” to retry.
- **Server URL / logout:** Open **Settings** to change the server URL or (when implemented) log out.

---

## 6. When you’re not on the same Wi‑Fi (optional)

To use the Tab on cellular or another network, set up **Cloudflare Tunnel** on your PC and use the tunnel URL as the server URL on the Tab. See `docs/CLOUDFLARE_TUNNEL_SETUP.md`.

---

## Quick checklist

| Step | Action |
|------|--------|
| 1 | Backend running on PC: `uv run uvicorn app.main:app --host 0.0.0.0 --port 8000` |
| 2 | Note PC IP (e.g. `192.168.1.100`) |
| 3 | Create user: `POST /api/v1/auth/register` (username, email, password) |
| 4 | Get APK from GitHub release (arm64) or build locally |
| 5 | Install APK on Tab S10 FE+ |
| 6 | In app: enter `http://PC_IP:8000/api/v1`, connect, then log in when the app supports it |
