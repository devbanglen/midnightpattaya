# Garage, car specs and racing classes

Owner task 3 and directive section 7, "Racing classes". Status: **written, not playtested**. Nothing in this
document has been run in Studio yet. Every "expected" below is a prediction.

## Files

| File (repo `roblox/src/…`) | Studio location | What it does |
|---|---|---|
| `ReplicatedStorage/CarSpecs.luau` | `ReplicatedStorage.CarSpecs` (ModuleScript) | Stats per car, PI formula, class bands, prices, levels, upgrades |
| `ServerScriptService/RaceCarServer.server.luau` | same (Script, replaces the old one) | Sets `CarId`, `Class`, `PI`, `UpgEngine`, `UpgGrip` (and `Owner` on personal cars) on every car it builds. Adds the `ServerStorage.BuildCar` BindableFunction. A personal car throws out anyone who is not its owner. |
| `ServerScriptService/PattayaGarageServer.server.luau` | same (new Script) | Garage ring and sign, the shop remote (`PattayaRemotes.GarageRequest`), buy/select/upgrade checks, personal car spawn |
| `StarterPlayer/StarterPlayerScripts/PattayaGarageClient.client.luau` | same (new LocalScript) | E prompt in the ring, shop window |
| `StarterPlayer/StarterPlayerScripts/CarController.client.luau` | same (LocalScript, replaces the old one) | Drives with the spec of the car you sit in. Supports `Equalised` and `SpeedCap`. Shows the car name, class and PI above the nitro bar. |
| `ServerStorage/PattayaProgress.luau` | same (ModuleScript, replaces the old one) | Adds `Progress.GetData(plr, key)` and `Progress.SetData(plr, key, value)`, and the `ProgressLoaded` player attribute |

## Car stats

The hatch has exactly the old global `CONFIG` numbers, so races tested with it stay valid. `CarController` still
uses `CONFIG` as a fallback: if `CarSpecs` is missing or a car has no known `CarId`, it drives as before. Suspension
numbers (rest length, sag, damping) are the same for every car because the server's parked-car spring uses them.

Speeds are in studs/s and the HUD shows them 1:1 as km/h.

| Car | Top | Nitro top | Accel | Nitro accel | Brake | Grip | Turn | Drift grip | Drift turn | Nitro tank | Drain/s | Drift refill/s | PI | Class | Price ฿ | Level |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| hatch (Hot Hatch, starter) | 160 | 215 | 60 | 110 | 130 | 9.0 | 2.30 | 1.4 | 1.40 | 100 | 28 | 14 | 483 | Street | free | 1 |
| kei (Kei Racer) | 146 | 200 | 64 | 108 | 142 | 10.5 | 2.65 | 1.6 | 1.50 | 100 | 26 | 16 | 493 | Street | 3,000 | 1 |
| jdm_coupe (JDM Coupe) | 168 | 222 | 66 | 115 | 138 | 9.5 | 2.50 | 1.2 | 1.75 | 100 | 28 | 22 | 587 | Sport | 12,000 | 4 |
| muscle (Muscle Car) | 182 | 236 | 74 | 125 | 112 | 7.5 | 2.00 | 1.5 | 1.30 | 120 | 28 | 14 | 578 | Sport | 15,000 | 5 |
| gt_sedan (GT Sedan) | 171 | 226 | 67 | 118 | 146 | 10.2 | 2.40 | 1.4 | 1.40 | 110 | 28 | 14 | 592 | Sport | 22,000 | 7 |
| supercar (Supercar) | 188 | 240 | 74 | 130 | 150 | 10.5 | 2.45 | 1.4 | 1.45 | 100 | 27 | 14 | 695 | Super | 55,000 | 10 |

All cars share these values: reverse 45, coast drag 0.25, nitro refill 4/s.

Each car has a role:
- **kei**: cheap and agile. It has the best grip and steering for its price and brakes late, but the lowest top speed.
- **hatch**: free starter with average numbers.
- **jdm_coupe**: the drift car. It has the lowest drift grip, the biggest drift turn and refills nitro fastest while
  sliding.
- **muscle**: straight-line car with the biggest nitro tank. Its brakes and cornering are the weakest.
- **gt_sedan**: all-rounder with good brakes and no weak stat.
- **supercar**: fastest and most expensive.

The PIs (483 to 695) are close together because RayCity was criticised as "too gear-dependent". A better car helps,
but it does not decide the race.

**Road Fight:** the Road King boss has a top speed of 172. The hatch (160), kei (146) and jdm_coupe (168) need
nitro on the straights to beat him. The gt_sedan (171) is about level with him. The muscle (182) and supercar (188)
are faster. The grid cars are shared and now drive with their own specs, so a player in the grid supercar has an
easier Road Fight than before. Bosses and AI bots keep their own speed profiles, so they did not change.

**Speed ceiling:** no nitro top speed can go above `CarSpecs.NITRO_LIMIT` = 245, upgrades included. The job,
challenge and race servers treat anything over 260 studs/s as a teleport.

## Performance Index

Each stat is first turned into a 0..1 rating. These same ratings are the shop's stat bars.

| Rating | Formula (clamped to 0..1) | Weight |
|---|---|---|
| speed | (top − 120) / 80 | 0.34 |
| accel | (accel − 40) / 60 | 0.20 |
| brake | (brake − 90) / 100 | 0.10 |
| grip (handling) | average of (grip − 6) / 8 and (turnRate − 1.8) / 1.2 | 0.18 |
| drift | average of (driftTurnBoost − 1.1) / 0.7 and (nitroDriftRegen − 8) / 18 | 0.06 |
| nitro | average of (nitroTop − 160) / 90 and ((tank / drain) − 2.5) / 3.5 | 0.12 |

`PI = round(100 + 900 × Σ weight × rating)`, clamped to 100..999. The code is `CarSpecs.PI(stats)`.

## Class bands

A car's class comes from its PI, never from its name. The name strings below are the exact values of the `Class`
model attribute.

| Class | PI | Cars today |
|---|---|---|
| Street | 100–549 | hatch, kei |
| Sport | 550–649 | jdm_coupe, muscle, gt_sedan |
| Super | 650–749 | supercar |
| Hyper | 750–849 | none yet (future cars) |
| Track Spec | 850–999 | none yet (future event/track cars) |

Every spawned car model has the attributes `CarId` (string), `Class` (string), `PI` (number), `UpgEngine` and
`UpgGrip` (0–3) and `RaceCar = true`. Personal cars also have `Owner` (UserId). The circuit race system can filter
entrants on `Class`. Street Challenge bots clone `RaceCar` models, which still works.

## Upgrades (optional)

There are two kinds, engine and grip, with 3 tiers each. Each engine tier adds +2% top speed, +2% nitro top speed
(still capped at 245), +4% acceleration and +3% nitro acceleration. Each grip tier adds +4% grip, +2% turn rate and
+3% braking.

**Class rule:** a tier can only be fitted if the upgraded PI stays in the car's stock class. Upgrades never move a
car up a league, so class races stay fair. In practice that allows about 2–4 tiers per car:

| Car | Upgrades that fit (bought engine then grip, alternating) | Best PI |
|---|---|---|
| hatch | E2 G2 | 548 |
| kei | E2 G1 | 548 |
| jdm_coupe | E2 G1 | 645 |
| muscle | E2 G2 | 646 |
| gt_sedan | E1 G3 | 649 |
| supercar | E1 G2 | 744 |

The price of a tier is 12% / 25% / 45% of max(car price, 8,000), rounded to 100. For example, the hatch costs
1,000 / 2,000 / 3,600 and the supercar 6,600 / 13,800 / 24,800.

Upgrades are never required. A new tier takes effect the next time you spawn the car ("Respawn the car to use it").
The shared grid cars are always stock.

## Equalised mode (Night Run / Survival)

`CarController` reads two player attributes while driving:
- `Equalised = true`: whatever car you sit in drives with `CarSpecs.Equalised()`, the stock hatch numbers (160 /
  215, brake 130). The HUD shows "EQUALISED".
- `SpeedCap = <number>`: caps both the top speed and the nitro top speed. If you are already above the cap when it
  is set, the car eases down to it (it is not a hard brake). The HUD shows "CAP n". It works with or without
  `Equalised`.

Changes take effect immediately, even mid-drive. To clear them, set `Equalised` to nil/false and `SpeedCap` to nil.

**Both are client-trusted.** The driver's client owns the car's physics, so a cheater can ignore them. The race
servers keep their own server-side teleport and speed checks (260 studs/s). If an event needs real enforcement, its
server should also check speed per sample against `SpeedCap`.

## Ownership and save format

The garage data goes through `Progress.GetData/SetData` and is saved in the same DataStore record
(`PattayaProgress_v1`, key `p<UserId>`):

```lua
{
  level = 5, money = 1234, exp = 40, title = "", roadFight = 3,   -- unchanged fields
  extra = {                                                        -- new; GetData/SetData keys live here
    carsOwned = {hatch = true, kei = true},
    carSelected = "kei",
    carUpgrades = {kei = {engine = 1, grip = 0}},
  },
}
```

- **Older records** have no `extra` and load as an empty table, so the player owns only the hatch. The hatch is
  always added on read, even if the data is missing.
- **Load flag:** `GetData` returns nil until the record has loaded. The player attribute `ProgressLoaded = true`
  marks the moment it has. The garage refuses requests until then.
- **Save timing:** data is saved when the player leaves and when the server closes, the same as money. A purchase
  is not saved at that moment, so a server crash loses it along with the money spent.
- **New safety change:** if the DataStore read fails (a pcall error, not "no data"), that session no longer saves
  over the record. Before, a failed read was overwritten with level 1 / 0 money.

## UI flow

1. **Find the garage.** The purple neon ring and the "GARAGE · CAR SHOP" sign are at the left road edge beside
   `PattayaSpawn`, where players start. The spot is found at runtime: the server walks left from the spawn,
   relative to the grid's direction, until the ground under the ray is no longer `Road`/`Junction`, then puts the
   ring 8 studs inside that edge. To override it, place a Part named `GarageSpot` in `workspace.PattayaWorld.Race`
   (or `workspace`); its front face sets the road direction.
2. **Open the shop.** Stand in the ring on foot, or stop in a car (under 30). The prompt "E GARAGE" appears; press E
   (gamepad X, or the GARAGE touch button). It does not open during a race, sprint, challenge or job.
3. **The shop window:**
   - **Left:** the 6 cars, each with its class and PI, and a status: SELECTED, OWNED, LOCKED Lv n, or ฿price.
   - **Right:** the chosen car's name, class and PI, and 6 stat bars (Top speed, Acceleration, Braking, Handling,
     Drift, Nitro) with numbers.
   - **Main button:** BUY ฿x, LOCKED (Lv n), SELECT or SELECTED. Owned cars also show ENGINE and GRIP buttons
     ("+1 ฿x", "class max" or "MAX").
   - **Bottom:** SPAWN MY <CAR>, CLOSE, and a result message (green for success, red for refusals).
4. **Buy.** The server checks that you are near the garage and not busy, that you don't already own the car, your
   level and your money. Then it deducts the price, adds the car and selects it.
5. **Spawn.** Your selected car is built with RaceCarServer's own `buildCar`, so it gets the same wheels, body,
   parked spring and driver hiding. It is named `PersonalCar_<UserId>` and parks in the first free bay past the
   ring (4 bays, 22 studs apart). Your previous personal car is removed first; if you were sitting in it you are
   moved into the new one. If you were on foot you are seated automatically. If you were in a shared car you stay
   in it.
6. **Ownership.** Only the owner can drive a personal car. Anyone else who sits in it is thrown out and sees "That
   car belongs to someone else". A personal car is removed when its owner leaves or when it falls out of the world.
7. **Shared cars.** The 6 shared grid cars, on RaceMap and on the Pattaya grid, are unchanged and anyone can still
   drive them.

## Studio install

1. **Create the new module.** Make a ModuleScript `ReplicatedStorage.CarSpecs` and paste in
   `roblox/src/ReplicatedStorage/CarSpecs.luau`.
2. **Replace 3 existing scripts.** Replace the source of `ServerStorage.PattayaProgress`,
   `ServerScriptService.RaceCarServer` and `StarterPlayer.StarterPlayerScripts.CarController` with the repo
   versions.
3. **Add the 2 new scripts.** Add the Script `ServerScriptService.PattayaGarageServer` and the LocalScript
   `StarterPlayer.StarterPlayerScripts.PattayaGarageClient`.
4. **Enable saving (optional).** For saves in Studio, turn on Game Settings → Security → "Enable Studio Access to API
   Services".

## Studio test plan (expected results)

Run these in Play (or Start Server with 2 players for test 9).

1. **Boot.** Expected: no errors in the Output from RaceCarServer, PattayaGarageServer, PattayaGarageClient or
   CarController. `workspace.PattayaGarage` exists with Ring, Posts, Sign and SignGlow. 12 shared cars are spawned,
   6 per grid.
2. **Attributes.** Run `for _,m in workspace:GetChildren() do if m:GetAttribute("RaceCar") then print(m.Name,
   m:GetAttribute("CarId"), m:GetAttribute("Class"), m:GetAttribute("PI")) end end` in the command bar (server
   side). Expected: hatch Street 483, kei Street 493, jdm_coupe Sport 587, muscle Sport 578, gt_sedan Sport 592,
   supercar Super 695.
3. **Hatch unchanged.** Drive the grid hatch on Beach Road. Expected: about 160 km/h on throttle and about 215 with
   nitro. The HUD shows "Hot Hatch · Street 483" above the nitro bar. Then run one loop race and one Street Sprint;
   both finish and pay as before.
4. **Cars differ.** Expected top speeds without nitro: kei about 146, muscle 182, supercar 188. The jdm_coupe
   slides more with Ctrl and refills the nitro bar faster while drifting. The muscle's nitro bar lasts longer.
5. **Garage spot.** Spawn at PattayaSpawn and look for the purple ring. Expected: the ring is on the road beside the
   spawn, close to its left edge, and the sign stands at the roadside facing the road. If it sits on a building or
   in the middle of the road, place a `GarageSpot` part and restart.
6. **Shop opens.** Walk into the ring. Expected: the prompt "E GARAGE …" appears and E opens the window. It shows
   level and money, the hatch as SELECTED, and the kei as ฿3,000. Cars whose level is above yours show LOCKED. Walk
   out of the ring and the window closes. Drive in at speed and there is no prompt; stop and the prompt appears.
7. **Buy refusals.** With 0 money, BUY on the kei gives the red message "Needs ฿3000 (you have ฿0)" and nothing
   changes. LOCKED cars give "Needs level n". To test buying, set money in the command bar:
   `game.Players.<you>.leaderstats.Money.Value = 20000`. Then BUY the kei: money drops by 3,000, the kei shows
   SELECTED and the button reads "SPAWN MY KEI RACER".
8. **Spawn.** Press SPAWN on foot. Expected: the window closes, the toast "Your Kei Racer is waiting beside the
   garage" appears, `PersonalCar_<id>` stands in the first bay with `Owner` set, and you are seated in it. It drives
   with kei numbers (about 146 top). Press SPAWN again while sitting in it: the old car disappears and you sit in
   the new one. There is only ever one `PersonalCar_<id>`.
9. **Owner only (2 players).** Player 2 tries to sit in player 1's personal car. Expected: player 2 is ejected and
   sees "That car belongs to someone else". Player 2 can still use the shared grid cars. When player 1 leaves,
   their personal car is removed.
10. **Upgrades.** On the owned kei, press ENGINE +1. Money drops by 1,000, the PI goes up to 515 and the message says
    to respawn the car. Keep upgrading. Expected: a button reads "class max" once the next tier would take the PI
    past 549, and the server refuses it with "Class rules: …". After a respawn the car's `PI` attribute shows the
    new value.
11. **Save.** With API access on, buy and select the kei, leave and rejoin. Expected: the kei is still OWNED and
    SELECTED, and the upgrades are kept. An old save with no `extra` loads without errors and owns only the hatch.
12. **Equalised.** Sit in the grid supercar and run `game.Players.<you>:SetAttribute("Equalised", true)` from the
    server command bar. Expected: the HUD shows "EQUALISED" and the top speed drops to about 160 / 215 with nitro.
    Then set `SpeedCap` to 120: the car eases down to about 120, and nitro does not pass 120 either. Clear both
    attributes and the supercar numbers return.
13. **Busy.** Start a Street Sprint, drive back through the ring and press E. Expected: no prompt. If a request
    still gets through, the server answers "Finish your race or job first".
14. **Regression.** Street Challenge (C) vs AI still starts and its bot car still appears. Road Fight bosses are
    still parked at their rings. Taxi jobs still start with E at a stand.

## Risks for existing races

- **Shared grid cars now differ.** A race tested in the hatch is unchanged, but a player in the shared supercar or
  muscle is now faster. Payouts that reward average speed (loop race, sprint) will pay those cars a little more.
  Road Fight is easier in fast cars.
- **Nitro speed stays under the teleport check.** The highest nitro top speed is 245, 15 below the 260 teleport
  check. Down a slope a car could still go faster than its set top speed, as it already could before.
- **Personal cars on the road.** They park on the shoulder past the garage ring, next to the start of the loop
  route. They could be in the way of racers finishing a lap. A `GarageSpot` part moves the whole garage.
- **Bots can clone personal cars.** Street Challenge bots copy any parked `RaceCar` model, so a bot may look like
  someone's personal car. This is harmless: the copy has no seat.
- **Merge conflict.** `PattayaProgress` now has GetData/SetData stored under `extra`. If the circuit teammate also
  adds them, keep one copy with the same signatures.

## Tested by the leader (2026-10-18, Studio Play)
- Grid cars: `CarId`/`Class`/`PI` attributes present on all 6 (hatch 483 Street, kei 493 Street, muscle 578 / jdm 587 /
  gt_sedan 592 Sport, supercar 695 Super).
- Garage ring found automatically beside `PattayaSpawn` (about 24 studs away); prompt "MIDNIGHT PATTAYA GARAGE".
- Buy supercar at level 1 / ฿0: "Needs level 10". At level 12 / ฿2,000: "Needs ฿55000 (you have ฿2000)". Upgrade and
  select on an unowned car: "Buy it first". SPAWN with only the hatch owned: personal hatch spawned and auto-seated,
  `Owner` = the player's UserId, PI 483.
- With ฿90,000: bought the supercar, engine tier 1 (PI 721) and 2 (PI 744) fitted, tier 3 refused ("would leave
  Super (PI 767)"), grip tier 1 refused for the same reason. SPAWN replaced the hatch with the supercar (exactly one
  `PersonalCar_<id>` in workspace, E2 G0). Money left ฿14,600 (55,000 + 2 engine tiers = ฿75,400 spent).
- Driving: W held 8 s then nitro in the E2 supercar on Beach Road peaked at 181 studs/s (the car left the road on
  the curve, so the 195 top speed was not reached); the hatch cap of 160 is therefore no longer global.
- Not tested: save/rejoin (no DataStore in Studio), owner-only seat with a second player, Equalised/SpeedCap by hand
  (the Survival event sets them; see RACING_ROUTE_DESIGN.md).
