# MATS v17.4：漂移与 I/O 税检查记录

## 检查范围

输入归档：multi-agent-task-split-v17.4.rar
SHA-256：3e2f947946b80ba097e1668f7049bd92545ea117cbff9fff4f5fd645a25c5ace

本次进行源码检查、临时 Git 仓库中的本地模拟、8 个既有定向测试，以及 2 个新增协议不变量回归测试。没有运行真实 Orca，没有启动真实模型，没有测量 provider token/账单，没有验证 Windows 实机行为。原始归档和 skill 源码未修改。

曾尝试运行四组离线测试，运行被工具的 60 秒执行时限终止，没有形成完整测试汇总；因此不能据此宣称全量回归通过。随后单独完成了 8 个相关既有测试，全部通过。新增两项测试在未修改的 v17.4 上都失败，分别对应下述缺陷。

## 已复现问题 1：被拒绝的 packet retry 覆盖已有交付草稿

定位：scripts/role_spawn.py:283–284，320–323，345–363。

交付草稿的 atomic_write 先于 preflight。使用已有 binding、但没有 native-confirmed failed 证据的 packet 发起 retry 时，Guard 正确拒绝重试，且没有创建/启动 native task；然而已有草稿已经被重新生成的 TSV 覆盖。

实测：rejected=true；original_draft_preserved=false；native_task_create_calls=0；native_start_calls=0。

建议不变量：拒绝操作不得改写现有执行尝试的草稿、业务产物或权威状态；审计记录可单独追加。先验证并预留操作，再初始化该次尝试的交付。并发下还要确保前置验证与提交之间的版本/预留有效，不能只机械地移动一行代码。

## 已复现问题 2：同批 worker_done 只释放最后一个 one-shot

定位：scripts/dispatchctl.py:182–190；scripts/guards.py:686–702。

同一个 native delivery batch 放入两个不同 WP 的 R1 完成事件，依次调用 result。第一个导入时 batch 尚不完整，因此不释放；最后一个导入时 batch 完整，但只释放当前 binding。随后整批被 acknowledge，全部 completion staging 与 delivery 草稿被删除。

本地模拟：R1 dispatch IDs = D7、D15；release 调用仅包含 D15；ack 调用一次；整批 staging 已清除。真实 native API 为 mock，结论是 MATS 该分支遗漏了对前一个 reviewer 的 release 调用，并非声称观测了线上 Orca 的资源泄漏。

建议不变量：逐 dispatch 记录 imported / release_required / released；只有整个 batch 的结果均已导入、所有 one-shot 的 release 均确认成功、其他事件也已处理，才 acknowledge 并清理。Owner 不属于 one-shot，不应在此被提前释放。已完成状态必须在重放/重试时仍可查询，不能靠临时文件存在性代替去重账本。

## 如何运行新增回归测试

将 test_protocol_invariants.py 复制到原仓库 tests/ 目录，在项目已有测试环境中运行：

```sh
python -m unittest discover -s tests -p test_protocol_invariants.py -v
```

两个测试在当前 v17.4 上预期失败；修复后应通过。这是回归测试，不是修复补丁。

## 架构改造建议

核心方向：正常状态推进由确定性 kernel 完成，Control 仅在语义决策、授权问题、无法机械恢复的异常处介入。保留已有 Owner、Planner、R1/R2 的判断与验收职责，不为节约 I/O 绕过评审。

可新增（目前未实现）advance/decide 接口。advance 消费原生事件、导入结果、执行 R0、按现有规则派发 review、检查接受条件、释放对应 Owner 并再次 guarded accept；遇到语义或授权节点时返回结构化 decision request。控制程序、文档与测试应来自同一份状态转移规范，避免 Markdown 与 Python 各维护一份流程。

错误与恢复使用稳定 code、state_revision、decision_id、allowed_actions、evidence_refs，而非依赖错误原文匹配。模型动作仍需重新验证权限、当前版本和允许动作。外部副作用以持久化 operation ID、状态日志和可验证原生回执做恢复；不能假定原子文件写入能提供跨原生调用的事务。

## I/O 静态观察

1. Control 激活必读文件合计 37,962 UTF-8 字节；首次 state/path 操作加载 storage 后合计 44,931 字节。这是源码字节，不是模型 token 或费用。
2. packets.py:176–193 的 packet_limits 约束的是 encode 后 envelope 字节。required_payload_refs 在 hydrate 时会重新加载，外置不是自动降低模型实际输入。
3. records.py:175–183 的 all(folder) 每个 YAML 调用 load 两次。next_index 通过 all 扫全量记录；多个 Guard 路径又重复扫描 bindings/results。可先单次解析、事务内缓存，再做可重建索引。
4. role_spawn.py:345–414 的锁内包含 runtime view、native task-create/start/show 等操作。缩短锁需要先设计持久化 admission reservation 和版本/fencing 校验，不能直接移除锁。
5. 现有 continuation delta、紧凑回执、语义 TSV、evidence-manifest 值得保留。下一步减少正常路径的模型唤醒次数，而非进一步缩写字段名称。
6. Guards 文档声明调用者是可信 coordinator；自然语言禁令、路径/hash 验证不等于 host 工具权限隔离。进一步强化需由宿主/工具 broker 限定角色允许的动作与写路径。

## 建议验收指标

在同一任务集、同一证据、同一验收标准下比较：成功验收的总费用、Control 唤醒次数、非缓存/缓存输入与输出、重复读取字节、Planner 修复次数、危险动作违规率、漏接收/漏释放事件、P50/P95 完成时延。统计失败与修复成本，不能只统计成功路径。模型费用以 provider 观测为准，静态文件字节不能再加到账单上。

## 文件说明

- test_protocol_invariants.py：可加入原仓库的两项新增回归测试。
- new_invariant_tests.txt：当前版本两项不变量失败的实测日志。
- targeted_suite.txt / targeted_suite_summary.json：8 项既有测试通过记录。
- probe_retry_result.json / probe_batch_result.json：本地模拟结果。
- source_excerpts.md：带原始行号的关键源码与契约摘录。
- context_bytes.json：必读文档字节数。
