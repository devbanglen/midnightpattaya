end
local fails = 0
local function check(name, cond, d)
	print((if cond then "PASS " else "FAIL ") .. name .. (if d ~= nil then "  " .. tostring(d) else ""))
	if not cond then fails += 1 end
end
local function plr(id, name) local p = {UserId = id, DisplayName = name, Name = name}; players[id] = p; return p end
local a, b, c = plr(1, "Alice"), plr(2, "Bob"), plr(3, "Cara")

-- store failing (Studio without API access): session memory
local L = load()
L.submitRating(a, "Sport", 1, 1024, true)
L.submitRating(b, "Sport", 1, 976, true)
L.submitRating(c, "Sport", 1, 1100, false)
L.submitRating(a, "Street", 1, 1300, false)
local top = L.rankedTop("Sport", 1, 5)
check("fallback: 3 rows", #top == 3, #top)
check("fallback: order", top[1].name == "Cara" and top[2].name == "Alice" and top[3].name == "Bob")
check("fallback: provisional marker", top[1].provisional == false and top[2].provisional == true)
check("fallback: buckets apart", #L.rankedTop("Street", 1, 5) == 1)
check("fallback: seasons apart", #L.rankedTop("Sport", 2, 5) == 0)
L.submitRating(a, "Sport", 1, 1043, true)
check("fallback: newer value wins", L.rankedTop("Sport", 1, 5)[2].rating == 1043)
check("board name", L.rankedBoardName("Track Spec", 1) == "CircuitRating_S1_Track_Spec", L.rankedBoardName("Track Spec", 1))

-- store working: encoded values and a fresh server reading them back
mode = "ok"
local L2 = load()
L2.submitRating(a, "Sport", 1, 1024, true)
L2.submitRating(c, "Sport", 1, 1100, false)
check("store: encoded provisional", data.u1 == 10240, data.u1)
check("store: encoded established", data.u3 == 11001, data.u3)
local L3 = load() -- another server: nothing in session memory
L3.rankedTop("Sport", 1, 5) -- first call starts the refresh (sync in this mock)
local t3 = L3.rankedTop("Sport", 1, 5)
check("store: read back", #t3 == 2 and t3[1].rating == 1100 and t3[1].provisional == false and t3[2].provisional == true
	and t3[2].name == "Alice", #t3)
-- lap boards still work
local t4 = L3.top("test_oval", 5)
check("lap board still works", type(t4) == "table")
print(fails .. " failures")
