//! Edge Agent Sidecar 生命周期（VF-007 DoD：关闭 UI 后 Sidecar 继续）。
//!
//! 关键设计：不用 Tauri 托管子进程（应用退出会连带杀死），而是
//! `process_group(0)` 把 sidecar 放进独立进程组并写 pidfile——
//! UI 进程退出后 sidecar 不受影响；下次启动通过 pidfile 重新接管。

use std::fs;
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};

use serde::Serialize;

#[derive(Serialize, Clone, Copy)]
pub struct SidecarStatus {
    pub running: bool,
    pub pid: Option<i32>,
}

fn state_dir() -> PathBuf {
    let base = std::env::var("VIDEOFORGE_STATE_DIR").unwrap_or_else(|_| {
        format!(
            "{}/Library/Application Support/dev.videoforge.desktop",
            std::env::var("HOME").unwrap_or_else(|_| "/tmp".into())
        )
    });
    PathBuf::from(base)
}

fn pidfile() -> PathBuf {
    state_dir().join("edge-agent.pid")
}

fn repo_root() -> PathBuf {
    // 开发期：src-tauri 的上三级即仓库根；打包分发时用环境变量覆盖
    std::env::var("VIDEOFORGE_REPO_ROOT")
        .map(PathBuf::from)
        .unwrap_or_else(|_| {
            Path::new(env!("CARGO_MANIFEST_DIR"))
                .ancestors()
                .nth(3)
                .expect("repo root")
                .to_path_buf()
        })
}

fn pid_alive(pid: i32) -> bool {
    // kill(pid, 0)：不发信号只探活
    unsafe { libc::kill(pid, 0) == 0 }
}

pub fn read_status() -> SidecarStatus {
    match fs::read_to_string(pidfile()) {
        Ok(text) => match text.trim().parse::<i32>() {
            Ok(pid) if pid_alive(pid) => SidecarStatus {
                running: true,
                pid: Some(pid),
            },
            _ => SidecarStatus {
                running: false,
                pid: None,
            },
        },
        Err(_) => SidecarStatus {
            running: false,
            pid: None,
        },
    }
}

pub fn start() -> Result<String, String> {
    let status = read_status();
    if status.running {
        return Ok(format!("sidecar 已在运行 (pid {})", status.pid.unwrap()));
    }
    let dir = state_dir();
    fs::create_dir_all(&dir).map_err(|e| format!("创建状态目录失败: {e}"))?;
    let log = fs::File::create(dir.join("edge-agent.log")).map_err(|e| e.to_string())?;
    let log_err = log.try_clone().map_err(|e| e.to_string())?;

    // 默认用 uv 跑仓库内 agent；分发形态后续换打包好的二进制
    let program = std::env::var("VIDEOFORGE_AGENT_PROGRAM").unwrap_or_else(|_| "uv".into());
    let args: Vec<String> = std::env::var("VIDEOFORGE_AGENT_ARGS")
        .map(|s| s.split_whitespace().map(String::from).collect())
        .unwrap_or_else(|_| {
            vec![
                "run".into(),
                "python".into(),
                "-m".into(),
                "videoforge_edge_agent".into(),
            ]
        });

    let child = {
        use std::os::unix::process::CommandExt;
        Command::new(&program)
            .args(&args)
            .current_dir(repo_root())
            .stdin(Stdio::null())
            .stdout(Stdio::from(log))
            .stderr(Stdio::from(log_err))
            .process_group(0) // 独立进程组：UI 退出不波及
            .spawn()
            .map_err(|e| format!("启动 sidecar 失败（{program}）: {e}"))?
    };
    let pid = child.id() as i32;
    fs::write(pidfile(), pid.to_string()).map_err(|e| e.to_string())?;
    // 有意不持有 Child：不回收、不随 Drop 杀进程；退出探活走 pidfile
    std::mem::forget(child);
    Ok(format!("sidecar 已启动 (pid {pid})"))
}

pub fn stop() -> Result<String, String> {
    let status = read_status();
    match status.pid {
        Some(pid) if status.running => {
            unsafe { libc::kill(pid, libc::SIGTERM) };
            let _ = fs::remove_file(pidfile());
            Ok(format!("已发送 SIGTERM (pid {pid})"))
        }
        _ => {
            let _ = fs::remove_file(pidfile());
            Ok("sidecar 未在运行".into())
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn pid_alive_detects_self_and_bogus() {
        assert!(pid_alive(std::process::id() as i32));
        assert!(!pid_alive(999_999_99));
    }

    #[test]
    fn status_without_pidfile_is_not_running() {
        std::env::set_var("VIDEOFORGE_STATE_DIR", std::env::temp_dir().join("vf-none"));
        let status = read_status();
        assert!(!status.running);
        assert!(status.pid.is_none());
    }
}
