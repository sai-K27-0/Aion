//! Aion Desktop Client - Rust Backend
//!
//! This module provides:
//! - Screen capture functionality
//! - System tray management
//! - Global shortcut handling
//! - Native OS integrations

#![cfg_attr(
    all(not(debug_assertions), target_os = "windows"),
    windows_subsystem = "windows"
)]

use base64::{engine::general_purpose::STANDARD, Engine};
use screenshots::Screen;
use std::io::Cursor;
use tauri::{
    CustomMenuItem, Manager, SystemTray, SystemTrayEvent, SystemTrayMenu, SystemTrayMenuItem,
};

#[cfg(target_os = "macos")]
use cocoa::appkit::NSWorkspace;
#[cfg(target_os = "macos")]
use cocoa::base::nil;
#[cfg(target_os = "macos")]
use cocoa::foundation::NSString;
#[cfg(target_os = "macos")]
use objc::{msg_send, sel, sel_impl};

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
    
    match entry.delete_credential() {
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
        let workspace: *mut objc::runtime::Object = msg_send![class!(NSWorkspace), sharedWorkspace];
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

/// Create the system tray menu
fn create_system_tray() -> SystemTray {
    let show = CustomMenuItem::new("show".to_string(), "Show Aion");
    let capture = CustomMenuItem::new("capture".to_string(), "Capture Screen");
    let quit = CustomMenuItem::new("quit".to_string(), "Quit");

    let tray_menu = SystemTrayMenu::new()
        .add_item(show)
        .add_item(capture)
        .add_native_item(SystemTrayMenuItem::Separator)
        .add_item(quit);

    SystemTray::new().with_menu(tray_menu)
}

fn main() {
    tauri::Builder::default()
        .system_tray(create_system_tray())
        .on_system_tray_event(|app, event| match event {
            SystemTrayEvent::LeftClick { .. } => {
                // Toggle window visibility on left click
                if let Some(window) = app.get_window("main") {
                    if window.is_visible().unwrap_or(false) {
                        let _ = window.hide();
                    } else {
                        let _ = window.show();
                        let _ = window.set_focus();
                    }
                }
            }
            SystemTrayEvent::MenuItemClick { id, .. } => match id.as_str() {
                "show" => {
                    if let Some(window) = app.get_window("main") {
                        let _ = window.show();
                        let _ = window.set_focus();
                    }
                }
                "capture" => {
                    // Emit event to frontend to trigger capture
                    if let Some(window) = app.get_window("main") {
                        let _ = window.emit("trigger-capture", ());
                    }
                }
                "quit" => {
                    std::process::exit(0);
                }
                _ => {}
            },
            _ => {}
        })
        .invoke_handler(tauri::generate_handler![
            capture_screen,
            capture_region,
            get_active_window_title,
            open_system_app,
            secure_storage_get,
            secure_storage_set,
            secure_storage_delete,
            secure_storage_exists,
        ])
        .setup(|app| {
            // Get the main window
            let window = app.get_window("main").unwrap();

            // Set window to be transparent (if not already set in config)
            #[cfg(target_os = "windows")]
            {
                use tauri::Manager;
                // Windows-specific transparency setup could go here
            }

            // Log startup
            println!("Aion Desktop Client started");
            println!("Window transparent: {:?}", window.is_decorated());

            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
