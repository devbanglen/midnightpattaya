# Recovery Kit and arcade traffic collision (team18/recovery, 2026-10-21)

Owner decision (on `docs/TRAFFIC_COLLISION_OPTIONS.md`): **Model B (arcade traffic collision) + the Recovery Kit**,
built in that order. Phase 1 is the Recovery Kit and ships alone. Phase 2 is the arcade hit model, behind a switch
that is **off by default** (`CollisionModel = "physical"`). The leader turns it on in Studio after testing.

**Status: written, compiled (`luau-compile`) and unit-tested offline (`luau` CLI). Not run in Roblox Studio.**
Nothing in this document is an in-game result. Section 6 is the Studio test plan.

Owner rule respected: grip, top speed, acceleration and handling are unchanged. The only new code in the physics
step runs while a traffic-hit window is open (arcade mode only), plus a road-name check on the existing wheel rays
(read only).

## สรุปภาษาไทย (สำหรับเจ้าของเกม)

- **ชุดกู้รถ (เฟส 1, เปิดอยู่แล้วเมื่อติดตั้ง):** รถคว่ำ (ล้อชี้ฟ้า) ครบ 1.5 วินาที หรือเอียงเกิน 60° และช้ากว่า 15
  ครบ 1.5 วินาที → เกมพลิกรถกลับเองใน 0.35 วินาที ขึ้นข้อความ "RECOVERED"
- **ปุ่ม R:** พลิกรถอยู่กับที่เหมือนเดิม แต่มีคูลดาวน์ 2 วินาที ใช้ได้เฉพาะตอนรถเอียงเกิน 30° หรือช้ากว่า 10
  ยกรถ 3 studs (เดิม 6) ถ้าที่ตรงนั้นมีของขวาง จะขอให้เซิร์ฟเวอร์กู้รถแทน
- **รถติด:** กดคันเร่งค้างแล้วรถขยับไม่ถึง 6 studs ใน 4 วินาที (หรือออกนอกถนนช้าๆ 6 วินาที) → ขึ้น
  "Stuck? Hold R to rescue" กด R ค้าง 1 วินาที → เซิร์ฟเวอร์ลากรถ **ย้อนกลับไปตามทางที่รถเพิ่งขับมา**
  ไปจุดล่าสุดที่รถยังวิ่งปกติบนถนน หันตามทิศถนน จึงใช้ข้ามเช็คพอยต์หรือเป็นทางลัดไม่ได้เลย
  คูลดาวน์ 10 วินาที ในสนามเซอร์กิตใช้ปุ่ม T เหมือนเดิม
- **ระบบชนแบบอาร์เคด (เฟส 2, ปิดไว้ก่อน):** ตั้ง `CollisionModel = "arcade"` แล้วรถจราจรไม่ชนทางฟิสิกส์อีก
  ชนเบา −20% ชนแรง −45 ถึง −70% หมุน 45–120° พวงมาลัยเหลือ 30% นาน 0.6–1.2 วินาที ชนประสานงา −85%
  **รถจราจรทำให้รถพลิกคว่ำไม่ได้** ชนแรงระหว่างงานแท็กซี่ยังตัดค่าโดยสารได้ (ต้องเพิ่มโค้ดใน PattayaJobsServer
  ตามข้อ 7.2)
- **ปิดทุกอย่างได้ทันที:** `Recovery_Enabled = false` (กลับเป็น R แบบเดิม) และ `CollisionModel = "physical"`
- **รอบ 6 (team18/arcade-fix-5, ข้อ 14, ยังไม่ได้ทดสอบใน Studio):**
  - เทียบตำแหน่งรถจราจรตามเวลาที่วาดจริง (DrawT) ไม่ช้าไป 1 เฟรมอีก
  - รถที่ชนระบุจาก key ในเหตุการณ์ชนเอง ไม่ใช้ตำแหน่งโมเดล
  - รถไม่เอียงระหว่างช่วงชน (แก้เฉพาะช่วงชนแบบอาร์เคด ฟิสิกส์รถปกติไม่เปลี่ยน)
  - ไม่นับชนซ้ำขณะรถยังซ้อนกัน
  - ตัดเลนที่วกกลับตามหัวมุม (สาเหตุ route 26)
  - มีตัวจำกัด FPS สำหรับทดสอบที่ 15/30/60 พร้อมขั้นตอนทดสอบ 2 ผู้เล่น
  - ค่าเริ่มต้นยังเป็น physical เสมอ

## 1. What each file does now

| File | Role |
|---|---|
| `roblox/src/ReplicatedStorage/PattayaRecovery.luau` (new) | Shared settings: every number below is a `workspace` attribute with a default, read live by `R.get` / `R.config()`. Pure decision functions (numbers in, numbers out): `uprightTick`, `resetAllowed`, `stuckTick`, `offRoadTick`, `fallen`, `pickCrumb`, `gateAllows`, `cpAllows`, `tangentAt`, `alignHeading`, `obbOverlap`, `sweptOverlap`, `closingSpeed`, `classifyHit`, `impactVelocity`, `spinProfile`, `buildTrafficRoutes`, `trafficNear`, `validateHitReport`. |
| `roblox/src/StarterPlayer/StarterPlayerScripts/CarController.client.luau` | Auto-upright, the new R rules, the stuck / off-road prompt ("Hold R to rescue"), the rescue request and its replies, a `RecoveryToast` label. Phase 2: creates `PlayerScripts.CarImpact` (BindableEvent), applies the arcade hit (speed cut, push-out, scripted spin, steering scale, drift grip, pitch/roll held at zero) and reports heavy hits (`TrafficHit`). |
| `roblox/src/StarterPlayer/StarterPlayerScripts/PattayaTraffic.client.luau` | Physical mode: unchanged, plus a 2 s ghost of nearby traffic after a rescue (`TrafficGhostUntil`). Arcade mode: the `Body` collider never collides; a swept box test finds the touch and fires `CarImpact`; the traffic car ghosts 1.5 s; the touch cancels that near miss. Near-miss rules are unchanged. |
| `roblox/src/ServerScriptService/PattayaRecoveryServer.server.luau` (new) | The server-side trail of every driven car (10 Hz), `RequestRescue` checks, the rescue spot choice, the tow, `RescueUpdate` replies. Phase 2: `TrafficHit` validation, the `TrafficHitAt / TrafficHitTier / TrafficHits` player attributes and `ServerStorage.PattayaTrafficHit` (BindableEvent) for the jobs server. |
| `roblox/src/ReplicatedStorage/PattayaTestKit.luau` | New helpers (existing API unchanged): `TK.flipCar`, `TK.flipTest`, `TK.holdThrottle`, `TK.recovery`, `TK.trafficNear`, `TK.hitTest`. `TK.ghostTraffic(on)` also sets `TrafficGhostAll` so arcade hits are skipped too. |
| `roblox/src/ServerScriptService/RaceCarServer.server.luau` | **Unchanged.** Nothing needed: the chassis, its size and its physics are as before. |
| `tools/qa/tests/test_recovery.py` (new) | 90+ checks of the pure functions in the `luau` CLI, plus static wiring checks. |

No new client scripts (the QA runner's `CLIENT_SCRIPTS` list stays valid). One new server script and three new
remotes: see 7.1 for the QA runner lists.

## 2. Phase 1: Recovery Kit

### 2.1 Auto-upright (client, CarController)

- **Trigger** (either, owner number 1.5 s):
  - upside down: `UpVector.Y < 0` for `Recovery_UprightDelay` = **1.5 s**, at any speed;
  - tilted and slow: `UpVector.Y < Recovery_TiltUpY` (0.5 = 60°) and horizontal speed < `Recovery_TiltSlowSpeed`
    (15) for `Recovery_TiltDelay` = **1.5 s**.
- Never while the chassis is anchored (race grid, server move, rescue), while `RescueActive`, in the first
  `Recovery_EnterGrace` (0.5 s) after getting in, or during the animation itself.
- **Action:** over `Recovery_UprightTime` (0.35 s) the chassis CFrame is blended to wheels-down, lifted
  `Recovery_UprightLift` (2.5) studs, heading = flattened look; if that is vertical, the direction of travel; else the
  last heading the car had while level. Angular velocity zero; at the end `Recovery_UprightKeepVel` (20 %) of the
  horizontal velocity is kept. Toast "RECOVERED". Player attributes `Recovery_Uprights` (count) and
  `Recovery_LastUprightAt` (server time) for tests.
- Expected cost: 1.5 s + 0.35 s + the drop, about 2 s from the moment the car is on its roof.

### 2.2 Manual R (client)

- Still "flip in place" (never moves the car along the road, so it cannot skip a checkpoint).
- `Recovery_ResetCooldown` = **2 s**; allowed only when tilted more than `Recovery_ResetMinTiltDeg` (30°) **or** slower
  than `Recovery_ResetMaxSpeed` (10). Otherwise a short toast explains why.
- Lift `Recovery_ResetLift` = 3 studs (was 6). An overlap query checks the spot first (car, character and traffic
  excluded, `RespectCanCollide`); if something solid is there, R asks the server for a rescue instead.
- `Recovery_Enabled = false` gives back today's R exactly (lift 6, no cooldown, no rules).
- Circuits: the server **T** reset (last gate, lap invalid, 3 s cooldown) is unchanged.

### 2.3 Stuck detection and the prompt (client)

- **Stuck:** throttle or reverse held (`|ThrottleFloat| > 0.5`) while the car stays within `Recovery_StuckDist`
  (6 studs) of where that started, for `Recovery_StuckTime` = **4 s**. Measured on position. Letting go of the
  throttle restarts it (waiting at a light is never "stuck").
- **Off-road:** no wheel ray on a road part (`PattayaRecovery.ROAD_NAMES`, or Asphalt material) for
  `Recovery_OffRoadTime` (6 s) while slower than `Recovery_OffRoadSpeed` (20) and holding the throttle.
- **Fallen:** chassis Y below `Recovery_FallY` (−30): the rescue is requested at once.
- **Prompt (owner: offered, not forced):** "Stuck? Hold R to rescue". Holding R for `Recovery_RescueHold` (1 s)
  sends `RequestRescue`; a short tap is still the normal R flip. The prompt stays until the car drives off (> 8
  studs/s). On a circuit the prompt says "press T".
- `Recovery_RescueAuto` (default **false**): an automatic rescue at `Recovery_RescueAutoTime` (8 s). Off, because the
  owner chose "prompt".

### 2.4 Rescue (server, PattayaRecoveryServer)

- **Trail:** every 0.1 s the server records each driven car: position, flat heading, horizontal speed (from
  position), up vector. 45 s are kept. A jump of more than 60 studs between two samples (garage, race grid, TestKit
  teleport, circuit reset) starts a new trail.
- **Checks:** `Recovery_Enabled` and `Recovery_AntiStuck`; seated in a race car; car not anchored; not
  `CircuitActive` (reply: use T); `Recovery_RescueCooldown` (**10 s**) since the end of the last rescue; server-seen
  horizontal speed < `Recovery_RescueMaxSpeed` (25); requests faster than 2 per second are dropped.
- **Spot (never forward):** walking back along the trail from the newest sample, the first sample that is
  - at least 1 s old, driven at 10+ studs/s with the car level (up.Y ≥ 0.8),
  - at least 8 studs from the stuck spot,
  - on a road: within half the road width + 2 of the nearest graph edge (`PattayaRoute.nearestEdge`, width from
    `PattayaData.graph`), with ground found by a raycast and above `Recovery_FallY`,
  - **loop race:** not inside the next gate's corridor and at least `Recovery_GateMargin` (25) studs before it
    (gate from `RaceNext`),
  - **sprints / street races:** at least 26 + 25 studs from `RouteNextCp` when a race server publishes it (7.3),
  - within `Recovery_RescueMaxPath` (300) studs of trail; at most 40 candidates are checked.

  Because the spot is always a place the car has already been, a rescue can only cost progress, never gain it:
  it cannot pass a checkpoint, and it cannot jump through a wall to another road. A second rescue goes further back
  (the trail after the chosen spot is dropped).
- **Fallback** (no usable trail, e.g. just got in or fell off the map): free roam and jobs only, the nearest road
  edge within 300 studs. In a race there is no fallback: "No safe spot behind you yet: press R".
- **Heading:** the road direction at that spot (edge tangent), flipped to agree with the heading the car had
  there. Without a road graph (old RaceMap place): the recorded heading.
- **Tow:** the car is anchored and moved back **along its own trail** (server `PivotTo`, 3 studs up in the middle)
  at `Recovery_RescueGlide` (60 studs/s), or `Recovery_RescueGlideJob` (45) during a job, so the jobs bump detector
  (a 55 studs/s drop) never reads the stop as a crash, and every race server sees ordinary slow movement (no
  teleport check trips, no gate is crossed forwards). Set down at road + 2.8 (+0.3), held anchored
  `Recovery_RescueHoldRace` (1 s) in races / `Recovery_RescueHoldFree` (0.5 s) elsewhere, then handed back
  (`SetNetworkOwner`). If another car stands on the spot it lands 12 studs further back along the road.
- **After:** `RescueUpdate "done"`; the client sets `TrafficGhostUntil` = now + `Recovery_RescueGhost` (2 s), and
  PattayaTraffic ghosts the traffic near the car until then. Player attributes `RescueActive`, `RescueAt`,
  `RescueEndAt` (server times) are there for the race / job servers and tests.
- Costs: the 1 s hold + the tow + restarting from 0 make a rescue always slower than driving. Not a bump in a job;
  the job clock keeps running.

## 3. Phase 2: arcade traffic collision (`CollisionModel = "arcade"`)

### 3.1 Detection (PattayaTraffic, client)

- The traffic `Body` collider is `CanCollide = false` in arcade mode (switching back restores today's solid boxes
  at once).
- In the existing per-car loop, in the traffic car's frame: a 2D oriented-box test (separating axes) of my chassis
  (7 × 15) against the traffic box (6.6–7.2 × 14–16), **swept** from last frame's position in ≤ 2-stud steps, so a
  30 FPS phone cannot pass through a car. A height gap over 6 studs (bridge) is ignored.
- On the first touch: contact normal and depth from the test; **closing speed vc** = my velocity minus the traffic
  car's velocity (its loop speed along its heading), along the normal; approach angle = asin(vc / relative speed);
  facing = my heading · its heading; which side and which half of my car it touched. Sent to CarController through
  `PlayerScripts.CarImpact`. The traffic car then ghosts for `Arcade_HitGhost` (1.5 s) and that near miss is
  cancelled. Physical contact never happens, so a traffic car cannot roll the car.

### 3.2 The hit table (`PattayaRecovery.classifyHit`, owner numbers)

| Tier | When | Speed lost | Spin (yaw kick) | Control loss | Other |
|---|---|---|---|---|---|
| Scrape | vc < 15, or approach < 15° | 8 % | 0–5° away | none | near miss cancelled |
| Light | 15 ≤ vc < 45 | **20 %** | 8–15° away | 0.25 s, steering 70 % | |
| Heavy | vc ≥ 45 | **45 %** at vc 45 → **70 %** at vc ≥ 130 | **45° → 120°** (front-half hit: nose pushed away; rear-quarter: tail pushed away, ×1.25, max 120°) | **0.6 → 1.2 s**, steering **30 %**, drift grip (the car slides) | reported to the server |
| Head-on | vc ≥ 90 and facing each other within 30° | **85 %**, then 10 studs/s back | 10° | 1.0 s, steering 30 %, drift grip | reported to the server |

- Examples (traffic at 45): rear-end at 150 → vc 105 → heavy, −63 %, about 98° spin, 1.0 s. Head-on at 150 →
  vc 195 → head-on. A 5° side-swipe at 150 → scrape; 20° → heavy.
- **Applied:** the horizontal velocity is cut at once (`impactVelocity`); push-out along the normal by depth + 0.5
  (max 2 studs); the spin is a yaw-rate profile ω(t) = ω0 (1 − t/T) with T = 0.6 × control (0.15–0.6 s) that adds
  up to the kick angle; for the whole window pitch and roll angular velocity are zeroed every step. Throttle stays.
  After the spin the car slides on drift grip, which scrubs extra speed on a big spin (part of the 1–2 s cost).
- Every number is a `workspace` attribute (`Arcade_*`, list in section 4), read live.
- Player attributes `Recovery_HitCount`, `Recovery_LastHit` ("heavy vc=105 150->56 yaw=97 ctl=1.00") for tests.
- Scenery (walls, palms, poles) stays physical; the Recovery Kit covers it. Player-vs-player contact is unchanged.

### 3.3 TrafficHit report (jobs bump)

A heavy hit at job speed (70 × 45 % = 32 studs/s) is below the jobs detector's 55 studs/s drop, so heavy and
head-on hits are reported: `TrafficHit:FireServer(tier, vc, speedBefore)`, at most one per second from the client.

Server checks (`validateHitReport`): arcade on; one accepted report per `Arcade_HitReportGap` (1 s), any report
per 0.25 s; tier heavy / head-on; vc a number between 0 and 400 and at most the server-seen speed + 80; the server
saw the car at `Arcade_HitMinSpeed` (40) or more in the last 0.6 s; a traffic car (the same deterministic formula
from `ReplicatedStorage.PattayaTraffic` and the server clock, checked now and 0.15 / 0.3 s earlier) within
`Arcade_HitTrafficRadius` (45) studs. A valid report sets `TrafficHitAt`, `TrafficHitTier`, `TrafficHits` and fires
`ServerStorage.PattayaTrafficHit (plr, tier, vc)`. **The fare cut needs the 12-line hook in 7.2** (PattayaJobsServer
is not this team's file). Light hits never cut the fare (team recommendation, owner decision 8 still open).

A cheater can skip reporting, as today (`TK.ghostTraffic` already shows traffic can be ignored); a report only
ever costs the reporter money, so nothing can be farmed.

## 4. Switches (workspace attributes, live)

Set them **on the server** (Studio command bar on "Server", or the execute tool on the server): attributes set on a
client do not replicate, and the rescue checks run on the server.

| Attribute | Default | Meaning |
|---|---|---|
| `Recovery_Enabled` | true | Master switch of the kit. false = today's R (lift 6, no cooldown), no auto-upright, no prompt, rescue refused. |
| `Recovery_AutoUpright` | true | Auto-upright on/off. |
| `Recovery_AntiStuck` | true | Stuck / off-road prompt and the server rescue on/off. |
| `Recovery_RescueAuto` | false | Automatic rescue at `Recovery_RescueAutoTime` (8 s). |
| `CollisionModel` | `"physical"` | `"arcade"` = Phase 2. Anything else = today's solid boxes. |
| `Recovery_UprightDelay`, `Recovery_TiltDelay`, `Recovery_TiltUpY`, `Recovery_TiltSlowSpeed` | 1.5, 1.5, 0.5, 15 | Upright trigger. |
| `Recovery_UprightTime`, `Recovery_UprightLift`, `Recovery_UprightKeepVel`, `Recovery_EnterGrace` | 0.35, 2.5, 0.2, 0.5 | Upright action. |
| `Recovery_ResetCooldown`, `Recovery_ResetMinTiltDeg`, `Recovery_ResetMaxSpeed`, `Recovery_ResetLift` | 2, 30, 10, 3 | Manual R (cooldown 0 = unlimited). |
| `Recovery_StuckTime`, `Recovery_StuckDist`, `Recovery_StuckThrottle` | 4, 6, 0.5 | Stuck. |
| `Recovery_OffRoadTime`, `Recovery_OffRoadSpeed`, `Recovery_FallY` | 6, 20, −30 | Off-road / fallen. |
| `Recovery_RescueHold`, `Recovery_RescueAutoTime` | 1, 8 | Prompt hold / auto time. |
| `Recovery_RescueCooldown`, `Recovery_RescueMaxSpeed`, `Recovery_RescueMaxPath` | 10, 25, 300 | Rescue checks. |
| `Recovery_RescueGlide`, `Recovery_RescueGlideJob`, `Recovery_RescueHoldRace`, `Recovery_RescueHoldFree`, `Recovery_RescueGhost` | 60, 45, 1, 0.5, 2 | Tow and hold. |
| `Recovery_GateMargin` | 25 | Rescue spot distance before the next gate / checkpoint. |
| `Arcade_ScrapeVc`, `Arcade_ScrapeAngle`, `Arcade_ScrapeLoss`, `Arcade_ScrapeYaw` | 15, 15, 0.08, 5 | Scrape tier. |
| `Arcade_HeavyVc`, `Arcade_LightLoss`, `Arcade_LightYawMin/Max`, `Arcade_LightControl`, `Arcade_LightSteer` | 45, 0.20, 8/15, 0.25, 0.7 | Light tier (vc between scrape and heavy). |
| `Arcade_HeavyLossMin/Max`, `Arcade_HeavyYawMin/Max`, `Arcade_HeavyControlMin/Max`, `Arcade_HeavySteer`, `Arcade_HeavyFullVc` | 0.45/0.70, 45/120, 0.6/1.2, 0.3, 130 | Heavy tier (min at vc 45, max at vc 130). |
| `Arcade_HeadOnVc`, `Arcade_HeadOnAngle`, `Arcade_HeadOnLoss`, `Arcade_HeadOnYaw`, `Arcade_HeadOnControl`, `Arcade_HeadOnBounce` | 90, 30, 0.85, 10, 1.0, 10 | Head-on. |
| `Arcade_HitGhost`, `Arcade_MaxPush` | 1.5, 2 | After a hit. |
| `Arcade_HitReportGap`, `Arcade_HitMinSpeed`, `Arcade_HitTrafficRadius` | 1, 40, 45 | TrafficHit server check. |

A missing attribute, or one of the wrong type, uses the default.

## 5. Remotes and signals

| Name | Where | Direction | Payload |
|---|---|---|---|
| `RequestRescue` | `ReplicatedStorage.PattayaRemotes` (RemoteEvent) | client → server | reason ("stuck", "offroad", "blocked", "fell", "auto") |
| `RescueUpdate` | `PattayaRemotes` (RemoteEvent) | server → client | `"start", {eta, hold, reason}` / `"done", {ghost}` / `"denied", text` |
| `TrafficHit` | `PattayaRemotes` (RemoteEvent) | client → server | tier, vc, speedBefore |
| `CarImpact` | `PlayerScripts` (BindableEvent, client only) | PattayaTraffic → CarController | hit table (3.1) |
| `PattayaTrafficHit` | `ServerStorage` (BindableEvent) | PattayaRecoveryServer → other servers | plr, tier, vc |

`tools/qa/tests/test_remotes_contract.py` passes with the three new remotes.

## 6. Studio test plan (for the leader; TestKit, docs/TEST_KIT.md)

Install the five changed / new files (PattayaRecovery, PattayaRecoveryServer, CarController, PattayaTraffic, PattayaTestKit) with `tools/studio/install.ps1`. Every Play:
server `require(game.ServerStorage.PattayaTestKitServer).start()`; client `local TK = require(game.ReplicatedStorage.PattayaTestKit)`,
`TK.hookRemotes()`, `TK.seatIn()`. `print(TK.recovery())` shows the switches and counters at any time.

| # | Test | How | Pass |
|---|---|---|---|
| 1 | Flip test | `print(TK.flipTest(180).text)`, then `TK.flipTest(90)`, `TK.flipTest(120)` | upright, seconds ≈ 1.9–2.4 (1.5 s trigger + 0.35 s turn + the drop), `auto-uprights 1`, toast "RECOVERED" |
| 2 | Flip with the kit off | server `workspace:SetAttribute("Recovery_Enabled", false)`; `TK.flipTest(180, 5)` | NOT upright (today's behaviour); R lifts 6 and works any time |
| 3 | R rules | drive at 80 and press R; stop and press R twice within 2 s | at 80 refused (toast); stopped: flip; second press "wait a moment" |
| 4 | Stuck test | `TK.jumpTo(<a building corner>)` facing the wall, hold W (or `TK.holdThrottle(1, 8)`) | prompt at ≈ 4 s; hold R 1 s → "RESCUE", the car is towed back along the way it came, lands on the road facing along it, "BACK ON THE ROAD"; `RescueActive` true then false |
| 5 | Rescue cooldown / speed | rescue again at once; request while driving at 40 | "Rescue ready in N s"; "slow down first" |
| 6 | Road-edge holes | the Soi 8 hole on Beach Road and the Sukhumvit outer lane (QUALITY_AUDIT_2026-10-20) | upright and / or rescue bring the car back on the road |
| 7 | Checkpoint-skip attempt, street race | start a Street Sprint; drive just past a checkpoint, wedge the car off-road, request a rescue; repeat just before the next checkpoint | the car always lands behind where it was; never past the next checkpoint (`RaceNext` / sprint "next" unchanged by the rescue); no "Run invalid" |
| 8 | Checkpoint-skip attempt, loop race | same on the Central Loop (`RaceNext`) | the car lands ≥ 25 studs before the next gate or behind the last one; no gate credited by the tow |
| 9 | Circuit | wedge the car on Bira, wait for the prompt | prompt says "press T"; `RequestRescue` replies "On a circuit: press T"; T reset unchanged |
| 10 | Job | during a taxi job, a staged stuck + rescue | no `JobUpdate "bump"`, no "Job invalid" |
| 11 | Traffic hits, physical | `CollisionModel` unset; `TK.hitTest("rear", 100)`, `("rear", 150)`, `("rear", 200)`, `("head", 150)`, `("side", 150, {angle = 5})`, `("side", 150, {angle = 20})`, `("rear", 150, {offset = 2})` | baseline numbers (today's physics); flips now recover by themselves (test 1 rules) |
| 12 | Traffic hits, arcade | server `workspace:SetAttribute("CollisionModel", "arcade")`; the same 7 calls, each 3× | `minUp ≥ 0.9` every run (**no flip**); `tier` and `lossPct` match the table ±5 % (rear 100 → vc 55 heavy ≈ 48 %; rear 150 → vc 105 heavy ≈ 63 %; rear 200 → vc 155 heavy 70 %; head 150 → head-on 85 %, small bounce; side 5° → scrape; side 20° → heavy); `yawDeg` in the tier's band ±15° |
| 13 | Arcade switch live | switch back to `"physical"` during a drive | boxes solid again at once (a hit is a physics knock again), no errors |
| 14 | Jobs bump (after 7.2 is applied) | arcade on, taxi job, `TK.hitTest("rear", 80)` | `JobUpdate "bump"` = 1, `TrafficHits` +1; a light hit (`TK.hitTest("side", 70, {angle = 25})`, vc ≈ 30) → no bump |
| 15 | Near misses | arcade on, `TK.drivePath` with `lateral` 4–6 past traffic at 120 | same `NearMissCombo` count as a physical-mode run |
| 16 | Phone | Device Emulator, tests 1, 4, 12 | same results; the toast fits the screen |
| 17 | Perf | `PattayaPerfProbe` with 70 traffic models in arcade mode | < 0.2 ms extra client Heartbeat |

`TK.hitTest` drives a straight homing approach (it may cross kerbs on a curved road) and lets go at the touch;
read `result.lastHit` for the vc the game used. Report `result.text` lines.

## 7. Proposed diffs for files this team does not own

### 7.1 `ServerStorage/PattayaQARunner.luau` (needed for `test_qa_runner.py`)

`RunnerSync.test_remotes_match_server_sources` and `RunnerSync.test_script_lists_match_repo` fail on this branch
until the runner lists the new script and remotes (verified: with this diff applied, every offline test passes):

```diff
 QA.REMOTES = {
 	...
-	RequestSprint = "RemoteEvent", RoadFightRequest = "RemoteEvent", SprintUpdate = "RemoteEvent",
+	RequestRescue = "RemoteEvent", RequestSprint = "RemoteEvent", RescueUpdate = "RemoteEvent",
+	RoadFightRequest = "RemoteEvent", SprintUpdate = "RemoteEvent", TrafficHit = "RemoteEvent",
 }
 QA.SERVER_SCRIPTS = {"CircuitServer", "PattayaChallengeServer", "PattayaEventsServer", "PattayaGarageServer",
-	"PattayaGPSServer", "PattayaJobsServer", "PattayaPerfTelemetry", "PattayaRaceServer", "PattayaSprintServer",
-	"PattayaTimeServer", "RaceCarServer"}
+	"PattayaGPSServer", "PattayaJobsServer", "PattayaPerfTelemetry", "PattayaRaceServer", "PattayaRecoveryServer",
+	"PattayaSprintServer", "PattayaTimeServer", "RaceCarServer"}
```

### 7.2 `ServerScriptService/PattayaJobsServer.server.luau` (jobs bump for arcade heavy hits)

After the `NearMiss.OnServerEvent` handler:

```lua
-- arcade traffic hits (PattayaRecoveryServer validated them): a heavy / head-on hit is a bump. Shares lastBumpAt
-- with the speed-drop detector so one crash never counts twice.
task.spawn(function()
	local hitSignal = ServerStorage:WaitForChild("PattayaTrafficHit", 60)
	if not hitSignal then return end
	hitSignal.Event:Connect(function(plr, tier)
		local st = active[plr]
		local now = workspace:GetServerTimeNow()
		if st and (tier == "heavy" or tier == "headon") and now - st.lastBumpAt > 1 then
			st.lastBumpAt, st.low = now, 0
			st.bumps += 1
			table.clear(st.history)
			JobUpdate:FireClient(plr, "bump", st.bumps)
		end
	end)
end)
```

Optional, in the Heartbeat before the bump detector (belt and braces; the 45 studs/s tow already stays below the
55 drop): `if plr:GetAttribute("RescueActive") then st.low = 0; table.clear(st.history) end`.

### 7.3 Sprint / street races: `RouteNextCp` (rescue checkpoint clamp)

The rescue already never moves a car forward (trail only). To also keep the spot 51 studs away from the next point
checkpoint, publish it:

- `PattayaSprintServer`: after `active[plr] = {...}` and after `st.next += 1`:
  `plr:SetAttribute("RouteNextCp", st.cps[st.next])`; in `stop` and at the finish:
  `plr:SetAttribute("RouteNextCp", nil)`.
- `PattayaStreetRace`: at GO and after `p.next += 1`: `p.plr:SetAttribute("RouteNextCp", race.cps[p.next])` (human
  parts only); in `knockOut`, `releaseCar` / `endRace`: `nil`.

Optional (sprint and street race checkpoint test, `Route.segDist(last, pos, c) < 26`): skip one sample after a
server move so the tow segment is never tested:
`if (plr:GetAttribute("RescueAt") or 0) > (st.rescueSeen or 0) then st.rescueSeen = plr:GetAttribute("RescueAt"); st.last = pos end`.
The tow follows the car's own trail, which did not pass within 26 studs of the next checkpoint (else it would have
counted then), so this only guards against the straight segments between 10 Hz trail samples.

## 8. Rollback

All live, on the server, no restart:

1. Arcade off: `workspace:SetAttribute("CollisionModel", "physical")` (or remove the attribute). Traffic boxes are
   solid again within one frame; `CarImpact` events are ignored.
2. Kit off: `workspace:SetAttribute("Recovery_Enabled", false)`. R is today's R; no upright, no prompt; the server
   refuses rescues. Pieces separately: `Recovery_AutoUpright`, `Recovery_AntiStuck`, `Recovery_ResetCooldown = 0`.
3. Full code rollback: delete `ServerScriptService.PattayaRecoveryServer` and `ReplicatedStorage.PattayaRecovery`.
   CarController and PattayaTraffic then run without the module (`pcall` require): CarController falls back to
   today's R, PattayaTraffic to physical traffic. Or `git revert` the two team18 commits.

## 9. Risks and open points

- **Not run in Studio.** Physics feel (the 0.35 s turn-over, the scripted spin on drift grip, the tow) is untested.
  The numbers are the owner's starting values; tune with the attributes.
- Arcade hits are decided on the client (as all car physics today). The server only checks the reports it gets.
- The spin profile only acts while 2+ wheels touch the ground; an airborne hit only loses speed.
- After a big spin the car slides on drift grip, so the total speed lost is more than the table's instant cut.
- A traffic car still overlapping the car when its 1.5 s ghost ends gives a second (usually scrape) hit.
- Off-road detection depends on road part names (`ROAD_NAMES`, same list as the TestKit); a road made of other
  part names counts as off-road, which only shows the prompt after 6 s of slow driving with the throttle held.
- The rescue tow lifts the car 3 studs mid-way but moves through whatever is between (anchored, no collision); the
  path is the car's own recent trail, so it is open road in practice.
- Rescue spot overlap with another player's car: it lands 12 studs further back without a second check.
- `TrafficHit` validation needs `ReplicatedStorage.PattayaTraffic`; without it only the speed checks run.
- Jobs: until 7.2 is applied, an arcade heavy hit at job speed usually does **not** cut the fare (the speed-drop
  detector still catches hits that lose more than 55 studs/s, e.g. head-ons and heavy hits above about 100).
- Bots still never meet traffic (owner decision 10 open). Camera shake / phone vibration are not built (decision 11).

## 10. Studio round 1 (2026-10-21): what was wrong with the arcade results, and the fixes (team18/arcade-fix)

Leader's runs: `docs/test_results/recovery_kit_studio.txt`. Investigated offline only; **the fixes are not yet
re-run in Studio.** Every Studio case is now replayed in the luau CLI (`StagedHits` in
`tools/qa/tests/test_recovery.py`: the traffic car on its route by the PattayaTraffic formula, my car on
`stagePlan`, `hitFromWorld` every frame at 60 / 30 / 20 FPS, on a straight and a round route).

1. **Wrong contact normal (a real game bug, `sweptOverlap`).** The normal was the axis of smallest overlap. When a
   frame step pushes my car's corner deep into the long side of a traffic car (20° side hit at 30 FPS), the
   smallest overlap is along the wrong axis, so the closing speed was measured along it: replayed offline with
   the old code, the 20° side hit at 150 at 30 FPS came out as a scrape (vc 15), and against an oncoming car the
   normal tilted 20° off the side face. Any frame where the length axis wins against an oncoming car gives
   vc ≈ 186 with facing −0.94, a "head-on": the likely cause of the Studio "side 150 a20 → headon −92 %" together
   with point 2 (the old helper could meet an oncoming car). Fixed:
   the normal is now the face the boxes really met on: of the axes that still separated them one sub-step
   earlier, the one that closed last (time of impact); sub-steps are 1 stud. The classifier itself (closing
   speed sign, facing, side / front, the tier table) was checked case by case and is correct: rear 100/150/200,
   head-on 100/150/200, side 5° / 20° / 25° all give the owner's tiers and losses at every frame rate.
2. **The test helper hit the wrong car or no car (TestKit).** The old `TK.hitTest` put the car on a straight line
   120 studs from the target and homed on its centre: on a curved road it started off the lane, met kerbs and
   scenery or *other* traffic, and its stop rule ("centres within 15.5 studs") fired without a touch. The tier it
   printed was whatever the next touch was, seconds later; the "after" speed was read 0.1 s after that stop (−4 %
   is just coasting). Fixed: `PattayaRecovery.stagePlan` plans the car on the target's own lane with the same
   route formula the traffic uses (rear: behind it along the route; head: ahead of it, against the route; side:
   from its right at the angle, level with it at the touch), `TK.hitTest` drives that plan and hands off on the
   frame the hit registers (arcade) or at contact (physical). It reports `onTarget` (the hit car's position,
   `Recovery_LastHitPos`, matches the target) and `MISSED (reason)` otherwise.
3. **Cars without a model cannot be hit (PattayaTraffic).** The pool holds 70 models; when more cars are within
   650 studs, the extra ones get none and are invisible and non-colliding in **both** modes (explains several
   physical "MISSED" runs too). Fixed: a car within 200 studs of my car that finds the pool full takes the model
   of the farthest car (beyond 350 studs) not yet placed this frame. `TK.hitTest` only picks a target that has a
   model (`TK.trafficModelAt`).
4. **Speed metric.** Arcade: `before` / `after` are now the game's own numbers for that hit
   (`Recovery_LastHitBefore` / `Recovery_LastHitAfter`, set in `applyImpact`), plus `measured` = the speed TK sees
   on the first step after the hit. Physical: the lowest speed in the 0.4 s after contact. Nobody presses the
   throttle in the test (the driver stays at 0), so neither number includes re-acceleration.
5. **Applied once, not overridden.** The cut is applied once per hit (the traffic car ghosts for 1.5 s, so it
   cannot fire again). `CarImpact` handlers run after the Heartbeat in which the touch was found and before the
   next physics step; CarController's own step only adds `accel × dt` (≤ 2 studs/s per frame at full throttle), and
   TestKit's driver checks the hit counter *before* it would set the velocity again. Nothing overwrote the cut in
   the Studio runs; the −4 % rows were the measurement in point 2.

Re-test (leader): the section 6 test 12 calls, now e.g. `print(TK.hitTest("rear", 200).text)`; expected
`hit tier=heavy vc=155 200->60 (-70%)`, `head 150` → `headon -85 %` (then 10 back), `side 150 {angle = 5}` →
scrape, `{angle = 20}` → heavy; every row must say `hit` without "(NOT the target car)".

## 11. Studio round 3 (2026-10-21, ~15 Hz unfocused): findings and fixes (team18/arcade-fix-2)

Rows: end of `docs/test_results/recovery_kit_studio.txt`. Investigated offline only; **not re-run in Studio.**

- **The classifier was right on every row that hit its target** (head 150 → head-on −93 %). Replayed offline
  (`StagedHits`): all 12 matrix rows × traffic speeds 38 / 45 / 55 × 60 / 30 / 20 / 15 FPS × four lanes (straight,
  round r = 300, a 4-stud lane change, a r = 400 bend) give the owner's tier and loss (±1 % straight, ±4 % on
  curves). That is more than 1,700 checks, plus one regression per Studio row.
- **"NOT the target car" (9 of 12) and "scrape 0→0" (3 rows) were the helper.** Traffic loops overlap on the main
  roads, so the target's lane (or the oncoming lane next to it) held other cars from other loops. The start spot
  could sit on another car, and the hit counter was armed before the teleport, so that hit at speed 0 counted.
  `side 150 a5 → heavy vc 147` and `side 150 a20 → scrape vc 0` were both hits on other cars (flagged as such).
  Fixes in `TK.hitTest`:
  - The target is now the nearest car with a model whose whole planned approach, start spot included, stays 30
    studs from every other traffic car (`PattayaRecovery.plannedPathClear`). If no car qualifies, every other car
    ghosts for the run. This uses the TestKit-only hook `TK_HitTarget` in PattayaTraffic, which works only in
    Studio or with `workspace.DevTest` and is ignored in normal play.
  - The car is held 0.3 s at its start, and the counter is re-armed every frame of the hold.
  - Only a hit after the approach began, within 0.35 s + 1.5 frames of the planned meeting, and on the target
    counts (`PattayaRecovery.acceptStagedHit`). Anything else ends the row as `MISSED (rejected: ...)`.
  - Each row shows the Heartbeat rate.
- **`side 70 a25` hit at 37:** the side run-up started up to 33 studs right of the lane, on the kerb, and between
  two 15 Hz frames the car hit it. Fixes:
  - The run-up is now at most 6 studs of sideways travel (`stagePlan`, `runLat`).
  - In arcade mode my car ignores scenery during the approach (`CanCollide` off until the hand-off; the wheel rays
    still hold it up).
- `TK.hitMatrix()` runs the 12 rows (`TK.HIT_MATRIX`) and prints one PASS / FAIL line per row with a summary. It
  checks five things against the table:
  - the tier, from the geometry and the target's real speed (`expectedStaged`);
  - the loss, ±5 %;
  - the head-on near-stop;
  - the speed at the hit, at least 90 % of the planned speed;
  - no flip.

Re-test (leader): server `workspace:SetAttribute("CollisionModel", "arcade")`, then client `TK.hitMatrix()`, at
15 Hz (unfocused) and focused.

## 12. Studio round 4 (2026-10-21, hitMatrix 9/12 then 5/12 at 60 Hz): findings and fixes (team18/arcade-fix-3)

Investigated offline only; **not re-run in Studio.** Every row that met its target at full speed matched the table.

- **(a) Isolation was not repeatable.** `plannedPathClear` judged a lane at the moment of choice, but in run 2
  rear 70 / 150 / 200 and head 150 / 200 still met another car 10 to 35 studs from the target. Fix:
  `TK.hitMatrix` now isolates every row by default, labelled "isolated" on each row and in the run summary:
  every other traffic car ghosts through the TestKit-only `TK_HitTarget` hook. Real-traffic runs are still
  possible with `TK.hitMatrix({isolate = false})` or `TK.hitTest(..., {isolate = false})`. In that mode the
  approach is re-checked every frame, and another car within 30 studs of mine before the touch aborts the row,
  which is retried with another target, up to 3 tries (`res.tries`).
- **(b) Side rows lost speed before the touch** (86, 126 and 59 of 150).
  - **Not a velocity override.** The plan sets the position and the velocity every step. Offline, the plan's
    velocity is exactly its own position change, and the 0.3 s hold ends before the approach.
  - **Not the kerb rays.** The wheel-ray spring cannot remove that much speed in one step.
  - **Likely cause: the seated character.** It is part of the car's assembly, and its torso and head collide.
    The arcade approach had switched off only the chassis, so the driver's body could still hit palms and signs
    beside the lane between two frames.
  - **Why the tiers flip.** The hit test reads the car's velocity after physics. A body hit changes that
    velocity's size and direction, so the closing speed can come out anywhere in the table: a5 → light or heavy,
    a20 → scrape. That fits all three side failures.
  - **Fix:** every part of my car and of the character ignores collisions for the whole hold and approach
    (re-applied every step), and is restored at the hand-off. Each row now prints the lowest speed seen on the
    approach (`approach-min`), so the next Studio run shows directly whether anything still slows the car.
- **Corner-first contact (side 100 a10 → heavy).** With the centres level at the meeting, my leading corner
  reached 7.4 studs ahead at 10°, which is the front corner of a 14-stud car. Offline that still gave the side
  normal, but the margin was nil. Fix: `stagePlan` now puts my front-left corner on the middle of its side
  (`alignCorner`). New tests cover all three vehicle kinds (sedan, songthaew, van) and check that every side row
  touches the side face (normal along its side axis, > 0.99 on straight lanes and > 0.95 on curves).
- **(c) head 100 rejected at −0.50 s.** The planned meeting is right for every kind at 60 and 15 Hz (new test,
  within 0.1 s). The −90 % head-on result needs a car facing mine, and a hit 0.5 s early at 145 studs/s
  closing speed is about 72 studs ahead of the target: most likely another car of an overlapping loop in that
  lane, as in run 2. The rejection message used to name only the first reason; it now names every one (time and
  "another car"). Isolation removes the case.
- `TK.hitMatrix({runs = 3})` prints each row, a line per run and an overall line that ends with "REPEATABLE" only
  when all 36 rows passed.

## 13. Studio round 5 (2026-10-21, hitMatrix 0/36): root cause of rounds 3-5, and the fix (team18/arcade-fix-4)

Investigated offline only; **not re-run in Studio.**

**Root cause: the same traffic car key was in two different places.** PattayaTraffic built the traffic loops with
`Vector3` maths. Roblox `Vector3` components are 32-bit floats (20816.7 is stored as 20816.69921875), so each loop
length differed from the double-precision length that TestKit and the server's TrafficHit check computed, by up
to about 0.01 studs. A car's arc is `phase + t * speed` with `t` the epoch clock (about 1.8e9 s), so it wraps around
its loop about 9 million times, and a 0.01-stud length difference moves the car hundreds of studs. Replayed offline
on the real `pattaya_wide` traffic data (1,155 cars) with the native float32 vector type:

- at 2026-10-21, the same key is a **median 711 studs** away (max 3,009);
- **not one car** is within 4 studs of where TestKit computed it.

Consequences:

- **Rounds 3-4:** every "target" was a different real car that happened to sit near the computed spot on the same
  lane. Rows that met it at a similar speed matched the table; rows where it drove differently were "another car",
  early, or late.
- **Round 4 run 2:** the lane check could not work either. TK.trafficNear dropped the key, so every
  `o.key ~= e.key` compared nil with nil, the "other cars" list was always empty, and the isolation attribute was
  set to nil, so nothing was isolated. Fixed by the leader in bc5bda9 (round 5 "table index is nil").
- **Round 5, rows 1-8:** with the key fixed, isolation ghosted every car except the computed key. The real car at
  the computed spot had another key, so it was ghosted and nothing could be hit ("no hit registered", approach at
  full speed).
- **Round 5, rows 9+ ("no traffic car with a model nearby"):** target picking needed a model within 4 studs of a
  computed spot, which only worked by coincidence on busy lanes. As the rows moved the car around, that stopped
  happening.
- **The server's TrafficHit check** compared against the same wrong positions, so a real arcade heavy hit at a job
  could be rejected as "no traffic near".

**Fix: one implementation, used by all three.**

- `PattayaRecovery` now provides one set of functions:
  - `TRAFFIC_ORIGIN_X / Z` and `TRAFFIC_ROAD_Y`;
  - `buildTrafficRoutes`;
  - `trafficKey(ri, k)`;
  - `trafficCarAt` and `trafficHeading`;
  - `forEachTrafficCar`, the draw loop;
  - `trafficNear`, built on `forEachTrafficCar`;
  - `tkTrafficEntry`, which keeps the key.
- **PattayaTraffic** draws its cars through `forEachTrafficCar` (double precision). The Vector3 build remains only
  as the fallback when `PattayaRecovery` is not installed (folder attribute `Positions` = "shared" or "legacy").
  Each model carries its key as the `TrafficKey` attribute.
- **TestKit** and **PattayaRecoveryServer** use the same functions and the same origin. Keys, positions and
  headings now agree by construction.
- **TestKit:**
  - `TK.selfCheck(n)` compares, for the 5 nearest cars, the computed key and spot with the model PattayaTraffic
    shows. It reports a missing `TrafficKey` (old PattayaTraffic installed) and a leftover `TK_HitTarget`.
  - `TK.hitMatrix` runs `selfCheck` first and refuses to run if it fails.
  - Targets are found by key and must be on their computed spot and not ghosted. This is checked again on every
    frame of the 0.3 s hold; a failed check aborts the row and it is retried with another target.
  - `TK_HitTarget` is cleared on every path: a finally-style cleanup in hitTest, plus `hitMatrix` and `TK.stopAll`.
  - Targets are searched around where the matrix started, and the car is stopped after each row.
  - `TK.hitMatrixStart(opts)` runs the matrix in the background (`:poll()`), so a 3-run matrix does not depend on
    one long execute call.
- **Tests (`TrafficKeys`):**
  - The old float32 drift is reproduced on synthetic and real data.
  - The PattayaTraffic draw loop and the TestKit list give identical key, x, z and heading for every car (874
    compared on the real data).
  - A separate copy of the module gives the same numbers.
  - PattayaTestKit itself is loaded in a mocked Roblox client:
    - `TK.trafficNear` keeps key, route, s and t;
    - `TK.selfCheck` passes on the shared drawing and fails on the old one, on untagged models and on a leftover
      hook;
    - an erroring hitTest leaves no `TK_HitTarget`.

Re-test (leader): install PattayaRecovery, PattayaTraffic, PattayaTestKit and PattayaRecoveryServer. In Play, run
`TK.selfCheck()` first: expect 5/5 "match" and "positions: shared". Then run `TK.hitMatrix({runs = 3})`, or
`local h = TK.hitMatrixStart({runs = 3})` and `print(h:poll())`.

## 14. Studio round 6 + owner review (2026-10-21, hitMatrix 26/36): findings and fixes (team18/arcade-fix-5)

Investigated and fixed offline only; **not re-run in Studio.** Every number below comes from the offline tests in
`tools/qa/tests/test_recovery.py` (the luau CLI, with the real `pattaya_wide` traffic data where it says so). None
of it is an in-game result.

### 14.1 What was wrong, item by item

**1. Models 5-6 studs behind in `hitMatrixStart` (selfCheck 0/5; run 3 row 12 "no traffic car whose model matches").**
A traffic car's position is a pure function of the server time. The background runner is a coroutine resumed by
TestKit's own Heartbeat connection. When that handler ran before PattayaTraffic's handler in the same frame (Roblox
does not order handlers; later connections usually fire first), TestKit read `GetServerTimeNow()` one frame after
the models had been drawn. At 15 fps one frame is 67 ms (about 0.1 s with a slow frame), which is 3-6 studs at the
traffic's 38-55 studs/s. That is more than the 4 studs selfCheck and pickTarget allowed. The direct execute call ran
after PattayaTraffic, so its lag was about 0. So the cause is a stale time, not a different Heartbeat rate: the lag
is one frame time multiplied by the traffic speed, which is why it only showed at 15 fps. The offline simulation
(TestKitSimulation, handlers newest first) reproduces it: the runner's selfCheck sees the models 3.5 studs / 67 ms
behind at 15 fps, 1.6 / 33 at 30 and 0.9 / 17 at 60 (0.0 with the handlers in connection order).

Fixes:

- **DrawT.** PattayaTraffic stamps its folder every Heartbeat with `DrawT` (the server time it drew and hit-tested
  with) and `DrawHz` (draws per second). TestKit computes positions at `DrawT` whenever it compares them with what
  is drawn, which is exact whatever the handler order or frame rate. `TK.selfCheck` checks the models at DrawT
  (within 0.5 studs). It reports the drawn-vs-now lag (studs and ms), the DrawT age and DrawHz as a diagnostic, never
  as a failure. Every row also prints its lag.
- **No model positions for targets or hits.** pickTarget only needs a model under the car's key that is not ghosted.
  The hit names its own car: PattayaTraffic puts the key in the CarImpact payload (`info.key`), CarController
  publishes `Recovery_LastHitKey` and `Recovery_LastHitT` (the server time of the touch), and
  `PattayaRecovery.acceptStagedHit` compares keys (`targetKey` / `hitKey`).
- **Car placed one physics step short.** TestKit put the car on the plan in PreSimulation and physics then moved it
  one more step before PattayaTraffic tested it at Heartbeat. Touches therefore came `speed * dt / vc` early: 0.16-0.3
  s for rear 70 at 15 fps, inside the 0.45 s slack but close to it. The car is now placed one PreSimulation step
  short, so at Heartbeat it is exactly on the plan. Offline, every touch is now within one frame after the planned
  time at 15, 30 and 60 fps. The "no hit registered (overlapping)" check uses the overlap at the last Heartbeat.

**2. Side rows tilt the car after the hit (side 150 a5 / a20, minUp 0.70-0.79 in 3 of 6).** Fixed by changing only
the arcade hit response:

- From the touch until the end of the hit window plus `Arcade_AntiRollExtra` (0.25 s), CarController holds the up
  axis the car had at the touch. A client-side AlignOrientation (PrimaryAxisParallel, so yaw stays free) is enabled
  only in that window.
- A per-step yaw-only projection runs in the same window: pitch and roll rate are removed, and the up axis is put back
  if it drifted more than `Arcade_AntiRollSnapDeg` (3 degrees).
- Switch: `Arcade_AntiRoll` (true; set it to false to turn this off live).
- Grip, drift grip, suspension, damping, mass and air damping are unchanged (static test `ArcadeHitScope`).

TestKit side:

- minUp is still measured over 2 s. Once the hit response is over (the window + 0.3 s), the car is now braked gently
  (120 studs/s², under the jobs bump detector).
- Round 6's side 150 rows went on at about 145 studs/s for the whole 2 s, about 290 studs, off the end of most
  straights into kerbs and scenery. That is ordinary driving, not the hit response, and it is the likeliest source of
  the tilt. This cannot be verified offline, so the row now prints when (`minUp ... at +0.21 s`) and over what (on /
  off road, part name) the car was lowest.
- The car's collisions come back on only once it is clear of every solid part that is not road, so turning them on
  never pops it out of a kerb or a palm.

**3. side 70 a25 "speed at the hit 33/37/40" (approach-min 69), r2 tier scrape: a second hit.** After the light
hit, my car ran alongside the traffic car while still overlapping it. When the car's 1.5 s ghost ran out,
PattayaTraffic hit it again. My car was down to 56·e^(−0.25·1.5) ≈ 38 studs/s (a scrape). TestKit read the
attributes 2 s after the first hit, so it saw the second hit. Reproduced offline (`LowClosingSpeed`: the second hit
at 1.5 s, 38.5 studs/s).

Fixes:

- A hit traffic car now stays ghosted for as long as it still overlaps my car (1-stud margin; `R.hitGhostStart` /
  `R.hitGhostStep`). Driving through it no longer counts again.
- TestKit snapshots every `Recovery_LastHit*` field in the frame the hit count changes, and counts later hits. "N
  more hit(s)" fails a row.
- Player speed (`Recovery_LastHitBefore`), traffic speed (`Recovery_LastHitTrafficSpeed`) and closing speed
  (`Recovery_LastHitVc`, plus the relative speed `Recovery_LastHitRel`) are now separate fields. The "speed at the
  hit >= 90 %" check uses the player speed. The tier comes from the closing speed.

**4. rear 70 on route 26 (r1 head-on vc 110 on key 26001; r2 a hit 0.38 s early on key 26012).** The generated lane
loops double back at corners: the inner lane offset overshoots and comes back. That is 342 "swallowtails" on
`pattaya_wide`, 10 of them across a loop seam, and 895 heading-reversal samples. A car on one is drawn facing
backwards, so a rear-end looks head-on (vc ≈ 70 + 45). The arc between the two cars is also longer than the real gap,
so the touch comes early.

Route 26 replayed offline (1,020 rear 70 runs at 15 fps):

| Lanes | Head-on | Early | Other wrong |
| --- | --- | --- | --- |
| Raw | 8 | 110 | 77 (curves) |
| Cleaned | 0 | 0 | 73 (curves) |
| Cleaned + TestKit's filter | 0 | 0 | 0 (220 runs) |

Fixes:

- **Lane cleanup.** `R.cleanLanePolyline` / `R.cleanLaneLoop`, used by `buildTrafficRoutes`, so PattayaTraffic,
  TestKit and the server all use the same cleaned lanes. Every loop is cleaned across its seam too, still starts
  where it started (or at the crossing point that replaced a cut first point), and closes exactly. 9 reversal
  samples are left, in junction shapes. Total lane length changes by −1.5 %, so the traffic sits at slightly
  different places than before (everyone agrees, since all of them use the shared maths).
- **Seam and wrap.** The data closed its loops only within 0.45 studs; now it is exact.
  - `s` wraps continuously, and `R.trafficHeading`'s point 6 studs on and `R.routeStraight` work across the seam.
  - Tested: a rear-end planned to touch exactly on a loop seam, and a car crossing every seam of the real data
    never turns round.
- **Target filter.** TestKit stages a hit only where the whole approach stays within `R.STAGE_BEND_DEG` (15 degrees)
  of one direction. For side hits, the target's heading must also stay steady within `R.SIDE_STEADY_DEG` (1 degree)
  around the touch.
- **Side plan.** It now runs straight at the angle to the target's heading at the touch, using the shared position
  and heading at that time, no longer along the lane. On gently curving lanes the lane direction where my car was
  differed from the target's heading by up to 5 degrees. side 150 a5 / a20 and side 100 a10 sit 1-3 degrees from a
  tier threshold (offline: 10-13 wrong tiers of 3,199 before this).
- **Low relative speed** (the owner's rear 70 review), tested at 15, 30 and 60 fps for rear vc 2, 5, 10, 20 and 25
  on a straight and on a seam:
  - exactly one hit, in the first frame after the planned touch;
  - normal on the rear face;
  - vc equal to the speed difference;
  - the table's tier;
  - no repeat while my car pushes on through it.

**5. side 150 a5 r3 MISSED "no hit registered (overlapping)".** Not reproducible offline: no such miss on the cleaned
lanes with the filter, in about 2,900 staged hits per frame rate. The likely causes are a lane kink (item 4), or an
auto-upright still turning the car over (CarController ignores hits then).

- TestKit now waits for an auto-upright to finish before a row.
- A miss now says why:
  - whether PattayaTraffic found a touch (`Traffic_Touches`, `Traffic_TouchKey`);
  - whether CarController ignored it (`Recovery_HitIgnored`: bad payload / not driving / arcade off / car anchored /
    auto-upright running);
  - whether the target was real, ghosted or had no model.

### 14.2 What a matrix row prints now

```
PASS 15fps r1  9 hitTest side @150 a5 [arcade, isolated, Heartbeat 15 Hz, render 15 fps]: hit | target 84002,
  hit 84002, match | impact 148, traffic 40, closing 13 (planned 13) | tier scrape | loss 8% (148 -> 136) |
  yaw -4 (scripted -4) | minUp 1.00 | approach-min 148 | touch meet+0.041 s, hand-off meet+0.108 s |
  lag 2.7 studs / 67 ms | table scrape 8%
```
(one line in the output; this example is from the offline simulation)

- Target traffic ID, actual hit ID and whether they match.
- Impact speed: the player's speed at the touch.
- Traffic speed, and closing speed (with the planned closing speed).
- Hit tier, speed loss (before → after), measured yaw (and the scripted kick), minUp (and when it was lowest).
- Heartbeat and render rates.
- The touch time and the TestKit hand-off time against the planned meeting.
- The drawn-vs-computed lag (diagnostic only).

A failing row (or every row with `verbose = true`) is followed by its per-frame log:

- the plan and the touch (key, vc, normal);
- the last 10 approach frames and the first 6 after the hit, each with:
  - my speed and velocity, the target's speed and velocity, the distance between the centres;
  - the relative speed;
  - the box overlap test on the computed boxes (vc, normal, depth);
- when collisions came back, when the braking started, and the lowest up.

Per frame-rate level: `hitMatrix @15 fps: 36/36 PASS over 3 runs (Heartbeat 15 Hz, render 15 fps) - REPEATABLE`.
The line warns when the rates measured were below the cap.

### 14.3 Offline checks (tools/qa/tests/test_recovery.py)

- `LaneCleanup`: synthetic swallowtail / U-turn / corner / seam cases, plus the real data (342 cut, reversals 895 →
  9, exact closure, starts kept, seams continuous).
- `StagedRealRoutes` (real data): every row of the owner's table, about 2,900 staged hits at each of 15, 30 and 60
  fps, staged like TK.hitTest and tested every frame like PattayaTraffic: all meet on time with the table's tier. The
  raw lanes without the filter get them wrong, and route 26 rear 70 reproduces the head-on and early hits.
- `LowClosingSpeed`: rear vc 2-25 at 15 / 30 / 60 fps, straight and on a seam; and side 70's second hit (old ghost)
  against no second hit (hold).
- `AntiRollAndNearMiss`: the yaw-only maths, and near misses at 15 / 30 / 60 fps:
  - a pass 5 studs beside the car at 110 pays once;
  - 9 studs (outside the 7-stud band), 60 studs/s (below 70), or a touch pays nothing;
  - a second near miss within 0.6 s is not paid;
  - the staged pass that TK.nearMissTest drives gives one near miss and no hit.
- `ServerTwoPlayers`: PattayaRecoveryServer in a mocked server with three drivers.
  - A real heavy or head-on hit beside a traffic car is accepted.
  - Refused: a report far from traffic, from a stopped car, a light tier, vc 1000, NaN, a second report within 1 s,
    and a flood of five (counted once).
  - Only the reporting player is ever named.
  - Reports are ignored with `CollisionModel = physical`.
- `TestKitSimulation`: the real PattayaTestKit in a simulated client (PreSimulation → physics → Heartbeat, stand-in
  PattayaTraffic and CarController on the shared maths), on synthetic straights and on the real map.
  - `hitMatrixStart` 12/12 at 15, 30 and 60 fps, with every owner field on every row, also with the other handler
    order.
  - `hitMatrix({fps = 30})` runs capped at 30 Hz, and the cap is removed at the end and when the matrix errors.
  - A later second hit does not replace the staged hit's numbers.
  - A hit naming another key is rejected.
  - A stopped matrix leaves no hook and no driven car.
  - `nearMissTest` cases, and `jobWatch` (one bump per accepted heavy hit, pay-out, a double bump caught).
- `ArcadeHitScope` (static):
  - the AlignOrientation exists and is enabled only in `antiRollOn`, called only from the arcade `applyImpact`;
  - the car physics constants are unchanged;
  - no script sets `CollisionModel`;
  - the hit key and telemetry are written before the count, and the misses are diagnosed;
  - TestKit identifies hits by key;
  - PattayaTraffic and CarController act on the local player's own car only, and the jobs hook counts per player.
- `TrafficKeys` (TestKit in a mocked client):
  - selfCheck passes with the models drawn 0.1 s ago, and reports the 3+ studs as a diagnostic (comparing at "now"
    with 4 studs would have failed);
  - it fails without DrawT;
  - `TK.fpsLimit` / `TK.cleanup` / `TK.stopAll`;
  - `TK.jobPayout`.

### 14.4 Studio procedures (leader)

Install PattayaRecovery, PattayaTraffic, CarController, PattayaRecoveryServer and PattayaTestKit together.
PattayaTraffic stamps DrawT, and TestKit's selfCheck fails without it.

**A. Hit matrix at 15 / 30 / 60 fps.**

1. Server: `workspace:SetAttribute("CollisionModel", "arcade")`.
2. Client:

   ```lua
   local TK = require(game.ReplicatedStorage.PattayaTestKit)
   print(TK.selfCheck()) -- expect 5/5 match, positions: shared
   local h = TK.hitMatrixStart({runs = 3, fps = {15, 30, 60}})
   print(h:poll()) -- repeat until done; h.lines has every line
   ```

3. The 60 fps level needs the Studio window focused. Alternatively run each level on its own, e.g.
   `TK.hitMatrixStart({runs = 3, fps = 60})` with Studio focused.
4. Expect one "hitMatrix @N fps: 36/36 PASS ... REPEATABLE" line per level, and a summary. The FPS cap (TestKit
   only, busy wait) is removed when the matrix ends, also on error or `h:stop()`.

**B. Near miss with arcade on.**

- `TK.nearMissTest()` pays one near miss and causes 0 hits.
- `TK.nearMissTest({gap = 9})` and `TK.nearMissTest({speed = 65, lead = 20})` pay none.

**C. Taxi / Delivery economy with arcade on.**

1. `local w = TK.jobWatch()`.
2. Start a taxi job. Drive into traffic once hard (a rear-end above about 100 studs/s = heavy) and once lightly. Finish
   the job.
3. `print(w:report())`. Expect one bump per accepted heavy / head-on hit, none for light ones, no two bumps within
   1 s, and "jobPayout ... PASS" (money = floor(fare × (1 − min(bumps × cut, 0.6))) + tip).
4. Drive by hand during a job. TK.hitTest teleports the car to its start spot, which can trip the job's 260 studs/s
   teleport check.

**D. Two players (Test > Clients and Servers, 2 players).**

1. Server: `workspace:SetAttribute("CollisionModel", "arcade")`.
2. Client 1, near traffic: `TK.hitTest("rear", 150)`. Its `Recovery_HitCount` goes up. On the server,
   `game.Players.Player1:GetAttribute("TrafficHits")` goes up by 1.
3. Client 2, watching nearby: its own `Recovery_HitCount` stays the same, and its car is not moved.
4. Client 2, parked far from traffic: `game.ReplicatedStorage.PattayaRemotes.TrafficHit:FireServer("heavy", 90, 120)`.
   Player2's `TrafficHits` stays nil (the fake is refused).
5. Repeat with the roles swapped. Near misses (B) are per player too.

**E. Cleanup.**

1. `print(TK.cleanup())`. Expect "nothing left over" (it clears staged runs, the FPS cap, `TK_HitTarget` and
   `TrafficGhostAll`).
2. Server: `workspace:SetAttribute("CollisionModel", "physical")`, or stop Play.

### 14.5 Arcade never becomes the default

`PattayaRecovery.DEFAULTS.CollisionModel = "physical"`, and no script sets the attribute (a test checks every Luau
file). Attribute changes made in Play are not saved, so the saved place stays `CollisionModel = physical`.

### 14.6 Risks and open points

- Nothing in this section has been run in Studio.
- The anti-roll is a constraint plus a CFrame snap during the hit window. How it feels with real contacts (kerb
  strikes inside the window) is unverified. `Arcade_AntiRoll = false` turns it off live, and the window length is
  `Arcade_AntiRollExtra`.
- The lane cleanup moves every traffic car slightly from where it was drawn before. It is consistent everywhere, but
  it changes the traffic's look at about 340 inner corners (no more backwards-facing cars).
- The target filter excludes cars on bends. If a row errors with "no traffic car to stage the hit on nearby (N
  without a model, N ghosted, N on a bend, ...)", start the matrix on a long straight (Beach Road, Second Road).
- The side rows are 1-3 degrees from a tier threshold by design of the owner's table. The 1-degree heading filter
  keeps them stable offline, but a real car's heading noise could still flip one in Studio.
- `docs/TEST_KIT.md` (not owned by this team) could list the new TestKit functions: `TK.fpsLimit`, `TK.cleanup`,
  `TK.nearMissTest`, `TK.jobWatch`, `TK.jobPayout`, `TK.drawT`, and `TK.hitMatrix({fps = ...})`.

## 15. Studio round 8 (2026-10-22, hitMatrix at 60 fps): rear @100 tips on the sidewalk (team18/arcade-econ)

**Status: offline analysis and offline tests only. Nothing in this section has run in Studio.**

### 15.1 What the leader saw

Round 7 (Studio Play) passed: hitMatrix 72/72 at 15 and 30 fps (repeatable) and near miss 3/3. At 60 fps (Heartbeat
60 Hz, leader run 2026-10-22), row 2 (rear @100) failed in 2 of 3 runs:

| Run | Target | Row 2 | Yaw (scripted) | Lowest up |
|---|---|---|---|---|
| 1 | 26013 | FAIL | 34 (53) | 0.82 at +1.43 s, "off road Sidewalk" |
| 2 | 26003 | PASS | | |
| 3 | 26017 | FAIL | 36 (53) | 0.82 at +1.43 s, "off road Sidewalk" |

In both failures the hit itself matched the table: hit key = target, heavy, closing speed 54 (planned 55), loss 48 %
(table 48 %). The collisions came back at +0.02 s and braking started at +1.22 s. The hit window was 0.67 s, plus
0.25 s of anti-roll.

### 15.2 Cause (offline analysis)

1. **The scripted spin is not short at 60 Hz.** CarController sets the yaw rate once per Heartbeat
   (`PattayaRecovery.spinProfile`). Integrated frame by frame, the rear @100 spin (scripted 53.8°) delivers:

   | Rate | Delivered yaw |
   |---|---|
   | 60 Hz | 51.6-56.1° |
   | 30 Hz | 49.4-58.3° |
   | 15 Hz | 45.0-62.8° |

   The range depends on whether CarController's handler runs before or after PattayaTraffic's in the hit frame. A
   yaw of 34-36° at 60 Hz therefore needs an outside torque: a contact.
2. **The kerb is close.** On route 26 (the matrix lane), the lane centre is a median 6.5 studs from the road edge,
   which is the 0.6-stud sidewalk kerb. On 10 % of the lane it is 3.3 studs or less (road width median 26 studs).
   The spin swings the car's front corner to the side: 7.2 studs from the lane centre at 35°, 8.1 studs at 53°. At
   53° the corner is over the kerb line on 73 % of route 26.
3. **So the corner meets the kerb during the spin.** The contact stops the rotation at about 35°, and the car slides
   on with one side over the sidewalk. The anti-roll ended at +0.92 s (0.67 + 0.25). At +1.43 s the car tipped to
   0.82: after the anti-roll, but inside the 2 s watch.
4. **Why only at 60 fps:** probably not the frame rate. It depends on where the target is on route 26: targets 26013
   and 26017 failed and 26003 passed in the same session, and at 15 / 30 fps the targets were elsewhere. The new
   diagnostics (15.4) will show it in the next run.

### 15.3 The fix (arcade only, a live switch)

- `PattayaRecovery.DEFAULTS.Arcade_AntiRollHeavyExtra = 1.5`: seconds after the hit window, for heavy and head-on
  hits only.
- New pure function `PattayaRecovery.antiRollHold(tier, window, cfg)`. It returns window + `Arcade_AntiRollExtra`,
  and for heavy / head-on hits at least window + `Arcade_AntiRollHeavyExtra`.
- `CarController.applyImpact` now calls `antiRollOn(chassis, up0, now + Recovery.antiRollHold(res.tier, window, cfg),
  cfg)`. Before, it used `now + window + cfg.Arcade_AntiRollExtra`.
- For rear @100 the anti-roll now holds to +2.17 s (0.67 + 1.5) instead of +0.92 s, so through the slide over the
  kerb and to the end of the 2 s watch. Yaw stays free; only roll and pitch are held.
- Unchanged: light and scrape hits (window + 0.25 s), physical mode, car physics outside arcade, the hit table and
  the tier numbers.
- `workspace:SetAttribute("Arcade_AntiRollHeavyExtra", 0)` brings back the round 7 behaviour live.
- **Owner decision needed.** Round 6 limited the anti-roll to the hit window (+0.25 s). This keeps it 1.5 s longer
  after heavy and head-on hits, in gameplay too. While it holds, the car keeps the up axis it had at the touch, so it
  cannot follow a slope for that time (the Pattaya roads are flat).

### 15.4 Diagnostics added to TK.hitTest (never a gate)

- A new per-row log line: `diag: the spin reached +X deg at +T s (scripted Y); off the target's lane up to +L studs
  (+ = right; the near kerb is on the left), at the lowest up ...; touched: <every part that is not road>`.
- The `after:` line now names the real anti-roll hold: `+1.50 anti-roll` after heavy hits.
- The row line shows `yaw A (spin B, scripted C)`. The result also carries `res.spinYaw`, `res.contacts` and
  `res.laneMax`.
- The pass criterion is unchanged: minUp ≥ 0.85 over the 2 s, and every case must match. The test driver's braking
  stays tied to `Arcade_AntiRollExtra`, as in round 7.

### 15.5 Proposal for the owner (not implemented): kerb contact after the hit window

The criterion is kept as it is. A car that slides sideways into a 0.6-stud kerb at about 50 studs/s after the hit
window is ordinary car physics, which happens without traffic too. Three ways to handle it, each needing the owner's
yes:

- **(a) Recommended: keep the criterion and the fix in 15.3.** The anti-roll covers the slide after heavy and
  head-on hits, in gameplay too.
- **(b) Change what the 2 s check measures.** Measure minUp ≥ 0.85 up to the end of the hit's anti-roll hold, and
  report any tilt after it as information.
- **(c) Change where the matrix hits.** Stage the matrix only on lanes at least about 9 studs from the kerb (the
  corner swing of a 53° spin). This is a test-side choice, not a game change.

### 15.6 Studio check (leader)

1. Install PattayaRecovery, CarController, PattayaTraffic, PattayaTestKit and PattayaTestKitServer from this branch.
2. Client, with Studio focused: `TK.hitMatrixStart({runs = 3, fps = 60, verbose = true})`. Poll `h:poll()` until
   done. Expect `hitMatrix @60 fps: 36/36 PASS ... REPEATABLE`. Row 2's `diag:` lines show whether the kerb stopped
   the spin.
3. Then `TK.hitMatrixStart({runs = 3, fps = {15, 30}})`. Expect 72/72, as in round 7.
