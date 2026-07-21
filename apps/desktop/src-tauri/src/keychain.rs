//! macOS Keychain 凭据 Broker（VF-007；架构规则：凭据只以 handle 流转）。
//!
//! 安全边界：`unseal`（取回明文）**不**注册为 Tauri 命令——WebView 永远
//! 拿不到秘密值；未来 sidecar 经本地 IPC 向 Broker 换取短期凭据时才用。
//! 本模块不打印、不返回、不记录秘密值本身。
//!
//! `CredentialStore` trait 隔离存储后端：生产用 macOS Keychain（keyring
//! crate），测试用内存实现——keyring 的 mock 不跨 Entry 共享状态，无法
//! 测持久化语义；真 Keychain 行为由 E2E 里 `security` CLI 实证。

use keyring::Entry;

const SERVICE: &str = "dev.videoforge.credentials";

pub trait CredentialStore: Send + Sync {
    fn set(&self, handle: &str, secret: &str) -> Result<(), String>;
    fn get(&self, handle: &str) -> Result<Option<String>, String>;
    fn remove(&self, handle: &str) -> Result<(), String>;
}

pub struct KeychainStore;

impl KeychainStore {
    fn entry(handle: &str) -> Result<Entry, String> {
        Entry::new(SERVICE, handle).map_err(|e| format!("keychain entry 失败: {e}"))
    }
}

impl CredentialStore for KeychainStore {
    fn set(&self, handle: &str, secret: &str) -> Result<(), String> {
        Self::entry(handle)?
            .set_password(secret)
            .map_err(|e| format!("写入 Keychain 失败: {e}"))
    }

    fn get(&self, handle: &str) -> Result<Option<String>, String> {
        match Self::entry(handle)?.get_password() {
            Ok(secret) => Ok(Some(secret)),
            Err(keyring::Error::NoEntry) => Ok(None),
            Err(e) => Err(format!("读取 Keychain 失败: {e}")),
        }
    }

    fn remove(&self, handle: &str) -> Result<(), String> {
        match Self::entry(handle)?.delete_credential() {
            Ok(()) | Err(keyring::Error::NoEntry) => Ok(()),
            Err(e) => Err(format!("删除 Keychain 条目失败: {e}")),
        }
    }
}

fn validate_handle(handle: &str) -> Result<(), String> {
    if handle.trim().is_empty() {
        return Err("credential handle 不能为空".into());
    }
    Ok(())
}

pub fn store(backend: &dyn CredentialStore, handle: &str, secret: &str) -> Result<(), String> {
    validate_handle(handle)?;
    if secret.is_empty() {
        return Err("secret 不能为空".into());
    }
    backend.set(handle, secret)
}

pub fn exists(backend: &dyn CredentialStore, handle: &str) -> Result<bool, String> {
    validate_handle(handle)?;
    Ok(backend.get(handle)?.is_some())
}

pub fn delete(backend: &dyn CredentialStore, handle: &str) -> Result<(), String> {
    validate_handle(handle)?;
    backend.remove(handle)
}

/// 仅进程内使用：给未来的 sidecar IPC Broker 用，绝不暴露为 Tauri 命令。
#[allow(dead_code)]
pub fn unseal(backend: &dyn CredentialStore, handle: &str) -> Result<String, String> {
    validate_handle(handle)?;
    backend
        .get(handle)?
        .ok_or_else(|| format!("credential handle 不存在: {handle}"))
}

#[cfg(test)]
mod tests {
    use std::collections::HashMap;
    use std::sync::Mutex;

    use super::*;

    #[derive(Default)]
    struct InMemoryStore(Mutex<HashMap<String, String>>);

    impl CredentialStore for InMemoryStore {
        fn set(&self, handle: &str, secret: &str) -> Result<(), String> {
            self.0.lock().unwrap().insert(handle.into(), secret.into());
            Ok(())
        }

        fn get(&self, handle: &str) -> Result<Option<String>, String> {
            Ok(self.0.lock().unwrap().get(handle).cloned())
        }

        fn remove(&self, handle: &str) -> Result<(), String> {
            self.0.lock().unwrap().remove(handle);
            Ok(())
        }
    }

    #[test]
    fn roundtrip_store_exists_unseal_delete() {
        let backend = InMemoryStore::default();
        let handle = "test-handle";
        assert!(!exists(&backend, handle).unwrap());
        store(&backend, handle, "s3cret-value").unwrap();
        assert!(exists(&backend, handle).unwrap());
        assert_eq!(unseal(&backend, handle).unwrap(), "s3cret-value");
        delete(&backend, handle).unwrap();
        assert!(!exists(&backend, handle).unwrap());
    }

    #[test]
    fn empty_handle_and_secret_rejected() {
        let backend = InMemoryStore::default();
        assert!(store(&backend, "", "x").is_err());
        assert!(store(&backend, "h", "").is_err());
    }

    #[test]
    fn delete_missing_is_idempotent() {
        let backend = InMemoryStore::default();
        delete(&backend, "never-existed").unwrap();
    }

    #[test]
    fn unseal_missing_handle_errors() {
        let backend = InMemoryStore::default();
        assert!(unseal(&backend, "ghost").is_err());
    }
}
