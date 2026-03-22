use serde_json::{json, Value as JsonValue};
use std::process::Command;

#[tauri::command]
pub fn check_docker_installed() -> Result<JsonValue, String> {
    let version_output = Command::new("docker")
        .arg("--version")
        .output();

    let (installed, version) = match version_output {
        Ok(output) if output.status.success() => {
            (true, String::from_utf8_lossy(&output.stdout).trim().to_string())
        }
        _ => (false, String::new()),
    };

    let compose_installed = Command::new("docker")
        .args(["compose", "version"])
        .output()
        .map(|o| o.status.success())
        .unwrap_or(false);

    Ok(json!({
        "installed": installed && compose_installed,
        "version": version,
    }))
}

#[tauri::command]
pub fn check_docker_running() -> Result<JsonValue, String> {
    let running = Command::new("docker")
        .arg("info")
        .output()
        .map(|o| o.status.success())
        .unwrap_or(false);

    Ok(json!({ "running": running }))
}

#[cfg(target_os = "windows")]
#[tauri::command]
pub fn install_docker() -> Result<JsonValue, String> {
    use std::env;

    let temp_dir = env::temp_dir();
    let installer_path = temp_dir.join("DockerDesktopInstaller.exe");
    let url = "https://desktop.docker.com/win/main/amd64/Docker%20Desktop%20Installer.exe";

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

    let install = Command::new("powershell")
        .args([
            "-Command",
            &format!(
                "Start-Process '{}' -ArgumentList 'install','--quiet','--accept-license' -Verb RunAs -Wait",
                installer_path.display()
            ),
        ])
        .output()
        .map_err(|e| format!("Install failed: {}", e))?;

    let success = install.status.success();
    let error_msg = if success {
        None
    } else {
        Some(String::from_utf8_lossy(&install.stderr).to_string())
    };

    Ok(json!({
        "success": success,
        "error": error_msg,
    }))
}

#[cfg(not(target_os = "windows"))]
#[tauri::command]
pub fn install_docker() -> Result<JsonValue, String> {
    Ok(json!({
        "success": false,
        "error": "Auto-install is only supported on Windows. Please install Docker Desktop manually.",
    }))
}

#[tauri::command]
pub fn start_docker_compose(
    compose_path: String,
    env_vars: Option<std::collections::HashMap<String, String>>,
) -> Result<JsonValue, String> {
    let mut cmd = Command::new("docker");
    cmd.args(["compose", "-f", &compose_path, "up", "-d"]);

    if let Some(vars) = env_vars {
        for (key, value) in vars {
            cmd.env(key, value);
        }
    }

    let output = cmd.output().map_err(|e| format!("Failed to start: {}", e))?;
    let success = output.status.success();
    let error_msg = if success {
        None
    } else {
        Some(String::from_utf8_lossy(&output.stderr).to_string())
    };

    Ok(json!({
        "success": success,
        "error": error_msg,
    }))
}

#[tauri::command]
pub fn stop_docker_compose(compose_path: String) -> Result<JsonValue, String> {
    let output = Command::new("docker")
        .args(["compose", "-f", &compose_path, "down"])
        .output()
        .map_err(|e| format!("Failed to stop: {}", e))?;

    Ok(json!({ "success": output.status.success() }))
}

#[tauri::command]
pub fn get_docker_compose_status(compose_path: String) -> Result<JsonValue, String> {
    let output = Command::new("docker")
        .args(["compose", "-f", &compose_path, "ps", "--format", "json"])
        .output()
        .map_err(|e| format!("Failed to get status: {}", e))?;

    if !output.status.success() {
        return Ok(json!({ "containers": [] }));
    }

    let stdout = String::from_utf8_lossy(&output.stdout);
    let containers: Vec<JsonValue> = stdout
        .lines()
        .filter_map(|line| serde_json::from_str(line).ok())
        .collect();

    Ok(json!({ "containers": containers }))
}

#[tauri::command]
pub async fn check_backend_health(url: Option<String>) -> Result<JsonValue, String> {
    let health_url = url.unwrap_or_else(|| "http://localhost:8000/health".to_string());

    let client = reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(5))
        .build()
        .map_err(|e| e.to_string())?;

    match client.get(&health_url).send().await {
        Ok(resp) if resp.status().is_success() => {
            let body: JsonValue = resp.json().await.unwrap_or(json!({}));
            Ok(json!({
                "healthy": true,
                "version": body.get("version").and_then(|v| v.as_str()).unwrap_or("unknown"),
            }))
        }
        Ok(resp) => Ok(json!({
            "healthy": false,
            "error": format!("HTTP {}", resp.status()),
        })),
        Err(e) => Ok(json!({
            "healthy": false,
            "error": e.to_string(),
        })),
    }
}
