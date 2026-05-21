# DoL Launcher

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
dolctl version remove <version_id>         # 删除已安装版本 / Remove installed version
```

### Mod 管理 / Mod Management

```bash
dolctl mod list                              # 列出已安装 mod / List installed mods
dolctl mod add <path_or_url> [--id <id>]     # 导入 mod / Import a mod
dolctl mod add <path> --force                # 覆盖同名 mod / Overwrite existing mod
dolctl mod remove <mod_id>                   # 删除 mod / Remove a mod
dolctl mod info <mod_id>                     # 查看 mod 详情 / Show mod metadata
```

### Profile 管理 / Profile Management

```bash
dolctl profile list                            # 列出 profile / List profiles
dolctl profile create <name>                   # 创建 profile / Create profile
dolctl profile use <name>                      # 切换活跃 profile / Switch active profile
dolctl profile set-version <id>                # 设置 profile 版本 / Set profile version
dolctl profile mod add <mod_id>                # 启用 mod / Enable a mod in profile
dolctl profile mod remove <mod_id>             # 禁用 mod / Disable a mod in profile
dolctl profile mod list                        # 列出 profile 内 mod 顺序 / List mods in profile
dolctl profile mod reorder <id1> <id2> ...     # 重新排序 mod / Reorder mods (full list required)
```

### 构建与运行 / Build & Run

```bash
dolctl build --profile <name>               # 构建运行目录 / Build runtime
dolctl run --port 8799                      # 构建并启动服务 / Build and serve
dolctl run --port 8799 --no-browser         # 不自动打开浏览器 / Don't open browser
dolctl serve --port 8799 --allow-lan        # 仅启动已构建的服务并允许局域网访问 / Serve existing build and allow lan access
```

## 远程渠道 / Remote Channels

要使用 `dolctl install latest --channel <name>` 从网络下载版本，需先在 `.dolctl/config.toml` 中配置一个 channel（一次性）：

To download versions via `dolctl install latest --channel <name>`, configure a channel in `.dolctl/config.toml` once:

```toml
[channels.vanilla]
provider = "github"
repo = "Vrelnir/degrees-of-lewdity"   # 示例 / example
asset_regex = ".*\\.zip$"              # 匹配 release 资产名 / matches the release asset
```

- `repo` 指向 `owner/name` 形式的 GitHub 仓库。
- `asset_regex` 用 `re.fullmatch` 校验，过于宽松会匹配到 source-code zip，请尽量精确。
- 设了 `GITHUB_TOKEN` 环境变量可避免命中匿名访问的速率限制。

- `repo` is a GitHub `owner/name` slug.
- `asset_regex` is matched with `re.fullmatch`; an overly broad pattern may match source archives, so be specific.
- Set `GITHUB_TOKEN` to avoid anonymous GitHub API rate limits.

之后：

Then:

```bash
dolctl version remote list --channel vanilla   # 列出可下载版本 / list remote versions
dolctl install latest --channel vanilla        # 安装最新版本 / install the latest
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

## 致谢 / Credits

Mod 管理与构建逻辑参考了 [DoL-Lyra/Lyra](https://github.com/DoL-Lyra/Lyra) 的架构设计与部分实现思路，包括 ModLoader 注入方式、mod 组合管理模式等。该项目基于 MIT 协议开源（Copyright (c) 2024 Sakari）。

The mod management and build logic is inspired by and partially adapted from [DoL-Lyra/Lyra](https://github.com/DoL-Lyra/Lyra), including its ModLoader injection approach and mod combination management patterns. Lyra is MIT-licensed (Copyright (c) 2024 Sakari).
Summarized