//! Aion Desktop Client - Rust Backend
//!
//! This module provides:
//! - Screen capture functionality
//! - System tray management
//! - Global shortcut handling
//! - Native OS integrations
//! - Click-through overlay mode
//! - Start minimized to tray

#![cfg_attr(
    all(not(debug_assertions), target_os = "windows"),
    windows_subsystem = "windows"
)]

use base64::{engine::general_purpose::STANDARD, Engine};
use screenshots::Screen;
use std::io::Cursor;
use std::sync::atomic::{AtomicBool, Ordering};
use tauri::{Emitter, Manager};
use tauri::menu::MenuBuilder;
use tauri::tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent};

// Global state for click-through mode
static CLICK_THROUGH_ENABLED: AtomicBool = AtomicBool::new(false);

#[cfg(target_os = "macos")]
use objc::{msg_send, sel, sel_impl};
#[cfg(target_os = "macos")]
use objc::runtime::Class;

use keyring::Entry;

// Keyring service name for Aion
const KEYRING_SERVICE: &str = "com.aion.desktop";

// =============================================================================
// Secure Storage Commands
// =============================================================================

/// Get a value from secure storage (OS keychain)
#[tauri::command]
fn secure_storage_get(key: String) -> Result<Option<String>, String> {
    let entry = Entry::new(KEYRING_SERVICE, &key)
        .map_err(|e| format!("Failed to create keyring entry: {}", e))?;
    
    match entry.get_password() {
        Ok(password) => Ok(Some(password)),
        Err(keyring::Error::NoEntry) => Ok(None),
        Err(e) => Err(format!("Failed to get from keychain: {}", e)),
    }
}

/// Set a value in secure storage (OS keychain)
#[tauri::command]
fn secure_storage_set(key: String, value: String) -> Result<(), String> {
    let entry = Entry::new(KEYRING_SERVICE, &key)
        .map_err(|e| format!("Failed to create keyring entry: {}", e))?;
    
    entry
        .set_password(&value)
        .map_err(|e| format!("Failed to save to keychain: {}", e))
}

/// Delete a value from secure storage (OS keychain)
#[tauri::command]
fn secure_storage_delete(key: String) -> Result<(), String> {
    let entry = Entry::new(KEYRING_SERVICE, &key)
        .map_err(|e| format!("Failed to create keyring entry: {}", e))?;
    
    match entry.delete_password() {
        Ok(_) => Ok(()),
        Err(keyring::Error::NoEntry) => Ok(()), // Already deleted
        Err(e) => Err(format!("Failed to delete from keychain: {}", e)),
    }
}

/// Check if a key exists in secure storage
#[tauri::command]
fn secure_storage_exists(key: String) -> Result<bool, String> {
    let entry = Entry::new(KEYRING_SERVICE, &key)
        .map_err(|e| format!("Failed to create keyring entry: {}", e))?;
    
    match entry.get_password() {
        Ok(_) => Ok(true),
        Err(keyring::Error::NoEntry) => Ok(false),
        Err(e) => Err(format!("Failed to check keychain: {}", e)),
    }
}

/// Close the application window
#[tauri::command]
fn close_window(app_handle: tauri::AppHandle) -> Result<(), String> {
    if let Some(window) = app_handle.get_webview_window("main") {
        window.close().map_err(|e| format!("Failed to close window: {}", e))?;
    }
    Ok(())
}

/// Exit the application process (use after sync is complete)
#[tauri::command]
fn exit_app() {
    std::process::exit(0);
}

// =============================================================================
// Click-Through Mode Commands
// =============================================================================

/// Toggle click-through mode for overlay
#[tauri::command]
fn toggle_click_through(app_handle: tauri::AppHandle) -> Result<bool, String> {
    let window = app_handle.get_webview_window("main")
        .ok_or_else(|| "Window not found".to_string())?;
    
    let current = CLICK_THROUGH_ENABLED.load(Ordering::SeqCst);
    let new_state = !current;
    
    // On Windows, we use web-based click-through via CSS pointer-events
    // The actual window click-through is handled by the frontend
    // This avoids Windows API version conflicts
    #[cfg(target_os = "windows")]
    {
        // Just store the state - frontend handles CSS pointer-events
        println!("Click-through mode set to: {}", new_state);
    }
    
    #[cfg(target_os = "macos")]
    {
        // Tauri 2: native click-through would use raw window handle; frontend can use pointer-events
        println!("Click-through mode set to: {} (macOS)", new_state);
    }
    
    #[cfg(target_os = "linux")]
    {
        // Linux X11 would need different handling through x11 crate
        // For now, just store the state
    }
    
    CLICK_THROUGH_ENABLED.store(new_state, Ordering::SeqCst);
    
    // Emit event to frontend so it knows the state
    let _ = window.emit("Click-through-changed", new_state);
    
    Ok(new_state)
}

/// Set click-through state (called by frontend with enabled: bool)
#[tauri::command]
fn set_click_through(app_handle: tauri::AppHandle, enabled: bool) -> Result<(), String> {
    CLICK_THROUGH_ENABLED.store(enabled, Ordering::SeqCst);
    if let Some(w) = app_handle.get_webview_window("main") {
        let _ = w.emit("Click-through-changed", enabled);
    }
    Ok(())
}

/// Get current click-through state
#[tauri::command]
fn get_click_through_state() -> bool {
    CLICK_THROUGH_ENABLED.load(Ordering::SeqCst)
}

// =============================================================================
// Window State Commands
// =============================================================================

/// Minimize window to system tray
#[tauri::command]
fn minimize_to_tray(app_handle: tauri::AppHandle) -> Result<(), String> {
    if let Some(window) = app_handle.get_webview_window("main") {
        window.hide().map_err(|e| format!("Failed to hide window: {}", e))?;
    }
    Ok(())
}

/// Show window from tray
#[tauri::command]
fn show_from_tray(app_handle: tauri::AppHandle) -> Result<(), String> {
    if let Some(window) = app_handle.get_webview_window("main") {
        window.show().map_err(|e| format!("Failed to show window: {}", e))?;
        window.set_focus().map_err(|e| format!("Failed to focus window: {}", e))?;
    }
    Ok(())
}

/// Check if window is visible
#[tauri::command]
fn is_window_visible(app_handle: tauri::AppHandle) -> Result<bool, String> {
    if let Some(window) = app_handle.get_webview_window("main") {
        Ok(window.is_visible().unwrap_or(false))
    } else {
        Ok(false)
    }
}

// =============================================================================
// Ollama Proxy (avoids CORS when frontend calls localhost:11434)
// =============================================================================

#[derive(serde::Serialize, serde::Deserialize)]
struct OllamaGenerateRequest {
    model: String,
    prompt: String,
    stream: bool,
}

#[derive(serde::Deserialize)]
struct OllamaGenerateResponse {
    response: Option<String>,
}

/// Call Ollama /api/generate from Rust so the webview doesn't hit CORS.
#[tauri::command]
async fn ollama_generate(prompt: String, model: String) -> Result<String, String> {
    let client = reqwest::Client::new();
    let body = OllamaGenerateRequest {
        model: if model.is_empty() { "llama3.2".to_string() } else { model },
        prompt,
        stream: false,
    };
    let res = client
        .post("http://127.0.0.1:11434/api/generate")
        .json(&body)
        .send()
        .await
        .map_err(|e| format!("Ollama connection failed: {}", e))?;
    if !res.status().is_success() {
        return Err(format!("Ollama error: {}", res.status()));
    }
    let data: OllamaGenerateResponse = res
        .json()
        .await
        .map_err(|e| format!("Ollama response error: {}", e))?;
    Ok(data.response.unwrap_or_default().trim().to_string())
}

// =============================================================================
// Screen Capture Commands
// =============================================================================

/// Capture the entire primary screen and return as base64 PNG
#[tauri::command]
async fn capture_screen() -> Result<String, String> {
    // Get all screens
    let screens = Screen::all().map_err(|e| format!("Failed to get screens: {}", e))?;

    // Use primary screen (first one)
    let screen = screens
        .first()
        .ok_or_else(|| "No screens found".to_string())?;

    // Capture the screen
    let image = screen
        .capture()
        .map_err(|e| format!("Failed to capture screen: {}", e))?;

    // Convert to PNG bytes
    let mut bytes: Vec<u8> = Vec::new();
    image
        .write_to(&mut Cursor::new(&mut bytes), image::ImageOutputFormat::Png)
        .map_err(|e| format!("Failed to encode image: {}", e))?;

    // Encode as base64
    let base64_string = STANDARD.encode(&bytes);

    Ok(base64_string)
}

/// Capture a specific region of the screen
#[tauri::command]
async fn capture_region(x: i32, y: i32, width: u32, height: u32) -> Result<String, String> {
    let screens = Screen::all().map_err(|e| format!("Failed to get screens: {}", e))?;

    let screen = screens
        .first()
        .ok_or_else(|| "No screens found".to_string())?;

    // Capture region
    let image = screen
        .capture_area(x, y, width, height)
        .map_err(|e| format!("Failed to capture region: {}", e))?;

    // Convert to PNG bytes
    let mut bytes: Vec<u8> = Vec::new();
    image
        .write_to(&mut Cursor::new(&mut bytes), image::ImageOutputFormat::Png)
        .map_err(|e| format!("Failed to encode image: {}", e))?;

    // Encode as base64
    let base64_string = STANDARD.encode(&bytes);

    Ok(base64_string)
}

/// Get active window title
#[tauri::command]
fn get_active_window_title() -> Result<String, String> {
    #[cfg(target_os = "windows")]
    {
        get_active_window_title_windows()
    }
    
    #[cfg(target_os = "macos")]
    {
        get_active_window_title_macos()
    }
    
    #[cfg(target_os = "linux")]
    {
        get_active_window_title_linux()
    }
}

#[cfg(target_os = "windows")]
fn get_active_window_title_windows() -> Result<String, String> {
    use windows::Win32::UI::WindowsAndMessaging::{GetForegroundWindow, GetWindowTextW};
    
    unsafe {
        let hwnd = GetForegroundWindow();
        if hwnd.0 == std::ptr::null_mut() {
            return Err("No foreground window found".to_string());
        }
        
        // Buffer for window title (max 256 chars)
        let mut buffer = [0u16; 256];
        let len = GetWindowTextW(hwnd, &mut buffer);
        
        if len == 0 {
            return Ok("Unknown Window".to_string());
        }
        
        // Convert from UTF-16 to String
        let title = String::from_utf16_lossy(&buffer[..len as usize]);
        Ok(title)
    }
}

#[cfg(target_os = "macos")]
fn get_active_window_title_macos() -> Result<String, String> {
    unsafe {
        let workspace_class = Class::get("NSWorkspace").ok_or_else(|| "NSWorkspace class not found".to_string())?;
        let workspace: *mut objc::runtime::Object = msg_send![workspace_class, sharedWorkspace];
        let frontmost_app: *mut objc::runtime::Object = msg_send![workspace, frontmostApplication];
        
        if frontmost_app.is_null() {
            return Ok("Unknown Application".to_string());
        }
        
        let localized_name: *mut objc::runtime::Object = msg_send![frontmost_app, localizedName];
        
        if localized_name.is_null() {
            return Ok("Unknown Application".to_string());
        }
        
        let utf8_ptr: *const i8 = msg_send![localized_name, UTF8String];
        if utf8_ptr.is_null() {
            return Ok("Unknown Application".to_string());
        }
        
        let name = std::ffi::CStr::from_ptr(utf8_ptr)
            .to_string_lossy()
            .to_string();
        
        Ok(name)
    }
}

#[cfg(target_os = "linux")]
fn get_active_window_title_linux() -> Result<String, String> {
    // Basic X11 implementation - requires x11 crate
    // For Wayland, this would need different handling
    Ok("Active Window (Linux)".to_string())
}

/// Open a system application
#[tauri::command]
fn open_system_app(app_name: String) -> Result<String, String> {
    #[cfg(target_os = "windows")]
    {
        let command = match app_name.to_lowercase().as_str() {
            "calculator" | "calc" => "calc",
            "notepad" | "notes" => "notepad",
            "explorer" | "files" | "file explorer" | "finder" => "explorer",
            "cmd" | "terminal" | "command prompt" => "cmd",
            "powershell" => "powershell",
            _ => return Err(format!("I don't know how to open '{}' yet.", app_name)),
        };

        std::process::Command::new(command)
            .spawn()
            .map_err(|e| format!("Failed to launch {}: {}", command, e))?;

        Ok(format!("Opened {}", command))
    }
    
    #[cfg(target_os = "macos")]
    {
        let app_path = match app_name.to_lowercase().as_str() {
            "calculator" | "calc" => "/System/Applications/Calculator.app",
            "notes" | "notepad" => "/System/Applications/Notes.app",
            "finder" | "files" | "explorer" | "file explorer" => "/System/Library/CoreServices/Finder.app",
            "terminal" | "cmd" | "command prompt" => "/System/Applications/Utilities/Terminal.app",
            "safari" => "/Applications/Safari.app",
            "settings" | "preferences" | "system preferences" => "/System/Applications/System Settings.app",
            "calendar" => "/System/Applications/Calendar.app",
            "reminders" => "/System/Applications/Reminders.app",
            "mail" => "/System/Applications/Mail.app",
            _ => return Err(format!("I don't know how to open '{}' yet.", app_name)),
        };

        std::process::Command::new("open")
            .arg(app_path)
            .spawn()
            .map_err(|e| format!("Failed to launch {}: {}", app_path, e))?;

        Ok(format!("Opened {}", app_name))
    }
    
    #[cfg(target_os = "linux")]
    {
        let command = match app_name.to_lowercase().as_str() {
            "calculator" | "calc" => "gnome-calculator",
            "files" | "explorer" | "finder" | "file explorer" => "nautilus",
            "terminal" | "cmd" | "command prompt" => "gnome-terminal",
            "settings" | "preferences" => "gnome-control-center",
            _ => return Err(format!("I don't know how to open '{}' yet.", app_name)),
        };

        std::process::Command::new(command)
            .spawn()
            .map_err(|e| format!("Failed to launch {}: {}", command, e))?;

        Ok(format!("Opened {}", command))
    }
}

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_updater::Builder::new().build())
        .plugin(tauri_plugin_process::init())
        .plugin(
            tauri_plugin_global_shortcut::Builder::new()
                .with_shortcuts(["Alt+Space", "Alt+G"])
                .expect("register global shortcuts")
                .with_handler(|app, shortcut, event| {
                    use tauri_plugin_global_shortcut::{Code, ShortcutState};
                    if event.state == ShortcutState::Pressed {
                        match shortcut.key {
                            Code::Space => {
                                if let Some(w) = app.get_webview_window("main") {
                                    let _ = w.show();
                                    let _ = w.set_focus();
                                }
                            }
                            Code::KeyG => {
                                if let Some(w) = app.get_webview_window("main") {
                                    let _ = w.emit("toggle-ghost", ());
                                }
                            }
                            _ => {}
                        }
                    }
                })
                .build(),
        )
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::CloseRequested { api, .. } = event {
                if window.label() == "main" {
                    api.prevent_close();
                    if let Some(w) = window.app_handle().get_webview_window("main") {
                        let _ = w.emit("sync-before-close", ());
                    }
                }
            }
        })
        .invoke_handler(tauri::generate_handler![
            ollama_generate,
            capture_screen,
            capture_region,
            get_active_window_title,
            open_system_app,
            secure_storage_get,
            secure_storage_set,
            secure_storage_delete,
            secure_storage_exists,
            close_window,
            exit_app,
            toggle_click_through,
            set_click_through,
            get_click_through_state,
            minimize_to_tray,
            show_from_tray,
            is_window_visible,
        ])
        .setup(|app| {
            // Tray menu (Tauri 2 API)
            let menu = MenuBuilder::new(app)
                .text("show", "Show Aion")
                .text("capture", "Capture Screen")
                .separator()
                .text("quit", "Quit")
                .build()?;

            let _tray = TrayIconBuilder::new()
                .menu(&menu)
                .on_menu_event(move |app, event| match event.id().as_ref() {
                    "show" => {
                        if let Some(window) = app.get_webview_window("main") {
                            let _ = window.show();
                            let _ = window.set_focus();
                        }
                    }
                    "capture" => {
                        if let Some(window) = app.get_webview_window("main") {
                            let _ = window.emit("trigger-capture", ());
                        }
                    }
                    "quit" => {
                        // Trigger sync before quitting instead of immediate exit
                        if let Some(window) = app.get_webview_window("main") {
                            let _ = window.emit("sync-before-close", ());
                        } else {
                            std::process::exit(0);
                        }
                    }
                    _ => {}
                })
                .on_tray_icon_event(|tray, event| {
                    if let TrayIconEvent::Click {
                        button: MouseButton::Left,
                        button_state: MouseButtonState::Up,
                        ..
                    } = event
                    {
                        let app = tray.app_handle();
                        if let Some(window) = app.get_webview_window("main") {
                            if window.is_visible().unwrap_or(false) {
                                let _ = window.hide();
                            } else {
                                let _ = window.show();
                                let _ = window.set_focus();
                            }
                        }
                    }
                })
                .build(app)?;

            let window = app.get_webview_window("main").unwrap();
            let _ = window.maximize();

            println!("Aion Desktop Client started");

            let args: Vec<String> = std::env::args().collect();
            if args.contains(&"--minimized".to_string()) || args.contains(&"--tray".to_string()) {
                window.hide().expect("Failed to hide window on startup");
                println!("Started minimized to system tray");
            }

            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building tauri application")
        .run(|app_handle, event| {
            if let tauri::RunEvent::ExitRequested { api, .. } = &event {
                // Prevent immediate exit (e.g. macOS Cmd+Q) so we can sync first.
                // If the window still exists, trigger sync; otherwise let the exit proceed.
                if let Some(w) = app_handle.get_webview_window("main") {
                    api.prevent_exit();
                    let _ = w.emit("sync-before-close", ());
                }
            }
        });
}
