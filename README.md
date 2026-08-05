# Neo Code

> 基于 DeepSeek V4 API 的交互式 AI 助手 CLI：51 个工具、PolicyPipeline 权限分层、Hermes 自我进化、多智能体与向量记忆。MIT License。

## 快速开始

```bash
# 安装依赖（或直接运行，启动时自动补装）
pip install -e .

# 设置 API key（必须；环境变量优先，也可写入 ~/.deepseek/config.json）
export DEEPSEEK_API_KEY="sk-your-key"

# 可选：Tavily key 用于联网搜索（缺省时降级 DuckDuckGo）
export TAVILY_API_KEY="tvly-your-key"

# 运行
python neo_code.py
```

配置查找顺序：`~/.deepseek/config.json`（全局）→ 当前目录 `.deepseek.json` / `.deepseek/config.json`（项目级）→ 环境变量（最高优先）。API key 不内置于代码，需通过环境变量或配置文件提供。

## 命令行参数

| 参数 | 说明 |
|------|------|
| `-c, --command <cmd>` / `-p, --prompt` | 单次执行模式：执行一条命令后退出 |
| `-m, --model <name>` | 模型（默认 `deepseek-v4-pro`，可选 `deepseek-v4-flash`） |
| `--no-thinking` | 关闭思考模式 |
| `--auto` | 信任模式启动（自动批准所有工具） |
| `--debug` | 调试日志到 `~/.deepseek/debug.log` |
| `--confirm always\|auto\|never` | 编辑确认策略（默认 auto） |
| `--smoke-test` | 运行冒烟测试后退出 |
| `--no-bootstrap` | 跳过启动时依赖自动安装（CI 用） |
| `--autonomous` | 启用自主驱动循环（实验） |
| `--index-code <DIR>` | 为目录建立语义代码索引后退出（需 chromadb + sentence-transformers） |
| `--version` | 版本信息 |

## 配置（`~/.deepseek/config.json`）

| Key | 默认 | 说明 |
|-----|------|------|
| `MODEL` | `deepseek-v4-flash` | AI 模型（代码默认；`--model` 覆盖） |
| `FLASH_MODEL` | `deepseek-v4-flash` | 自动路由用的轻量模型 |
| `BASE_URL` | `https://api.deepseek.com` | OpenAI 兼容端点（LM Studio 等需带 `/v1`） |
| `MAX_OUTPUT_TOKENS` | `32768` | 含思考 token；调高避免思考阶段触发 length 截断 |
| `THINKING_ENABLED` | `true` | 思考模式 |
| `REASONING_EFFORT` | `max` | 思考深度（low/medium/high/max） |
| `STRICT_MODE` | `false` | 严格工具 schema 校验 |
| `JSON_MODE` | `false` | 强制 JSON 输出 |
| `AUTO_MODEL_ROUTING` | `false` | 简单查询自动切 Flash |
| `CONTEXT_STRATEGY` | `summarize` | 上下文策略 |
| `MODEL_LIMIT` | `1000000` | 上下文 token 上限 |
| `SUMMARY_TRIGGER` | `0.7` | 触发压缩的占用比例 |
| `TRUNCATE_KEEP_ROUNDS` | `15` | 截断保留轮数 |
| `CMD_TIMEOUT` | `120` | 命令超时（秒） |
| `PROXY` | `""` | 代理（如 `http://127.0.0.1:7890`） |
| `PATH_CLAMP_ROOT` | `false` | 写/删/执行工具路径钳制到项目根 |
| `PATH_ALLOWLIST` | `[]` | 额外允许访问的根目录列表 |
| `TEMP_CLEANUP_INTERVAL` | `0` | 临时产物自动清理间隔秒数（0=关，仅 `/clean`） |
| `PRELOAD_ASR` | `false` | 启动预加载 FunASR（省首次 `/voice` 等待，启动慢 ~21s） |
| `HOOKS_ENABLED` | `true` | 工具前后钩子 |
| `safety.allow` | `["*"]` | 允许工具（支持 `group:*`） |
| `safety.deny` | `[]` | 拒绝工具（deny-first） |
| `safety.ai_classifier` | `false` | Flash 模型风险预分类 |
| `cli_mode` | 只读白名单 | 非交互模式默认拒绝写/删/命令（`--auto` 可信任模式） |
| `tts` | 关闭 | 语音合成设置（enabled/voice/speed） |

> 配置文件中 `sk-your*` / 空串等占位符会被跳过，避免覆盖有效密钥。

## REPL 命令

| 命令 | 说明 |
|------|------|
| `/exit` | 退出 |
| `/help` | 全部命令 |
| `/auto` | 切换信任模式（自动批准全部工具） |
| `/clear` | 清空会话（向量记忆保留） |
| `/history` | 消息数统计 |
| `/save` | 导出会话为 markdown |
| `/load` | 加载已保存会话 |
| `/dump` | 导出原始消息 JSON |
| `/stats` | 会话统计与上下文占用 |
| `/model` | 查看/切换模型 |
| `/effort` | 设置思考深度（low/medium/high/max） |
| `/tools` | 列出全部工具与权限 |
| `/config` | 配置面板（tts\|model\|safety\|search\|voice） |
| `/compact` | 摘要压缩上下文降 token |
| `/search <kw>` | 在历史消息中检索 |
| `/undo` | 回退上一轮对话 |
| `/recall <query>` | 查询向量记忆 |
| `/memory` | 向量记忆状态 / `clear` 清空 |
| `/balance` | 查询 API 余额 |
| `/hermes` | 收集/应用学习反馈 |
| `/clean` | 清理临时产物 |
| `/agents` | 查看后台子代理状态 |
| `/image <path>` | 附加图像（下条消息携带）/ `clear` |
| `/tts` | TTS 开关（on\|off\|list\|voice\|speed） |
| `/talk` | 语音对话模式 |
| `/subtitle` | 桌面字幕悬浮（on\|off\|toggle，需 PySide6） |
| `/voice` | 语音输入（麦克风 → STT → AI） |

## 工具（51 个）

权威清单以代码 `TOOL_GROUPS` 与 `/tools` 输出为准，按功能分组（与 `safety.allow` 的 `group:*` 一致）：

| Group | Tools |
|-------|-------|
| `group:fs` | read_file, write_file, edit_file, apply_patch, list_files, delete_file, undo_edit |
| `group:search` | grep_search, glob_search, web_search, web_fetch, web_extract, web_crawl, web_research, read_webpage, search_codebase |
| `group:exec` | run_command, run_interpreter, run_python, lsp_check, process, get_terminal_output |
| `group:web` | web_search, web_fetch, web_extract, web_crawl, web_research, read_webpage, social_fetch |
| `group:plan` | plan_mode_enter, plan_mode_exit, todowrite, question, task, update_plan, goals |
| `group:mcp` | mcp_call |
| `group:memory` | memory_search, update_memory |
| `group:safe` | 39 个只读/安全工具（含 search/exec/plan 等，见代码 TOOL_GROUPS） |
| `group:write` | write_file, edit_file, apply_patch, run_command, process, delete_file, undo_edit |
| `group:all` | `*`（全部） |

未入组工具：`workflow` `github_cli` `hermes_collect` `hermes_apply`。

> `[EXPERIMENTAL]`：`workflow` / `social_fetch` / `cron` / `hermes_collect` / `hermes_apply`。工具权限分四档：`ALLOW`（直接执行）、`ASK`（需确认）、`GATE`（SafetyGate 风险拦截）、`DENY`。

## 核心特性

### PolicyPipeline 权限分层
deny-first 语义 + 组展开，示例：

```json
{"safety": {"allow": ["group:safe", "group:plan"], "deny": ["run_command"]}}
```

### Hermes 自我进化（实验）
`hermes_collect` → 分析轨迹沉淀经验（含验证与来源）；`hermes_apply` → 应用/预览/丢弃/回滚（写前备份，可回滚）。

### 上下文压缩
SmartCrusher 分析工具输出，保留错误/异常，`headroom_retrieve` 可逆恢复。另支持 `/compact` 摘要压缩与输出截断自动续写。

### 多智能体
`agent_spawn` 生成后台智能体，`task` 启动子代理（最多嵌套 2 层），`process` 控制后台进程，`/agents` 查看状态。

### Plan Mode
`plan_mode_enter` 禁用全部写操作，仅保留只读/规划工具。

### 向量记忆
`memory_search` / `memory_recall` / `update_memory`，需 `pip install neo-code[vector]`（chromadb + sentence-transformers）。

### 语音与字幕
TTS（edge-tts）、麦克风输入（FunASR / SpeechRecognition）、桌面字幕悬浮（PySide6）。

## 项目文件

- `neo_code.py` — 主程序（单文件）
- `NEO_CODE.md` — 项目指令（注入 system prompt；`DEEPSEEK.md`/`AGENTS.md`/`CLAUDE.md` 同效）
- `pyproject.toml` / `requirements.txt` — 依赖
- `tests/` — pytest 测试套件
- `.github/workflows/test.yml` — CI（Ubuntu + Windows / Python 3.12）
- `~/.deepseek/` — 配置、hooks、skills、会话、向量记忆、自主任务等

## 测试

```bash
pip install pytest
python -m pytest tests/ -q
python neo_code.py --smoke-test
```

## 自主驱动循环（实验）

对话回合结束后，模型自主决策是否/何时主动找用户继续话题（结构化 JSON 决策）；
同意则持久化调度，到期通过事件队列与终端提示发起；拒绝则休眠。频率硬上限防止烧钱。

```bash
python neo_code.py --autonomous
```

任务存于 `~/.deepseek/autonomous_tasks.jsonl`（JSONL 追加写，重启不丢）。该模块独立，
可移植到常驻项目（如 AI 虚拟主播）作为"异步存在"层。

## Changelog

### v1.1.0 (2026-08-02)

- **安全**：`run_interpreter` 弃用可逃逸的 AST 白名单沙箱，与 `run_python` 共用子进程执行通道（超时 + 自动清理），由 SafetyGate 统一把关
- **线程安全**：`_file_locks` / `_background_processes` / `_process_registry` / 进程输出缓冲全部加锁，修复并发竞态
- **错误处理**：工具分发边界统一"工具函数一律返回字符串"约定，并补契约测试
- **代码健康**：文件顶部新增「调参区」常量块；合并 `_pip_install` / `_pip_install_visible`；`repl_loop` 拆出 `_handle_slash_command`；`process_stream` 渲染纯函数外提；smoke_test 外迁至 `tests/test_smoke.py`
- **标记**：workflow / social_fetch / cron / hermes 系列标记为 `[EXPERIMENTAL]`
- **环境**：Windows 下命令执行优先 pwsh（避免误选 WSL 商店占位 bash）
- **测试**：测试套件修复至全绿（177 passed），并修复 `micro_compact` 旧名引用等遗留问题
