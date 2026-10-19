--!strict
-- PattayaWorkQueue (MIDNIGHT PATTAYA, team10/streaming): frame-budgeted work for the client look scripts.
-- Written offline, not run in Studio; the leader measures it (docs/STREAMING_PERFORMANCE.md).
--
-- Why: with StreamingEnabled the world arrives as Atomic 512-stud chunk Models, so one chunk delivers its whole
-- subtree (hundreds of Parts, their Textures and lights) in ONE frame. Every client script that reacted to each
-- instance at once (property writes, attribute writes, GetChildren, task.defer per instance) piled its work into that
-- frame. This module gives them shared queues:
--   WQ.new(name, fn) -> q; q:push(item) (deduplicated: an item that is already pending is not added twice),
--   q:cancel(item) (e.g. on streaming out), q:size(). Items are processed by fn(item) on Heartbeat. ALL queues share
--   ONE time budget per frame (workspace attribute WorkQueue_BudgetMs, default 1.5 ms), round robin between queues,
--   at least one item per frame so a queue always drains. The Heartbeat connection exists only while work is pending.
--   Steady state (nothing streaming): no per-frame work, no allocations (the item array is reused).
-- Leader measurement 2026-10-20: these look scripts are a minor share of the stream-in hitch (the engine's own
-- per-instance cost dominates), so this only flattens their part of the burst.
-- Rollback: workspace attribute WorkQueue_Enabled = false -> every queue drains completely on the next
-- Heartbeat with no time limit, i.e. the old "all at once, one frame later" behaviour.
-- Debug: require(game.ReplicatedStorage.PattayaWorkQueue).stats()
local RunService = game:GetService("RunService")

local WQ = {}

local DEFAULT_BUDGET_MS = 1.5

export type Queue = {
	name: string,
	fn: (any) -> (),
	items: {any},
	head: number,
	tail: number,
	pending: {[any]: boolean},
	count: number,
	processed: number,
	errors: number,
	push: (Queue, any) -> (),
	cancel: (Queue, any) -> (),
	size: (Queue) -> number,
}

local queues: {Queue} = {}
local rr = 1 -- round-robin start
local conn: RBXScriptConnection? = nil
local budgetSec = DEFAULT_BUDGET_MS / 1000
local budgetOn = true
local stats = {frames = 0, maxFrameMs = 0, lastFrameMs = 0}

local function readKnobs()
	local v = workspace:GetAttribute("WorkQueue_BudgetMs")
	budgetSec = (if type(v) == "number" and v > 0 then v else DEFAULT_BUDGET_MS) / 1000
	budgetOn = workspace:GetAttribute("WorkQueue_Enabled") ~= false
end
readKnobs()
workspace:GetAttributeChangedSignal("WorkQueue_BudgetMs"):Connect(readKnobs)
workspace:GetAttributeChangedSignal("WorkQueue_Enabled"):Connect(readKnobs)

-- pops and runs one item; false when the queue is empty
local function step(q: Queue): boolean
	local items, pending = q.items, q.pending
	while q.head <= q.tail do
		local h = q.head
		local item = items[h]
		items[h] = nil
		q.head = h + 1
		if pending[item] then
			pending[item] = nil
			q.count -= 1
			local ok, err = pcall(q.fn, item)
			q.processed += 1
			if not ok then
				q.errors += 1
				if q.errors <= 3 then
					warn(`[PattayaWorkQueue] {q.name}: {err}`)
				end
			end
			if q.head > q.tail then
				q.head, q.tail = 1, 0
			end
			return true
		end
	end
	q.head, q.tail = 1, 0
	return false
end

local function onHeartbeat()
	local t0 = os.clock()
	local n = #queues
	local anyLeft = false
	if not budgetOn then
		for i = 1, n do
			local q = queues[i]
			while q.count > 0 and step(q) do end
		end
	else
		local deadline = t0 + budgetSec
		local done = false
		if rr > n then
			rr = 1
		end
		for k = 0, n - 1 do
			local q = queues[(rr + k - 1) % n + 1]
			while q.count > 0 do
				step(q)
				if os.clock() >= deadline then
					done = true
					break
				end
			end
			if done then
				break
			end
		end
		rr += 1
	end
	for i = 1, n do
		if queues[i].count > 0 then
			anyLeft = true
			break
		end
	end
	local ms = (os.clock() - t0) * 1000
	stats.frames += 1
	stats.lastFrameMs = ms
	if ms > stats.maxFrameMs then
		stats.maxFrameMs = ms
	end
	if not anyLeft and conn then
		conn:Disconnect()
		conn = nil
	end
end

local function activate()
	if not conn then
		conn = RunService.Heartbeat:Connect(onHeartbeat)
	end
end

local function push(q: Queue, item: any)
	if item == nil or q.pending[item] then
		return
	end
	q.pending[item] = true
	q.count += 1
	local t = q.tail + 1
	q.tail = t
	q.items[t] = item
	activate()
end

local function cancel(q: Queue, item: any)
	if q.pending[item] then
		q.pending[item] = nil
		q.count -= 1
	end
end

local function size(q: Queue): number
	return q.count
end

-- a new queue; fn(item) runs once per pushed item, inside the shared per-frame budget
function WQ.new(name: string, fn: (any) -> ()): Queue
	local q: Queue = {name = name, fn = fn, items = {}, head = 1, tail = 0, pending = {}, count = 0, processed = 0,
		errors = 0, push = push, cancel = cancel, size = size}
	table.insert(queues, q)
	return q
end

function WQ.stats()
	local out = {budgetMs = budgetSec * 1000, enabled = budgetOn, running = conn ~= nil, frames = stats.frames,
		lastFrameMs = math.floor(stats.lastFrameMs * 1000) / 1000, maxFrameMs = math.floor(stats.maxFrameMs * 1000) / 1000,
		queues = {}}
	for _, q in queues do
		out.queues[q.name] = {pending = q.count, processed = q.processed, errors = q.errors}
	end
	return out
end

function WQ.resetMax()
	stats.maxFrameMs = 0
end

return WQ
