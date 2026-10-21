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
