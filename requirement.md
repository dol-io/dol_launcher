# dolctl — requirements.md

> 目标：用 **Python + uv** 实现一个“Minecraft 启动器风格”的 **DoL 启动器（CLI 版）**：多版本管理（原版/改版）、一键下载部署、在本地端口启动（默认 8799）、启动前 Mod 管理。  
> 本文档应当足够详细，使另一个 agent 可以据此直接实现项目。

---

## 1. 范围与非目标

### 1.1 范围（必须实现）
- **版本管理**
  - 支持安装、列出、切换多个 DoL 版本（包括“原版”和“改版/分支版”）。
  - 支持从网络 **自动抓取可用版本并下载**（不要求 GUI）。
  - 支持从本地 zip/html 包导入版本。
- **一键部署启动**
  - 将选定版本（叠加启用 Mod）构建成可运行目录
  - 启动一个本地 HTTP 服务，默认 `localhost:8799`
  - 自动打开浏览器（可关闭自动打开）
- **一键管理 Mod（启动前）**
  - 支持导入 Mod（文件夹/zip/url）
  - 支持 profile 级启用/禁用 Mod
  - 支持 Mod 顺序/优先级（后加载覆盖前加载）
  - 支持构建时冲突报告（哪个文件被覆盖）

### 1.2 非目标（本期不做）
- ~~不实现游戏内部的 ModLoader 注入逻辑~~ → **已纳入范围**（见第 4.2、5.4、5.6 节）。
- 不实现存档 DAG / git-save（可预留接口）。
- 不实现复杂的 Mod 依赖解析（可预留 manifest 字段）。
- 不实现跨设备同步/云端存档。
- 不实现 GUI（可预留未来扩展点）。

---

## 2. 技术栈与约束

### 2.1 技术栈
- Python >= 3.11
- 包管理：**uv**
- CLI：`typer`（或 `argparse`，优先 typer）
- HTTP 服务器：优先 Python 标准库 `http.server`；若需更好控制可用 `uvicorn` + `fastapi`（MVP 用标准库）
- 下载：`httpx`（或 `requests`，优先 httpx）
- 解压：标准库 `zipfile`（支持 zip），可选 `tarfile`（如遇 tar.gz）
- 校验：标准库 `hashlib`（sha256）
- 配置：`tomllib`/`tomli-w` 或 `pydantic`（MVP 用 toml）

### 2.2 运行环境
- 默认面向 Linux；Windows/macOS 允许“尽量工作”，但不作为硬性验收项。
- 不写入 XDG 路径；所有数据**必须**位于用户指定 root 目录。

---

## 3. Root 目录模型（最重要）

### 3.1 root 选择规则
- 每次运行 `dolctl` 必须确定一个 `ROOT`：
  1. `--root <path>` 参数（最高优先）
  2. 环境变量 `DOLCTL_ROOT`
  3. 从当前目录向上查找 `.dolctl/`（类似 git 的 `.git`）
  4. 若仍找不到：报错并提示 `dolctl init <dir>`

### 3.2 root 目录布局（必须按此实现）
```
<ROOT>/
  .dolctl/
    config.toml          # 全局默认配置（端口、浏览器行为、默认 profile）
    state.toml           # 当前选择（active profile、last used version 等）
    cache/
      downloads/         # 下载缓存（zip/html 包）
      index/             # 版本索引缓存（API/网页解析结果）
    logs/
  versions/
    <version_id>/
      ... (解压后的 DoL 内容)
      .manifest.toml
  mods/
    <mod_id>/
      <mod_id>.mod.zip    # ModLoader 格式 zip，内含 boot.json
      .mod.toml
  profiles/
    default/
      profile.toml
    <profile_name>/
      profile.toml
  runtime/
    <profile_name>/
      merged/            # 构建输出（可删除重建）
      build_meta.json    # 上次构建元信息（冲突、hash、时间等）
```

---

## 4. 核心概念与数据结构

### 4.1 Version（版本）
- Version 代表一套可运行的 DoL 文件树（含 `index.html`、`game/`、`img/` 等）
- 版本类型：`vanilla`（原版）与 `variant`（改版/分支版）
- 版本来源：
  - remote（网络下载：release / artifact）
  - local（本地 zip / 本地目录导入）

#### 4.1.1 version manifest（必须）
位置：`versions/<version_id>/.manifest.toml`
字段：
```toml
id = "0.5.3"                       # 内部唯一 id（可带前缀，如 "vanilla-0.5.3"）
display_name = "DoL 0.5.3"
channel = "vanilla"                # "vanilla" | "variant"
source = "remote"                  # "remote" | "local"
source_ref = "https://..."         # URL 或本地路径
sha256 = "..."                     # 若可得
installed_at = "2026-02-25T09:00:00Z"
entry = "index.html"               # 入口相对路径（默认 index.html）
```

### 4.2 Mod

> **参考实现**：Mod 系统架构参照 [DoL-Lyra/Lyra](https://github.com/DoL-Lyra/Lyra)（MIT License, Copyright (c) 2024 Sakari）的 ModLoader 注入方式设计，而非简单文件覆盖。

- Mod 是符合 DoL **ModLoader** 格式的 `.mod.zip` 文件，内含 `boot.json` 描述文件
- Mod 以 `mod_id` 作为目录名存放在 `mods/<mod_id>/`，核心文件为 `<mod_id>.mod.zip`
- Build 阶段不做文件树覆盖，而是将启用的 mod zip 路径注入到 `index.html` 的 ModLoader 加载列表中（仿照 Lyra 的 `ModInjector`）
- Mod 加载顺序由 profile 中的 `mod_order` 决定，顺序即 ModLoader 加载顺序

#### 4.2.1 mod manifest（必须）
位置：`mods/<mod_id>/.mod.toml`
字段：
```toml
id = "my_mod"
name = "My Mod"                    # 从 boot.json 读取或用户指定
version = "1.0.0"                  # 从 boot.json 读取
author = ""
description = ""
source = "local"                   # "local" | "url"
source_ref = "..."                 # 来源 URL 或本地路径
installed_at = "..."
```

#### 4.2.2 ModLoader boot.json 结构（参考）
mod zip 内的 `boot.json` 由 DoL ModLoader 读取，字段示例：
```json
{
  "name": "MyMod",
  "version": "1.0.0",
  "scriptFileList_inject_early": [],
  "scriptFileList_earlyload": [],
  "scriptFileList_preload": [],
  "styleFileList": [],
  "scriptFileList": [],
  "tweeFileList": [],
  "imgFileList": []
}
```

### 4.3 Profile
- Profile = 版本选择 + 启用的 mod 集合 + 构建偏好（端口可覆盖）
- 多 profile 的意义：像 Minecraft 一样，一套 profile 对应一套 modpack/版本组合

#### 4.3.1 profile manifest（必须）
位置：`profiles/<profile>/profile.toml`
字段：
```toml
name = "default"
version_id = "vanilla-0.5.3"

# mod 加载列表，即 ModLoader 注入顺序（前→后）
mod_order = ["modA", "modB"]

# 可选：端口/浏览器覆盖
port = 8799
open_browser = true
```

---

## 5. 功能需求（分模块）

> 要求“解耦合设计”：以下模块必须隔离，模块之间仅通过接口/DTO 交互，不直接读写彼此内部文件。

### 5.1 Root & Config 模块
**职责**
- 解析 root（规则见 3.1）
- 初始化目录结构
- 读写 `.dolctl/config.toml` 与 `state.toml`

**接口**
- `resolve_root(cli_root: str | None) -> Path`
- `init_root(root: Path) -> None`
- `load_config(root) -> Config`
- `save_config(root, config) -> None`
- `load_state(root) -> State`
- `save_state(root, state) -> None`

**验收**
- `dolctl init <dir>` 创建所有必需目录与最小配置文件
- 在 root 内任意子目录运行命令，都能自动定位 root

---

### 5.2 Version Index（远程索引）模块
**职责**
- “自动抓取下载功能”的核心：从远端获取可用版本列表（vanilla 与 variant）
- 支持至少一种索引提供者（Provider），并可扩展多个 Provider

**设计要求：Provider 抽象**
- `VersionProvider` 接口：
  - `list_versions() -> list[RemoteVersion]`
  - `resolve(version_selector) -> RemoteVersion`（按 id/标签/最新）
  - `download(remote_version, dest_zip_path) -> DownloadResult`

**MVP Provider**
- `GitHubReleasesProvider`：
  - 基于配置中的 repo（例如 vanilla repo 与某个 variant repo）
  - 通过 GitHub API 获取 releases 与资产列表
  - 选择 zip/可运行包资产（按文件名规则）
- 允许在 `config.toml` 中配置多个 channel：
```toml
[channels.vanilla]
provider = "github"
repo = "..."
asset_regex = ".*\\.zip$"

[channels.variant_plus]
provider = "github"
repo = "..."
asset_regex = ".*\\.zip$"
```

**缓存**
- 将 `list_versions()` 结果缓存到 `.dolctl/cache/index/`
- 默认缓存有效期：10 分钟（可配置）

**验收**
- `dolctl version remote list` 能显示远端可用版本（至少包含 id、发布时间、channel）
- `dolctl install <selector>` 能自动解析 selector 并下载

---

### 5.3 Version Install（安装）模块
**职责**
- 从 remote 下载 zip 到 cache 并校验
- 解压到 `versions/<version_id>/`
- 生成 `.manifest.toml`
- 支持从本地 zip/目录导入

**接口**
- `install_from_remote(root, channel, selector) -> version_id`
- `install_from_file(root, file_path, version_id | None, channel) -> version_id`
- `install_from_dir(root, dir_path, version_id | None, channel) -> version_id`
- `list_installed(root) -> list[InstalledVersion]`
- `remove_version(root, version_id) -> None`（可选）

**约束**
- 解压必须在临时目录完成后再原子性移动到最终位置（避免半装状态）
- 若目标版本已存在：
  - 默认拒绝覆盖
  - `--force` 允许重装

**验收**
- 安装成功后 `versions/<id>/index.html` 存在
- `.manifest.toml` 完整可读

---

### 5.4 Mod 管理模块

> 参照 Lyra 的 `warmup.py` / `prepare.py` 中对 ModLoader mod 的管理方式设计。

**职责**
- 导入 mod zip（本地路径 / URL）到 `mods/<mod_id>/`，核心文件为 `<mod_id>.mod.zip`
- 解析 mod zip 内的 `boot.json` 提取名称、版本等元信息
- 读取/写入 `.mod.toml`
- 列出/删除 mod

**接口**
- `add_mod_from_zip(root, path_or_url, mod_id | None) -> mod_id`
- `list_mods(root) -> list[Mod]`
- `remove_mod(root, mod_id) -> None`
- `get_mod_info(root, mod_id) -> Mod`

**约束**
- 导入的 zip 必须是有效的 ModLoader mod（根目录含 `boot.json`）；若无则警告但仍可导入
- mod zip 以 `<mod_id>.mod.zip` 命名存放，路径：`mods/<mod_id>/<mod_id>.mod.zip`
- 不修改 mod zip 内容，仅做存储与元信息管理

**验收**
- `dolctl mod add` 后在 `mods/<id>/` 能看到 `.mod.zip` 与 `.mod.toml`
- `.mod.toml` 中 name/version 从 `boot.json` 自动填充

---

### 5.5 Profile 模块
**职责**
- 创建/删除/切换 profile
- 管理 profile 的 mod 列表与加载顺序
- 设置 profile 的 `version_id`

**接口**
- `create_profile(root, name) -> None`
- `set_profile_version(root, profile, version_id) -> None`
- `add_mod_to_profile(root, profile, mod_id) -> None`
- `remove_mod_from_profile(root, profile, mod_id) -> None`
- `reorder_mods(root, profile, ordered_mod_ids) -> None`
- `get_profile(root, profile) -> Profile`
- `list_profiles(root) -> list[str]`

**验收**
- profile 改动会写入 `profiles/<name>/profile.toml`
- `state.toml` 维护当前 active profile

---

### 5.6 Build（构建）模块

> 参照 Lyra 的 `build.py`（`ZipBuilder`）与 `prepare.py`（`ModInjector`）实现。

**职责**
- 将 `versions/<version_id>/` 复制到 `runtime/<profile>/merged/`（base 拷贝）
- 将 profile 中启用的 mod zip 路径**注入到 `index.html`**，由 ModLoader 在运行时按顺序加载
- 生成构建元信息

**ModLoader 注入策略（核心）**
仿照 Lyra `ModInjector.add_mods()`：在 `index.html` 的 `<head>` 中插入一段引导脚本，将各 mod zip 的相对路径写入 `window.modList`（或 ModLoader 识别的等效接口），使 ModLoader 在游戏启动时自动加载。

具体流程：
1. 复制 base version 文件树到 `merged/`（忽略 `.manifest.toml`）
2. 将已启用 mod zip 复制到 `merged/mods/`
3. 修改 `merged/index.html`，在 `<head>` 的 ModLoader `<script>` 标签前插入 mod 路径列表注入脚本
4. 写入 `build_meta.json`

**输出 `build_meta.json`**：
- base version id
- mod 列表与加载顺序
- 构建时间
- 可选：各文件 hash 指纹（用于增量构建，后续实现）

**接口**
- `build_runtime(root, profile_name, clean=True) -> BuildResult`

**验收**
- merged 目录存在且 `index.html` 可访问
- `index.html` 中含有 mod 注入脚本（若有启用 mod）
- mod zip 文件存在于 `merged/mods/`
- `build_meta.json` 存在

---

### 5.7 Serve（本地部署）模块
**职责**
- 在 `localhost:<port>` 启动 HTTP 服务，root 指向 `runtime/<profile>/merged/`
- 默认端口 8799，若占用则：
  - 若 `--port` 指定：直接报错
  - 否则自动寻找可用端口（8799, 8800, 8801... 上限可配置）

**接口**
- `serve(directory: Path, host="127.0.0.1", port=8799) -> ServerHandle`
- `ServerHandle.stop()`

**验收**
- `dolctl run` 后浏览器可打开并正常加载资源文件（img/game 等）

---

### 5.8 Launch（运行编排）模块
**职责**
- 一键流程：读 profile -> build -> serve -> open browser
- 支持 `--no-browser`
- 支持 `--profile` 覆盖 active profile
- 支持 `--root` 覆盖 root
- 结束行为：
  - 默认前台运行并显示 URL
  - `--detach` 可选后台（MVP 可不做）

**接口**
- `run(root, profile, port_override, open_browser_override) -> RunResult`

**验收**
- 一条命令完成构建+启动：
  - `dolctl run`
  - 默认端口 8799
  - 自动打开浏览器（可配置）

---

## 6. CLI 规范（必须）

### 6.1 顶层命令
- `dolctl init <dir>`
- `dolctl where`
- `dolctl doctor`

### 6.2 版本命令
- `dolctl version list`（已安装）
- `dolctl version remote list [--channel <name>] [--refresh]`
- `dolctl install <selector> [--channel vanilla] [--force]`
- `dolctl install --file <zip> [--as <version_id>] [--channel <name>]`
- `dolctl use <version_id> [--profile <p>]`

Selector 规则（remote install）：
- `latest`
- 具体 id（如 `0.5.3` 或 `vanilla-0.5.3`）
- 可选：`channel:latest`（如 `variant_plus:latest`）

### 6.3 Mod 命令
- `dolctl mod list`
- `dolctl mod add <path_or_url> [--id <mod_id>]`（接受 `.mod.zip`）
- `dolctl mod remove <mod_id>`
- `dolctl mod info <mod_id>`

### 6.4 Profile 命令
- `dolctl profile list`
- `dolctl profile create <name>`
- `dolctl profile use <name>`
- `dolctl profile set-version <version_id> [--profile <name>]`
- `dolctl profile mod add <mod_id> [--profile <name>]`
- `dolctl profile mod remove <mod_id> [--profile <name>]`
- `dolctl profile mod list [--profile <name>]`

### 6.5 构建与运行
- `dolctl build [--profile <name>]`
- `dolctl run [--profile <name>] [--port <p>] [--no-browser]`
- `dolctl serve [--profile <name>] [--port <p>]`（仅服务已构建目录，可选）

---

## 7. 配置文件规范（必须）

### 7.1 `.dolctl/config.toml`
最小示例：
```toml
default_profile = "default"
default_port = 8799
open_browser = true

[channels.vanilla]
provider = "github"
repo = "..."              # 由用户填写
asset_regex = ".*\\.zip$"

# 可选：改版渠道
[channels.variant_plus]
provider = "github"
repo = "..."
asset_regex = ".*\\.zip$"
```

### 7.2 `.dolctl/state.toml`
```toml
active_profile = "default"
last_used_version = "vanilla-0.5.3"
```

---

## 8. 解耦合与代码结构（必须）

### 8.1 分层要求
- `cli`：仅解析参数与打印输出，不包含业务逻辑
- `core`：纯业务逻辑（root、versions、mods、profiles、build、serve、run）
- `providers`：远端索引与下载实现（GitHub 等）
- `infra`：文件系统、下载、解压、hash、浏览器打开等工具

### 8.2 简化项目结构（要求）
项目必须保持少量文件与清晰模块边界。推荐：
```
dolctl/
  pyproject.toml
  dolctl/
    __init__.py
    cli.py
    core_root.py
    core_versions.py
    core_mods.py
    core_profiles.py
    core_build.py
    core_serve.py
    core_run.py
    providers_github.py
    infra_fs.py
    infra_net.py
    infra_zip.py
    infra_open.py
    models.py
```

### 8.3 模块依赖方向（强约束）
- `core_*` 可以依赖 `infra_*` 和 `models`
- `providers_*` 可以依赖 `infra_*` 和 `models`
- `cli.py` 只能依赖 `core_*` / `models`
- 任何模块不得直接跨层写别的模块的内部文件；统一通过 core 的接口完成

---

## 9. 行为与错误处理（必须）

### 9.1 原子性与一致性
- install 解压需在临时目录完成后原子移动
- build 输出在写入前清理旧 merged（除非支持增量构建）
- 任何失败应留下可诊断日志（写入 `.dolctl/logs/`）

### 9.2 错误信息
- CLI 输出必须用户可理解
- 失败时返回非 0 exit code
- 常见错误：
  - 未 init root
  - 版本不存在
  - mod 不存在
  - 端口占用
  - 下载失败/校验失败
  - zip 结构异常（无 index.html）

---

## 10. 验收清单（必须通过）

### 10.1 初始化
- `dolctl init ~/Games/DoL` 创建完整结构
- 在 `~/Games/DoL` 子目录执行 `dolctl where` 能找到 root

### 10.2 安装与切换版本
- `dolctl install --file dol.zip --as vanilla-0.5.3 --channel vanilla`
- `dolctl version list` 可见已安装版本
- `dolctl use vanilla-0.5.3` 修改 default profile 的 version_id

### 10.3 Mod 管理与构建
- `dolctl mod add some_mod.zip --id modA`（mod zip 含有效 `boot.json`）
- `dolctl profile mod add modA` 将 modA 加入当前 profile 的加载列表
- `dolctl build` 生成 merged，`index.html` 内含 mod 注入脚本，`mods/modA.mod.zip` 存在

### 10.4 一键运行
- `dolctl run` 默认端口 8799
- 访问 `http://127.0.0.1:8799/` 能加载页面与资源
- `--no-browser` 不自动打开浏览器但输出 URL

### 10.5 远端索引（最小）
- 配置 github channel 后：
  - `dolctl version remote list --channel vanilla`
  - `dolctl install latest --channel vanilla`
  - 能成功下载并安装

---

## 11. 参考实现说明

### 11.1 Lyra 参考

Mod 系统的设计与实现参照 [DoL-Lyra/Lyra](https://github.com/DoL-Lyra/Lyra)（MIT License, Copyright (c) 2024 Sakari），以下模块在设计上有直接对应关系：

| dolctl 模块 | Lyra 参考模块 | 说明 |
|---|---|---|
| `core_mods.py` | `lyra/warmup.py` | mod zip 的本地存储与元数据管理 |
| `core_build.py`（注入部分） | `lyra/prepare.py` (`ModInjector`) | 向 `index.html` 注入 ModLoader mod 列表 |
| `core_build.py`（复制部分） | `lyra/build.py` (`ZipBuilder`) | base 版本文件树复制 |
| `models.py` (`Mod`) | `lyra/config_loader.py` (`ModloaderModConfig`) | mod 元信息结构 |

**与 Lyra 的主要差异**：
- dolctl 是本地单机启动器，不做并行构建、APK 打包、CI 矩阵
- dolctl 的 mod 由用户手动管理（任意 `.mod.zip`），Lyra 的 mod 集合固定由配置文件驱动
- dolctl 的 profile 允许不同 mod 组合，Lyra 枚举所有位标志组合批量构建

### 11.2 ModLoader 注入机制说明

DoL 的 ModLoader 通过修改 `index.html` 加载外部 mod。注入方式参照 Lyra `ModInjector`：

```python
# 伪代码：在 index.html 的 <head> 内插入
<script>
window.modList = [
  "mods/modA.mod.zip",
  "mods/modB.mod.zip"
];
</script>
```

Mod zip 内必须含 `boot.json`，ModLoader 据此识别加载内容。

---

## 12. 未来扩展点（预留，不实现）
- overlayfs/增量构建（减少复制）
- mod 依赖/冲突规则（manifest schema 扩展）
- 多实例运行（不同 profile 不同端口）
- 集成存档/设置管理（如 profile 下的 saves/）
- GUI（Tauri/Electron）复用 core 层

---
