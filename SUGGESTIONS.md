# SUGGESTIONS / 待改进事项

本文档记录对当前 dolctl 实现的审阅意见，按优先级分组。每条都给出**问题位置**、**现状**、**建议**，便于后续 agent 直接拾取。

> 审阅时间：2026-05-21 · 审阅范围：`core/`、`infra/`、`providers/`、`dolctl/`、`intro.md`、`AGENTS.md`、`README.md`
>
> 进度（2026-05-21 第二轮）：已解决 #1、#2、#3、#5、#6、#7、#8、#12、#15、#16；其余条目仍待处理。已解决项标 ✅。

---

## P0 — 安全与正确性

### 1. zip-slip 漏洞：`extract_zip` 未校验成员路径 ✅ 已解决
- 位置：`infra/zip.py:8-18`
- 现状：直接调用 `zip_handle.extractall(dest)`。若 zip 内含 `../../foo` 之类的成员名，可写出到 `dest` 之外的位置。
- 影响：`dolctl install --file <zip>`、`dolctl install latest --channel ...` 都会处理外部 zip；`dolctl mod add <url>` 也接受任意 URL。
- 建议：解压前遍历 `zip_handle.infolist()`，对每个 `ZipInfo.filename` 做规范化：
  - 拒绝绝对路径与含 `..` 的成员；
  - 解析后的目标路径必须仍在 `dest` 内（`resolved.is_relative_to(dest)`）。
  - 失败时抛 `DolCtlError`，并在临时目录中清理已写入文件。

### 2. 下载未原子写入，断点会留下损坏的缓存 ✅ 已解决
- 位置：`infra/net.py:24-41`、`core/versions.py:215-216`
- 现状：`download_file` 直接写入最终路径。下载中断后，缓存中留下不完整的 zip；下一次安装可能仍读到这个坏文件（因为路径已固定）。
- 建议：先写入 `dest.with_suffix(dest.suffix + ".part")`，校验完成后 `os.replace` 到目标；异常时删除 `.part`。

### 3. ModLoader 注入命名与 spec 不一致 ✅ 已解决（intro.md 同步）
- 位置：`core/build.py:21,95-105` vs `intro.md:322,569-583`
- 现状：实现使用 `window.modDataValueZipList`（Lyra 实际使用的 base64 数组），spec 文档却仍写 `window.modList` 并描述「写入相对路径」。
- 建议：以**实现为准**修订 `intro.md` §5.6 与 §11.2，明确两点：
  - 注入字段名是 `window.modDataValueZipList`；
  - 内容是 mod zip 的 base64，而非路径，因此 `merged/mods/` 不再需要存放 zip 文件（§5.6 第 2 步 "复制 mod zip 到 merged/mods/" 与验收 "mod zip 文件存在于 merged/mods/" 都应删除或改写）。

---

## P1 — 用户体验 / 缺失功能

### 4. 大文件下载无进度条
- 位置：`infra/net.py:24-41`
- 现状：DoL 完整包 100MB+，`download_file` 静默下载，用户不知道是否卡死。
- 建议：在 `client.stream` 循环中按 `response.headers.get("content-length")` 输出进度（每 ~5% 一次），或接入 `rich.progress`。CLI 与库使用要分层：在 `core/versions.py` 调用处包一层进度回调，`infra/net.py` 接受 `on_progress: Callable[[int,int], None] | None`。

### 5. `doctor` 漏检 `mods/` 目录 ✅ 已解决
- 位置：`dolctl/cli.py:126`
- 现状：检查列表是 `[".dolctl", "versions", "profiles", "runtime"]`，少了 `mods/`（spec §3.2 要求）。
- 建议：加上 `"mods"`。同时考虑校验 `default` profile 是否存在、`active_profile` 指向的 profile 是否存在。

### 6. 缺少 `dolctl profile mod reorder` 与 `dolctl version remove` ✅ 已解决
- 位置：`core/profiles.py:94-106` 已有 `reorder_mods`，无 CLI 暴露；`core/versions.py` 未实现 `remove_version`。
- 建议：
  - 增加 `dolctl profile mod reorder <id1> <id2> ...`（直接转发到 `reorder_mods`）。
  - 增加 `dolctl version remove <id>`（删除 `versions/<id>/`，并提醒受影响的 profile）。spec §5.3 标记为可选，但用户体验上应有。

### 7. `dolctl mod add` 不支持重装 ✅ 已解决
- 位置：`core/mods.py:115-119`
- 现状：目标目录存在即报错，无 `--force`。
- 建议：与 `install` 对齐，增加 `--force` 选项；默认拒绝覆盖。

### 8. 远端索引：`asset_regex` 默认值过于宽松 ⚠️ 部分解决（已改 `re.fullmatch`；默认正则未改，留给用户配置）
- 位置：`core/models.py:16`、`providers/github.py:47-52`
- 现状：默认 `.*\.zip$` 会匹配 release 的 source code 自动 zip。对 DoL vanilla 这是错的（应只匹配真正的游戏包）。
- 建议：默认改为更严格的、文档里给出 vanilla 与 variant 的示例；并把 `re.match` 改为 `re.fullmatch` 以避免「前缀匹配」的隐含陷阱。

### 9. 缺少 channel 管理命令
- 位置：用户需手编 `.dolctl/config.toml` 才能用 `install latest`。
- 建议：增加 `dolctl channel add <name> --provider github --repo <user/repo> [--asset-regex ...]` 与 `dolctl channel list/remove`。降低首次使用门槛。

---

## P2 — 代码质量 / 可维护性

### 10. CLI 错误处理依赖 `click` 内部 API
- 位置：`dolctl/cli.py:8,82`（`import click; click.get_current_context(silent=True)`）
- 现状：typer 是建立在 click 之上，但混用 typer 的 `typer.Context` 与 click 的 `get_current_context` 是不必要的耦合。
- 建议：把 `with_errors` 改为接受 `typer.Context`（已经是各命令的参数），从函数参数读取而非全局调用 click API。

### 11. `serve.py` 同时使用 `type(...)` 动态子类化 + `functools.partial`
- 位置：`core/serve.py:79-85`
- 现状：两层间接降低了可读性。
- 建议：要么定义一个真正的子类（如 `_ConfiguredHandler`）在模块顶层并通过类属性配置，要么传一个 factory 函数。文档注释里也已经说明了为什么不能用 `partial` 传 `entry_name`，可以保留注释但简化代码结构。

### 12. mod_id slug 退化为空字符串风险 ✅ 已解决
- 位置：`core/mods.py:53-57`
- 现状：纯 CJK 或纯 emoji 的 mod name 会全部被替换为 `_`，最终 strip 后变成 `""`，回退到 `"mod"`。多个无 ASCII 名字的 mod 都会撞 `"mod"` 这个 id。
- 建议：当 slug 退化时，附加 zip 文件名 stem 或简短 hash（如 `mod-3a7f`），保证唯一。

### 13. `infra/log.py` 仅在错误时记录
- 位置：`infra/log.py:10-19`、`dolctl/cli.py:73`
- 现状：成功的 install/build 没有任何日志痕迹。spec §9.1 只要求失败留下日志，因此非阻断，但调试时无操作流水。
- 建议：把 `log.py` 抽象成 `info/warn/error` 三档（写入 `.dolctl/logs/YYYY-MM-DD.log`），关键步骤（install start/finish、build start/finish）写 info。

### 14. 没有任何自动化测试
- 位置：`pyproject.toml` `dev` 组已有 pytest，但 `tests/` 不存在。
- 建议：起码补足以下单元测试（hermetic，不打网络）：
  - `infra/zip.py`：zip-slip 抵抗、`strip_single_dir` 行为。
  - `core/versions.py`：`_select_remote_version` 的 selector 解析、`_make_version_id` 的命名规则。
  - `core/build.py`：`_inject_mods_into_html` 在三种 HTML（无 `<head>`、有 `<head>` 无 ModLoader 数组、有 `<head>` 且已有数组）下的输出。
  - `core/profiles.py`：`reorder_mods` 校验。
- 端到端可用 `testdata/` 起一个小型 DoL fixture（已存在 `testdata/versions`、`testdata/mods`），验收 §10 全部走一遍。

### 15. `AGENTS.md` 与现状脱节 ✅ 已解决
- 位置：`AGENTS.md:3,23`
- 现状：
  - 第 3 行引用 `requirement.md`，实际文件名是 `intro.md`。
  - 第 23 行说模块命名为 `core_versions.py`/`infra_zip.py`/`providers_github.py`，但仓库实际采用子包结构 `core/versions.py` 等。
- 建议：修订两处，与 spec §8.2 现状对齐。

### 16. README 缺 channel 配置示例 ✅ 已解决
- 位置：`README.md`
- 现状：README 只演示了从本地 zip 安装，没提 `dolctl install latest --channel vanilla` 之前需要先编辑 `.dolctl/config.toml` 增加 channel。新用户跑到这一步会卡住。
- 建议：在「快速开始」之后加一节「远程下载（可选）」，给出 `[channels.vanilla]` 的最小示例。

---

## P3 — 长期演进（不急）

### 17. base64 嵌入策略的体积问题
注入策略把 mod zip 以 base64 写进 `index.html`，每个 mod ~30% 膨胀。若 profile 启用十几个 mod，单个 HTML 可达数百 MB，浏览器解析与本地服务的内存压力显著。后续可考虑：
- 仍按 Lyra 的 base64 路线，但把数据切到独立的 `mods.bundle.js`，HTML 只 `<script src=...>`。
- 或改回路径注入（spec 原始设计），把 mod zip 真实拷到 `merged/mods/`，HTTP 服务直接提供。两种各有利弊，需要在性能/兼容性上权衡。

### 18. 增量构建
当前每次 `run` 都 `clean=True` 全量复制。DoL 资源 ~1GB 级别，每次冷启动有几秒到十几秒拷贝代价。可在 `build_meta.json` 中保留源 manifest 的 sha256 + mod_order 哈希，若未变则跳过复制（spec §12 已列出）。

### 19. Provider 抽象只剩 GitHub
`providers/github.py` 是唯一实现；`core/versions.py:_get_provider` 显式判断 `provider != "github"` 抛错，未通过接口实例化。未来加 `gitea`/`mirror`/`local-index` 时，最好抽出一个 `VersionProvider` 协议 + 注册表。

---

## 修订建议清单（汇总）

修复优先级建议顺序：

1. **#1 zip-slip**、**#2 原子下载** — 安全；
2. **#3 注入命名与 spec 对齐** — 文档可信度；
3. **#15、#16 文档修复** — 顺手；
4. **#5、#6、#7 缺失/不完整的命令** — 用户路径上的痛点；
5. **#14 测试** — 进一步演进的前置；
6. 其余按需。
