# Cloudflare Tunnel Setup for Aion Backend

When you're not on the same LAN as your Windows PC (e.g. phone on cellular), devices can still reach the Aion backend using a **Cloudflare Tunnel**. The tunnel exposes your local backend via a public HTTPS URL that forwards to `http://localhost:8000` on this PC.

## Prerequisites

- A Cloudflare account (free tier is enough).
- Your backend running on this PC (e.g. `http://127.0.0.1:8000`).

## 1. Install cloudflared

On Windows:

- Download from [Cloudflare Zero Trust](https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/install-and-setup/installation/) or use winget: `winget install Cloudflare.cloudflared`
- Or download the executable from GitHub: [cloudflared releases](https://github.com/cloudflare/cloudflared/releases)

## 2. Log in to Cloudflare

```bash
cloudflared tunnel login
```

A browser window opens; sign in and authorize the connector for your domain (or use a subdomain).

## 3. Create a tunnel

```bash
# Create a named tunnel (e.g. "aion")
cloudflared tunnel create aion
```

Note the tunnel ID from the output.

## 4. Configure the tunnel

Create a config file, e.g. `%USERPROFILE%\.cloudflared\config.yml` (or the path shown after `tunnel create`):

```yaml
tunnel: <TUNNEL_ID>
credentials-file: C:\Users\<YOU>\.cloudflared\<TUNNEL_ID>.json

ingress:
  - hostname: aion.yourdomain.com
    service: http://localhost:8000
  - hostname: aion-ws.yourdomain.com
    service: http://localhost:8000
  - service: http_status:404
```

Replace:

- `<TUNNEL_ID>` with the ID from step 3.
- `aion.yourdomain.com` with a hostname you control in Cloudflare (DNS → add CNAME for that hostname to `<TUNNEL_ID>.cfargotunnel.com`).

For a quick test without a custom domain you can use a quick tunnel:

```bash
cloudflared tunnel --url http://localhost:8000
```

This prints a temporary URL like `https://xxxx-xx-xx.trycloudflare.com`. Use that URL (with `https://`) as the server URL in the Aion mobile/desktop app when off-LAN.

## 5. Run the tunnel

```bash
cloudflared tunnel run aion
```

Keep this running while you want the backend reachable from the internet. Optionally install and run as a Windows service so it starts on boot.

## 6. Client configuration

- **On LAN:** Use `https://<this-PC-LAN-IP>` (or your HTTPS URL) as the Aion server URL.
- **Off LAN (e.g. phone on cellular):** Set the Aion server URL to your tunnel URL, e.g. `https://aion.yourdomain.com` or the trycloudflare.com URL. Ensure the path is the API base, e.g. `https://aion.yourdomain.com/api/v1` if your app expects that.

In **Aion mobile**: Settings → Server URL → enter `https://<tunnel-hostname>` (and WebSocket URL will be derived as `wss://<tunnel-hostname>`).

In **Aion desktop**: Set the server URL in settings/local storage to the same `https://` tunnel URL.

## Security

- The tunnel is HTTPS by default; traffic is encrypted.
- Keep **auth required** for all sync and API endpoints so only logged-in devices can access data.
- Prefer a custom domain you control so you can revoke or change the tunnel without relying on trycloudflare.com.
