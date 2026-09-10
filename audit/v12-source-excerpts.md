# Input implementation excerpts

These are from the user-supplied v12 ZIP, not a live Orca runtime.

## v12 policy.py:20-40

```text
20:               "packet_max_bytes","result_max_bytes","max_project_tokens","max_project_cost_microusd","capability_ttl_seconds"}
21:     require_fields(p["limits"],required)
22:     if any(type(v) is not int or v<=0 for v in p["limits"].values()): raise Rejected("limits must be positive integers")
23:     # This implementation deliberately avoids shared-worktree writer races.
24:     if p["limits"]["max_owner_inflight"]!=1: raise Rejected("reference runtime permits one owner writer; parallel worktree adapter required")
25:     if not isinstance(p["checks"],dict): raise Rejected("checks must be an approved mapping")
26:     if not isinstance(p["evidence_roots"],list) or not all(isinstance(x,str) for x in p["evidence_roots"]): raise Rejected("invalid evidence_roots")
27:     if not isinstance(p["structural_paths"],list) or not all(isinstance(x,str) for x in p["structural_paths"]): raise Rejected("invalid structural_paths")
28:
29:
30: def capability_check(policy: dict, caps: dict, now: int, role: str) -> None:
31:     require_fields(caps,{"schema_version","verified_at","source","simulation","features","models"})
32:     if type(caps["simulation"]) is not bool or not isinstance(caps["features"],dict) or not isinstance(caps["models"],dict): raise Rejected("invalid capability field types")
33:     if caps["schema_version"]!=7 or type(caps["verified_at"]) is not int: raise Rejected("invalid capability manifest")
34:     age=now-caps["verified_at"]
35:     if age<0 or age>policy["limits"]["capability_ttl_seconds"]: raise Rejected("expired/future capability manifest")
36:     if not isinstance(caps["source"],str) or not caps["source"]: raise Rejected("capability source required")
37:     needed={"idempotent_dispatch","session_identity","isolated_review_context","permissions_enforced","aggregate_limits_enforced","cancellation_reconciliation"}
38:     if any(caps["features"].get(x) is not True for x in needed): raise Rejected("adapter lacks required capability")
39:     binding=policy["bindings"][role]; model=caps["models"].get(binding["model"],{})
40:     if model.get("available") is not True or binding["reasoning_effort"] not in model.get("efforts",[]):
```

## v12 kernel.py:180-208

```text
180:             if request["reason"]=="project_steer" and not request["directive_ids"]: raise Rejected("project steer requires raw directives")
181:             if request["reason"]=="plan_conflict":
182:                 if rec is None or rec["status"]!="plan_conflict": raise Rejected("missing source plan_conflict")
183:                 src=self.store.get(rec["latest_result_digest"])["result"]["source_memo"]
184:                 if digest(src)!=digest(request["source_memo"]): raise Rejected("scheduler rewrote the source memo")
185:             role="planner"
186:         else: raise Rejected("unknown operation; model/effort overrides are forbidden")
187:         capability_check(policy,s["capabilities"],now,role)
188:         if s["circuits"].get(role,0)>=limits["circuit_threshold"]: raise Rejected("role circuit open")
189:         if now<s.get("retry_after",{}).get(role,0): raise Rejected("role backoff is active")
190:         t,c=self._account(s);reservation=a["reservation"]
191:         if t+reservation["total_tokens"]>limits["max_project_tokens"] or c+reservation["cost_microusd"]>limits["max_project_cost_microusd"]:
192:             raise Rejected("project budget admission denied; do not reduce review quality")
193:         op={"id":a["dispatch_id"],"role":role,"wp_id":wp["id"] if wp else None,"status":"prepared",
194:             "binding":copy.deepcopy(policy["bindings"][role]),"plan_version":s["plan"]["version"],
195:             "contract_digest":digest(wp if wp else {"project":s["project"],"plan":s["plan"]}),
196:             "created_revision":s["revision"]+1,"prepared_at":now,"lease_until":now+limits["lease_seconds"],"deadline":now+limits["max_wall_seconds"],
197:             "reservation":reservation,"usage":None,"request":request,
198:             "permissions":{"write_paths":wp["scope"]["paths"] if role in OWNERS else [],
199:                            "control_plane_write":False,"spawn_children":False}}
200:         if operation=="synthesis":op["synthesis_fingerprint"]=fp
201:         op["packet_digest"]=build(self.store,s,op,request,wp)
202:         s["operations"][op["id"]]=op
203:         if operation=="owner":
204:             rec["status"]="running";rec["attempts"]+=1;rec["active_owner"]=op["id"]
205:         return {"dispatch_id":op["id"],"packet_digest":op["packet_digest"],"binding":op["binding"],
206:                 "simulation":s["simulation"],"status":"prepared"}
207:
208:     def _ack(self,s,a,now):
```

## v12 kernel.py:240-251

```text
240:     def _complete(self,s,a,now):
241:         self._fields(a,{"dispatch_id","session_id","packet_digest","result"})
242:         op=self._op(s,a);self._identity(op,a)
243:         if op["status"]!="running" or now>op["lease_until"] or s["mode"]=="cancelled": raise Rejected("late/inactive completion")
244:         if op["plan_version"]!=s["plan"]["version"]: raise Rejected("completion from obsolete plan")
245:         result=a["result"]
246:         if len(encode(result))>s["policy"]["limits"]["result_max_bytes"]: raise Rejected("result too large; source must scope explicitly")
247:         role=op["role"];wp=rec=None
248:         if op["wp_id"]:wp,rec=self._wp(s,op["wp_id"])
249:         if wp and digest(wp)!=op["contract_digest"]: raise Rejected("WP contract changed")
250:         if role in {"luna_aux","synthesis"}:
251:             verify_evidence(self.store.repo,op["request"]["evidence"],s["policy"]["evidence_roots"])
```

## v12 kernel.py:427-475

```text
427:         if any(o["status"]=="cancel_requested" for o in s["operations"].values()):raise Rejected("remote sessions not yet reconciled")
428:         s["mode"]="open";return {"mode":"open"}
429:
430:     def _directive(self,s,a,now):
431:         self._fields(a,{"directive_id","raw_text","intent"});identifier(a["directive_id"])
432:         if a["directive_id"] in s["directives"]:raise Rejected("directive immutable")
433:         if not isinstance(a["raw_text"],str) or not a["raw_text"].strip() or len(a["raw_text"].encode())>12000:raise Rejected("invalid/oversized directive")
434:         if a["intent"] not in {"status","technical_query","local_steer","project_steer","unknown"}:raise Rejected("invalid intent")
435:         # Unknown free text is preserved, not guessed into a local mutation.
436:         intent="project_steer" if a["intent"]=="unknown" else a["intent"]
437:         s["directives"][a["directive_id"]]={"directive_id":a["directive_id"],"raw_text":a["raw_text"],"intent":intent,"recorded_at":now}
438:         return {"intent":intent,"requires_planner":intent=="project_steer"}
439:
440:     def _apply_plan(self,s,a,now):
441:         self._fields(a,{"dispatch_id"});op=self._op(s,a)
442:         if s["mode"]=="cancelled" or op["role"]!="planner" or op["status"]!="completed" or op.get("applied"):raise Rejected("completed unapplied Planner receipt required")
443:         if any(o["status"] in ACTIVE for o in s["operations"].values()):raise Rejected("drain all operations before replacing contracts")
444:         proposal=self.store.get(op["result_digest"]);validate("planner_result",proposal)
445:         if proposal["base_plan_version"]!=s["plan"]["version"] or op["plan_version"]!=s["plan"]["version"]:raise Rejected("stale Planner proposal")
446:         project,plan=proposal["project"],proposal["plan"]
447:         validate("project",project);validate("plan",plan)
448:         if project["project_id"]!=s["project"]["project_id"] or plan["project_id"]!=project["project_id"] or plan["plan_id"]!=s["plan"]["plan_id"]:raise Rejected("project/plan identity immutable")
449:         if plan["version"]!=s["plan"]["version"]+1:raise Rejected("plan version must advance by one")
450:         old={w["id"]:w for w in s["plan"]["work_packages"]};new={w["id"]:w for w in plan["work_packages"]}
451:         invalid=set(proposal["invalidate_completed"])
452:         if not invalid.issubset(old):raise Rejected("unknown invalidation target")
453:         changed={wid for wid in old if wid not in new or digest(old[wid])!=digest(new[wid])}|invalid
454:         if any(project[k]!=s["project"][k] for k in ("goal","commitments","boundaries")):changed|=set(old)
455:         # Descendants of changed accepted facts must also be explicitly invalidated.
456:         while True:
457:             more={wid for wid,w in {**old,**new}.items() if set(w["dependencies"]) & changed}
458:             if more<=changed:break
459:             changed|=more
460:         affected_done={wid for wid in changed if s["work_packages"].get(wid,{}).get("status")=="done"}
461:         if not affected_done<=invalid:raise Rejected("completed contract/downstream change needs explicit invalidation closure")
462:         for w in new.values():
463:             if any(k not in s["policy"]["checks"] for k in w["required_checks"]):raise Rejected("Planner cannot add unapproved executable checks")
464:         records={}
465:         for wid,w in new.items():
466:             prev=s["work_packages"].get(wid,{"attempts":0})
467:             if prev.get("status")=="done" and wid not in changed:records[wid]=prev
468:             else:
469:                 records[wid]={"status":"pending","attempts":prev.get("attempts",0),"reviews":{}}
470:                 if prev.get("base_commit"):records[wid]["base_commit"]=prev["base_commit"]
471:         s["project"]=project;s["plan"]=plan;s["work_packages"]=records;op["applied"]=True
472:         self._ready(s);return {"plan_version":plan["version"],"invalidated":sorted(invalid)}
473:
474:     def _refresh_capabilities(self,s,a,now):
475:         self._fields(a,{"capabilities"});caps=a["capabilities"]
```
