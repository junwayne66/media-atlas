mod keychain;
mod sidecar;

use sidecar::SidecarStatus;

#[tauri::command]
fn sidecar_status() -> SidecarStatus {
    sidecar::read_status()
}

#[tauri::command]
fn start_sidecar() -> Result<String, String> {
    sidecar::start()
}

#[tauri::command]
fn stop_sidecar() -> Result<String, String> {
    sidecar::stop()
}

#[tauri::command]
fn credential_store(handle: String, secret: String) -> Result<(), String> {
    keychain::store(&keychain::KeychainStore, &handle, &secret)
}

#[tauri::command]
fn credential_exists(handle: String) -> Result<bool, String> {
    keychain::exists(&keychain::KeychainStore, &handle)
}

#[tauri::command]
fn credential_delete(handle: String) -> Result<(), String> {
    keychain::delete(&keychain::KeychainStore, &handle)
}

pub fn run() {
    tauri::Builder::default()
        .setup(|_app| {
            // 应用启动即拉起 sidecar；失败不阻塞 UI（窗口内可手动重试）
            if let Err(err) = sidecar::start() {
                eprintln!("sidecar 自启动失败: {err}");
            }
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            sidecar_status,
            start_sidecar,
            stop_sidecar,
            credential_store,
            credential_exists,
            credential_delete
        ])
        .run(tauri::generate_context!())
        .expect("tauri 运行失败");
}
