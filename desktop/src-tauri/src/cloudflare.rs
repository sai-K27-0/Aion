use serde_json::{json, Value as JsonValue};
use std::process::Command;

#[tauri::command]
pub fn check_cloudflared() -> Result<JsonValue, String> {
    let output = Command::new("cloudflared")
        .arg("--version")
        .output();

    match output {
        Ok(o) if o.status.success() => {
            let version = String::from_utf8_lossy(&o.stdout).trim().to_string();
            Ok(json!({ "installed": true, "version": version }))
        }
        _ => Ok(json!({ "installed": false, "version": "" })),
    }
}

#[cfg(target_os = "windows")]
#[tauri::command]
pub fn install_cloudflared() -> Result<JsonValue, String> {
    use std::env;

    let temp_dir = env::temp_dir();
    let installer_path = temp_dir.join("cloudflared-windows-amd64.msi");
    let url = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.msi";

    let download = Command::new("powershell")
        .args([
            "-Command",
            &format!(
                "Invoke-WebRequest -Uri '{}' -OutFile '{}'",
                url,
                installer_path.display()
            ),
        ])
        .output()
        .map_err(|e| format!("Download failed: {}", e))?;

    if !download.status.success() {
        return Ok(json!({
            "success": false,
            "error": String::from_utf8_lossy(&download.stderr).to_string(),
        }));
    }

    let install = Command::new("msiexec")
        .args(["/i", &installer_path.display().to_string(), "/quiet"])
        .output()
        .map_err(|e| format!("Install failed: {}", e))?;

    Ok(json!({ "success": install.status.success() }))
}

#[cfg(target_os = "macos")]
#[tauri::command]
pub fn install_cloudflared() -> Result<JsonValue, String> {
    let output = Command::new("brew")
        .args(["install", "cloudflared"])
        .output()
        .map_err(|e| format!("brew install failed: {}", e))?;

    Ok(json!({ "success": output.status.success() }))
}

#[cfg(target_os = "linux")]
#[tauri::command]
pub fn install_cloudflared() -> Result<JsonValue, String> {
    let output = Command::new("bash")
        .args(["-c", "curl -fsSL https://pkg.cloudflare.com/cloudflare-main.gpg | sudo tee /usr/share/keyrings/cloudflare-main.gpg >/dev/null && sudo apt-get update && sudo apt-get install -y cloudflared"])
        .output()
        .map_err(|e| format!("Install failed: {}", e))?;

    Ok(json!({ "success": output.status.success() }))
}

#[tauri::command]
pub async fn start_quick_tunnel(port: u16) -> Result<JsonValue, String> {
    use tokio::process::Command as AsyncCommand;
    use tokio::io::{AsyncBufReadExt, BufReader};

    let mut child = AsyncCommand::new("cloudflared")
        .args(["tunnel", "--url", &format!("http://localhost:{}", port)])
        .stderr(std::process::Stdio::piped())
        .stdout(std::process::Stdio::piped())
        .spawn()
        .map_err(|e| format!("Failed to start tunnel: {}", e))?;

    let stderr = child.stderr.take().ok_or("No stderr")?;
    let mut reader = BufReader::new(stderr).lines();

    let timeout = tokio::time::timeout(
        std::time::Duration::from_secs(30),
        async {
            while let Ok(Some(line)) = reader.next_line().await {
                if let Some(url_start) = line.find("https://") {
                    let url_part = &line[url_start..];
                    if let Some(url_end) = url_part.find(|c: char| c.is_whitespace() || c == '|') {
                        let url = &url_part[..url_end];
                        if url.contains("trycloudflare.com") {
                            return Ok::<String, String>(url.to_string());
                        }
                    } else if url_part.contains("trycloudflare.com") {
                        return Ok(url_part.trim().to_string());
                    }
                }
            }
            Err("Could not find tunnel URL in output".to_string())
        }
    ).await;

    match timeout {
        Ok(Ok(url)) => Ok(json!({ "url": url, "pid": child.id() })),
        Ok(Err(e)) => Err(e),
        Err(_) => Err("Tunnel startup timed out after 30 seconds".to_string()),
    }
}
