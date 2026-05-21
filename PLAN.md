# PLAN.md — 后续工作规划

> 范围：`SUGGESTIONS.md` 中未实现的 7 个条目。本文件给出每项的目标、设计、影响面、风险与开放问题，并在末尾给出推荐执行顺序。
>
> 编写时间：2026-05-21
>
> 决策（2026-05-21 第二轮）：
> - #1 Channel CLI：**提供预设**（`--preset` 与 `dolctl channel preset list`），首次使用门槛降到一行命令。
> - #4 日志分级：**默认安静**（stderr 不输出 INFO），`--verbose` 才打开。文件 handler 始终记录 INFO。
> - #6 增量构建：**不每次重算 hash**，依赖 mod zip mtime + size + cached sha256 三元组判定脏。
> - #7 Provider 抽象：`ChannelConfig` 保留核心字段并新增 `extra: dict[str, str]`；Protocol 仅 `list_versions` + `download`，`resolve(selector)` 留在 core。

## 依赖关系总览

```
Tests (5)  ──┬──→ CLI errors refactor (2)
             ├──→ serve.py 简化 (3)
             ├──→ 日志分级 (4)
             ├──→ Provider 抽象 (7) ──→ Channel CLI (1)
             └──→ 增量构建 (6)
```

- **测试是其他所有 refactor 的前置**：没有测试覆盖，#2/#3/#7 的回归风险都太高。
- **Provider 抽象先于 Channel CLI**：channel 命令需要知道有哪些 provider 可配，不抽象就只能写死 github。
- **增量构建独立**：与其他重构无耦合，但内部最复杂。

---

## 1. Channel CLI 子系统

### 目标
让用户用 CLI 而不是手编 `.dolctl/config.toml` 管理远程渠道。

### 命令面（提案）
```
dolctl channel list
dolctl channel show <name>
dolctl channel add <name> --provider github --repo <owner/name> [--asset-regex <re>]
dolctl channel remove <name>
dolctl channel set <name> [--repo <r>] [--asset-regex <re>]
```

- `add`：name 已存在 → 报错；`--force` 覆盖。
- `remove`：同时清掉 `.dolctl/cache/index/<name>.json` 缓存。
- `add`/`set` 完成后可选地做一次 `provider.list_versions()` 测试拉取，失败仅警告。

### 代码改动
- 新增 `core/channels.py`：`add_channel`、`list_channels`、`remove_channel`、`show_channel`、`set_channel_fields`。读取/回写 `Config.channels` 并 `save_config`。
- 新增 `dolctl/cli.py` 内的 `channel_app = typer.Typer()` 与 5 个命令。
- `core/models.py` 已有 `ChannelConfig` dataclass，足以承载，无需扩展。

### 决策
1. **提供预设**：`core/channel_presets.py` 维护一张小表，键如 `dol-vanilla`、`dol-modloader` 指向 `(provider, repo, asset_regex)`。`dolctl channel add <name> --preset <key>` 一行配完。`dolctl channel preset list` 列出可用预设。
2. provider 名必须在 `providers.REGISTRY` 内（#7 落地后启用枚举校验）。

### 风险
- 用 CLI 写回 `config.toml` 会丢失用户的注释。`tomli_w` 不保留注释——可接受，但要在 README 注明。

### 依赖
- 推荐先做 #7，让 `--provider` 选项的取值与注册表对应。否则当前只支持 `github` 时也可独立做。

---

## 2. CLI 错误处理 refactor

### 目标
摆脱 `dolctl/cli.py:8` 的 `import click` 与 `click.get_current_context(silent=True)`（typer 内部 API，未来易破）。

### 现状
`with_errors` 装饰器为了拿 `ctx`（用于 `log_error(root, ...)`），绕道用 click 的 `get_current_context`。所有命令都已经把 `ctx: typer.Context` 写在签名里，没必要再绕道。

### 方案
1. 修改 `with_errors`：用 `inspect.signature` 检查被包装函数有没有名为 `ctx` 的参数。
2. 若有：从 `args`/`kwargs` 取出 ctx，调用 `_handle_error(ctx, exc)`。
3. 若无（如 `init` 不需要 root）：仅 `typer.echo` + `raise typer.Exit(1)`。
4. 删除 `import click`。

伪代码：
```python
def with_errors(func):
    sig = inspect.signature(func)
    has_ctx = "ctx" in sig.parameters

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except DolCtlError as exc:
            ctx = kwargs.get("ctx") if has_ctx else None
            if ctx is None and has_ctx and args:
                ctx = args[0]
            if ctx is not None:
                _handle_error(ctx, exc)
            else:
                typer.echo(f"Error: {exc}", err=True)
                raise typer.Exit(code=1)
    wrapper.__signature__ = sig
    return wrapper
```

### 风险
- 错改后所有命令的 exit code / 错误日志可能静默坏掉。**必须先有测试**：起码一个对每个命令的 happy-path subprocess 测试 + 几个故意触发 `DolCtlError` 的负例。

### 依赖
- #5 测试。

---

## 3. serve.py 简化

### 现状评估
重新读了 `core/serve.py:79-85`：动态 `type()` 子类化 + `functools.partial` 注入 `directory` 是 stdlib `http.server` 的**标准做法**——`BaseHTTPServer` 实例化 handler 时只能传 `(request, client_address, server)` 三个参数，自定义属性必须挂到类上。

### 建议（降级）
这条原本是「代码异味」直觉，但实际无更简洁的等价写法。建议**降级**为：
- 把 `type()` 的两层包装抽到一个具名 helper：`def _build_handler_class(entry_name, allow_lan) -> type[_GameHandler]`。
- 把现有的注释补全成「为什么用 `type()` 而不是 `partial`」的设计说明。
- 删除多余的 `entry_name: str = "index.html"` / `allow_lan: bool = False` 类属性（既然每次都通过子类化覆盖，留默认值反而误导）。

不再做更激进的重写。

### 依赖
- 无强依赖；建议放在 #5 之后顺手做。

---

## 4. 日志分级

### 目标
- 用标准 `logging` 替换当前 `infra/log.py` 中的手卷文件写入。
- 关键步骤（install start/finish、build start/finish、download 进度）走 INFO；CLI 默认安静，`--verbose` 才打到 stderr。

### 设计
- `infra/log.py:setup_logging(root, verbose=False)`：
  - 文件 handler：`logging.handlers.TimedRotatingFileHandler(.dolctl/logs/dolctl.log, when="midnight", backupCount=14)`，level=INFO。
  - 控制台 handler：StreamHandler(stderr)，仅在 `verbose=True` 时挂上，level=INFO；默认仅挂 WARNING。
  - format: `[%(asctime)s] %(levelname)s %(name)s: %(message)s`。
- `dolctl/cli.py:main` 增 `--verbose/-v` 选项。在 callback 内尝试 `resolve_root` → 调 `setup_logging`；失败（未 init）则用临时 `StreamHandler` only。
- `_handle_error` 改为 `logger.exception(message)`，文件 handler 自动落盘，stderr 仍由 `typer.echo` 显式打印（保持 CLI 输出体验）。
- 关键调用点埋点：
  - `core/versions.py`: install 三个入口前后各一条 INFO。
  - `core/build.py`: 已用 logger，但当前没人配置 handler；引入 setup_logging 后自动生效。
  - `infra/net.py:download_file`: 每 ~5% 一条 INFO（可选）。

### 决策
1. **默认安静**：stderr handler 仅在 `--verbose` 时挂载（level=INFO），否则仅 WARNING 起。文件 handler 始终是 INFO。
2. 不加 `--quiet`，WARNING 始终可见。

### 依赖
- #5 测试（用 pytest 的 `caplog` 验证级别）。

---

## 5. 补测试

### 目标
建立可用的 pytest 套件，让后续 refactor 可回归。

### 范围与文件结构
```
tests/
  conftest.py                # tmp_root fixture：在 tmp_path 内跑 init_root
  fixtures/
    sample_version.zip       # 含 index.html 的最小 zip
    sample_mod.zip           # 含 boot.json 的最小 mod zip
    malicious.zip            # 用于 zip-slip 验证（CI 安全脚本生成，不入仓）
  unit/
    test_zip.py              # extract_zip 抵抗 zip-slip、strip_single_dir
    test_versions.py         # _select_remote_version / _make_version_id / _normalize_id
    test_mods.py             # _slugify_mod_id、_read_boot_json
    test_profiles.py         # reorder_mods 校验
    test_build.py            # 三种 HTML 形态（无 head / 有 head 无数组 / 已有数组）下的注入
  integration/
    test_install.py          # install_from_file / install_from_dir 端到端
    test_build_serve.py      # build + serve，断言 entry HTML 被 inject
  cli/
    test_cli_smoke.py        # subprocess 跑完 init→install→build 流程
```

### 关键测试点（必须有）
- `test_zip.py`：构造一个含 `../escape.txt` 成员的 zip，断言 `extract_zip` 抛 `ValueError`，且 dest 外没有文件。
- `test_build.py`：
  - 输入 HTML 无 `<head>` → 数组写在文件开头。
  - 输入 HTML 有 `<head>` 但无 `modDataValueZipList` → 数组写在 `</head>` 前。
  - 输入 HTML 已有 `modDataValueZipList=[...existing]` → 追加而非覆盖。
- `test_versions.py`：`selector="latest"` 选最新 published；`selector="vanilla-0.5.3"` 与 `0.5.3` 等价；`channel:tag` 形式分割。
- `test_cli_smoke.py`：用 `subprocess.run([..., "--root", tmp])` 跑核心流程，断言 exit code 与 stdout。

### 网络
所有 GitHub provider 调用用 `monkeypatch.setattr("infra.net.fetch_json", fake)` 替换；不打真实网络。

### 工具
- 加 `pytest-cov` 到 dev 组。
- CI 暂不做，本期只要本地 `uv run pytest` 跑过。

### 估时
集中投入 1–2 天可到 ~60% 覆盖率，足以支撑后续 refactor。

### 依赖
无。先做。

---

## 6. 增量构建

### 目标
`dolctl run` 当前每次都全量拷贝 `versions/<id>/` 到 `runtime/<profile>/merged/`。DoL 资源接近 GB 级，每次冷启 5–15 秒。希望未改变时跳过。

### 触发完整重建的条件
1. `profile.version_id` 与上次构建不同。
2. `profile.mod_order` 不同（含顺序）。
3. 任一 enabled mod 的 zip "脏标记"变化（**mtime + size 不变即视为未变**，避免每次 build 重算大文件 sha256）。
4. `merged/` 不存在或不完整。

### 决策：避免每次重算 hash
`mod_zip_paths` 的脏检测采用三元组 `(mtime_ns, size, cached_sha256)`：
- 仅当 `(mtime_ns, size)` 与上次一致时，复用 cached_sha256（不读盘）。
- 不一致才重新算 sha256 并写回缓存。

这样典型场景（mod 未动）零 IO；唯一一次成本是首次构建或 mod 真的被替换时。

### 数据结构变更
`build_meta.json` 扩展：
```json
{
  "schema_version": 2,
  "base_version_id": "vanilla-0.5.3",
  "mod_order": [
    {"id": "modA", "mtime_ns": 1716200000000000000, "size": 12345, "sha256": "..."},
    {"id": "modB", "mtime_ns": 1716200001000000000, "size": 67890, "sha256": "..."}
  ],
  "built_at": "..."
}
```

### 算法
```
load existing meta (if any)
need_copy   = meta missing OR meta.base_version_id != profile.version_id OR merged/ incomplete
need_inject = need_copy OR mod_order_or_hashes_changed

if need_copy:
    rm -rf merged/
    copy versions/<id>/ → merged/
elif need_inject:
    # 仅重写 entry HTML：从 versions/<id>/<entry> 拷一份覆盖 merged/<entry>，再 inject
    cp versions/<id>/<entry> → merged/<entry>
# else: 完全跳过

if need_inject:
    inject_mods_into_html(merged/<entry>, ...)

write new build_meta.json
```

### 关键设计点
- **保留一份 pristine entry HTML**：注入是在 HTML 上修改文本，第二次注入若直接在已注入的 HTML 上操作，要么用现有的「追加现有数组」分支（已实现），要么从原始 HTML 重新拷贝。**后者更鲁棒**，避免依赖正则去解析自己写出的内容。
- **CLI 接口**：`dolctl build [--clean]`、`dolctl run [--clean]`。默认走增量；`--clean` 强制全量。
- **失败回退**：增量过程中任一步抛异常 → 删 `merged/`，下次走全量。

### 风险
- 用户手工编辑 `versions/<id>/` 内容时，缓存判定不出。**文档明确说明：`versions/<id>/` 视为只读 artifact，要改请重新 install**。
- mod zip 替换：mtime + size 在同一文件系统内可靠；跨设备 cp 会保留 mtime → 可能漏检。`dolctl mod add` 与 `--force` 走代码路径会更新 mtime，影响小。极端场景可用 `dolctl build --clean` 兜底。

### 触及文件
- `core/build.py`：核心改动。
- `core/models.py`：可选扩展 `BuildResult`（增 `was_incremental: bool`）。
- `dolctl/cli.py`：`build` / `run` 增 `--clean`。
- `tests/integration/test_build.py`：必须覆盖三条路径（全量、仅注入、完全跳过）。

### 开放问题
1. 增量构建后是否还重写 `build_meta.json`？是——`built_at` 始终刷新，便于诊断。
2. 是否需要 `dolctl build --status` 显示当前 merged 是否新鲜？锦上添花。

### 依赖
- #5 测试。改 build 路径不打测试很危险。

---

## 7. Provider 抽象

### 目标
让 `providers/` 真正成为可扩展层，而不是只剩 GitHubReleasesProvider 的硬编码分支。

### 现状
`core/versions.py:130-139` `_get_provider` 写死：
```python
if channel_cfg.provider != "github":
    raise DolCtlError(f"Unsupported provider: {channel_cfg.provider}")
return GitHubReleasesProvider(...)
```

### 设计
1. 定义 `core/models.py:VersionProvider` Protocol：
   ```python
   class VersionProvider(Protocol):
       def list_versions(self) -> list[RemoteVersion]: ...
       def download(self, version: RemoteVersion, dest: Path) -> str: ...
   ```
   注：`resolve(selector)` 当前在 `core/versions.py:_select_remote_version` 实现，可不迁入 provider。
2. `providers/__init__.py` 暴露注册表：
   ```python
   REGISTRY: dict[str, Callable[[str, ChannelConfig], VersionProvider]] = {}
   def register(name): ...
   ```
3. `providers/github.py` 通过 `@register("github")` 注册一个 factory。
4. `core/versions.py:_get_provider` 改为：
   ```python
   factory = providers.REGISTRY.get(channel_cfg.provider)
   if factory is None:
       raise DolCtlError(f"Unsupported provider: {channel_cfg.provider}")
   return factory(channel_name, channel_cfg)
   ```

### 第二个 provider 候选（先不实现，只为验证抽象）
- `providers/manifest.py`：从一个 JSON URL 拉取版本清单（schema 自定义），适合自架镜像或 Gitea 一类没有 GitHub API 的源。

### 触及文件
- `providers/__init__.py`：新增注册表与 `register` 装饰器。
- `providers/github.py`：注册 + 微调。
- `core/versions.py:_get_provider`：改为查表。
- `tests/unit/test_versions.py`：用 `FakeProvider` 注册一个测试 provider，跑 `install_from_remote` 全程不打网络。

### 决策
1. 采用**方案 B**：`ChannelConfig` 保留 `provider`/`repo`/`asset_regex`，新增 `extra: dict[str, str]`。github 用一等字段，其他 provider 从 `extra` 取自定义字段并自验。
2. provider 仅负责拉取，缓存保持在 `core/versions.py`。Protocol 只暴露 `list_versions()` + `download(version, dest) -> sha256`。`resolve(selector)` 留在 core，避免每个 provider 重复实现 "latest" 排序。
3. 注册表：`providers/__init__.py` 暴露 `REGISTRY: dict[str, Callable[[str, ChannelConfig], VersionProvider]]` 与 `register(name)` 装饰器。第二 provider 不本期实现，仅用 `FakeProvider` 在测试中验证抽象。

### 依赖
- #5 测试。
- 推荐与 #1 一并设计：Channel CLI 的 `--provider` 选项值就是 `providers.REGISTRY.keys()`。

---

## 推荐执行顺序

按优先级与依赖排好的路线图：

| 序 | 项 | 估时 | 备注 |
|---|---|---|---|
| 1 | **#5 补测试** | 1–2 天 | 所有后续 refactor 的前置 |
| 2 | **#4 日志分级** | 0.5 天 | 引入 `--verbose`，行为兼容 |
| 3 | **#2 CLI 错误 refactor** | 0.5 天 | 摘掉 click 依赖 |
| 4 | **#3 serve.py 简化（降级）** | 0.5 天 | 抽 helper + 完善注释，到此为止 |
| 5 | **#7 Provider 抽象** | 1 天 | 为 #1 铺路 |
| 6 | **#1 Channel CLI 子系统** | 1 天 | 真正解决用户首次配置门槛 |
| 7 | **#6 增量构建** | 2–3 天 | 单独推进，影响最大 |

合计约 7–10 天单兵投入。

### 建议第一步
开 PR `tests: bootstrap pytest suite`，提交 #5 中的 `conftest.py` 与 `tests/unit/test_zip.py`、`tests/unit/test_versions.py`、`tests/unit/test_build.py` 三个最关键的文件。验证最近一轮修复（zip-slip、注入逻辑）有回归保护，再开始动其余 refactor。
