# dolctl

`dolctl` 是一个简洁的 Degrees of Lewdity 本地启动器。它采用类似 Prism
Launcher 的实例模型：每个实例独立选择游戏版本、启用的 Mod 顺序和启动设置，
日常使用只需要选中实例并启动。

项目同时提供：

- Textual TUI：主要交互界面；
- Typer CLI：适合脚本和终端工作流；
- 同一套核心逻辑：两种界面的安装、构建与启动行为一致。

## 安装

需要 Python 3.11 或更高版本，以及
[uv](https://docs.astral.sh/uv/)。

```bash
git clone <repo-url>
cd dol_launcher
uv sync
```

## 最快上手

```bash
# 1. 创建一个完全独立的游戏目录
uv run dolctl init ~/Games/DoL

# 2. 打开启动器界面
uv run dolctl --root ~/Games/DoL tui
```

TUI 现在围绕日常启动流程组织为三个工作区：

1. `Play`：左侧选择实例，右侧查看版本、Mod 和启动设置；直接启动、停止或
   构建，也可以打开独立弹窗修改配置和 Mod 顺序；
2. `Library`：集中管理 `Versions`、`Mods` 和 `Sources`；
3. `System`：查看 ROOT 和诊断结果。

第一次使用时，先在 `Library → Versions` 导入游戏，再回到 `Play` 的
`Configure` 为实例选择版本；需要 Mod 时先在 `Library → Mods` 导入，然后用
`Manage mods` 启用和排序。之后日常只需选中实例并按 `Launch`。

快捷键 `1`–`3` 切换工作区，`F5` 刷新，`q` 退出，`?` 查看完整帮助；在
`Play` 中还可以使用 `n/a/e/m/b/l/x` 完成新建、设为活动、配置、管理 Mod、
构建、启动和停止。TUI 的背景使用终端默认色，界面强调只使用 ANSI 16 色名；
实际色值仍由用户自己的 terminal color scheme 决定，不会写死 RGB 或
256-color 色号。按钮和面板参考 rmpc，采用紧凑单行动作、蓝色圆角边框和清晰
的活动/状态色。

## CLI 工作流

### 从本地安装

```bash
GAME_ROOT=~/Games/DoL

uv run dolctl --root "$GAME_ROOT" version install \
  --file /path/to/game.zip --as game
uv run dolctl --root "$GAME_ROOT" instance configure default --version game

uv run dolctl --root "$GAME_ROOT" mod add /path/to/example.mod.zip --id example
uv run dolctl --root "$GAME_ROOT" instance mod add example

uv run dolctl --root "$GAME_ROOT" run default
```

`run` 会按需构建实例、启动 loopback HTTP 服务，并依据设置打开浏览器。按
`Ctrl+C` 停止服务。

### 从远程安装

新 ROOT 已预置可直接使用的 ModLoader GitHub 来源：

```bash
uv run dolctl --root "$GAME_ROOT" version remote --channel modloader
uv run dolctl --root "$GAME_ROOT" version install latest --channel modloader
uv run dolctl --root "$GAME_ROOT" instance configure default \
  --version <安装后显示的版本-id>
```

也可以添加自己的 GitHub Releases 来源：

```bash
uv run dolctl --root "$GAME_ROOT" channel add custom \
  --repo owner/repository --asset-regex 'game-.*\.zip'
```

`asset_regex` 使用完整匹配。若设置了 `GITHUB_TOKEN`，远程请求会携带它，
以减少 GitHub 匿名 API 限流。

官方 vanilla 目前不通过 GitHub Releases 分发，因此请从官方页面下载 zip 后，
使用 `version install --file ...` 导入；启动器不会内置一个已失效的 GitHub 镜像。

## 常用命令

```text
dolctl init <dir>
dolctl where
dolctl doctor
dolctl tui

dolctl instance list
dolctl instance create <name> [--version <id>] [--select]
dolctl instance select <name>
dolctl instance show [<name>]
dolctl instance configure [<name>] [--version <id>] [--port <port>]
dolctl instance delete <name>
dolctl instance mod list|add|remove|reorder ...

dolctl version list
dolctl version remote [--channel <name>] [--refresh]
dolctl version install [latest|<id>] [--channel <name>]
                       [--file <zip> | --dir <path>] [--as <id>] [--force]
dolctl version remove <id> [--force]

dolctl mod list
dolctl mod add <path-or-url> [--id <id>] [--force]
dolctl mod info <id>
dolctl mod remove <id>

dolctl channel list
dolctl channel preset
dolctl channel add <name> (--preset <preset> | --repo <owner/repo>)
dolctl channel remove <name>

dolctl build [<instance>] [--clean]
dolctl run [<instance>] [--port <port>] [--no-browser] [--allow-lan]
dolctl serve [<instance>] [--port <port>] [--allow-lan]
```

ROOT 的解析顺序是 `--root`、`DOLCTL_ROOT`、从当前目录向父目录搜索。
除 `init` 外，命令不会隐式创建 ROOT。

`serve` 只服务已有且仍然有效的构建；`run` 会先检查构建缓存并在需要时重建。
默认只监听 `127.0.0.1`，只有显式传入 `--allow-lan` 才允许局域网访问。

## 数据目录

所有运行数据都位于用户选择的 ROOT 下：

```text
<ROOT>/
  .dolctl/          配置、状态、缓存、日志和临时 staging
  versions/         已安装的不可变游戏版本
  mods/             本地 Mod 库
  profiles/         实例配置（保留旧版目录名以兼容已有数据）
  runtime/          每个实例的构建结果
```

版本、Mod、实例和运行目录都通过 staging + 原子替换发布。下载先写入 `.part`，
zip 解压会拒绝路径穿越、符号链接和异常膨胀包。

完整格式和行为约束见 [`intro.md`](intro.md)。

## 开发与验证

```bash
uv run --frozen pytest
uv run --frozen ruff check .
uv run --frozen mypy dolctl core infra providers tests
```

## License

见 [`LICENSE`](LICENSE)。ModLoader 注入思路参考了 MIT 许可的
[DoL-Lyra/Lyra](https://github.com/DoL-Lyra/Lyra)。
