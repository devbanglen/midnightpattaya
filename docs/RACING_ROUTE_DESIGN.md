# Racing route design

Background research on RayCity's race systems: `docs/RAYCITY_RESEARCH.md`. What is built follows its Phase 1
recommendations: a lap race on a real-road loop, a street challenge on a server-picked route, a RayCity-style
nitro gauge, and money/EXP for every race.

## 1. Pattaya Central Loop (lap race)
Generator: `tools/mapgen/gameplay_layout.py` (config block `layout`). Runtime: `PattayaRaceServer`, `PattayaRaceClient`.
- The route is built from legs named by OSM road names: Beach Road (Pattaya Sai 1) southbound → Pattaya Tai →
  Pattaya Sai 2 northbound → Pattaya Klang → back to Beach Road. These are the real one-way directions.
  Each leg is a Dijkstra path between the junctions where the legs meet, and every route edge keeps its OSM way id.
- Length is 6,647 studs per lap (1.86 km in game), 2 laps, 22 checkpoints about 300 studs apart.
- Every checkpoint stays at least 35 studs from any 3-way or bigger junction. Gates are judged by plane crossing,
  so a gate on a junction never counted a lap: a car turning in from the crossing road is already past the plane.
  The automated test caught this.
- Gate width is the width of the route edge at the gate's position along the route, plus 6 studs.
- The route centreline (one point every 20 studs, starting at gate 1) is the attribute `Path` on
  `PattayaWorld.Race`. It is used for GPS, the minimap and the tests.
- 6-slot start grid behind gate 1, with `PattayaSpawn` behind the grid.

Rules (server):
- A gate counts when the car's path between two samples crosses the gate plane going forwards, within the gate
  width plus 12 studs.
  - This is edge-triggered, so a car parked in the finish gate cannot restart the race.
  - A late network sample cannot jump over a gate.
- Start: cross gate 1 going forwards. Pass the gates in order. Finish: cross gate 1 after the last lap.
- Teleport check: if the car moves faster than 260 studs/s between two gates, the run is invalid. Nitro top
  speed is 215.
- Reward: money = distance/25 + 3 × (average speed above 90) + 150 for a personal best. EXP = distance/50.
- Each checkpoint adds 15 nitro.

## 2. Street Sprint (point-to-point challenge on the live streets)
Runtime: `PattayaSprintServer` (route finding on `ServerStorage.PattayaData.graph`) and `PattayaSprintClient`.
- While driving, press **H** (or tap the SPRINT button on mobile). The server takes the nearest junction within
  400 studs, preferring one ahead of the car.
  - It runs Dijkstra over the real road graph. Sois cost 1.6×, so main roads are preferred.
  - It picks a random destination 1,500–2,600 studs away.
  - It places checkpoints every ~250 studs, ending at the destination.
- On the client:
  - Gates appear only for this player: cyan posts, gold for the next one, white for the finish.
  - A gold GPS arrow above the car points at the next checkpoint. The HUD shows distance and time.
- A checkpoint counts when the car's path since the last sample passes within 26 studs of it.
- Limits and checks: 150 s time limit, the same 260 studs/s teleport check, and the run stops if you leave the car
  or start the loop race.
- Reward: money = distance/20 + 2 × (average speed above 90). EXP = distance/40. Each checkpoint adds 20 nitro.
- A RayCity-style "challenge another driver" (two players) is not built yet. This is the solo version.

## 3. Nitro gauge (RayCity SP style, in `CarController`)
Capacity 100.
- Drain: 28 per second while boosting (Shift + throttle).
- Refill: 4 per second always, plus 14 per second while drifting above 40 studs/s, plus 15 or 20 per checkpoint.
- Boosting raises top speed from 160 to 215 studs/s.
- Shown as a bar above the speedometer, orange while boosting.

## 4. Progression (`ServerStorage.PattayaProgress`)
- leaderstats: Level, Money (฿), EXP. EXP needed per level = 100 + 60 × (level − 1).
- A reward toast is shown on screen (`LastReward` attribute).
- Data is saved with DataStoreService under `PattayaProgress_v1`. In Studio this needs "Enable Studio Access to
  API Services". Without it the values last for the session only; the code handles that with a warning.

## 5. Taxi and delivery jobs (RayCity missions)
Generator: `job_stands` in the `layout` config block. `gameplay_layout.py` snaps each OSM POI to the kerb lane of
the nearest non-express road (skipped if that road is more than 220 studs away). `export_roblox.py` writes
`jobs.luau`. Runtime: `PattayaJobsServer`, `PattayaJobsClient`. Route finding uses `ServerStorage.PattayaRoute`, which
Street Sprint also uses now.
- There are 12 stands. Taxi (yellow): Central Festival, Terminal 21, Walking Street, Alcazar, Tiffany's, Art in
  Paradise, Pattaya Police Station. Delivery (green): Made in Thailand Night Plaza, Bua Khao Market, Wat Chai Mongkhon
  Market, Hong Tu La Night Market, Windy Plaza. Bali Hai Pier was skipped because no road is within reach (the OSM
  node is at the end of the pier).
- To take a job, stop (below 30 studs/s) inside a stand's ring and press **E** (Y on a gamepad, a TAXI/JOB button on
  mobile). The server picks another stand 900 to 3,200 studs away by road.
- On the client you get a GPS line drawn on the road (RayCity auto-navigation), a beacon at the destination, a gold
  arrow over the car, and a HUD with distance, time left and fare.
- The route is only a guide; any way there counts. Stop inside the destination ring to finish. Press E again to
  cancel.

| | Taxi | Delivery |
|---|---|---|
| Time limit | 20 s + length/70 | 15 s + length/85 |
| Fare | 60 + length/10 | 80 + length/8 |
| EXP | length/18 | length/22 |
| Each knock | −12% | −15% |
| Tip | 1.5 ฿ per second left | 2 ฿ per second left |

- Knocks are capped at −60% in total.
- **What counts as a knock:** ground speed is measured from the car's position at 10 Hz. A knock is a drop of more
  than 55 studs/s within 0.35 s that holds for two samples.
  - Full braking (130 studs/s²) loses at most 45 studs/s in that window, so it never counts.
  - Replicated velocity was tried first and gave false knocks on corners.
- The job fails if the time runs out ("Too late! The customer left") or you leave the car. The same 260 studs/s
  teleport check applies, measured once a second.
- You can't take a job during a race or sprint, and you can't start a sprint or race during a job.
- Near misses past traffic add 5 ฿ each to the tip (section 6).

## 6. Ambient traffic and near misses
Generator: `tools/mapgen/traffic.py` (config block `traffic`) writes `traffic.json`. `export_roblox.py` turns it into
`traffic.luau`, which goes to `ReplicatedStorage.PattayaTraffic`. Runtime: `PattayaTraffic` (LocalScript); the
near-miss remote is handled in `PattayaJobsServer`.
- **Loops:** 36 closed loops, 464 cars, about 420 studs apart on each loop at 38–55 studs/s (roughly 40–55 km/h).
  - Each loop is a random walk over the directed road graph that keeps to main roads 85% of the time and respects
    one-way streets, closed with a shortest path back to its start.
  - Cars drive in the **left** lane (Thailand), offset a quarter of the road width from the centreline.
- **Same traffic for everyone:** each car's position is a pure function of the server clock, so every client shows
  the same traffic with no network cost. Only cars within 650 studs of the camera get a model, from a pool of at
  most 70: sedans/taxis (pink and green cabs have a TAXI-METER light), blue songthaews (baht buses) and vans, with
  head and tail lights.
- **Crashes:** traffic is solid for your own car (client physics), so hitting it is a real crash. That gives a
  knock during a job.
  - If you are stopped or slower in front of a traffic car, it turns into a ghost for 1.5 s and drives through you
    instead of shoving you.
  - Driving into one head-on is still a crash.
- **Near miss:** pass a traffic car end to end with less than 7 studs of side gap, without touching, at 70+ studs/s.
  - The client reports it. The server can only sanity-check, because traffic is client-side: you must be in a car
    at 60+ studs/s, at most one every 0.6 s.
  - Pays 6 + 2 × combo nitro, where the combo grows while near misses come within 4 s of each other, up to 10.
  - During a job it adds 5 ฿ to the tip. A "NEAR MISS x3" toast is shown.
- **Known limits:**
  - Traffic cars don't stop for each other, for junctions or for traffic lights; they pass through each other at
    crossings.
  - Traffic also runs on the loop race roads.
  - Other players' cars are not avoided. Each client only knows its own car.

The loop race also ignores any sample-to-sample jump longer than 60 studs. In testing, a teleport (respawn or a
test move) from the grid across gate 1 started a race.

## 7. Street Challenge (RayCity 1-on-1 on the live streets, up to 4 cars)
Runtime: `PattayaChallengeServer`, `PattayaChallengeClient`. The race itself is drawn by `PattayaSprintClient` (gates,
GPS arrow, HUD with position). Routes come from `PattayaRoute.pointToPoint`, which Street Sprint also uses.
- **Challenging:** while driving, press **C** (L1 on a gamepad, a RACE button on mobile). This challenges the nearest
  free driver within 150 studs. They see "NAME challenges you!" and have 10 s to press **Y** (accept) or **N**
  (decline). You can send at most one request every 3 s.
- **No driver near:** an AI street racer (Ae Turbo, Nong Benz, Somchai R, …) pulls up in a copy of one of the
  parked cars and races you.
  - Its speed profile comes from route curvature: 135 studs/s top speed, a lateral-grip limit in corners, braking at
    110 studs/s² and accelerating at 45.
  - It is a ghost: no collisions. It is the base for RayCity-style Road Fight bosses later.
- **Start:** the route starts at the junction nearest the cars, 1,500–2,600 studs long with checkpoints every 250.
  Cars are placed side by side at its start and held (anchored) through a 3-2-1-GO countdown.
- **Rules:**
  - Checkpoints are passed in order, within 26 studs.
  - First to the last checkpoint wins.
  - Overall limit 180 s. Everyone else is out 60 s after the winner.
  - Leaving the car forfeits. The 260 studs/s teleport check applies.
  - Catch-up: a driver behind the leader gets 30 nitro per checkpoint instead of 20.
- **Pay:**
  - Winner: length/15 + 100 × (cars − 1) ฿ and length/30 EXP.
  - Others who finish: length/40 ฿ and length/60 EXP.
  - Did not finish: nothing.
- While a challenge, sprint or job runs, the loop race panel hides so its banner doesn't cover the HUD.

## 8. Road Fight (RayCity single-player bosses)
Generator: `road_fight` in the `layout` config block. Bosses are snapped to roads like job stands, written to
`roadfight.luau` and loaded as `ServerStorage.PattayaData.roadfight`. Runtime: in `PattayaChallengeServer`, which
reuses the Street Challenge race engine, and `PattayaChallengeClient` for the E prompt.

| Order | Road Master | Spot (OSM) | Car | Top speed / corner grip | Course |
|---|---|---|---|---|---|
| 1 | Walking Street Wolf (South Pattaya) | Royal Garden | jdm_coupe | 128 / 140 | 1,974 studs |
| 2 | Beach Road Baron (Central Pattaya) | Basaya Beach Hotel | muscle | 142 / 150 | 2,283 studs |
| 3 | Naklua Night Hawk (North Pattaya) | The Beach Garden Resort | gt_sedan | 155 / 165 | 2,527 studs |
| 4 | **Road King** | "Pattaya" city node | supercar | 172 / 185 | 3,358 studs |

- **Starting a fight:** each boss has a red ring (gold for the King) with a sign, and its car parked in front of the
  ring. Stop in the ring and press **E** (Y on a gamepad, a FIGHT button on mobile). The boss says its line and the
  race starts.
- **Fixed course:** each boss always races its own course. It starts from the junction nearest its spot and the
  route pick is seeded, so it is the same every time and can be learned.
- **Order:** beat them South → Central → North. The King unlocks after all three. A locked ring says who to beat
  first.
- **Rewards:**
  - First win: 300 / 400 / 500 / 1,000 ฿ and 150 / 200 / 250 / 500 EXP. Rematches pay a third.
  - Losing (finishing 2nd) pays a little EXP and no money.
- **Titles:** "Road Fighter" after the three Road Masters, "Road King" after the King. The title shows in a new
  leaderboard column, `Title`.
- **Saving:** wins (attribute `RoadFight`, one bit per boss) and the title are saved with the player's progress.

## 9. Scheduled events: Night Run and Survival (RayCity Jilju/Pokju and Survival)
Runtime: `PattayaEventsServer` (schedule, gathering, rounds, pay) and `PattayaEventsClient` (banner, GPS arrow, J
to join). The race itself runs on `ServerStorage.PattayaStreetRace`, the engine shared with Street Challenge and Road
Fight. Gates, HUD and countdown come from the usual `PattayaSprintClient` and `PattayaChallengeClient`.

**Not playtested yet.** Everything below describes the design as built in code.

### Shared race engine (`PattayaStreetRace`)
This code moved out of `PattayaChallengeServer` and is meant to behave exactly as before:
- the AI racer: model, speed profile and step
- grid placement, with the cars anchored through the 3.5 s countdown
- ordered checkpoints within 26 studs, and standings every 0.5 s
- catch-up nitro (30 instead of 20)
- leaving the car forfeits; the 260 studs/s teleport check
- the time limit, DNF after the winner, and the Challenge payout

`startRace(parts, opts)` takes these options: a title, a route function, the time limit, the DNF delay, the forfeit
text, `gridAlongRoute`, a start banner, and `onResult` / `onEnd` callbacks. With `gridAlongRoute`, a big grid follows
the road instead of a straight line. Challenge uses the defaults. Road Fight passes its seeded course, its own payout
and the boss reset.

### Schedule and joining
- **Schedule:** every **15 real minutes** (`CONFIG.intervalMinutes`) the server announces an event **60 s** ahead
  (`CONFIG.leadSeconds`). Every 3rd event is Survival (`CONFIG.survivalEvery`). The others are Night Run.
- **Name:** it follows the clock, as RayCity did with Jilju by day and Pokju at night. It is **NIGHT RUN** (purple)
  when `ClockTime` is after 17:48 or before 06:18, and **DAY RUN** (gold) by day. Survival is red.
- **Start point:** a junction on a main road (tier 2, at least two roads). When someone is driving, it is 150–1,500
  studs from a random driver. The route is picked when the event is announced.
- **Gathering ring:** a ring 90 studs across marks the start. It has a 260-stud neon beacon and an always-on-top
  label ("NIGHT RUN / JOIN HERE 0:42 (3)").
- **On every client:** a banner with the countdown and the distance to the ring. Until you join, a coloured GPS arrow
  floats over your car.
- **To join:** drive into the ring, or press **J** while driving within **1,500 studs** of the ring
  (`CONFIG.joinRadius`). J is R1 on a gamepad and the JOIN button on mobile. Players who join with J are moved onto
  the grid at the start.
- **While waiting:** joined players count as busy (`SprintActive`), so they can't start a sprint, job or challenge.
- **At the start:** players who are not in their car, or are in a job or a loop race, are dropped with "You missed
  the start". If nobody is left: "cancelled - nobody joined".
- **Grid size:** up to **16** entrants. AI street racers fill the grid up to **6 cars**: always for Survival, and for
  a Night Run when fewer than 2 humans joined. So both work with a single player.

### Night Run / Day Run
- **Route:** one long point-to-point route of **2,500–4,500 studs**, with checkpoints every 300 studs. Main roads are
  preferred (sois cost 1.6×).
- **Grid:** several rows on the road itself, two cars per row, 20 studs between rows.
- **Limits:** 240 s. Anyone still racing **45 s after the winner** is out. Leaving the car also puts you out, and
  pays nothing.
- **AI racers:** top speed 125–150 studs/s, corner grip 150.
- **`EventActive`:** set to `true` on every human entrant from the start until their result.
  - **Needed in `PattayaJobsServer`** for extra near-miss nitro during events. In the NearMiss handler, replace the
    `NitroBonus` line with:
    `NitroBonus:FireClient(plr, (6 + 2 * ns.combo) * (if plr:GetAttribute("EventActive") then 2 else 1))`
- **Pay** (n = cars on the grid, h = human entrants, p = place):

| | Money | EXP |
|---|---|---|
| Finisher | length/25 + 20 × (n − p) + podium × (1 + 0.25 × (h − 1)) | length/40 + 10 × (n − p) |
| Podium bonus | 1st 200, 2nd 100, 3rd 50 | – |
| Did not finish / left the car | 0 | 0 |

  Example: a 3,500-stud route with 6 cars and 1 human. A win pays 140 + 100 + 200 = 440 ฿ and 137 EXP.
- At the end, everyone on the server gets "NIGHT RUN won by NAME 74.20 s".

### Survival
- **Gathering:** the same as Night Run.
- **Rounds:** **4** (`CONFIG.survival.rounds`, clamped to 3–5). Each round is a short route of **1,000–1,600
  studs** that starts where the last one ended. There is a 7 s break between rounds.
- **Ranking after each round:**
  1. finishers, by place
  2. drivers who did not finish, by progress
  3. drivers who left the car
- **Elimination:**
  - The slowest **20%** are out (rounded down, **at least 1**), plus anyone who left the car.
  - It is **never everyone**: the best of them stays in.
  - With 2 drivers left, or in the last round, the round is the final, and its winner wins.
- **Round limits:** 120 s. A driver still racing 25 s after the round winner has not finished and is ranked by
  progress.
- **Equalised cars:**
  - Entrants get `Equalised = true` and `SpeedCap = 150` (studs/s) until they are out.
  - The garage/car-class teammate is making `CarController` honour these.
  - AI racers in Survival run at 128–142.
- **Pay:**
  - 40 ฿ + 20 EXP per round survived, paid when you are out.
  - Winner: 600 ฿ + 300 EXP, plus the round pay for every round.
  - The winner also gets the title **"Survivor"** if they have no title yet. Road Fighter and Road King are kept.
- If every human is out, the best remaining AI is announced as the winner.

### Config and test hooks
- **Constants:** `CONFIG` at the top of `PattayaEventsServer`.
- **Live overrides:** attributes on that script: `IntervalMinutes` (0 = no schedule), `SurvivalEvery`,
  `LeadSeconds`.
- **Force a start** from the Studio command bar (switch it to **Server** in Play):
  - `game.ServerStorage.StartEvent:Fire("nightrun", 15)`
  - `game.ServerStorage.StartEvent:Fire("survival", 15)`
  - The number is the lead time in seconds (at least 5).
- **Public state:** attributes on `ReplicatedStorage.PattayaEvent`: Phase (idle/gathering/running), Kind, Title,
  StartAt, RingPos, Entrants, Round, Rounds, Alive, NextAt.
- **Per-player attributes:** `EventJoined`, `EventActive`, `Equalised`, `SpeedCap`.

### Test plan (Studio Play, 1 player, then 2 players)
1. Get in a car. In the command bar (Server), run `game.Lighting:SetAttribute("TimeLock", 21)`, then
   `game.ServerStorage.StartEvent:Fire("nightrun", 20)`.
   - Expect a toast "NIGHT RUN in 20 s!" and the banner with the countdown and the distance to the ring.
   - Expect the purple beacon in the distance and a purple arrow over the car.
2. Press J (within 1,500 studs). Expect "You're in!" and the banner "you're in! (1 drivers)". H and C now do
   nothing.
3. At 0:
   - The car is moved onto the grid, and 5 AI racers line up behind it on the road.
   - The 3-2-1-GO countdown plays, and the car is held until GO.
   - The HUD shows `NIGHT RUN CP 1/n … P1/6`, and a toast says "NIGHT RUN 6 cars x.x km".
4. Drive (or use the autopilot) through all gates.
   - Expect a "NIGHT RUN WINNER!" or "kth place of 6" toast, and a reward toast with the pay from the table.
   - Expect the server-wide "won by" message.
   - `EventActive` is set while racing and cleared after.
5. Repeat and get out of the car mid-race. Expect "Left the car - out of the NIGHT RUN" and no pay. The AI cars
   disappear after the race ends.
6. Set `TimeLock = 12` and start again. The event is called DAY RUN, with a gold ring.
7. Drive into the ring instead of pressing J. You join as soon as the car is inside the ring.
8. Start with nobody joining. Expect "cancelled - nobody joined", the ring removed, and no errors.
9. Run `StartEvent:Fire("survival", 15)` and join.
   - Expect `SURVIVAL R1/4`, and the `Equalised`/`SpeedCap` attributes on the player.
   - After each round, expect "Round 1 survived! Eliminated: NAME. 5 left", or "ELIMINATED in round k of 4" with
     the round pay.
   - Expect a 7 s break, then the next round starting where the last one ended.
   - The final winner gets 600 ฿ plus the round pay, and the title "Survivor" if they had no title.
   - The attributes are cleared at the end.
10. Regression: these must behave exactly as in the "Tested" section, with the same messages and pay:
    - Street Challenge vs AI (C)
    - Challenge between 2 players (C/Y)
    - a Road Fight win and a loss
    - Street Sprint (H)
11. With 2 players, both join. Expect no AI in the Night Run, both players in the standings, and pay using h = 2.
12. Set `IntervalMinutes = 1` on the script and wait. An event is announced automatically about 1 minute later.

## Tested (2026-10-18, Studio Play, client-owned car moved by a client-side test autopilot at 140 studs/s)
- **Jobs:**
  - Delivery Windy Plaza → Wat Chai Mongkhon (2,135 studs): road under the car at 116/116 samples. It paid, but the
    old velocity-based knock check counted 2 knocks for 1 staged crash, which led to the fix above.
  - After the fix, taxi Central Festival → Night Plaza (2,327 studs, limit 53 s): 1 staged crash (0.4 s dead stop)
    gave exactly 1 knock, and braking at 100 studs/s² into the stop gave none. Finished in 22.1 s and paid
    292 × 0.88 + 46 tip = 302 ฿, +129 EXP.
  - A request from 80 studs away was refused. Sprint during a job was refused. Cancel cleared the job and the route
    line.
  - Waiting out the limit (46 s) gave "Too late! The customer left" and no money.
- **Traffic (Play):**
  - 58 cars around the start, moving about 44 studs/s, at 61 FPS. Screenshots show the van, songthaew and pink taxi
    in the correct (left) lane.
  - Oncoming pass with a 3-stud gap at 100 studs/s: near miss fired, with a combo of 2 (probably a second car on an
    overlapping loop).
  - Head-on crash under real physics: 57 → −14 studs/s bounce, then the traffic car ghosted through.
  - Taxi Walking Street → Windy Plaza with traffic on: 1,224 studs in 12.5 s, 0 knocks, 5 near misses accepted
    (2 sent by the test, 3 real). Tip 61 = 36 for time left + 25 for near misses, total 243 ฿. 60 FPS while driving.
- **Street Challenge vs the AI:**
  - Pressing C with nobody near brought in "Somchai R" 14 studs beside the car. The car was held through the
    countdown. Screenshot of the HUD: `CHALLENGE CP 1/9 … P2/2`.
  - Leaving the car mid-race forfeited it, cleared the gates and removed the AI car after 4 s.
  - Autopilot at 150 studs/s: P1 at halfway. "YOU WIN! 12.43 s", paid 211 ฿ (1,673/15 + 100).
  - Autopilot at 70 studs/s: the AI led, the player finished 2nd in 22.96 s and was paid 39 ฿. Catch-up nitro was 30
    per checkpoint while behind.
  - Street Sprint still starts after the refactor.
- **Street Challenge between two players** (Studio "Test → Clients and Servers", 2 players; the owner started it and
  pressed C/Y):
  - Both clients showed 7 gates with `P1/2` / `P2/2`. Cars were released after GO with each driver owning their car.
  - Player1 driven by autopilot: all checkpoints, "Finished 1st - waiting for the others".
  - Player2 then finished: "2nd place 116.70 s" (+45 ฿, +30 EXP). Player1 got "Challenge won" (+220 ฿ = length/15
    + 100, +60 EXP). Both were back to free roam afterwards.
  - Decline: Player2 saw "Player1 challenges you…", replied no, and Player1 got "Player2 declined".
  - No answer: after 10.5 s Player1 got "Player2 didn't answer" and Player2's box closed.
  - No script errors on the server (only the known DataStore Studio-access warning).
  - Seen in the test: a request sent while the two cars were still drifting apart after the autopilot stopped got
    the AI instead. The other car was over the 150-stud range at that moment (138 studs a few seconds later).
  - **Seen once and not reproduced:** a parked grid car ended up 21 studs ahead of its slot, past gate 1, after the
    player got in. That started the loop race. Getting out and back in, it moved only ~1 stud.
- **Road Fight (autopilot, one Play session):**
  - All 4 rings came up with their boss car parked. No script errors.
  - The Central ring before South said "Locked: beat Walking Street Wolf (South Pattaya) first".
  - South at 150 studs/s: "YOU BEAT WALKING STREET WOLF! 14.32 s", +300 ฿ / +150 EXP, "Unlocked: … Beach Road
    Baron".
  - Central at 80: lost ("Beach Road Baron wins. Come back faster.", 0 ฿, +28 EXP). Central at 165: won, +400 ฿.
    Both runs used the same 2,283-stud course.
  - North at 175: won, +500 ฿, title "Road Fighter".
  - King at 205 (nitro speed): won in 17.90 s, +1,000 ฿, title "Road King".
  - South rematch: same 1,974-stud course, paid a third (100 ฿ / 50 EXP).
  - Afterwards all boss cars were back in place and no race bots were left behind. Street Challenge (C) still
    started a normal AI race.
  - Not checked: how the boss stands look (the screenshot of the 3D view came back white; only the HUD rendered),
    and whether a human can actually beat the King without nitro. Its top speed of 172 is above the car's 160, so
    nitro is needed on straights.
- **Events on the shared engine (leader, 2026-10-18, after merging team/events):**
  - Regression after the `PattayaStreetRace` refactor: Road Fight South gave the same course (1,974 studs, 8 gates),
    the same messages and pay (+300 ฿ / +150 EXP, "Unlocked: … Beach Road Baron"); Central was still locked before
    South. Street Challenge vs AI: 2,465 studs, "YOU WIN! 17.60 s", 264 ฿ (= 2,465/15 + 100).
  - **Night Run** (clock locked at 21, `StartEvent:Fire("nightrun", 14)`): banner "NIGHT RUN in 0:06 - ring 67 m -
    J to join"; the join remote answered "You're in!"; 5 AI filled the grid; 3,431 studs, 12 checkpoints, won in
    24.26 s: "NIGHT RUN WINNER!" +437 ฿ / +135 EXP, server-wide "NIGHT RUN won by …". `EventActive` and
    `SprintActive` cleared afterwards.
  - A join sent while the car was outside the 1,500-stud ring radius (first Survival attempt) was ignored and the
    event was cancelled with "nobody joined", as designed. The client shows "Too far away" only when in a car.
  - **Survival** (`Fire("survival", 30)`, joined inside the ring): 4 rounds of 1,497 / 1,356 / 1,125 / 1,428 studs;
    during each round `Equalised=true`, `SpeedCap=150`, `EventActive=true`; one AI eliminated per round (6 → 3);
    "LAST DRIVER STANDING - you won SURVIVAL!"; +760 ฿ (600 + 4 × 40), title "Survivor"; attributes cleared and the
    event back to idle.
  - Not tested: a real second player in an event; the 15-minute scheduler (only forced starts); the near-miss x2
    during events; the Day Run variant by name only (clock was night).
- **Regression after the route-module refactor:** Street Sprint 1,571 studs, 6/6 checkpoints, 11.23 s, paid. Loop
  race: driving through gate 1 started it and gates 2–5 counted.
- **Loop race:** 2 laps.
  - Road under the car at 5,740 of 5,740 samples.
  - States went racing → finished, and the car stayed "finished" while parked past the line.
  - Time 94.63 s. Paid +833 ฿ and +265 EXP (Level 1 → 3).
- **Street Sprint:** 2,339 studs, 9 checkpoints, 9 local gates shown.
  - All checkpoints counted and the run finished in 17.25 s. Paid +208 ฿ and +58 EXP.
- **Teleport cheat:** jumping onto checkpoints 1 and 2 ended the run with "Run invalid (moved too fast)".
- **Nitro:**
  - 2 s of Shift+W took the gauge from 1.00 to 0.43, with the speed label at "217 km/h NOS".
  - 3.5 s without boost refilled it 0.43 → 0.55.
- Not tested: a human driving a full lap or sprint, and multiplayer.
