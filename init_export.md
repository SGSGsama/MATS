# Codex conversation

## User

加载 $multi-agent-task-split

## User

加载 $multi-agent-task-split

## Assistant

我会按 `$multi-agent-task-split` 的激活流程加载该技能：先读取其完整 [`SKILL.md`](http://SKILL.md) 及规定的控制、工作流、路由、策略和存储说明；仅完成加载，不会擅自派发子任务。

## Activity

    $ "C:\\Program Files\\Git\\usr\\bin\\bash.exe" -c "pwd; printf '%s\\n' '--- [SKILL.md](http://SKILL.md) ---'; cat 'C:/Users/SGSG/.codex/skills/multi-agent-task-split/[SKILL.md](http://SKILL.md)'; printf '%s\\n' '--- files ---'; find 'C:/Users/SGSG/.codex/skills/multi-agent-task-split' -maxdepth 3 -type f | sort"

    status: Completed · exit 0

      D:/meituan_re_by_codex

      --- [SKILL.md](http://SKILL.md) ---

      ---

      name: multi-agent-task-split

      description: Managed task decomposition/role dispatch over native Orca.

      ---



      # Multi-Agent Task Split v17.4



      ## Activate



      Only explicit activation counts. Root Control=Luna/max. Before action read verbatim `references/roles/[control.md](http://control.md)`, `references/[workflow.md](http://workflow.md)`, `references/[routing.md](http://routing.md)`, `config/policy.yaml`. Read [`storage.md`](http://storage.md) for state/path work. Read [`native-boundary.md`](http://native-boundary.md) + `orca skills get orchestration --full` only for native lifecycle/identity/recovery/CLI anomalies. Never replace these authorities with a summary. Control only coordinates.



      ## Runtime



      Use only `bin/mats` (POSIX) or `bin\mats.cmd` (Windows); both isolate the Skill-local `.venv`. Missing runtime -&gt; `MATS_NOT_INSTALLED`; installation/repair is outside model authority. Never call uv, pip, py.exe or other Python.



      ## Dispatch / wait



      Every child uses MATS `dispatch`; never hand-write managed native launch, supply model/effort or translate receipts. Dispatch resolves policy binding, injects Role Contract/reread/runtime paths and verifies the receipt. Owners may request bounded read-only Luna Aux through it; if nesting is blocked, Control runs the unchanged request. `--repo` works before/after the subcommand.



      MATS controls decomposition, fixed authority roles, WP ownership/scope, assignment/reassignment and review routing. A WP `specialty` may name any domain persona but grants no authority and never selects model/effort. Domain skills control methods/artifacts inside the packet; they cannot change authority, scope, workers or acceptance. On conflict, follow MATS orchestration.



      Free-form terminal delivery uses `native-send` and submits once. Control waits with `wait --control`; Owners use the injected `wait --actor-packet ...`. Each wait returns a resume anchor. Default/minimum is 20 minutes; timeout is checkpoint, never failure or permission to drift/poll.



      ## State and semantics



      `.task/` is the repo-local control root; bootstrap files stay under `.task/bootstrap/<id>/`. Internal refs use POSIX `/`; host paths stay adapter-only.



      Orca owns native lifecycle; MATS owns roles/contracts/evidence/routing/acceptance. `worker_done` != acceptance. `.task/semantic.yaml` is current state; Planner history is audit/write protocol only.



      Bindings: Control/Luna Aux=Luna max; Research/Engineering/R1=Terra high; Synthesis/R2=Sol high; Planner=Astra xhigh. Control marks cybersecurity work (e.g. vulnerability analysis/reverse engineering) with `dispatch -cyber`; Sol-bound roles then use daybreak-blue at the same effort, falling back once to Sol only on explicit model-unavailable response. No difficulty routing or in-flight effort change.



      No managed state -&gt; bootstrap before owners. Planner packets carry Guard-generated contract checklists. Rejected Planner output is preserved; unchanged-base repair is generated mechanically and uses one fresh Planner. Never reset/archive `.task` to bypass Guard. Bootstrap is consumed only after successful apply; runtime planning is patch-only.



      Candidate -&gt; R0 -&gt; fresh R1 -&gt; required R2 -&gt; guarded accept. Only accepted dependencies unlock downstream work. Preserve raw directives/source memos, stable commitments, exact candidate identity and explicit side-result consumption. Domain/third-party skills are methodology only.

      --- files ---

      C:/Users/SGSG/.codex/skills/multi-agent-task-split/.venv/Scripts/Activate.ps1

      C:/Users/SGSG/.codex/skills/multi-agent-task-split/.venv/Scripts/activate

      C:/Users/SGSG/.codex/skills/multi-agent-task-split/.venv/Scripts/activate.bat

      C:/Users/SGSG/.codex/skills/multi-agent-task-split/.venv/Scripts/[activate.fish](http://activate.fish)

      C:/Users/SGSG/.codex/skills/multi-agent-task-split/.venv/Scripts/deactivate.bat

      C:/Users/SGSG/.codex/skills/multi-agent-task-split/.venv/Scripts/pip.exe

      C:/Users/SGSG/.codex/skills/multi-agent-task-split/.venv/Scripts/pip3.14.exe

      C:/Users/SGSG/.codex/skills/multi-agent-task-split/.venv/Scripts/pip3.exe

      C:/Users/SGSG/.codex/skills/multi-agent-task-split/.venv/Scripts/python.exe

      C:/Users/SGSG/.codex/skills/multi-agent-task-split/.venv/Scripts/pythonw.exe

      C:/Users/SGSG/.codex/skills/multi-agent-task-split/.venv/pyvenv.cfg

      C:/Users/SGSG/.codex/skills/multi-agent-task-split/[SKILL.md](http://SKILL.md)

      C:/Users/SGSG/.codex/skills/multi-agent-task-split/agents/openai.yaml

      C:/Users/SGSG/.codex/skills/multi-agent-task-split/bin/mats

      C:/Users/SGSG/.codex/skills/multi-agent-task-split/bin/mats.cmd

      C:/Users/SGSG/.codex/skills/multi-agent-task-split/config/operator-defaults.yaml

      C:/Users/SGSG/.codex/skills/multi-agent-task-split/config/policy.yaml

      C:/Users/SGSG/.codex/skills/multi-agent-task-split/references/[native-boundary.md](http://native-boundary.md)

      C:/Users/SGSG/.codex/skills/multi-agent-task-split/references/roles/[control.md](http://control.md)

      C:/Users/SGSG/.codex/skills/multi-agent-task-split/references/roles/[engineering.md](http://engineering.md)

      C:/Users/SGSG/.codex/skills/multi-agent-task-split/references/roles/luna_[aux.md](http://aux.md)

      C:/Users/SGSG/.codex/skills/multi-agent-task-split/references/roles/[planner.md](http://planner.md)

      C:/Users/SGSG/.codex/skills/multi-agent-task-split/references/roles/[research.md](http://research.md)

      C:/Users/SGSG/.codex/skills/multi-agent-task-split/references/roles/review_[r1.md](http://r1.md)

      C:/Users/SGSG/.codex/skills/multi-agent-task-split/references/roles/review_[r2.md](http://r2.md)

      C:/Users/SGSG/.codex/skills/multi-agent-task-split/references/roles/[synthesis.md](http://synthesis.md)

      C:/Users/SGSG/.codex/skills/multi-agent-task-split/references/[routing.md](http://routing.md)

      C:/Users/SGSG/.codex/skills/multi-agent-task-split/references/[storage.md](http://storage.md)

      C:/Users/SGSG/.codex/skills/multi-agent-task-split/references/[workflow.md](http://workflow.md)

      C:/Users/SGSG/.codex/skills/multi-agent-task-split/schemas/contracts.schema.yaml

      C:/Users/SGSG/.codex/skills/multi-agent-task-split/scripts/[common.py](http://common.py)

      C:/Users/SGSG/.codex/skills/multi-agent-task-split/scripts/[contracts.py](http://contracts.py)

      C:/Users/SGSG/.codex/skills/multi-agent-task-split/scripts/[dispatchctl.py](http://dispatchctl.py)

      C:/Users/SGSG/.codex/skills/multi-agent-task-split/scripts/[guards.py](http://guards.py)

      C:/Users/SGSG/.codex/skills/multi-agent-task-split/scripts/[mats.py](http://mats.py)

      C:/Users/SGSG/.codex/skills/multi-agent-task-split/scripts/[minischema.py](http://minischema.py)

      C:/Users/SGSG/.codex/skills/multi-agent-task-split/scripts/native_[orca.py](http://orca.py)

      C:/Users/SGSG/.codex/skills/multi-agent-task-split/scripts/[packets.py](http://packets.py)

      C:/Users/SGSG/.codex/skills/multi-agent-task-split/scripts/[records.py](http://records.py)

      C:/Users/SGSG/.codex/skills/multi-agent-task-split/scripts/role_[spawn.py](http://spawn.py)

      C:/Users/SGSG/.codex/skills/multi-agent-task-split/scripts/[routing.py](http://routing.py)

      C:/Users/SGSG/.codex/skills/multi-agent-task-split/scripts/[verification.py](http://verification.py)

## Activity

    $ "C:\\Program Files\\Git\\usr\\bin\\bash.exe" -c "printf '%s\\n' '--- references/roles/[control.md](http://control.md) ---'; cat 'C:/Users/SGSG/.codex/skills/multi-agent-task-split/references/roles/[control.md](http://control.md)'; printf '%s\\n' '--- references/[workflow.md](http://workflow.md) ---'; cat 'C:/Users/SGSG/.codex/skills/multi-agent-task-split/references/[workflow.md](http://workflow.md)'; printf '%s\\n' '--- references/[routing.md](http://routing.md) ---'; cat 'C:/Users/SGSG/.codex/skills/multi-agent-task-split/references/[routing.md](http://routing.md)'; printf '%s\\n' '--- config/policy.yaml ---'; cat 'C:/Users/SGSG/.codex/skills/multi-agent-task-split/config/policy.yaml'; printf '%s\\n' '--- references/[storage.md](http://storage.md) ---'; cat 'C:/Users/SGSG/.codex/skills/multi-agent-task-split/references/[storage.md](http://storage.md)'"

    status: Completed · exit 0

      # Storage and materialized state



      `.task/` is the **only repository-local control-plane root**. Source code, build outputs, logs, traces, decompiler output and other domain evidence stay outside `.task`; `.task` stores orchestration/semantic documents and refs only.



      ## Canonical layout



      Separate files are allowed and often useful. They do **not** need to be collapsed into one document; they only need to stay under `.task/`:



      ```text

      .task/

        semantic.yaml                 # one materialized current semantic view

        operator.yaml                 # mutable operator caps, not semantics

        bootstrap/&lt;id&gt;/

          project.yaml                # bootstrap staging/draft/returned full project as applicable

          plan.yaml                   # bootstrap staging/draft/returned coarse plan as applicable

          planning-request.yaml

          inventory.yaml

          planner-result.yaml

          ...                         # other bootstrap control artifacts

        config/

        provenance/

        directives/

        requests/

        packets/

        payloads/

        bindings/

        results/

        r0/

        reviews/

      ```



      A bootstrap file outside `.task/` is invalid control-plane placement. `bin/mats bootstrap-paths <id>` creates/prints the canonical bootstrap directory and standard file locations. `init` accepts bootstrap project/plan only from `.task/bootstrap/...`.



      ## Current view vs history



      `.task/semantic.yaml` is the **single materialized current semantic view**. It contains the current project model, current plan, pinned semantic/model-policy ref, current candidates, source refs, acceptances, invalidation fences, native Run provenance and the last applied planning anchor. It contains no native process lifecycle truth.



      Bootstrap may keep separate `project.yaml` and `plan.yaml` artifacts in its bootstrap folder. They are staging/provenance, not a second current-state authority. After bootstrap apply, normal roles read `semantic.yaml` or packet slices derived from it.



      Runtime Planner calls return sparse patches. The semantic guard validates a patch, materializes the complete target project/plan, computes impact, then atomically replaces `.task/semantic.yaml`. No role replays historical Planner patches to reconstruct current state.



      ## Canonical logical paths



      All semantic/internal refs use `/` POSIX separators even on Windows. Example: `packets/WP17.yaml`, never `packets\\WP17.yaml`. Filesystem adapters convert host `Path.relative_to()` parts to a POSIX logical ref **before** schema/path validation. Windows drive letters, UNC roots and backslashes never enter an internal ref.



      Absolute/native workspace paths may appear only in native receipts/runtime views where the schema explicitly represents a host filesystem location. They are not internal refs.



      ## Writes and locks



      Semantic writes use a short cross-platform local file lock plus file fsync and atomic replace/create. POSIX uses `flock`; Windows uses `msvcrt.locking`. Directory fsync is best-effort on hosts that expose it. The lock is admission/commit serialization only: never a lease, heartbeat or worker-liveness authority.



      `.task/operator.yaml` is a separate mutable operator-control document. Cap changes do not change project/WP semantic digests.

## Assistant

技能的完整说明和激活所需的权威文件已读取。根据其工作流要求，我现在仅运行一次 `bin/mats doctor` 做运行时自检；这不会创建或修改分析任务。

## Activity

    $ "C:\\Program Files\\Git\\usr\\bin\\bash.exe" -c "'C:/Users/SGSG/.codex/skills/multi-agent-task-split/bin/mats' --repo 'D:/meituan_re_by_codex' doctor"

    status: Completed · exit 0

      isolated_runtime: true

      jsonschema_external_required: false

      live_orca_verified: false

      model_calls: 0

      note: Binary presence is not runtime/model/permission verification. No live launch is made.

      operator_defaults_valid: true

      orca_executable: C:\Users\SGSG\AppData\Local\Programs\orca\resources\bin\orca.EXE

      policy_valid: true

      python: C:\Users\SGSG\.codex\skills\multi-agent-task-split\.venv\Scripts\python.exe

      schema_version: 9

      skill_release: '17.4'

      skill_version: 17

      yaml_module: C:\Users\SGSG\.codex\skills\multi-agent-task-split\.venv\Lib\site-packages\yaml\__init__.py

## Assistant

已加载并激活 `$multi-agent-task-split`。

- 已读取完整技能说明及必需权威文件。

- 已运行 `bin/mats doctor`，检查通过。

- 当前作为 Root Control，仅完成加载和自检；未派发子任务、未修改 `.task` 或其他项目文件。
