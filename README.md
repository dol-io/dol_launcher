# dolctl

**dolctl** 是一个 Degrees of Lewdity (DoL) 启动器 CLI 工具，支持多版本管理、Profile 切换和本地 HTTP 服务启动。

**dolctl** is a CLI launcher for Degrees of Lewdity (DoL) that supports multi-version management, profile switching, and local HTTP serving.

## 安装 / Installation

需要 Python >= 3.11 和 [uv](https://docs.astral.sh/uv/)。

Requires Python >= 3.11 and [uv](https://docs.astral.sh/uv/).

```bash
git clone <repo-url>
cd dol_launcher
uv sync
```

## 快速开始 / Quick Start

```bash
# 初始化根目录 / Initialize root directory
dolctl init ~/Games/DoL
cd ~/Games/DoL

# 从本地 zip 安装版本 / Install a version from local zip
dolctl install --file /path/to/dol.zip --as vanilla-0.5.3

# 设置当前 profile 使用该版本 / Set profile to use this version
dolctl use vanilla-0.5.3

# 构建并启动 / Build and launch
dolctl run --port 8799
```

浏览器会自动打开 `http://127.0.0.1:8799/`，按 `Ctrl+C` 停止服务。

The browser will open `http://127.0.0.1:8799/` automatically. Press `Ctrl+C` to stop.

## 命令参考 / Command Reference

### 全局选项 / Global Options

| 选项 / Option | 说明 / Description |
|---|---|
| `--root`, `-r` | 指定根目录 / Specify root directory |
| `--version` | 显示版本号 / Show version |

也可通过环境变量 `DOLCTL_ROOT` 指定根目录，或在根目录内任意子目录运行时自动检测。

You can also set `DOLCTL_ROOT` environment variable, or run from any subdirectory within the root.

### 初始化与诊断 / Init & Diagnostics

```bash
dolctl init <dir>     # 初始化根目录 / Initialize root directory
dolctl where          # 显示当前根目录 / Show current root
dolctl doctor         # 检查目录完整性 / Check directory integrity
```

### 版本管理 / Version Management

```bash
dolctl version list                        # 列出已安装版本 / List installed versions
dolctl version remote list                 # 列出远程可用版本 / List remote versions
dolctl install --file <zip> --as <id>      # 从 zip 安装 / Install from zip
dolctl install --dir <path> --as <id>      # 从目录安装 / Install from directory
dolctl install latest --channel vanilla    # 从远程下载 / Download from remote
dolctl use <version_id>                    # 切换版本 / Switch version
```

### Profile 管理 / Profile Management

```bash
dolctl profile list                  # 列出 profile / List profiles
dolctl profile create <name>         # 创建 profile / Create profile
dolctl profile use <name>            # 切换活跃 profile / Switch active profile
dolctl profile set-version <id>      # 设置 profile 版本 / Set profile version
```

### 构建与运行 / Build & Run

```bash
dolctl build --profile <name>               # 构建运行目录 / Build runtime
dolctl run --port 8799                      # 构建并启动服务 / Build and serve
dolctl run --port 8799 --no-browser         # 不自动打开浏览器 / Don't open browser
dolctl serve --port 8799                    # 仅启动已构建的服务 / Serve existing build
```

## 目录结构 / Directory Layout

```
<ROOT>/
  .dolctl/
    config.toml       # 全局配置 / Global config
    state.toml        # 状态 / State
    cache/            # 缓存 / Cache
    logs/             # 日志 / Logs
  versions/           # 已安装版本 / Installed versions
  profiles/           # Profile 配置 / Profile configs
  runtime/            # 构建输出 / Build output
```

## 许可 / License

见 [LICENSE](LICENSE)。 / See [LICENSE](LICENSE).
