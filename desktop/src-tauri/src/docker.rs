use serde_json::{json, Value as JsonValue};
use std::process::Command;

/// Find the docker executable, trying PATH first, then common install locations.
fn find_docker() -> Option<String> {
    // Try PATH first
    let try_path = Command::new("docker")
        .arg("--version")
        .output();
    if let Ok(output) = &try_path {
        if output.status.success() {
            return Some("docker".to_string());
        }
    }

    // Windows: try common install locations
    #[cfg(target_os = "windows")]
    {
        let candidates = [
            r"C:\Program Files\Docker\Docker\resources\bin\docker.exe",
            r"C:\Program Files (x86)\Docker\Docker\resources\bin\docker.exe",
        ];
        for path in &candidates {
            if std::path::Path::new(path).exists() {
                return Some(path.to_string());
            }
        }
    }

    None
}

#[tauri::command]
pub fn check_docker_installed() -> Result<JsonValue, String> {
    let docker = find_docker();

    let (installed, version) = match &docker {
        Some(docker_path) => {
            let version_output = Command::new(docker_path)
                .arg("--version")
                .output();
            match version_output {
                Ok(output) if output.status.success() => {
                    (true, String::from_utf8_lossy(&output.stdout).trim().to_string())
                }
                _ => (false, String::new()),
            }
        }
        None => (false, String::new()),
    };

    let compose_installed = match &docker {
        Some(docker_path) => {
            Command::new(docker_path)
                .args(["compose", "version"])
                .output()
                .map(|o| o.status.success())
                .unwrap_or(false)
        }
        None => false,
    };

    Ok(json!({
        "installed": installed && compose_installed,
        "version": version,
        "docker_path": docker,
    }))
}

#[tauri::command]
pub fn check_docker_running() -> Result<JsonValue, String> {
    let docker = find_docker();
    let running = match &docker {
        Some(docker_path) => {
            Command::new(docker_path)
                .arg("info")
                .output()
                .map(|o| o.status.success())
                .unwrap_or(false)
        }
        None => false,
    };

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
            "-NoProfile", "-Command",
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
            "-NoProfile", "-Command",
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

/// Launch Docker Desktop application (non-blocking).
#[tauri::command]
pub fn start_docker_desktop() -> Result<JsonValue, String> {
    #[cfg(target_os = "windows")]
    {
        // Try common Docker Desktop install paths
        let paths = [
            r"C:\Program Files\Docker\Docker\Docker Desktop.exe",
            r"C:\Program Files (x86)\Docker\Docker\Docker Desktop.exe",
        ];
        for path in &paths {
            if std::path::Path::new(path).exists() {
                Command::new(path)
                    .spawn()
                    .map_err(|e| format!("Failed to start Docker Desktop: {}", e))?;
                return Ok(json!({ "success": true }));
            }
        }
        // Fallback: try via shell
        let _ = Command::new("cmd")
            .args(["/C", "start", "", "Docker Desktop"])
            .spawn();
        return Ok(json!({ "success": true, "fallback": true }));
    }

    #[cfg(target_os = "macos")]
    {
        let _ = Command::new("open")
            .args(["-a", "Docker"])
            .spawn()
            .map_err(|e| format!("Failed to start Docker: {}", e))?;
        return Ok(json!({ "success": true }));
    }

    #[cfg(target_os = "linux")]
    {
        let _ = Command::new("systemctl")
            .args(["--user", "start", "docker-desktop"])
            .spawn();
        return Ok(json!({ "success": true }));
    }
}

/// Find the docker-compose.yml file by walking up from the executable location.
#[tauri::command]
pub fn find_compose_file() -> Result<JsonValue, String> {
    let exe_path = std::env::current_exe().unwrap_or_default();
    let mut searched = Vec::new();

    // Walk up from the exe directory looking for backend/docker-compose.yml
    let mut dir = exe_path.parent();
    while let Some(current) = dir {
        let candidate = current.join("backend").join("docker-compose.yml");
        searched.push(candidate.to_string_lossy().to_string());
        if candidate.exists() {
            // Return the parent directory (project root) so we can use
            // `docker compose` with the working directory set correctly.
            // Avoid canonicalize() on Windows — it adds \\?\ prefix which
            // breaks Docker volume mounts (colon in C: conflicts).
            let project_root = current.to_string_lossy().to_string();
            return Ok(json!({
                "found": true,
                "path": format!("{}/backend/docker-compose.yml", project_root.replace('\\', "/")),
                "project_root": project_root.replace('\\', "/"),
            }));
        }
        dir = current.parent();
    }

    // Also check CWD
    let cwd_candidate = std::path::PathBuf::from("backend/docker-compose.yml");
    searched.push(cwd_candidate.to_string_lossy().to_string());
    if cwd_candidate.exists() {
        let cwd = std::env::current_dir().unwrap_or_default();
        return Ok(json!({
            "found": true,
            "path": "backend/docker-compose.yml",
            "project_root": cwd.to_string_lossy().to_string().replace('\\', "/"),
        }));
    }

    Ok(json!({
        "found": false,
        "error": "docker-compose.yml not found. Please ensure the backend directory is accessible.",
        "searched": searched,
    }))
}

#[tauri::command]
pub fn start_docker_compose(
    compose_path: String,
    env_vars: Option<std::collections::HashMap<String, String>>,
) -> Result<JsonValue, String> {
    let docker = find_docker().unwrap_or_else(|| "docker".to_string());
    let compose_file = std::path::Path::new(&compose_path);
    let mut cmd = Command::new(&docker);

    // Set working directory to compose file's parent to avoid Windows path issues
    if let Some(parent) = compose_file.parent() {
        if parent.exists() {
            cmd.current_dir(parent);
            cmd.args(["compose", "up", "-d", "--build"]);
        } else {
            cmd.args(["compose", "-f", &compose_path, "up", "-d", "--build"]);
        }
    } else {
        cmd.args(["compose", "-f", &compose_path, "up", "-d", "--build"]);
    }

    if let Some(vars) = env_vars {
        for (key, value) in vars {
            cmd.env(key, value);
        }
    }

    let output = cmd.output().map_err(|e| format!("Failed to start: {}", e))?;
    let success = output.status.success();
    let stdout = String::from_utf8_lossy(&output.stdout).to_string();
    let stderr = String::from_utf8_lossy(&output.stderr).to_string();

    Ok(json!({
        "success": success,
        "error": if success { None } else { Some(&stderr) },
        "stdout": stdout,
        "stderr": stderr,
    }))
}

#[tauri::command]
pub fn stop_docker_compose(compose_path: String) -> Result<JsonValue, String> {
    let docker = find_docker().unwrap_or_else(|| "docker".to_string());
    let compose_file = std::path::Path::new(&compose_path);
    let mut cmd = Command::new(&docker);
    if let Some(parent) = compose_file.parent() {
        if parent.exists() {
            cmd.current_dir(parent);
        }
    }
    let output = cmd.args(["compose", "down"])
        .output()
        .map_err(|e| format!("Failed to stop: {}", e))?;

    Ok(json!({ "success": output.status.success() }))
}

#[tauri::command]
pub fn get_docker_compose_status(compose_path: String) -> Result<JsonValue, String> {
    let docker = find_docker().unwrap_or_else(|| "docker".to_string());
    let compose_file = std::path::Path::new(&compose_path);
    let mut cmd = Command::new(&docker);
    if let Some(parent) = compose_file.parent() {
        if parent.exists() {
            cmd.current_dir(parent);
        }
    }
    let output = cmd.args(["compose", "ps", "--format", "json"])
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
