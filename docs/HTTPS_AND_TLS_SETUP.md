# HTTPS and TLS Setup for Aion Backend

All sync traffic between devices and your Windows PC backend should use HTTPS so data is encrypted in transit. This document describes how to run the backend with TLS using a **self-signed certificate** and how to trust that certificate on each device.

## Overview

- **Backend** runs on this PC (e.g. `http://127.0.0.1:8000` internally).
- **Clients** (desktop, mobile, MacBook) connect over the network using **HTTPS**.
- Use a **self-signed certificate**; you will trust it once on each device to avoid browser/app certificate errors.

## Option A: Reverse proxy (Caddy) with self-signed cert

Run Caddy (or nginx) on this PC: listen on port 443 with TLS, proxy to `http://127.0.0.1:8000`.

### 1. Generate a self-signed certificate

On Windows (PowerShell as Admin), or use OpenSSL:

```powershell
# Using OpenSSL (install if needed, e.g. via Git for Windows or OpenSSL)
openssl req -x509 -newkey rsa:4096 -keyout key.pem -out cert.pem -days 365 -nodes -subj "/CN=aion.local"
```

Save `cert.pem` and `key.pem` in a folder, e.g. `C:\aion-tls\`.

### 2. Run Caddy with the certificate

Example Caddyfile (save as `Caddyfile`):

```
:443 {
    tls /path/to/cert.pem /path/to/key.pem
    reverse_proxy 127.0.0.1:8000
}
```

Run Caddy (after installing from https://caddyserver.com/):

```bash
caddy run
```

### 3. Client URLs

- **This PC (Windows desktop app):** `https://localhost` or `https://127.0.0.1`
- **Other devices on LAN:** `https://<this-PC-LAN-IP>` (e.g. `https://192.168.1.100`)
- **Optional local hostname:** If you set `CN=aion.local` and add `192.168.x.x  aion.local` to your hosts file (or LAN DNS), use `https://aion.local`

## Option B: Uvicorn with SSL

Run the FastAPI app with Uvicorn and TLS directly:

```bash
cd backend
uv run uvicorn app.main:app --host 0.0.0.0 --port 443 --ssl-keyfile=key.pem --ssl-certfile=cert.pem
```

Use the same `cert.pem` and `key.pem` from step 1. Client URLs are the same as in Option A.

## Trusting the self-signed certificate on each device

### Windows (this PC)

- **Desktop app (Tauri/Electron):** The system may prompt for certificate trust, or you can install the cert:
  - Double-click `cert.pem` → Install Certificate → Local Machine → Place in "Trusted Root Certification Authorities".
- **Browser:** When you first open `https://localhost` or `https://<IP>`, accept the security exception (e.g. "Advanced" → "Proceed to site").

### MacBook

- **System:** Keychain Access → File → Import Items → select `cert.pem` → add to "System" or "Login" keychain → double-click the cert → expand "Trust" → set "When using this certificate" to **Always Trust**.
- **Browser:** Same as Windows, or use the cert in Keychain as above.

### Android (phone / tablet)

- **Option 1:** Settings → Security → Encryption & credentials → Install a certificate → CA certificate → select the `.pem` file (you may need to copy `cert.pem` to the device and rename to `.crt`).
- **Option 2:** If the Aion app uses a custom HTTP client, you may need to configure it to trust the certificate (e.g. Android network security config with the cert in the app).

### Summary

| Device        | Base URL (LAN)              | Base URL (this PC only)   |
|---------------|-----------------------------|----------------------------|
| Windows PC    | `https://localhost` or `https://127.0.0.1` | same |
| MacBook       | `https://<PC-LAN-IP>` or `https://aion.local` | N/A |
| Android       | `https://<PC-LAN-IP>` or `https://aion.local` | N/A |

After trusting the cert, desktop and mobile config should use these base URLs (no `http://` in production). Sync and auth endpoints are then served over HTTPS.

---

## Data encryption at rest (optional)

To encrypt sensitive fields (e.g. block content, entry data) in the database, set a Fernet key:

```bash
# Generate a key (Python)
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Set in your environment or `.env`:

```
DATA_ENCRYPTION_KEY=<the-generated-key>
```

With this set, the backend encrypts sensitive fields before writing and decrypts when reading. Do not log this key or commit it to version control.
