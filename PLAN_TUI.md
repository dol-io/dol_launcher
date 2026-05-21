# PLAN_TUI.md — dolctl TUI 规划

> 目标：把 dolctl 的全部命令搬到一个 Textual TUI 里。CLI 保留并和 TUI 共享 `core/*` 业务逻辑——TUI 只是另一种 frontend。
>
> 编写时间：2026-05-21

---

## 1. 目标与非目标

### 目标
- **覆盖所有现有命令**：channel / version / mod / profile / build / run / doctor / where。
- **一个二进制就能用**：`dolctl ui`（或 `dolctl tui`）启动 TUI；不强制用户离开 CLI。
- **长任务不阻塞**：安装、下载、构建、HTTP serve 都在后台 worker 里跑；UI 始终可响应。
- **错误友好**：`DolCtlError` 统一在底部 toast / status bar 显示，不抛栈。
- **状态自动同步**：每个屏幕在 mount/focus 时从磁盘重新读取，不维护内部缓存。

### 非目标（本期）
- 不做主题/配色定制。Textual 默认主题足够。
- 不做翻译。中英混排（命令字英文，提示文中文）。
- 不内嵌浏览器。`run` 启动服务后仍然由系统浏览器打开。
- 不支持鼠标拖拽排序 mod（用键盘 `+`/`-` 上下移即可）。
- 不替换 CLI；CLI 不动一行。

---

## 2. 整体布局

```
┌──────────────────────────────────────────────────────────────────┐
│ dolctl  root=/home/x/Games/DoL  active=default  version=ml-0.5.8.9│  Header
├──────────────────────────────────────────────────────────────────┤
│ [Home] [Channels] [Versions] [Mods] [Profiles] [Run] [Doctor]    │  TabbedContent
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│   <当前 Tab 的 body>                                              │
│                                                                  │
├──────────────────────────────────────────────────────────────────┤
│ status: ready · last action: built profile default (cache hit)   │  StatusBar
├──────────────────────────────────────────────────────────────────┤
│ F1 help · F5 refresh · 1-7 tabs · q quit                         │  Footer
└──────────────────────────────────────────────────────────────────┘
```

实现：Textual 的 `TabbedContent` + `TabPane`。Header / Footer 用内置 widget。

**全局键绑定**

| 键 | 作用 |
|---|---|
| `1`..`7` | 跳到对应 tab |
| `F5` / `r` | 重新从磁盘加载当前 tab |
| `F1` / `?` | 打开 help modal |
| `q` / `Ctrl+C` | 退出（如果有 server 在跑，先停） |

---

## 3. 各 Tab 详细设计

### 3.1 Home
**作用**：一眼看清当前状态 + 提供最常用动作。

**布局**：四个 metric 卡片 + 两个大按钮。

```
+ ROOT --------------------+  + PROFILE -----------------+
|  /home/x/Games/DoL       |  |  default (active)        |
|  3 versions · 6 mods     |  |  version: ml-0.5.8.9     |
|  2 channels              |  |  6 mods enabled          |
+--------------------------+  +--------------------------+

[ Build ]  [ Run --port 8799 ]
```

数据来源：`list_installed`、`list_mods`、`list_profiles`、`list_channels`、`load_state`。

按钮：
- `Build` → 调用 `build_runtime(root, active_profile)`，结果写 status bar。
- `Run` → 切到 Run tab 并自动按上次配置启动。

### 3.2 Channels
**作用**：channel CRUD + 预设。

```
+-- Configured ----------------------------------+ +-- Presets ---------+
| name      provider  repo                       | | dol-vanilla        |
| ▶ vanilla github    Vrelnir/degrees-of-lewdity | | dol-modloader      |
|   modded  github    ...                        | |                    |
+------------------------------------------------+ +--------------------+
[ Add from preset ] [ Add custom ] [ Edit ] [ Remove ]
```

- 左侧 `DataTable` 显示当前 channels；右侧 `ListView` 显示可用预设。
- `Add from preset`：弹 modal，输入 name + 选预设 + 可选覆盖 repo/regex。
- `Add custom`：弹 modal，name/provider/repo/asset_regex 四个 `Input`。
- `Edit`：对选中行同样的 modal，字段预填。
- `Remove`：确认后调 `remove_channel`。

核心：`core/channels.py`（已存在）。

### 3.3 Versions
**作用**：装/卸版本，浏览远程，切换 active 版本。

```
+-- Installed -----------------------------+  +-- Remote (vanilla) ----------+
| id              channel  installed_at    |  | id      published   asset    |
| ▶ ml-0.5.8.9    vanilla  2026-05-21      |  | 0.5.8.9 2024-12-01  ...zip   |
|   variant-x     modded   2026-04-10      |  | 0.5.8.8 2024-09-12  ...zip   |
+------------------------------------------+  +------------------------------+
                                              channel: [ vanilla ▾ ] [Refresh]

[ Install local zip ]  [ Install local dir ]  [ Install selected remote ]
[ Use selected installed ]  [ Remove selected installed ]
```

- 左 `DataTable`：本地版本，列出 `list_installed`。
- 右 `DataTable`：远程版本。channel 用 `Select` 切换，按 `Refresh` 调 `list_remote_versions(refresh=True)`。
- `Install local zip/dir`：弹 `Input` 让用户填路径（支持 tab 补全？暂不做，纯输入）。
- `Install selected remote`：后台 worker，进度通过 status bar 显示。
- `Use`：调 `set_profile_version(active_profile, id)`。

### 3.4 Mods
**作用**：mod 仓库管理（不是 profile 启用列表，profile 启用走 3.5）。

```
+-- Installed mods -----------------------------------+
| id              name           version  source     |
| ▶ cheat-lyra    Cheat-Lyra     1.1.3    local      |
|   modi18n       ModI18N        ...      local      |
+----------------------------------------------------+
[ Add from path ]  [ Add from URL ]  [ Info ]  [ Remove ]
```

- `Add from path`：弹 modal，path + 可选 id + force 复选框。
- `Add from URL`：modal，url + id + force。后台 worker 下载。
- `Info`：弹只读 modal 显示 `get_mod_info` 全部字段。
- `Remove`：确认后 `remove_mod`。

### 3.5 Profiles
**作用**：profile 全周期管理 + mod 启用顺序。这是最复杂的一屏。

```
+-- Profiles -------+   +-- profile: default ---------------------+
| ▶ default (active)|   | version: [ ml-0.5.8.9 ▾ ]  port: 8799   |
|   alt             |   |                                         |
+-------------------+   | Enabled mods (order matters):           |
[New] [Use] [Delete]    |   ┌──────────────────────────────────┐  |
                        |   │ ▶ ☑ modi18n              ↑ ↓     │  |
                        |   │   ☑ cheat-lyra           ↑ ↓     │  |
                        |   │   ☑ combatstatusdisplay  ↑ ↓     │  |
                        |   │   ☐ aufemale_model       ↑ ↓     │  |
                        |   └──────────────────────────────────┘  |
                        | space=toggle · +/- move · enter info    |
                        +-----------------------------------------+
```

左侧：profile 列表，标注 active。`New` 弹 modal 输入 name。`Use` 调 `set_active_profile`。`Delete` 确认后删 profile 目录。

右侧：选中 profile 的详情。
- `version` 用 `Select`，options 来自 `list_installed`；改动立即调 `set_profile_version`。
- mod 列表是核心：列出**所有** installed mods（不是只 enabled 的），每行一个 `Checkbox`。勾选 = 加入 profile.mod_order；取消 = 移除。
- `↑/↓` 在 checkbox-on 的行之间移动顺序（`reorder_mods`）。`+`/`-` 也接受。
- 顺序与 enable 状态都立刻写盘——不需要 "save" 按钮。

**实现注意**：把 mod 列表渲染为 `ListView`，每个 `ListItem` 包含 `Checkbox + Label`。`Checkbox.Changed` 事件触发 add/remove。`+`/`-` 处理 reorder。

### 3.6 Run
**作用**：构建 + 启动 HTTP 服务，带实时日志。

```
+-- Build options ----+   +-- Server options --------+
| Profile: [default ▾]|   | Port:        [8799     ] |
| [ ] --clean         |   | [ ] --no-browser         |
+---------------------+   | [ ] --allow-lan          |
                          +--------------------------+

[ Build ]  [ Run ]  [ Stop ]      Status: idle

+-- Log -----------------------------------------------+
| 21:36:18 INFO build  Building profile default ...    |
| 21:36:19 INFO build    Embedding mod: cheat-lyra ... |
| 21:36:19 INFO build  Injected 1 mod(s) ...           |
| 21:36:19       Serving http://127.0.0.1:8799/         |
+------------------------------------------------------+
```

- `Build`：worker 调 `build_runtime(root, profile, clean=)`；日志追加。
- `Run`：worker 调 `prepare_run(...)` + `server.serve_forever()`。`Stop` 调 `server.shutdown()` + `server_close()`。
- 日志：本屏挂一个 `logging.Handler` 把 dolctl logger 的 INFO+ 推到 `RichLog` widget。
- 服务运行中，header 状态从 `idle` 变成 `serving :8799`；切 tab 不影响。

### 3.7 Doctor
**作用**：只读诊断。

```
+-- Checks --------------------------------+
| ✓ root exists                            |
| ✓ .dolctl present                        |
| ✓ versions/ mods/ profiles/ runtime/     |
| ⚠ no channels configured                 |
| ✓ active profile 'default' exists        |
| ✓ active version 'ml-0.5.8.9' installed  |
| ⚠ profile 'alt' references missing v2    |
+------------------------------------------+
[ Re-run ]
```

逻辑沿用现有 `doctor` 命令，扩展到也校验 profile→version 引用。

---

## 4. 异步与后台执行

Textual 是 async-first，但 `core/*` 都是同步。统一策略：

- **短同步操作**（列出、读 toml）：直接在 Textual event handler 内调用，<100ms。
- **长同步操作**（install、build、download、serve_forever）：用 `@work(thread=True)`，把 callable 丢到线程池。线程结束时通过 `self.call_from_thread` 把结果 marshal 回主循环更新 UI。
- **进度上报**：给 `download_file` 和 `_copy_tree` 加可选的 `on_progress: Callable[[int, int], None]`，TUI 注入一个回调把字节数/百分比推到 status bar。CLI 不传 → 无侵入。
- **HTTP serve 终止**：`server.shutdown()` 必须在另一个线程调，否则会死锁。TUI 已经在 worker 线程跑 `serve_forever`，`Stop` 按钮的 handler 在主线程调用 `worker.cancel()` 或直接 `server.shutdown()`。

---

## 5. 错误与通知

- 所有 worker 用一个共同的装饰器 / 包装函数捕获 `DolCtlError`：
  - 写 status bar
  - 调用 `self.notify(message, severity="error")`（Textual toast）
- 未预期异常（不是 DolCtlError）：toast 显示 + 写日志，让用户知道发生了什么但不崩溃 TUI。
- 关键操作（remove、delete）需要确认 modal。

---

## 6. 状态同步策略

- 每个 Tab 实现一个 `refresh_from_disk()` 方法。
- 触发时机：
  1. Tab 第一次被显示时（`on_show`）。
  2. 用户按 `F5`/`r`。
  3. 该 tab 自己的写操作完成后（如 Channels tab 调完 `add_channel` 立刻 `refresh_from_disk()`）。
- 跨 tab 影响：例如 `Mods` tab 删了 mod，`Profiles` tab 的 mod 列表过期。处理方法：发布一个内部消息 `DataChanged("mods")`，订阅者刷新。简单实现：在 App 上挂一个 `reactive` 的版本号，每次写操作 +1，每个 tab `watch` 这个号并刷新。

---

## 7. 文件与代码结构

```
dolctl/
  cli.py            # 不动
  __init__.py
  tui/              # 新增子包
    __init__.py     # 暴露 app 实例
    app.py          # DolctlApp(App)
    screens/
      home.py
      channels.py
      versions.py
      mods.py
      profiles.py
      run.py
      doctor.py
    modals.py       # 共用 modal（确认 / 输入 / 错误）
    log_handler.py  # 把 dolctl logger 接到 RichLog
core/               # 不动
infra/              # 不动
providers/          # 不动
```

CLI 入口：在 `dolctl/cli.py` 新增

```python
@app.command("ui")
@with_errors
def ui_cmd(ctx: typer.Context) -> None:
    root = _get_root(ctx)
    from dolctl.tui.app import DolctlApp
    DolctlApp(root).run()
```

`pyproject.toml` 依赖增 `textual>=0.60`。无可选依赖——TUI 是一等公民。

---

## 8. 测试策略

Textual 提供 `App.run_test()` 上下文，可以驱动按键、断言 widget 状态。但 TUI 测试通常脆弱，重点应放在 **非 UI 的辅助逻辑** 上：

- `dolctl/tui/log_handler.py`：单元测试。
- 各 screen 的「从磁盘组装表格行」逻辑：抽出纯函数，单元测试（不需要 Textual 上下文）。
- 一个端到端 smoke：`App.run_test()` 打开 → 按 `2` 切到 Channels → 关闭。验证 mount 不炸。

不写：键盘流的全 happy-path 测试（成本高，回报低）。

---

## 9. 依赖影响

| 项 | 当前 | 新增 |
|---|---|---|
| 运行时 deps | typer, httpx, tomli-w | + textual (~3MB wheel) |
| 启动开销 | 一次性 ~150ms（typer/click） | TUI 启动 ~250ms（rich+textual） |
| Python 版本 | 3.11+ | 不变 |

CLI 路径不依赖 textual——`dolctl install ...` 仍然可以在没装 textual 的环境跑（运行时 `import textual` 只发生在 `dolctl ui` 调用时）。这点要在 `pyproject.toml` 把 textual 标为 **必装**，不做 extras，因为它已经是一等命令；强行可选只是增加复杂度。

---

## 10. 实施顺序

1. **骨架**：`DolctlApp` + `TabbedContent` + 7 个空 `TabPane`，header/footer 跑通。
2. **Home**：最简单，验证 metric 卡片 + 从磁盘读状态的模式。
3. **Channels**：CRUD 已存在，直接接表格。
4. **Mods**：与 Channels 同模式，先做。
5. **Versions**：先做 installed 这半边；远程那半边后做（要 worker + 进度）。
6. **Profiles**：最复杂，留到中段。
7. **Run**：worker 模型 + log handler 是新东西，单独一个迭代。
8. **Doctor**：最简单的只读，最后扫尾。
9. **集成测试**：smoke + 关键辅助函数单测。
10. **文档**：README 增「TUI 模式」一节，AGENTS.md 增 `dolctl/tui/` 模块约定。

预计工作量：3–4 个 commit 单元，每个 commit 包含 1–3 个 tab + 必要的支持代码。

---

## 11. 已确认的决策

- 命令名：**`dolctl tui`**。
- 不带子命令的 `dolctl` 保持现状（显示 help / 错误）——不改变现有行为。
- Header 右侧显示版本信息：`dolctl vX.Y.Z`。

按本文执行。
