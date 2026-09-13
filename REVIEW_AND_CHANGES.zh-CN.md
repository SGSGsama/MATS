# MATS v1.3.0 会话审计与本轮修改总览

本轮以 `init_export.md`、`engineer-session_1.md`、`control_session_1`、`control_session_2.md`、`control_session_3.md`、`control_4.md` 和现场 `.task/` 为运行证据。目标不是削弱约束，而是把可机械复现的事务工作从模型 I/O 中移走，同时保留足够的角色、路由和恢复约束，防止长任务指令漂移。

## 会话暴露的主要问题

- `control_session_2.md` 共 4,890 行、362,763 字节。旧版激活预读 policy、storage、native boundary、两份 Orca Skill/完整指南；恢复后又枚举 Skill 并读取 `packets.py`、`role_spawn.py`、`records.py`、`routing.py`、`contracts.py`、`guards.py`、`verification.py`、`common.py` 和大段完整 Schema。正常命令信息不足时，Control 被迫用源码补接口。
- Worker/Planner/Reviewer 需要手写 schema、snapshot、target/base identity、path/SHA/version wrapper 和长 evidence 索引。模型输出了 98 行候选，其中大量内容可从文件和工作区机械复现；Control 又手算 SHA、猜 mode 和修 wrapper，形成高频 Guard 拒绝。
- “看不到当前工作区 snapshot”被误报为 `blocked`。这是接口缺口，不是领域阻塞；snapshot 本应由 Guard 从绑定工作区生成。
- 现场候选的 27 个 evidence 文件 hash 全部与当前文件一致，但候选 snapshot 与 Guard 结果不一致。根因是旧 snapshot 纳入 `st_mode & 0777`：同一 Windows 文件在 Git Bash 中呈现 0644/0755（420/493），在 Windows Python 中呈现 0666/0777（438/511）。不是 `.task` 目录、日志未 flush 或领域内容变化。
- Worker 在 finalizer 前仍可能保留后台进程/日志句柄；finalizer 后继续写 evidence 会造成真正的候选漂移。
- admission/semantic 两个可见 lock carrier、嵌套加锁和手工“释放锁”认知增加了恢复复杂度；carrier 文件实际上不表示持锁状态。
- R1 `fix_local` 后频繁关闭原 Owner 并 fresh-spawn，重复加载初始 prompt，也丢失同 WP 上下文。
- 根 Control receipt、bootstrap seed project/plan/request 仍需手写，导致 Control 在项目开始前就读取 Schema/源码。
- Windows 原生回执包含 `•` 时，输入虽已解码，CLI 再经 GBK `print(str)` 仍可能抛编码异常。输出异常不能证明原生启动失败，也不能授权第二次 retry。
- `mats dispatch` 成功输出仍回显完整 prompt、固定 binding、argv 和多份原生 receipt，重复占用 Control 上下文并暴露脚本私有 policy 结果。
- `control_4.md` 中 Owner 已正确完成 `check-delivery` 与 `worker_done`，但旧 MATS 只透传重复的原生 wait 回执，未提供 completion receipt/result import 的公开桥接。Control 因而执行约 40 条命令，反复搜索 `.task`/`.codex`、尝试旧 result、猜 binding/runtime view 并调用 Python/Orca；这属于缺失接口导致的工具修复循环，不是合理的任务编排成本。

## 已应用的修改

### 1. 确定性加载、角色和路由

- 激活只固定读取 `SKILL.md`、Control Role、workflow、routing 和一次 doctor。storage 在首次状态/路径操作前加载；native boundary 与完整 Orca 指南只在原生生命周期/身份/恢复异常时加载。
- policy 改为脚本私有；Control 不读取 `config/policy.yaml` 或 `policy_ref`。缺少参数只运行 `mats <command> -h`，所有模型明确禁止读取/搜索 `scripts/*.py` 推断用法。
- 八个角色统一为 Identity/Owns/May/Must not/Output/Handoff/Refresh。MATS 的角色、WP、scope、分配和 review routing 优先于垂类 Skill；垂类 Skill 只提供已分配范围内的方法。
- Research 明确负责独立 evidence/decision、逆向、测量和协议/格式恢复，可写有限分析/探针/提取脚本，但不负责大型产品实现；普通“查 bug 并修复”保持一个 Engineering WP。Research 与 Engineering 只有在退出条件独立、scope 不冲突且实现不依赖未完成研究结论时并行，否则声明 Research -> Engineering 依赖。
- Owner session 按 WP 持久化至 blocked/failed 语义纠正、R0/R1/R2/Synthesis/local repair 完成；`worker_done`、result import 和 reviewer dispatch 都不是 release。`--continue-owner` 可从当前 candidate 或最新 Owner result 恢复，因此错误 blocked 也不会强制 fresh-spawn。
- candidate -> R0 -> fresh R1 是固定正确链；R2 只由 R1 `escalate_r2` 或 guarded accept 的精确 `passing R2 required` 触发。
- Control 对漏洞分析、逆向等正向网络安全任务添加 `-cyber`。Sol-bound Synthesis/R2 自动改用 `gpt-daybreak-blue-latest`、effort 不变；仅明确 `model unavailable` 时自动回退 Sol，其他失败不回退。

### 2. 所有角色协议改为“语义草稿 + 脚本事务化”

- 每次 dispatch 预创建唯一 `.task/tmp/deliveries/<packet-id>.yaml` 语义草稿。Owner、R1/R2、Luna/Synthesis、Planner 只填各自判断，不再填 schema/hash/version/snapshot/target/base 等事务字段。
- `check-delivery --workspace` 现在强制生成并覆盖 Guard-owned 字段，而不是只在字段缺失时补齐。旧草稿中的错误 snapshot、target、schema 或 plan identity 不再诱导模型手算。
- 当前 workspace snapshot 的缺失被明确规定为“预期状态，绝不构成 blocked/failed”；worker 完成语义草稿后直接运行 finalizer。
- 同一 immutable packet 因原生失败重试而产生多个同 workspace binding 时，finalizer/manifest 根据 packet+workspace 工作，不再错误要求“恰好一个 binding”。
- 所有角色交付前都必须先跑机械 gate；失败在同一 session 修正和重跑，Control 只做语义判断。Planner 也从生成草稿开始，避免再次提交 Guard 无法解析的合同。
- Owner/R1 side request 同样由 Guard 补 schema、commitment/evidence identity；R1 可以机械复用精确候选 evidence。
- `evidence-manifest` 将多个文件/目录生成一个确定性 manifest。模型只写 path 或 `{manifest: path}`；脚本生成每项 hash，Guard 递归验证。几十行 evidence/hash 索引不再经过模型输入输出。
- 角色间 packet 使用语义投影：隐藏 completion、binding、receipt、snapshot manifest、hash/version，只传结论、findings 和必要 evidence paths。Planner 的 accepted/review 数据按需外置为内容寻址 payload。
- Control transition 命令可直接接收 binding ID 或真实 artifact path，脚本生成并验证 internal ref；不再创建 path/SHA wrapper，也不再让 Control 手算 SHA。
- public dispatch receipt 只返回状态机所需的 packet/task/dispatch/binding identity，以及实际发生时的 fallback attestation bit；不再回显完整 prompt、固定 binding、argv 和原生 receipt。

### 3. Bootstrap 与根 Control 事务化

- `milestone-paths m0_<milestone>` 返回固定 `goal.txt` 路径。Control 只需把用户目标原文写入该纯文本文件。
- 新增 `bootstrap-init`：机械生成合法 seed project、空 WP plan、紧凑 Git inventory、Planner request、semantic state，并从 `CODEX_SESSION_ID` 与脚本私有固定 binding 自动 attach 当前 Control。
- 旧 `init` 与 receipt 文件参数保留兼容，但正常流程不再要求模型打开 Schema、拼 root receipt 或手写 bootstrap contract。
- 仓库 inventory 只提供计数、目录/扩展名汇总、根/marker 路径及有界 changed paths，不含模型手写 hash，也不把完整文件树无界塞进 Planner prompt。

### 4. Snapshot、资源和锁

- snapshot 删除 host `stat()` mode，改用 Git binary worktree/index diff 表示 tracked content/mode；untracked 文件仍以规范 path+SHA 固定。
- Git diff 的 snapshot identity 显式排除 `.task`，即使控制文件被误 stage，也不会污染领域候选。
- finalizer 前必须停止本角色启动的后台进程并关闭/flush workspace/evidence 句柄；finalizer 成功后不得再改 workspace/evidence。
- 所有本地事务统一使用一个 `.task/coordinator.lock`。锁由 OS 在命令退出/崩溃时自动释放；carrier 文件持久存在但不是锁状态，模型不创建、删除、检查或维护它。
- `.task` 长期记录按 `m<number>_<milestone-slug>/` 分层；packet 使用全局自动 `p000001` index，binding/result/review 使用实现必需的机械 key。`.task/tmp` 只保留固定 staging，不产生 timestamp/retry/fix/final 文书堆。

### 5. Windows/POSIX、编码和安装

- 内部 logical ref 一律使用 POSIX `/`；host workspace path 仍由 `Path`/原生 receipt 表示，Git Bash、Windows CMD 和 POSIX launcher 共用同一 Python 实现。
- 机器输出通过 UTF-8 bytes 写 stdout/stderr，launcher 同时启用 `-X utf8`。包含 `•` 的原生回执不会再因 GBK 输出失败；即使原生边界异常，也按 receipt 核验，不以控制台编码推断启动失败。
- `wait` 现在把 Orca `worker_done` 与不可变 binding 做身份核验并自动生成私有 completion staging；Control 只运行返回的 `result <binding-id>`，脚本完成 draft 定位、导入、FIFO ack 与 tmp 清理。正常事件链不再搜索 `.task`/`.codex`、猜 receipt 或调用 Python。checkpoint/纯 completion 也不再强制重载三份控制规范。
- 用户安装器位于 Skill 外部，优先使用 `uv` 创建目标本地 `.venv` 和安装固定依赖；无 uv 时保留 Python 兼容路径。`uv pip --link-mode copy` 避免 Windows 已加载 DLL/硬链接导致强制升级时无法删除 backup。
- 安装先 staging、自检，再替换 `%CODEX_HOME%/skills/multi-agent-task-split`；`--force` 才覆盖，失败可回滚。安装器、测试和开发文档不会复制到模型可见 Skill。
- Windows 上 staging/backup 目录交换对刚退出的 Python、DLL 扫描或杀毒软件短暂句柄使用有界退避重试；不会把已经通过 doctor 的安装随机报成 `WinError 5`，也不会牺牲失败回滚。

### 6. 小任务与 Control 权限边界

- 新增闭合定义：Script 权限只覆盖命名的 MATS 状态/hash/gate/inventory 命令；产品 build/test/benchmark/reproducer、流量发生器、远端命令及结果解释均是领域执行，不属于 Control。
- 任务短、只读、看似简单、dispatch 成本高都不会改变激活后的语义权限。test -> diagnose -> possible fix -> retest 合并为一个 Engineering WP，并复用同一可用 Owner；不另拆微型测试 WP，也不由 Control 吸收。
- Luna Aux 仍只承接 Owner 发起的高容量、只读、可机械核验的提取/整理任务，不能运行项目测试或替代小型 Research/Engineering Owner。
- 用户要求在 push/deploy/restart/replacement 前询问时，该条件成为 Owner 的明确停止点；Owner 提问，Control 原样转发并等待，Control 不执行外部变更。

### 7. Worker session 释放时机

- Research/Engineering Owner 是 WP 级持久 session。`worker_done`、result import、R0、R1/R2 调度或结果、空闲、成本和上下文压力均不允许 Control 提前关闭。
- 正常完成时只有一个释放点：所有 required review 已通过，且 guarded accept 明确返回 live writer 是唯一剩余 blocker。此时已经确认无需 `fix_local` 复用，Control 释放精确 Owner 后立即重试 accept。
- Fresh 一次性 Planner、R1/R2、Luna/Synthesis side role 可在验证交付后结束；Research/Engineering Owner 不能仅因首次 launch 的 `fresh_context=true` 被误归入此例外。

### 8. Control 路径锚定

- `LOAD_COMPLETE` 时绑定 host 提供的当前 workspace repository；之后每个 MATS 命令都显式传 `--repo`。shell CWD、之前访问的目录和 host temp 均不产生写权限。
- Control 自身产生的 log/capture/redirect 只能复用该仓库 `.task/tmp` 下的固定路径，不得写入外部目录。领域测试 evidence 由 Owner 写入 assigned workspace 与声明 scope。

### 9. Control 与 Orca 上下文成本

- 成本汇总不再只收集 worker dispatch；managed evaluation 必须同时提供每个 Control session 的最终累计 provider usage。
- Control 的 input/cost 已包含 MATS 与 host 实际加载的 Orca Skill，上下文记录仅用于归因，禁止再次累加。每次新 session、compaction 或 refresh 导致的重载分别记录。
- 普通路径和异常路径分开：正常统计实际加载的 MATS/Orca 入口；`native-boundary.md` 与 full Orca guide 仅在真实 native anomaly 触发时统计。缺 Control、缺 Orca load、partial 或 unknown 均令项目总成本保持 unknown。
- 新增 `evaluation/context_footprint.py`，机械测量 UTF-8 source bytes 以监控 prompt 膨胀；明确禁止把 byte 数当作 tokenizer 或账单数据。

### 10. `control_session_3.md` 末段回归

- 该会话实际激活的是 v16，不是当前 v17.4：旧流程预读 policy/storage/native boundary、`orchestration`、`orca-cli` 和 full guide，恢复后又枚举 Skill、读取 scripts/Schema。
- 最新几轮还直接手算产品与日志 SHA，并在目标目录无 Git HEAD 后进入无关 `D:/meituan_re_by_codex` 枚举源码与状态。当前规则现将 native inventory 中其他 workspace 定义为不透明元数据；Control 的读写根都固定为 host 目标仓库。
- 精确目标无 Git HEAD 时必须 STOP，请用户选择授权初始化基线或纠正路径；禁止从父目录/其他 terminal 推断替代仓库。
- 正常 `bin/mats` 调用不构成直接 Orca CLI 使用，不得因此额外加载 `orca-cli` 或 full guide；host 已加载一个所需 Orca Skill 入口时禁止重复，full guide 仍只在真实 native anomaly 后加载。
- 旧 Control session 不会因磁盘 Skill 被替换而热重载。安装器改为让 payload mtime 反映本次复制，并明确提示更新后新建 Control session。

### 11. Runtime view 与恢复接口闭合

- 现场最新版仍要求 Control 传入 `--runtime-view/--workspace-key/--access`，却没有公开命令生成 runtime view；Control 因此反复检查不存在的固定文件、重绑 `control`、裸调 `orca open/status`、读完整指南并猜测“权限上下文”。这是 MATS 接口缺口，不是 Guard 或宿主故障。
- `dispatch` 现在自动检查 Orca 就绪状态；必要时只启动一次并复验，然后读取当前 Run 的 worker inventory、只投影 MATS 已绑定 dispatch、解析精确仓库的真实 worktree ID，并推导 packet 所需 access。紧凑 view 由脚本覆盖写入 `.task/tmp/runtime-view.yaml`，Control 不读写或传递它。
- `accept` 与 `apply-plan` 同样自动刷新 view；exact-packet retry 自动沿用原 placement/access。普通 CLI 隐藏旧的 runtime/workspace/access 兼容参数。
- 缺失 runtime-view 文件不再是任何状态或权限证据。Control 在正常 transition 前不得运行 raw `orca open/status`、进程扫描、重复 `control` 或 full-guide 加载；只有 MATS 返回的具体 native error 才进入异常恢复。

### 12. `control3` / Planner 运行期证据与提问闭环

- `control3.md` 与旧 `control_session_2.md`、`control_session_3.md` 逐字节相同，仍是旧 v16 导出，并不包含本次 `p000007` 交互；有效的新证据来自同目录 `plan` 导出及当前 `.task`。
- Planner 的注入说明要求 `scope.refs` 写路径字符串，但旧 `check-delivery` 没有物化嵌套引用，随后又用只接受 `{path,sha256,version}` 的 schema 校验，因而必然返回模糊的 `oneOf matched 0 branches`。Planner 两次询问 Control、Control 再让用户选择格式，都是这个脚本接口矛盾的放大结果。
- finalizer 现在同时处理 full plan 与 runtime patch：已有路径复用原 pin，新路径从已绑定 Planner workspace 计算 content pin。模型不写或复制 hash/version；`oneOf` 错误同时返回各分支的具体失败路径。
- `scope.paths` 仅定义 Owner 写边界；`scope.refs` 是 plan-time seed evidence，不是运行期读取白名单。新增日志、trace、测试结果、复现输入或修正 evidence path 属于同 WP `local_steer`，直接以原文交给持久化 Owner，不调用 Planner、不修改 plan version；若旧规则已经误开 Planner，则结束该 exchange、不得应用其 proposal，再继续 Owner。
- Control 不再把用户/worker 的问题自动升级为 planning occasion。schema/ref/hash/snapshot/runtime/routing/retry/session 等 MATS 手续由脚本处理，禁止互动式向上询问；可逆且范围内的细节直接执行。只有缺少会改变目标/权限的决定，或不可逆/外部变更授权时，才合并为一次用户问题。

### 13. 读取建议与写边界分离

- 旧 `snapshot(scope.paths)` 把所有 scope 外 changed/untracked 文件一律视为越界写，即使它是用户后来提供、Owner 只读取并在交付中引用的日志；因此 `p000006` 的 `Moonlight-1788837751.log` 被机械拒绝，Owner 又错误改写为 `plan_conflict`，诱发无关 Planner/新 packet。
- 回退逐文件 `allow-read-evidence` Control 能力；读取本身不需要授权。`scope.refs` 与 packet evidence 只提供导航建议，任何角色均可直接读取环境允许的任务相关来源。
- 候选产品快照只覆盖 `scope.paths`；工作区中其他 tracked/untracked 文件视为环境状态，不参与快照，也不阻断交付。Owner 引用 scope 外文件时即声明它是只读输入，finalizer 自动固定内容并与产品变更分离；Owner 产物仍必须写在 `scope.paths`，不得伪装成输入。
- `scope.refs` 的历史 SHA 只保留计划来源身份，不再进入 candidate/R0 的当前内容校验；旧 packet 中 `debug.log` 改变或消失不会阻断。Owner 真正依赖它时，必须在 delivery evidence 中引用当前路径，由 finalizer 重新固定当前内容。
- 该路径不修改 plan/version/packet，不启动 Planner、不询问用户、不新建 worker。文件在交付后变化仍使候选失效。

### 14. `control_4.md` 的完成事件闭环

- `mats wait` 现在只暴露已规范化的事件与确定性下一步，不再把同一份 raw native receipt 重复注入 Control。纯 checkpoint 或纯 `worker_done` 事件的 resume anchor 不要求重读；question、escalation、语义漂移、compaction/interruption 或 authority uncertainty 仍保留精确按需刷新。
- 收到 `worker_done` 时，脚本先将 run/task/dispatch/outcome 与不可变 binding 逐项核验，再从 binding 推导唯一注入交付路径并写入仅由 MATS 管理的 completion staging。任何身份不一致都在导入前拒绝；通用 `reportPath` 不参与文件选择。
- `wait` 对纯完成批次返回顶层 `next_operation: advance`；Control 走统一推进器，不再逐项推导导入、评审和验收步骤。每个 `ready_results[].result <binding-id>` 仍保留为单步恢复接口；模型不搜索回执、不拼 wrapper、不手算 SHA。
- 原生 acknowledgement 在 result 已导入后失败时，不把已完成语义工作判为失败，也不允许另起事务；保留 staging 并返回同一条命令的幂等重试。旧的双文件 result 形式仅保留兼容。
- `SKILL.md` 上限由 3500 字节提高到 4096 字节，用于容纳增加的角色连续性、事件闭环、选择性刷新和工具故障停止条件；当前保持在 4096 字节内，没有以删减关键约束换取体积。

### 15. R2 出队与 Orca Skill 误加载

- review delivery 会写入 `reviews/`，旧 completion 判断却只检查 `results/`，因此 R1/R2 已导入仍无法 ack，Orca 重放同一 delivery。现在脚本按 binding role 解析 canonical collection，并核对 canonical record 的 binding/completion dispatch identity；R2 的 `reviews/` 导入可正常 ack 和清理。
- 真实 `p000012` R2 原生 preamble 已逐项核对：它包含 terminal/task/dispatch/capability、worker_done、heartbeat、ask、escalation、check 及完成后停止/idle 的精确命令和行为。叶子 prompt 不再重复 CLI，也不允许因“被监督派发”激活 coordinator-only `orchestration` Skill。
- `orca-cli` 不是常规依赖；仅在至少两次 context compaction 后，必要语法已不在上下文且精确子命令 `-h` 仍不能恢复时，允许加载一次作为最后语法兜底。它不能重建丢失的 dispatch 身份或 capability。

### 16. `agent_unconfigured`、`user-takeover` 与 Owner 复用

- 实录确认续用请求传给 Orca 的是正确 `term_...` handle，不是 binding 中的 process-incarnation UUID；但源码副本缺少已安装版的 handle 解析，强制重装会造成回归。现在源码固定从精确 `worker-show` 解析 handle，并校验 incarnation 身份。
- `external`/`user-takeover` 可能只是用户查看终端或执行 `/status`，不能据此认定 Owner 丢失。
- `dispatch --continue-owner` 在 handle、incarnation、session、worktree 一致时保留 Owner。后续实录又证明 `--inject` 会对实际存活的 Codex 终端返回 `inject_rejected/no_agent_detected`，因此不再把 agent detector 作为 continuation 的事实来源，也不重复初始化注入。
- Control 新增明确工具故障停止条件：若没有公开恢复接口、接口与已加载 contract 矛盾，或继续需要修改 Skill/事务文件/绕过 Guard，必须暂停并提交精确命令与错误作为 bug；禁止自行修编排脚本、循环试错或要求用户代办 MATS 手续。
- Orca 的 `worker_done.reportPath` 是可选长报告展示元数据，不是 MATS 事务字段。旧 Guard 强制它等于注入 draft，与原生 preamble 冲突，导致 worker 合理填写受控测试报告时被拒。现在 MATS 只按不可变 binding 推导并导入唯一 draft，完全不读取 worker 给出的路径；draft 缺失、身份错误或内容未通过 finalizer 仍会拒绝。

### 17. 长生命周期 Owner 的增量派发

- 旧 `--continue-owner` 虽然复用同一 terminal/session，每次仍重复注入完整 Role Contract、通用权限边界、Aux 说明和交付说明；Engineering/Research 单次约 5.8 KB，长期修复循环会线性占用上下文并提前触发压缩。
- 首次派发及所有 fresh 角色仍使用完整 prompt。健康的同 WP continuation 改走独立 compact prompt，只发送内容寻址 semantic delta、delivery/gate 身份、逐字保留的本轮 instructions，以及从对应 Research/Engineering contract 固定提取的短 recap；不再内联完整 contract/packet。
- launcher 比较 `role_contract_digest` 与 native identity。正常 continue 只发送指令、内容寻址 packet delta、短角色 recap 与 Control session；契约变化才补当前完整 MATS contract，身份不存在或改变才 fresh。续派不重发 Orca init prompt。

### 18. 事务性协议改为脚本生成

- Owner、Reviewer、Planner、Luna Aux、Synthesis 的交付均从 UTF-8 TSV 语义表开始；模型不再手写 schema、snapshot、版本、binding/ref/hash 或证据索引。
- Owner/R1 的 side request 与 Control 的 runtime Planner request 也使用固定 TSV 表。脚本归档原始 directive、生成不可变 request 和内部引用；Control 不能在用户原文之外自行补出协议、兼容、算法、测试或验收设计。
- Planner repair form 从精确 rejected result 预填，只允许修正门禁指出的行；runtime 始终是 sparse patch。

### 19. Control 吸收域任务与远程证据缺口

- 对未导出的 Orca 实时 Control terminal 进行只读诊断后确认：保留的 Terra Owner 仍可复用时，Luna Control 却自行校验二进制、查端口、启动客户端、读取服务端日志并搜索 `main.go/common.go`；随后依据自己得出的“协议字段变化”创建 Planner。这是角色越界与 Planner 误触发，不是小测试无需派发的合理优化。
- Control role 现在明确只读取当前转换点名的 MATS 语义/控制状态，不得通过产品源码、二进制、原始业务日志/证据或 worker transcript 做诊断和执行。工作量、只读性质和成本均不放宽该边界。
- 未验收 WP 收到测试请求、新日志或域内行为修正时，必须不经产品检查地原样 `--continue-owner`。协议/API/架构影响等词汇本身不构成 Planner 条件；用户 steer 只有在明确取代当前 materialized project/plan 的具体字段时才直接进入 Planner，否则由 Owner/Reviewer 在契约确需变化时提交 `plan_conflict`。
- 所有 fresh worker prompt 与同 Owner compact continuation 都新增远程证据规则：必要但不可获取的远程证据直接通过原生 preamble 提出精确缺项；禁止猜测、伪造或误报为 MATS/Guard 故障，非必要证据不产生询问。

### 20. R1 等一次性 session 自动回收

- 旧文档只声明 R1/R2/Planner/Luna/Synthesis 不保留，但正常 `result` 实现仅导入、ack、清理 tmp，没有实际 `worker-release`，因此 Control 会遗留已完成终端。
- 现在批处理会先导入同一 delivery 中的全部结果，再释放其中**每一个**一次性 session，最后 ack 并清理 staging；Research/Engineering Owner 明确不受影响，继续保留给同 WP 修复。
- 每个 release 与 batch acknowledgement 都有脚本生成的最小确认记录。回收/确认失败不会吞掉事件或要求 Control 枚举 terminal：同一 completion 保持不变，重试跳过已确认步骤；只有整批闭合才清理。

### 21. Control 不得扩写设计后误导 Planner

- 实录中的 Planner occasion 本身成立：原 `wp-transport-candidate` 已在 plan v5 下通过 R2 并 accepted，新的 TCP 伪装能力不能直接修改旧候选。但 Control 将用户的“TCP 伪装”扩写为真实 TCP 握手、长度分帧、保留 UDP 回退、沿用 lane/seq/READY 和禁止裸 TCP 头，越过了协调权限。
- Control 现在只能保留不可变用户/来源原文，并补 MATS 必需结构、精确引用的当前 project/plan 事实和用户明确的授权边界。Planner question 必须保持中性，不能自行加入架构、协议/帧格式、实现、兼容/回退、算法、测试或验收设计。
- 歧义本身作为 Planner 的决策输入。Control 不得先解决歧义再让 Planner 为其方案背书；“下一轮”也不会自动解释为新 milestone，新增 WP、修改并 invalidate 已验收 WP、调整依赖或新 milestone 均由 Planner 基于语义状态决定。

### 22. 独立 Review 与原始对话合并

- 已逐项对照 `MATS_v17.4_Review_and_Improvement_Plan` 的计划、证据、两条协议不变量测试以及新增的 `review_dialog.md`。原始参考支持 review 的核心判断：优先减少昂贵 worker 的无依据启动、重复输入与返工；不能把静态字节数包装成 token/费用结论。Review 目录仅作为开发输入，不进入安装包。
- P0 retry 草稿覆盖已复现并修复：launcher 先渲染、后准入，在 coordinator mutex 内通过 admission 后才替换 delivery；准入拒绝时旧 draft 字节不变。对应 review 原始测试已转绿。跨原生调用结果不明仍明确停止，不承诺 Orca/MATS 间 exactly-once。
- P0 同批 one-shot 漏释放已复现并修复：只有全批导入后才逐个释放所有 Planner/R1/R2/Luna/Synthesis，确认记录使重放跳过成功步骤；全部释放后才 ack/清理。Owner 与 reviewer 混合批次只回收 reviewer。
- P1 新增薄层 `mats advance`：共享 Guard/routing 语义，自动完成 completion -> R0 -> R1/必要 R2 -> source-backed fix/Synthesis/Planner -> proven Owner release -> accept；返回稳定状态、`reason_code`、`next_operation` 和有界 trace。单次最多创建一个 worker，默认最多 16 个本地步骤；`--dry-run` 不创建 packet/task/delivery/state，也不落盘 runtime view。新 WP 首个 Owner 必须由 Control 明确 `-cyber`/`--non-cyber`，省略时返回 `NEEDS_DECISION` 而非默认否；后续角色继承。Control 只解释 `NEEDS_DECISION`，不再匹配错误字符串。
- Planner `plan_conflict` 请求由脚本从精确 Owner/Reviewer memo 生成，问题与 source ref 原样保留；binding 自动记录调用 role/WP/reason/mode/source，provider usage 不可得时为 unknown，不要求 worker 写监控文书。
- 合法 Planner proposal 若改变仍有 retained Owner 的 affected closure，Guard 必须先证明没有 active affected dispatch 且 writer release 是唯一 apply blocker；脚本仅解析并释放受影响的当前 Owner、记录确认、刷新后重试原 proposal。身份不明即停止，未受影响 Owner 不回收。
- P1/P2 的 continuation 优化只落地了有稳定键的对象级增量（`previous_reviews.role`、`direct_downstream.id`），并把 artifact 扫描改为每个 YAML 只解析一次。它们是静态 I/O 改善，不宣称实际 token、缓存、费用或延迟收益。
- 本轮没有实现泛化 `mats decide`、跨 Orca/MATS 的事务预留/exactly-once，也没有缩短包含 native launch 的临界区：现有语义决策渠道已足够，而后两项需要 Orca 提供可核对的 reservation/fencing/operation receipt。没有该能力时贸然解锁或自动重试会扩大风险；长锁只在 profile 与协议支持后优化。
- Control 的角色上限单独放宽到 1536 字节，其他叶子角色仍为 1250 字节；这是可用额度而非填充目标，当前 Control 实际为 1238 字节。额外额度只用于协调连续性和防漂移约束，不能吸收域任务。

### 23. Orca 存活 Owner 的无注入自动续派

- 最新实时终端核验显示，目标 Owner 同时满足 `running`、`connected=true`、`writable=true`、`agentIdentity=codex` 且 incarnation 未变，但 Orca `worker-start --terminal`/`dispatch --inject` 仍会分别报 `agent_unconfigured` 和 `no_agent_detected`。这是 detector 假阴性，不是 Owner 退出，也不是 Control 应手动释放/重开的条件。
- 所有 retained Owner continuation 统一改走独立路径：脚本核验精确 terminal handle/incarnation 与 connected/writable/Codex 身份，等待 `tui-idle`，通过公共 API 创建**不注入**的 dispatch，再用一次 `terminal send --enter` 提交 MATS 已生成的 compact continuation。随后仍以 `worker-show` 核验 task/dispatch/session/worktree 并生成 binding。
- compact continuation 包含逐字本轮 instruction、semantic delta、短角色契约、当前 task/dispatch 和 supervising Control session；明确沿用首次加载的 Orca 生命周期规则，禁止再次加载 `orchestration` 或 init prompt。脚本不请求 `--return-preamble`，避免生成后丢弃仍带来 I/O/token 风险。
- 自动路径不调用 `worker-release`、不 fresh、不要求 Control 查看源码、恢复 runtime view 或处理终端 ownership 标签。身份不一致才回到既有 fresh 恢复；dispatch/send 失败或回执不明确时保留 Owner 并停止，若 dispatch 已创建则明确禁止盲目重复派发。

### 24. `tui-idle` 假阴性与无人工作误阻断

- 实时现场同时证明：Run 的 82 个 worker 中 `nonsettled=[]`，目标 Owner terminal 为 connected/writable Codex 且停在输入提示符，`worktree ps` 对其精确 pane 返回 `state=done`；但 `terminal wait --for tui-idle` 仍稳定 timeout。旧续派把后者当唯一事实，错误返回 `OWNER_REBIND_NOT_IDLE`，Control 随后进入无事件的长等待。
- 续派现在先以 terminal show 固定 handle/incarnation/worktree/tab/leaf，再从 `worktree ps` 精确匹配同一 pane。唯一匹配的 Codex `state=done` 直接视为可续派，不调用失效 idle detector；working、缺失、重复、其他 pane 的 done 或截断视图均不能放行，只能通过原有有界 idle wait。
- 错误语义同步改为 `OWNER_REBIND_ACTIVITY_UNVERIFIED`，不再把“检测器无法证明”误报成“Owner 正在工作”。真实目标只读调用已返回 `same_terminal_done: true`；未发送任务、未关闭终端。

### 25. Orca 重启边界、nested receipt 与 continue init 回归

- 真实 p000076 已成功创建 native dispatch，但 `worker-show` 按当前 Orca schema 返回 `dispatch.id`；旧归一化器只读取顶层 `dispatchId`/`dispatch.dispatch_id`，在消息发送后误报缺失 `dispatch_id`。现在同时读取 start/show 的 nested `dispatch.id`，并拒绝多来源身份冲突。下次 continue 会先自动收养唯一同 Run/WP/packet/session/workspace 的未绑定 dispatch；若 multiline prompt 已停在 composer，只补一次 Enter，不再发送正文或新建 packet/task。
- Orca terminal handle 是 runtime-scoped routing metadata，不再作为持久 session 身份。旧 handle 失效时，脚本仅凭 binding 固定的 `incarnationId + worktreeId` 唯一匹配 connected/writable Codex terminal；零个或多个匹配均停止。Control provider session 与 Orca process incarnation 属于不同身份域，不互相比对。若 dispatch 回执跨 runtime 边界丢失，先以同一 task 只读恢复既有 dispatch；只有明确 stale handle 且 task 尚无 dispatch 时才在新 handle 上重试一次。
- 旧代码在安装版 Role Contract digest 更新时把同一 session 的 continuation 降级为完整 first-launch prompt；p000076 因而重复产生整份 init 内容。现在只要 native session 可证明，同 WP continue 永远保持 compact：当前 role recap 覆盖冲突的旧条款，逐字 instruction 与 semantic delta 保留；只有 session 缺失或不可证明才 fresh/full。

### 26. MATS 命令面清理与事务参数下沉

- 旧解析器累计 29 个功能命令，扁平目录会把初始化原语、Guard 分步、兼容入口和恢复动作同时暴露给 Control/worker，诱发读源码、试命令和手工维护 path/SHA/session/workspace。根帮助现在按 actor 只列 6 个 Control 主路径、2 个条件表单和 2 个 worker 短命令；恢复命令只可按结构化 `next_operation` 使用。
- 新 `activate` 一次完成 doctor 与当前 Control session 刷新，不启动 Orca，也不回显完整 doctor/status 或 control hash。新会话不会继续绑定旧 Control；未初始化仓库只返回 `bootstrap` 下一步。
- 新 `bootstrap` 只接受一个 `.task/tmp` UTF-8 用户目标和 milestone/project 语义名；当前 Orca Run、seed、inventory、目录、Control receipt 与 Planner request 全由脚本生成，并直接返回精确 Planner dispatch。模型不再执行 `milestone-paths -> bootstrap-init -> control` 手续。
- 新 packet 只注入 `deliver <packet-id>`；脚本从 immutable packet/binding 推导 digest、固定 draft、workspace、snapshot、refs/version/hash 并完成 Guard。Owner 的 `evidence <packet-id> <output> <inputs...>` 同样推导 workspace/digest。旧长命令仍仅为在途 packet 兼容。
- Owner/R1 的 `side-request-form` 从当前受管子 session 唯一反查 binding 与 caller session；模型不再复制 session ID。`dispatch -h` 只显示 role/WP/request/instruction/continue/cyber 等语义输入，worktree、CLI、retry digest、dry-run 等机械/恢复参数继续可执行但不进入常规提示。
- `issue`、`bind`、`preflight`、`directive` 被根 launcher 明确标为 private transaction primitive；`dispatchctl-help` 和旧 `spawn` 返回稳定 deprecated 错误。兼容解析仍留在脚本内部，避免升级时破坏已有 packet/session。
- `SKILL.md` 保持 4096 字节以内，完整 Role Contract、状态转换、Owner 连续性、工具故障停止、按需加载和防指令漂移规则未删；减少的是重复帮助、事务回显和模型可机械复现的参数。
- 当前确定性字节口径：Control 激活四份 authority 共 39,684 bytes（不含、也禁止重复加载 Orca full guide）；默认 Owner continuation 从 4,036 降至 3,717 bytes，Planner/R1/R2 首次 prompt 分别从 5,167/5,366/5,037 降至 4,903/5,144/4,772。Research/Engineering 首次 prompt 因新增精确 `evidence`/side-request 用法分别增加 43/46 bytes；这是用极小一次性增量换掉后续源码/help 探索，未伪装成净 token/费用测量。

### 27. 同一 Control session 更新契约时的 immutable ID collision

- 实时复现中的 `activate` 失败并非普通 artifact path/ID 解析错误。旧实现把不可变 Control receipt 固定命名为 `control-<session-id>`；Orca/Codex session 可以跨 Skill 更新存活，而更新后的 `control.md` 具有新的 `role_contract_digest`，同名 artifact 内容因此合法变化并被 `Records.put` 当成碰撞。
- Control receipt 改为完整 receipt 的 SHA-256 内容寻址 ID：`control-<receipt-digest>`。同 session、同契约的重复激活幂等返回同一引用；同 session、新契约生成新 artifact 并原子更新 `semantic.yaml.control_ref`。历史 `control-<session-id>` 文件和引用保持可读，不需要删除、覆盖或迁移。
- `_control` 现在还核对当前安装版 Control contract digest。Skill 已更新但当前 session 尚未执行 `activate` 时，任何受管动作会返回精确恢复指令，而不是沿用旧角色约束继续运行。
- 安装后已在原现场 session `01a0804d-eef8-7f12-a14c-8a0047972d05` 验证：旧 receipt SHA-256 保持 `2f0a94…a1828`，新引用为 `provenance/control-6d3b98…a060d.yaml`；随后 `advance --dry-run` 正常解析状态并返回 `OWNER_RESULT_NOT_CANDIDATE/NEEDS_DECISION`，不再出现 artifact collision。

### 28. continuation 停在输入框、静默等待与运行中调整

- 现场同时存在 `workerState=unsupervised` 与 Owner pane `state=done`，terminal preview 明确停留在 `› [Pasted Content 6825 chars]`。旧 `advance` 只看到不可变 binding 对应 active dispatch，直接返回等待；没有 completion 事件会产生，因此构成真实死锁而非 Owner 正在执行。
- compact continuation 现在只固定发送一次正文+Enter；launcher 随后读取一次精确 terminal preview，仅在明确出现 `[Pasted Content ...]` 时补一个空 Enter，绝不盲发第二条终端消息。若 renderer 更晚才留下已绑定 paste，下一次 `advance` 会从 exact binding/session/workspace 恢复，只补 Enter，返回 `OWNER_PROMPT_SUBMITTED` 后进入正常事件等待，不重复正文、不新建 packet/task/session。Windows wrapper 即使退出 1，只要结构化回执明确 `ok: true/accepted: true` 仍按成功处理，避免已生效发送被误入 adoption。
- `wait` 在进入 20 分钟原生阻塞前向 stderr 输出一条 YAML comment，明确这是无进度播报的事件驱动等待；阻塞期间禁止 heartbeat、轮询和重复状态 commentary，事件或 checkpoint 返回后才继续。
- 新增 `mats steer --wp <WP> --instructions <原文>`：仅当该 WP 恰有一个 active Research/Engineering Owner 时，把用户增量原文通过 Orca dispatch 定向消息持久转发，并带 supervising Control session；不写 packet、contract、hash 或新 session，也不占用 terminal composer。若该 dispatch 的原任务恰好仍 staged，`steer` 会先执行同一自动补提交。没有 active Owner 时继续使用 `dispatch --continue-owner`。
- 补 Enter 后现场又暴露出 lifecycle 缺口：非注入 dispatch 的 `capability_hash=null`，旧 compact recap 只给新 IDs，却要求沿用 first-launch lifecycle，Owner 因而正确拒绝使用旧凭据。新 recap 现在同时给出当前 Run/task/dispatch/Control identity、attested worker terminal，以及脚本生成的精确 question/`worker_done` 公共命令；旧 capability 明确作废，仍不加载 Orca full guide 或 init preamble。
- Orca 接受补发的 completion 后又显示 `dispatchStatus=completed`、`workerState=unsupervised`。后者描述可复用非注入 terminal，不是任务仍在运行；runtime view 改为有 `dispatchStatus` 时以它判定 active/settled，仅对旧 host 缺失该字段时回退 `workerState`。现场 dispatch 已从 active 正确归一化为 settled succeeded，terminal 继续 retained。

### 29. 非零 wrapper 假失败与过密 Owner continuation

- 最新现场 p000077 已正常执行，但 Owner 约一分钟内只做少量检查便把“实现还很大、本轮不能安全完成”作为 `failed` 交付。Control 又把该结果自己的 `decision_requested/unresolved` 当成继续授权，立即生成 p000078；两份 packet 的 semantic delta 都为空，第二轮仍重复约 5 KB 固定续接内容。这不是低 I/O，也不是 `advance` 授权的自动路由。
- Owner 首次与 continuation prompt 现在都明确：只要本地范围内仍可推进，就继续同一 inspect/edit/test turn；工作量大、多步骤或“本轮未完成”不是 `failed`/`worker_done` 检查点。`failed` 只用于穷尽可用工作后的具体外部、权限或工具终止阻塞。
- `OWNER_RESULT_NOT_CANDIDATE/NEEDS_DECISION` 明确停止自动推进。Owner 自己写入的 `decision_requested`、`unresolved` 或继续建议不是 Control 的新授权，Control 不得把它扩写成下一轮实现命令；只有已有计划权限覆盖的新用户/来源原文才能再次续接。
- continuation 的 role recap 从几乎整份角色合同缩为四类角色边界的固定短 recap；空 semantic delta 直接在正文标明，不再要求读取 delta 文件；重复的 Aux、schema、事务说明不再续轮注入。完整首次角色合同、逐字 instruction、Control session、delivery gate 和当前 lifecycle 命令仍保留，防漂移约束没有删掉。
- 原提交路径还存在独立的 Windows 回执 bug：`orca terminal send` 已返回 `ok: true/accepted: true` 并把文本放入 composer，但 wrapper 退出码为 1；旧 `_decode` 把它升级成异常，使 Control 进入 adoption。现在结构化成功回执优先，退出码只保留为诊断字段；launcher 不再无条件再发空 Enter，仅在精确 preview 明确 staged 时补一次。
- 当前确定性字节口径：正常 Control activation 为 40,044 bytes，基本空-delta continuation 为 2,066 bytes，附加当前原生 lifecycle route 后实际 terminal 文本为 2,813 bytes；均为 UTF-8 源字节而非 provider token/费用。实录中约 5.3 KB 的 p000078 还包含较长的 Control 自拟重复指令，新规则同时禁止该无授权续轮来源。

### 30. continuation 状态收敛与用户输入角色归属

- 最新现场出现四份相互矛盾的事实：旧 p000078 已创建 Orca `ctx_0e...`，却没有 MATS binding；终端实际输入已被用户清空，但 Orca preview 仍显示旧 `[Pasted Content ...]`；`advance` 只投影 bound dispatch，因而判断无人工作；新的 p000079 又因旧 native dispatch 占有同一终端而被拒。该状态不能靠继续读 preview、补 Enter 或新建 packet 修复。
- 正常续派删除“低层 dispatch -> terminal send -> preview/额外 Enter -> binding”链，统一为同终端原生 `worker-start`。MATS Task spec 仍只含逐字 instruction、内容寻址 delta、短角色/Control recap、gate 与 Control session；不重发 MATS init、完整 Role Contract 或完整 packet。Orca 原生 preamble只负责当前生命周期身份。
- 保障没有删除：Run/task/dispatch/session/worktree、connected/writable Codex identity、固定模型绑定和 Guard 仍逐项校验。若原生 `worker-start` 已提交而 binding 尚未落盘，下次从唯一 Task/worker-show 回执直接收养，不再次发送 prompt。旧版 `unsupervised/context_only` dispatch 返回 `TASK_MIGRATION_REQUIRED`；正常流程不 fence、不适配。`mats migrate` 只读列出目录/ref/hash问题并按需返回手工迁移手册。
- `advance` 不再维护 composer/paste/Enter 恢复分支；正常推进仍是原有单入口 `advance -> WAIT/READY/NEEDS_DECISION/BLOCKED/DONE`，completion、R0、R1/R2、source-backed repair、release 和 acceptance 链未拆散。
- 用户输入先判定接收角色。“继续/重试/检查目前进度或状态/Skill、工具、生命周期、session 诊断”默认发给 Control：Control 自己回答或执行 `advance`，不得原样塞进 `steer`/Owner instruction。只有具体产品修改、测试、证据/日志解释、域约束或明确点名 Owner 才是子任务输入。`OWNER_RESULT_NOT_CANDIDATE` 后用户授权继续时使用 `advance --resume-owner`，脚本引用精确旧结果，不转发用户的编排话术。
- 因此本次剪裁删除的是不可可靠观察的并行状态，不是防漂移信息或可审计门禁；短增量 prompt 与有界自动推进均保留。

### 31. v17.5 单一状态路径与显式手工迁移

- 正常流程移除旧 `init/control/bootstrap-init`、多步 bootstrap、事务参数版 delivery/evidence、显式 result/completion 文件和 ref-wrapper 输入；现行入口只接受当前结构的 ID、里程碑路径或脚本固定 staging。
- 同 Owner 续派只走原生同终端 `worker-start`；唯一已提交且受监督的同身份 dispatch 可被收养。旧 `unsupervised/context_only` dispatch 不再由正常流程自动 fence、补回车或转写状态，而是返回 `TASK_MIGRATION_REQUIRED`。
- `TASK_MIGRATION_REQUIRED` 只授权 STOP/向用户报告，不自动读取迁移材料。仅当用户明确要求迁移时，Control 才运行最后保底入口 `mats migrate`；该命令只读检查 `.task` 的 milestone 目录、固定文件名、内部 POSIX ref、字段与 YAML digest，不扫描或推断复杂产品目录。
- `mats migrate` 不移动、重命名、删锁、改 ref/hash 或操作 Orca session。仅在 `valid: false` 时返回按需加载的 `references/migration.md`。Control 备份后按稳定 issue code 逐项人工迁移，遇到归属/冲突不明确即停止。
- 新初始化和 Planner milestone 切换机械创建当前 milestone 根；全局 `config/directives/payloads/provenance/operations` 与 milestone typed records 保持单一读取规则。短增量 continuation、Control session recap、角色边界与 `advance -> WAIT/READY/NEEDS_DECISION/BLOCKED/DONE` 均保留。

### 32. v17.6 Codex session 唯一索引与自动重绑

- 现场 `ctx_66895ce14416` 的 Owner terminal 仍为 `connected=true/writable=true`，且绑定 session 与 terminal `incarnationId` 完全一致；Orca 却省略了 `agentIdentity`。旧 MATS 因附加 detector 字段缺失返回 `OWNER_REBIND_IDENTITY_UNVERIFIED`，属于错误拒绝。
- 绑定中的 Codex session ID 现在是 Owner 唯一持久索引。每次 continuation 都直接枚举绑定 workspace，在恰好一个 session 匹配上取当前 handle；旧 dispatch、handle、PTY、runtime epoch、`agentIdentity` 与 user-takeover 状态只作运行时元数据，不再参与身份判定。session 缺失才允许 fresh；枚举失败、重复、错 workspace 或不可写分别返回稳定错误。
- 当前 Orca 对复用终端可能返回合法 `unsupervised/context_only`。它不再被误判成旧版目录迁移。若相同 packet/Control session 的 native dispatch 已提交而 MATS 尚未 binding，恢复路径按 session 重绑、只补一个空 Enter、直接收养，不重发正文或创建第二份 Task。
- v17.6 曾优先 `worker-start --terminal` 并在 `agent_unconfigured` 时回退 `dispatch --inject`；现场继续出现 `no_agent_detected` 后，该路径已由下述 v17.7 方案取代。

### 33. v17.7 无识别依赖续接与孤儿 Task 自动对账

- 现场证明 session/handle 查找成功仍不足以恢复：Orca 可同时在终端清单中标记 `agentIdentity=codex`，却让同终端 `worker-start`/`dispatch --inject` 返回 `agent_unconfigured`/`no_agent_detected`。续接因此改为原生无注入 context Dispatch；MATS 自行发送一次短增量和精确 lifecycle route，再发送不带空 `--text` 的纯 Enter。
- `advance --resume-owner` 失败曾在每轮留下 ready Task/packet，而一个旧 `context_only` Dispatch 仍占用 Owner。新对账先按 Run/WP/Control session 与不可变 packet ID+digest 匹配：只 fence 已确认空闲且未执行的 stale context-only Dispatch，不关闭 Owner 终端；自动 settle 旧 ready 重试并复用最新精确 Task。精确任务已执行时只补 binding，不重发输入。
- 该修改不读取 Codex session 日志、不扫描 `.codex`、不猜终端标题或模型，也不把迁移变成恢复分支。Control 无需手工恢复 Orca handle、释放旧 Owner 或请求用户另开 worker。

### 34. v17.7 续接语义与运行中 Owner 唤醒

- 首次无注入续接虽然成功复用了 session，但旧 `--resume-owner` 只要求保留已有 findings/unknowns；Owner 可以只复述“仍需实现”便结束该 turn，而 dispatch 仍保持 active，Control 随后只能无限等待。现在恢复指令明确要求把当前 packet 下所有本地可执行项推进到实现、验证和候选，只有具体外部证据、权限或工具终止阻塞才能返回；禁止把未完成检查点当作交付。
- 旧 `steer` 只写入 Orca orchestration inbox，而 Owner 只有进入下一轮并主动 `check` 才能读到，不能解除空闲 active dispatch。现在 `steer` 从 binding 重新核验 run/task/dispatch、Codex session 和 workspace，按 session 找到当前 connected/writable handle，直接发送一份短调整并补纯 Enter；不创建 packet、Task 或新 session，也不重新注入 init/full Role Contract。
- 这条直接唤醒仍受角色/WP/外部变更边界约束；Control 层的“继续、状态、工具诊断”等输入仍不得转发给 Owner。它只解决已经判定为 Owner 产品输入的增量在 active dispatch 中无人读取的问题。

### 35. v17.8 context turn 无回执完成的自动续接

- 现场 `ctx_5a04e1a1a67d` 已被 Orca 明确标成 `dispatchStatus=completed`，Owner terminal/session 仍 connected、writable、retained。按 Control terminal 查询的 mailbox 为空，但 Run-scoped FIFO 实际已有稍后到达的 `worker_done`；因此 terminal-scoped 检查不能代表 Control 事件队列，真实事件必须优先且用户不应承担“worker 已结束”的通知职责。
- Control wait 现在可在 dispatch 后立即开始。脚本在同一个 20 分钟外层等待中，静默交替执行有界事件等待和 exact `worker-show`；只监视当前 plan/WP 下最新、未导入、与 current candidate/latest result 同一 Codex session 的 context-only Owner。它不读取 terminal transcript/title/composer，也不依赖实测不可靠的 `tui-idle`。
- completion probe 前后各做一次 Run-scoped mailbox peek；任何已排队或竞态到达的 `worker_done`/question/escalation 优先。Orca 的 peek 不带 `deliveryId`，所以脚本再用一次 blocking check 领取同一 FIFO batch 后才交给 staging。仅当 exact Dispatch completed 且第二次 peek 仍空时，才生成内部 `CONTEXT_TURN_COMPLETED_WITHOUT_EVENT`，由 `advance` 立即用 compact continuation 续接同一 session。该信号不是 candidate、blocked、failed、用户决策或新的 Planner occasion。
- fresh replacement、旧/错 session、非最新 packet、active/failed Dispatch、已导入 delivery 均不能触发自动续接；Owner 自己的 `--actor-packet` wait 保持纯事件路径。没有增加模型可调用的恢复参数、持久锁、手工状态文件或重复 init prompt。
- 安装后现场重放确认了竞态顺序：`wait --control` 先领取 `ctx_5a04...` 的真实事件并生成 staging，`advance` 完成导入/FIFO ack/tmp 清理后停在来源声明的 `OWNER_RESULT_NOT_CANDIDATE`，没有错误启动 no-event continuation。纯无事件分支由 exact Dispatch、session、新旧 packet 和导入状态的回归测试覆盖。

### 36. v1.0.0 非规范生命周期结束不再让 Control 傻等

- 现场最后一个 Owner 已经没有任何活动 Dispatch，但旧 `wait --control` 仍进入 20 分钟原生等待；这说明仅等待 Run mail 无法覆盖 worker 未规范发送 `worker_done` 的结束路径。已精确终止那一个孤立 wait 进程树，未关闭 Control、Owner、Orca 或产品进程，Control 随即恢复到确定性 `advance`。
- Control wait 现在先做一次非阻塞 Run-mail probe，再从 fresh runtime view 计算全部 active bound Dispatch。没有邮件也没有 active Dispatch 时直接返回当前 `advance` 状态；若状态显示仍有未导入的 settled binding，则立即返回 `BLOCKED/LIFECYCLE_DELIVERY_MISSING`，不再进入空等或要求用户再次唤醒。
- 真正阻塞时同时监视全部相关 active Dispatch。只有成功完成且属于最新 current same-session context continuation 的任务可自动续接；fresh/reviewer 以及 `failed`、`stopped`、`abandoned`、`cancelled` 的无交付结束均明确阻塞。若另一 Control 已在竞态中导入结果，则返回最新 `advance` 状态，不误报缺失，也不重复派发。
- actor-packet wait 仍是纯事件路径；20 分钟仍是实际阻塞后的 checkpoint。此次没有增加锁、手写状态、兼容分支或重复 init/Role Contract 注入。
- `p000083` 的原始终端与文件复核还定位出另一处表面矛盾：TSV 其实已被 `deliver` 正确识别；通用 “expected YAML” 来自 Owner 把普通 GNU `evidence.sha256` 放进 `evidence_manifest`，并把 `.task` 结果路径放进 domain `memo_evidence`。工具现在按实际内容区分普通文件与带 MATS marker 的 YAML bundle，普通 checksum 被单文件 pin，内部结果/评审被机械 materialize 为 `memo_source` ref；模型不写 hash，也不需手改 YAML。
- 生成表单现在直接列出 Owner status 闭集，并明确 native `succeeded` 只属于稍后的 `worker_done`，不能作为 `candidate` 的同义词。当前 p000083 同时含有 `status=succeeded` 与尚未清除的旧 unknown/decision，工具会精确拒绝该语义而不会擅自宣称候选；同一 Owner 必须按真实 exit conditions 修正语义，机械格式不再成为阻点。
- 现场还重放出纯 escalation delivery 未确认导致同一历史事件反复返回、`advance` 再次进入 WAIT 的独立缺口。`wait` 现在在捕获纯 question/escalation 批次后立即做一次 FIFO ack，并把事件只返回一次；任何含 `worker_done` 的批次仍保持 staged/unacked，直至全部结果导入和一次性角色释放成功，避免为了去重而吞掉候选。
- 同一现场随后证明：新 continuation `p000083` 已完成并发送 `worker_done`，但旧相关性判断仅比较 packet ref，错误地把它当成已被旧 blocked source 淘汰，`advance` 因而先返回旧 `OWNER_RESULT_NOT_CANDIDATE`。现在使用全局单调 packet ID 区分方向：早于或等于已导入 source 的尝试可忽略，晚于 source 的 continuation 必须先完成交付导入，不能被旧结果遮蔽。

### 37. v1.0.2 context-only Owner 释放回执归一化

- Orca 对受监督资源返回 `state=released`；但同 session 增量派发使用的 context-only Dispatch 是 `unsupervised`，不拥有预存终端。它结算后的合法 `worker-release` 回执是同一 `dispatchId`、`state=retained`、`reason=no_owned_resource`、`processAction=none`。旧 MATS 把该合法回执误判为未确认，导致已通过 R1/R2 的候选永远卡在 accept。
- native boundary 现在只接受上述四字段精确组合或正常 `released`；普通 retained、错 Dispatch ID 或可能执行了其他进程动作仍拒绝。确认后写入原有幂等 lifecycle 记录，runtime view 不再把已释放 MATS authority 的 settled Owner 投影成 writer。
- 接受结果区分 `owner_dispatch_released`、`owner_session_released` 与 `owner_terminal_retained`：context-only 情况完成 Dispatch 清理和验收，但如实保留用户/Control 预存终端，不虚报关闭 session。

### 38. v1.1.0 fresh prompt、跨角色 payload 与一次性问答优化

- 七类 child 的 fresh Task spec 均新增上限回归。完整首次 Role Contract、角色/WP 优先级、逐字 instructions、精确 packet/delivery 路径、远程证据规则、漂移恢复和机械交付门仍保留；删除的是同一规则在 authority、packet、Aux 小手册和结尾中的重复表述。Owner 的 Luna/evidence 入口改为按需 `-h`，不再内联长操作流程。
- Owner packet 的 project 只投影全局及当前 WP 相关 commitment；上游 accepted result 由脚本投影 summary、evidence paths、unknowns、impact、tags 和 source memo。不可变 `dependency_bindings` 仍供 Guard 校验，但其原始 result 路径明确不是模型 drill-down 输入，因此 60KiB 级 `snapshot_manifest`、binding/completion/hash 事务不会被下游重复读取。Reviewer candidate、Planner accepted delta、Luna/Synthesis source request 同样维持语义投影测试。
- Control 能从用户文本、控制状态或已验证语义摘要回答时直接回答，不产生 worker I/O，也不自行打开产品源码/原始日志重新取证。只有需要新增领域证据的纯问题才走 `mats query`：它通过 Codex session ID 复用 Research/Engineering Owner，只发送逐字问题和一个固定 answer 路径，不创建 packet、candidate、delivery form 或 fresh init；`mats answer` 校验并发送一条不完成原 Dispatch 的关联回执。每个 WP 同时只允许一个 pending query，相同问题重复调用为幂等；Control wait 核验、确认并清理 tmp 后返回 `OWNER_ANSWER_READY`，Control 必须直接回答用户，不能再次 query/continue。
- Fresh、普通 `dispatch --continue-owner` 与显式 steer 均明确要求以 `deliver` 和一次 `worker_done` 收束；所有七类 child role 的契约都声明终端自然语言不构成交付。只有脚本标记的 `MATS OWNER QUERY` 使用 answer 回执。这样既不会为一句问答生成候选事务，也不会因无规范回执而把同一问题再问一轮；答案与另一 worker_done 同批到达时延迟到该批结果导入后统一 ack，重放也不再次返回答案。

### 39. v1.2.0 Planner 到 Engineering 的接口决策无损传递

- Engineering WP 新增可选 `interface_specs`。它只用于必须跨 Planner/Owner 边界保真的架构接口，承载精确声明以及 invariant、lifecycle、compatibility、validation 义务；Planner 不写函数体，也不替代 Engineering 做普通局部设计。
- 每项接口显式标记 `required` 或 `advisory`。Engineering 对 required 项只能精确落实，确实不兼容时返回 `plan_conflict`；advisory 项允许基于证据调整，但不得改变 commitment 或 exit condition。
- Planner 的 bootstrap/full 与 runtime/patch TSV 均可往返这一结构。MATS 校验接口 ID 唯一、仅属于 Engineering WP、目标路径位于写 scope、basis path 为规范仓库相对路径；模型不手写 YAML、ref 或 hash。
- Owner/R1/R2 packet 通过 `work_package.interface_specs` 读取同一份声明，另附短小 binding policy，不复制接口正文。接口修改自动进入既有 WP contract digest、计划影响闭包和复审链，不增加状态机、锁、报告字段或迁移分支；旧计划保持合法。
- 新增角色文本保留自然、确定性的完整句子：Planner 1284 bytes，Engineering 1349 bytes，分别受 1400-byte 专属上限约束；其他 worker 仍为 1250 bytes，fresh init 总预算也未放宽，没有恢复重复 init prompt。

### 40. v1.3.0 二进制恢复事实的无损交接

- Planner 只定义逆向问题、证据和退出条件，不再把猜测的 ABI、数据布局、协议、状态机、关键执行链、算法或密码/安全行为写成 Engineering 接口。Research 通过可选 `recovered_specs` 交付结构化恢复事实，每项包含单一二进制 subject、稳定 locator、facts、validation、evidence 和 `confirmed|probable|hypothesis` 置信度。
- Research 仍可编写有界分析、探针和提取脚本；它不承担大型产品工程。接受后的 Research 结果由脚本直接投影到依赖 Engineering packet，避免 Astra/Research -> prose report -> Planner/Terra 二次转述造成的信息失真。
- 模型只填写语义路径和判断，不手写 SHA/version。finalizer 固定 subject/evidence 身份，Guard 校验实际文件、拒绝重复 ID，并禁止 Engineering 伪装成恢复事实的作者；R1 对 locator、fact、置信度和原始证据做独立复核。
- `recovered_specs` 是认识论证据，不自动成为项目需求。Engineering 在依赖 probable/hypothesis 前自行验证；只有独立、明确的项目决策才能把已接受事实提升为 `required interface_spec`。旧 result 不含该可选字段时完全不变，无需目录或 schema 迁移。
- 为保留自然、确定性的角色边界说明，Research/Planner/Engineering 正文实测为 1407/1507/1554 bytes，统一受 1600-byte 上限约束；其他角色、状态机、continue 增量路径和一次性交付约束不变。fresh init 实测为 4355/4205/4505 字符，各自预算仅增加 100 bytes，不恢复重复说明。

## 验证口径

- Skill Creator `quick_validate.py`：通过。
- 完整测试集合：402 项（400 个核心测试：`test_spawn.py` 198 项、其余模块 202 项；另有 2 个独立协议不变量）。新增覆盖七类 child prompt 预算/机械交付声明、跨 WP commitment 与 accepted-result 语义投影、Owner 问答单发/幂等/固定答案、纯答案立即 ack、答案与 worker_done 混合批次延迟 ack 及重放去重、steer 交付提醒、`interface_specs` 的旧计划兼容/角色/路径/ID Guard/full+patch TSV 往返/packet 单份投影/required-advisory 语义，以及 `recovered_specs` 的 Research-only 作者约束、TSV 往返、证据固定、重复 ID 拒绝和下游无 hash 无损投影；并保留无 active 即返、未交付 settled 阻塞、导入竞态、非阻塞 mail probe、事务 materialize、status/lifecycle 分离和 context-only 释放覆盖。
- Windows 用户安装/强制替换/隔离运行测试：通过；额外覆盖含空格路径和 unmanaged interpreter 拒绝。
- 回归覆盖：所有 role finalizer、Planner 嵌套 `scope.refs` 自动 pin、无授权只读证据自动 pin/产品快照隔离/稳定性、详细 oneOf 诊断、local evidence steer、错误事务字段覆盖、同 packet 多 retry binding、evidence manifest、模型投影、bootstrap-init、自动 Control receipt/runtime view/workspace/access、Orca 单次启动恢复、`.task` snapshot 排除、host mode 差异、单 OS mutex、GBK/UTF-8 输出、daybreak-blue 回退、Owner continuity 和小任务权限边界。

这轮没有把角色/路由约束删成“轻提示”。压缩的是重复加载、私有实现、原生回执和可机械重建的事务字段；防角色漂移的 Role Contract、状态表、委派条件、恢复锚点、同 WP Owner 连续性和 Guard 语义门仍然保留。
