-- MIDNIGHT PATTAYA UI components (ReplicatedStorage.MidnightUI.Components, ui-core). Client only.
-- Every builder takes one props table (with `parent`) and returns the Instance it made; colours, fonts, radii and
-- motion come from Theme only. Builders run once when a panel is made: nothing here runs per frame (hover/press use
-- input events and TweenService). Full API: docs/UI_SYSTEM.md "Components".
--   panel, accentLine, label, valueLabel, bar (+ setBar), button, iconButton (+ setBadge), icon, pill (+ setPill),
--   divider, toastCard (+ setToast), toggle, slider, tween, corner, stroke, padding, gradient, kindColor, hex
local TweenService = game:GetService("TweenService")
local UserInputService = game:GetService("UserInputService")

local Theme = require(script.Parent.Theme)
local Responsive = require(script.Parent.Responsive)

local C = {}
local col = Theme.color

export type Props = {[string]: any}

-- helpers ------------------------------------------------------------------------------------------------------------
function C.hex(c: Color3): string
	return "#" .. c:ToHex()
end

-- tween that honours reduced motion (instant set); speed = "fast" | "normal" | "slow" | seconds
function C.tween(obj: Instance, goal: {[string]: any}, speed: (string | number)?, style: Enum.EasingStyle?): Tween?
	local t = if type(speed) == "number" then speed else (Theme.motion :: any)[speed or "normal"] or Theme.motion.normal
	if Responsive.reducedMotion() or t <= 0 then
		for k, v in goal do
			(obj :: any)[k] = v
		end
		return nil
	end
	local tw = TweenService:Create(obj, TweenInfo.new(t, style or Theme.motion.ease, Theme.motion.easeOut), goal)
	tw:Play()
	return tw
end

function C.corner(obj: Instance, radius: number?): UICorner
	local c = Instance.new("UICorner")
	c.CornerRadius = UDim.new(0, radius or Theme.radius.panel)
	c.Parent = obj
	return c
end

function C.stroke(obj: Instance, color: Color3?, thickness: number?, transparency: number?): UIStroke
	local s = Instance.new("UIStroke")
	s.ApplyStrokeMode = Enum.ApplyStrokeMode.Border
	s.Color = color or col.line
	s.Thickness = thickness or Theme.stroke.thin
	s.Transparency = transparency or 0
	s.Parent = obj
	return s
end

function C.padding(obj: Instance, px: number | {number}): UIPadding
	local p = Instance.new("UIPadding")
	local l, r, t, b
	if type(px) == "table" then
		l, r, t, b = px[1], px[2], px[3], px[4]
	else
		l, r, t, b = px, px, px, px
	end
	p.PaddingLeft, p.PaddingRight = UDim.new(0, l), UDim.new(0, r)
	p.PaddingTop, p.PaddingBottom = UDim.new(0, t), UDim.new(0, b)
	p.Parent = obj
	return p
end

function C.gradient(obj: Instance, seq: ColorSequence, rotation: number?, transparency: NumberSequence?): UIGradient
	local g = Instance.new("UIGradient")
	g.Color = seq
	g.Rotation = rotation or 0
	if transparency then
		g.Transparency = transparency
	end
	g.Parent = obj
	return g
end

-- accent colour for a toast / pill kind
function C.kindColor(kind: string?): Color3
	if kind == "reward" or kind == "money" then
		return col.green
	elseif kind == "warn" then
		return col.red
	elseif kind == "pb" then
		return col.yellow
	elseif kind == "levelup" then
		return col.purple
	end
	return col.cyan
end

local function font(f: any): Enum.Font
	if typeof(f) == "EnumItem" then
		return f
	end
	return (Theme.font :: any)[f or "body"] or Theme.font.body
end

local function place(obj: GuiObject, props: Props)
	if props.size then obj.Size = props.size end
	if props.position then obj.Position = props.position end
	if props.anchor then obj.AnchorPoint = props.anchor end
	if props.layoutOrder then obj.LayoutOrder = props.layoutOrder end
	if props.zIndex then obj.ZIndex = props.zIndex end
	if props.name then obj.Name = props.name end
	if props.visible ~= nil then obj.Visible = props.visible end
end

-- one shared gamepad selection look (cyan ring), used as SelectionImageObject by every button
local selectionLook: Frame? = nil
function C.selectionImage(): Frame
	if not selectionLook then
		local f = Instance.new("Frame")
		f.Name = "MidnightSelection"
		f.BackgroundTransparency = 1
		f.Size = UDim2.new(1, 8, 1, 8)
		f.Position = UDim2.fromOffset(-4, -4)
		C.corner(f, Theme.radius.button + 4)
		C.stroke(f, col.cyan, Theme.stroke.thick)
		selectionLook = f
	end
	return selectionLook :: Frame
end

-- panel: glass surface, rounded, hairline stroke, soft vertical gradient, optional neon accent line on top ------------
-- props: parent, name, size, position, anchor, color, alpha, radius, stroke (false = none), strokeColor, glow (cyan
-- stroke), accent (top line), gradient (default true), canvas (CanvasGroup, for group fades), clip, zIndex, layoutOrder
function C.panel(props: Props): GuiObject
	local radius = props.radius or Theme.radius.panel
	local f: GuiObject
	local surface: GuiObject
	if props.canvas then
		-- a UIGradient or UIStroke on a CanvasGroup would tint / outline the whole rendered group, so a CanvasGroup
		-- panel draws its glass on an inner "Surface" frame (inset 2 px so the stroke is not clipped)
		f = Instance.new("CanvasGroup")
		f.BackgroundTransparency = 1
		C.corner(f, radius)
		surface = Instance.new("Frame")
		surface.Name = "Surface"
		surface.Position = UDim2.fromOffset(2, 2)
		surface.Size = UDim2.new(1, -4, 1, -4)
		surface.ZIndex = 0
		surface.Parent = f
		C.corner(surface, math.max(0, radius - 2))
	else
		f = Instance.new("Frame")
		surface = f
		C.corner(f, radius)
	end
	surface.BackgroundColor3 = props.color or col.surface
	surface.BackgroundTransparency = props.alpha or Theme.alpha.panel
	surface.BorderSizePixel = 0
	f.BorderSizePixel = 0
	f.ClipsDescendants = props.clip == true
	place(f, props)
	if props.stroke ~= false then
		if props.glow then
			C.stroke(surface, props.strokeColor or col.cyan, Theme.stroke.normal, 0.45)
		else
			C.stroke(surface, props.strokeColor or col.line, Theme.stroke.thin, 0.2)
		end
	end
	if props.gradient ~= false then
		-- lighter top, deeper bottom: reads as glass without hiding the world behind it
		C.gradient(surface, ColorSequence.new(col.surface2, col.navy), 90)
	end
	if props.accent then
		C.accentLine({parent = f, inset = radius})
	end
	f.Parent = props.parent
	return f
end

-- the panel's hairline stroke (on the panel itself, or on its "Surface" child for a CanvasGroup panel)
function C.panelStroke(f: Instance): UIStroke?
	local surface = f:FindFirstChild("Surface") or f
	return surface:FindFirstChildOfClass("UIStroke")
end

-- accentLine: thin cyan -> purple line along the top edge of a panel
function C.accentLine(props: Props): Frame
	local line = Instance.new("Frame")
	line.Name = props.name or "Accent"
	local inset = props.inset or Theme.radius.panel
	line.Position = UDim2.fromOffset(inset, 0)
	line.Size = UDim2.new(1, -2 * inset, 0, props.thickness or 2)
	line.BackgroundColor3 = col.text
	line.BorderSizePixel = 0
	line.ZIndex = props.zIndex or 2
	C.gradient(line, Theme.accentGradient(), 0,
		NumberSequence.new({NumberSequenceKeypoint.new(0, 0.6), NumberSequenceKeypoint.new(0.5, 0),
			NumberSequenceKeypoint.new(1, 0.6)}))
	line.Parent = props.parent
	return line
end

-- label --------------------------------------------------------------------------------------------------------------
-- props: parent, text, size, position, anchor, textSize, font ("display"|"bold"|"body"|"mono"|Enum.Font), color,
-- align ("left"|"center"|"right"), vAlign ("top"|"center"|"bottom"), wrap, fit (TextScaled up to textSize, never
-- below minSize; no ellipsis unless truncate = true), autoX (width follows the text), rich, transparency, name, zIndex, layoutOrder
local XALIGN = {left = Enum.TextXAlignment.Left, center = Enum.TextXAlignment.Center, right = Enum.TextXAlignment.Right}
local YALIGN = {top = Enum.TextYAlignment.Top, center = Enum.TextYAlignment.Center, bottom = Enum.TextYAlignment.Bottom}
function C.label(props: Props): TextLabel
	local t = Instance.new("TextLabel")
	t.BackgroundTransparency = 1
	t.Size = UDim2.new(1, 0, 0, (props.textSize or Theme.size.body) + 4)
	t.Font = font(props.font)
	t.TextSize = props.textSize or Theme.size.body
	t.TextColor3 = props.color or col.text
	t.TextTransparency = props.transparency or 0
	t.TextXAlignment = XALIGN[props.align or "left"]
	t.TextYAlignment = YALIGN[props.vAlign or "center"]
	t.TextWrapped = props.wrap == true
	t.TextTruncate = if props.wrap then Enum.TextTruncate.None else Enum.TextTruncate.AtEnd
	t.RichText = props.rich == true
	t.Text = props.text or ""
	place(t, props)
	if props.fit then
		-- shrink-to-fit instead of an ellipsis (owner fix: "Missions"/"Settings" showed "…" at 88 px / HUD scale 0.62);
		-- truncate = true keeps the ellipsis for free text that can be longer than the box (toast lines)
		t.TextScaled = true
		if not props.truncate then
			t.TextTruncate = Enum.TextTruncate.None
		end
		local lim = Instance.new("UITextSizeConstraint")
		lim.MaxTextSize = props.textSize or Theme.size.body
		lim.MinTextSize = props.minSize or 9
		lim.Parent = t
	end
	if props.autoX then
		t.AutomaticSize = Enum.AutomaticSize.X
		t.Size = UDim2.new(0, 0, t.Size.Y.Scale, t.Size.Y.Offset)
	end
	t.Parent = props.parent
	return t
end

-- valueLabel: big number with a small caption under it (children "Value", "Caption") ----------------------------------
-- props: parent, value, caption, size, position, anchor, valueSize, color, captionColor, align, name, layoutOrder
function C.valueLabel(props: Props): Frame
	local f = Instance.new("Frame")
	f.BackgroundTransparency = 1
	f.Size = UDim2.fromOffset(120, 64)
	place(f, props)
	local vs = props.valueSize or Theme.size.big
	local v = C.label({parent = f, name = "Value", text = props.value or "", font = "display", textSize = vs,
		color = props.color, align = props.align, fit = true, size = UDim2.new(1, 0, 1, -(Theme.size.caption + 4))})
	v.TextTruncate = Enum.TextTruncate.None
	C.label({parent = f, name = "Caption", text = props.caption or "", font = "bold", textSize = Theme.size.caption,
		color = props.captionColor or col.textDim, align = props.align, anchor = Vector2.new(0, 1),
		position = UDim2.fromScale(0, 1), size = UDim2.new(1, 0, 0, Theme.size.caption + 4)})
	f.Parent = props.parent
	return f
end

-- bar: rounded track with a gradient fill (+ optional segment ticks). setBar(bar, 0..1, animate?) ----------------------
-- props: parent, size, position, anchor, value, from, to (fill gradient colours), segments, trackColor, name
function C.bar(props: Props): Frame
	local track = Instance.new("Frame")
	track.Name = props.name or "Bar"
	track.BackgroundColor3 = props.trackColor or col.navy
	track.BackgroundTransparency = 0.25
	track.BorderSizePixel = 0
	track.Size = UDim2.new(1, 0, 0, 8)
	place(track, props)
	C.corner(track, Theme.radius.pill)
	local fill = Instance.new("Frame")
	fill.Name = "Fill"
	fill.BackgroundColor3 = col.text
	fill.BorderSizePixel = 0
	fill.Size = UDim2.fromScale(math.clamp(props.value or 0, 0, 1), 1)
	C.corner(fill, Theme.radius.pill)
	C.gradient(fill, ColorSequence.new(props.from or col.cyan, props.to or col.purple), 0)
	fill.Parent = track
	local n = props.segments or 0
	for i = 1, n - 1 do
		local tick = Instance.new("Frame")
		tick.Name = "Tick"
		tick.BackgroundColor3 = col.navy
		tick.BackgroundTransparency = 0.2
		tick.BorderSizePixel = 0
		tick.AnchorPoint = Vector2.new(0.5, 0)
		tick.Position = UDim2.fromScale(i / n, 0)
		tick.Size = UDim2.new(0, 2, 1, 0)
		tick.ZIndex = fill.ZIndex + 1
		tick.Parent = track
	end
	track.Parent = props.parent
	return track
end

function C.setBar(track: Instance, value: number, animate: boolean?)
	local fill = track:FindFirstChild("Fill") :: Frame?
	if not fill then
		return
	end
	local goal = {Size = UDim2.fromScale(math.clamp(value, 0, 1), 1)}
	if animate then
		C.tween(fill, goal, "slow")
	else
		fill.Size = goal.Size
	end
end

-- shared hover / press / gamepad-selection feedback for any button --------------------------------------------------
local function interactive(b: GuiButton, base: Color3, hover: Color3, strokeObj: UIStroke?, strokeBase: number?)
	b.AutoButtonColor = false
	b.Selectable = true
	b.SelectionImageObject = C.selectionImage()
	local scale = Instance.new("UIScale")
	scale.Name = "PressScale"
	scale.Parent = b
	local function set(on: boolean)
		C.tween(b, {BackgroundColor3 = if on then hover else base}, "fast")
		if strokeObj then
			C.tween(strokeObj, {Transparency = if on then 0 else (strokeBase or 0.2)}, "fast")
		end
	end
	b.MouseEnter:Connect(function() set(true) end)
	b.MouseLeave:Connect(function()
		set(false)
		C.tween(scale, {Scale = 1}, "fast")
	end)
	b.SelectionGained:Connect(function() set(true) end)
	b.SelectionLost:Connect(function() set(false) end)
	b.MouseButton1Down:Connect(function() C.tween(scale, {Scale = 0.95}, "fast") end)
	b.MouseButton1Up:Connect(function() C.tween(scale, {Scale = 1}, "fast") end)
end

-- button: text button, 44 px tall by default. style "primary" (cyan) | "secondary" (surface) | "danger" | "ghost"
-- props: parent, text, size, position, anchor, style, onClick, textSize, name, layoutOrder
function C.button(props: Props): TextButton
	local b = Instance.new("TextButton")
	local style = props.style or "secondary"
	local base, hover, textColor
	if style == "primary" then
		base, hover, textColor = col.cyan, col.text, col.navy
	elseif style == "danger" then
		base, hover, textColor = col.red, col.text, col.navy
	elseif style == "ghost" then
		base, hover, textColor = col.navy, col.surface2, col.text
	else
		base, hover, textColor = col.surface2, col.line, col.text
	end
	b.BackgroundColor3 = base
	b.BackgroundTransparency = if style == "ghost" then 0.5 else 0.05
	b.BorderSizePixel = 0
	b.Size = UDim2.fromOffset(160, 44)
	b.Font = Theme.font.bold
	b.TextSize = props.textSize or Theme.size.label
	b.TextColor3 = textColor
	b.Text = props.text or ""
	b.TextTruncate = Enum.TextTruncate.AtEnd
	place(b, props)
	C.corner(b, Theme.radius.button)
	local s = C.stroke(b, if style == "secondary" or style == "ghost" then col.line else base, Theme.stroke.thin, 0.2)
	interactive(b, base, hover, s, 0.2)
	if props.onClick then
		b.Activated:Connect(props.onClick)
	end
	b.Parent = props.parent
	return b
end

-- icons: vector-drawn from Frames (no images). icon(name, parent, sizePx, color) -> Frame "Icon" ----------------------
local function box(parent: Instance, x: number, y: number, w: number, h: number, color: Color3, radius: number?,
	rot: number?): Frame
	local f = Instance.new("Frame")
	f.BackgroundColor3 = color
	f.BorderSizePixel = 0
	f.AnchorPoint = Vector2.new(0.5, 0.5)
	f.Position = UDim2.fromScale(x, y)
	f.Size = UDim2.fromScale(w, h)
	f.Rotation = rot or 0
	if radius then
		local c = Instance.new("UICorner")
		c.CornerRadius = if radius >= 1 then UDim.new(1, 0) else UDim.new(radius, 0)
		c.Parent = f
	end
	f.Parent = parent
	return f
end

local function glyph(parent: Instance, text: string, color: Color3, padScale: number)
	local t = Instance.new("TextLabel")
	t.BackgroundTransparency = 1
	t.Size = UDim2.fromScale(1, 1)
	t.Font = Theme.font.display
	t.TextScaled = true
	t.TextColor3 = color
	t.Text = text
	t.Parent = parent
	local pad = Instance.new("UIPadding")
	pad.PaddingTop, pad.PaddingBottom = UDim.new(padScale, 0), UDim.new(padScale, 0)
	pad.Parent = t
end

local ICONS: {[string]: (Frame, Color3) -> ()} = {}
ICONS.garage = function(p, c) -- car side view
	box(p, 0.5, 0.36, 0.5, 0.24, c, 0.4) -- cabin
	box(p, 0.5, 0.55, 0.92, 0.26, c, 0.35) -- body
	box(p, 0.27, 0.7, 0.2, 0.2, col.navy, 1) -- wheels
	box(p, 0.73, 0.7, 0.2, 0.2, col.navy, 1)
	box(p, 0.27, 0.7, 0.1, 0.1, c, 1)
	box(p, 0.73, 0.7, 0.1, 0.1, c, 1)
	box(p, 0.42, 0.36, 0.16, 0.12, col.navy, 0.3) -- windows
	box(p, 0.6, 0.36, 0.14, 0.12, col.navy, 0.3)
end
ICONS.map = function(p, c) -- location pin
	box(p, 0.5, 0.58, 0.4, 0.4, c, 0.15, 45)
	box(p, 0.5, 0.38, 0.62, 0.62, c, 1)
	box(p, 0.5, 0.38, 0.24, 0.24, col.navy, 1)
end
ICONS.events = function(p, c) -- chequered flag
	box(p, 0.2, 0.5, 0.08, 0.86, c, 0.5)
	local flag = box(p, 0.56, 0.32, 0.62, 0.44, c, 0.1)
	for i = 0, 3 do
		for j = 0, 1 do
			if (i + j) % 2 == 0 then
				box(flag, 0.125 + i * 0.25, 0.25 + j * 0.5, 0.25, 0.5, col.navy)
			end
		end
	end
end
ICONS.missions = function(p, c) -- clipboard
	local board = box(p, 0.5, 0.54, 0.66, 0.82, c, 0.12)
	box(p, 0.5, 0.14, 0.32, 0.12, c, 0.4)
	for i = 0, 2 do
		box(board, 0.5, 0.32 + i * 0.2, 0.6, 0.08, col.navy, 0.5)
	end
end
ICONS.settings = function(p, c) -- gear: 4 bars = 8 teeth, disc, hole
	for i = 0, 3 do
		box(p, 0.5, 0.5, 0.2, 0.92, c, 0.15, i * 45)
	end
	box(p, 0.5, 0.5, 0.7, 0.7, c, 1)
	box(p, 0.5, 0.5, 0.3, 0.3, col.navy, 1)
end
ICONS.menu = function(p, c) -- three bars (compact quick-menu button)
	for i = 0, 2 do
		box(p, 0.5, 0.26 + i * 0.24, 0.84, 0.13, c, 0.5)
	end
end
ICONS.help = function(p, c) -- ? in a ring
	local ring = box(p, 0.5, 0.5, 0.86, 0.86, c, 1)
	ring.BackgroundTransparency = 1
	local s = Instance.new("UIStroke")
	s.Color = c
	s.Thickness = 2.5
	s.Parent = ring
	glyph(ring, "?", c, 0.18)
end
ICONS.nitro = function(p, c) -- bottle
	box(p, 0.5, 0.6, 0.44, 0.7, c, 0.3)
	box(p, 0.5, 0.18, 0.2, 0.16, c, 0.2)
end
ICONS.star = function(p, c) -- level up: 8-point star
	box(p, 0.5, 0.5, 0.62, 0.62, c, 0.1)
	box(p, 0.5, 0.5, 0.62, 0.62, c, 0.1, 45)
	box(p, 0.5, 0.5, 0.26, 0.26, col.navy, 1)
end
ICONS.coin = function(p, c)
	box(p, 0.5, 0.5, 0.86, 0.86, c, 1)
	glyph(p, "฿", col.navy, 0.2)
end
ICONS.warn = function(p, c)
	box(p, 0.5, 0.5, 0.86, 0.86, c, 1)
	box(p, 0.5, 0.4, 0.12, 0.38, col.navy, 0.5)
	box(p, 0.5, 0.74, 0.12, 0.12, col.navy, 1)
end
ICONS.info = function(p, c)
	box(p, 0.5, 0.5, 0.86, 0.86, c, 1)
	box(p, 0.5, 0.58, 0.12, 0.36, col.navy, 0.5)
	box(p, 0.5, 0.28, 0.12, 0.12, col.navy, 1)
end
ICONS.trophy = function(p, c)
	box(p, 0.5, 0.36, 0.6, 0.5, c, 0.3)
	box(p, 0.5, 0.7, 0.14, 0.24, c)
	box(p, 0.5, 0.86, 0.46, 0.1, c, 0.3)
end
C.ICON_NAMES = {}
for k in ICONS do
	table.insert(C.ICON_NAMES, k)
end
table.sort(C.ICON_NAMES)

function C.icon(name: string, parent: Instance?, sizePx: number?, color: Color3?): Frame
	local f = Instance.new("Frame")
	f.Name = "Icon"
	f.BackgroundTransparency = 1
	f.Size = UDim2.fromOffset(sizePx or 28, sizePx or 28)
	local draw = ICONS[name] or ICONS.info
	draw(f, color or col.text)
	f.Parent = parent
	return f
end

-- iconButton: quick-menu tile (icon over a label, shortcut hint chip in a corner, red badge dot) ------------------------
-- props: parent, icon, label, hint, size (default 88x88, >= 44 px on every device), position, anchor, onClick, name,
-- layoutOrder. Children: "Icon", "Label", "Hint", "Badge".
function C.iconButton(props: Props): TextButton
	local b = Instance.new("TextButton")
	b.Text = ""
	b.BackgroundColor3 = col.surface
	b.BackgroundTransparency = Theme.alpha.panel
	b.BorderSizePixel = 0
	b.Size = UDim2.fromOffset(88, 88)
	place(b, props)
	C.corner(b, Theme.radius.panel)
	local s = C.stroke(b, col.line, Theme.stroke.thin, 0.2)
	C.gradient(b, ColorSequence.new(col.surface2, col.navy), 90)
	interactive(b, col.surface, col.surface2, s, 0.2)
	local hasLabel = props.label ~= nil and props.label ~= ""
	local ic = C.icon(props.icon or "info", b, 34, col.text)
	ic.AnchorPoint = Vector2.new(0.5, 0.5)
	ic.Position = if hasLabel then UDim2.fromScale(0.5, 0.4) else UDim2.fromScale(0.5, 0.5)
	if hasLabel then
		C.label({parent = b, name = "Label", text = props.label, font = "bold", textSize = Theme.size.label,
			align = "center", fit = true, minSize = 8, anchor = Vector2.new(0.5, 1),
			position = UDim2.new(0.5, 0, 1, -8), size = UDim2.new(1, -6, 0, Theme.size.label + 4)})
	end
	local hint = C.label({parent = b, name = "Hint", text = props.hint or "", font = "bold",
		textSize = Theme.size.caption - 1, color = col.textDim, align = "center",
		position = UDim2.fromOffset(6, 6), size = UDim2.fromOffset(18, 16)})
	hint.BackgroundColor3 = col.navy
	hint.BackgroundTransparency = 0.3
	hint.Visible = (props.hint or "") ~= ""
	C.corner(hint, Theme.radius.small)
	local badge = Instance.new("Frame")
	badge.Name = "Badge"
	badge.AnchorPoint = Vector2.new(0.5, 0.5)
	badge.Position = UDim2.new(1, -8, 0, 8)
	badge.Size = UDim2.fromOffset(12, 12)
	badge.BackgroundColor3 = col.red
	badge.BorderSizePixel = 0
	badge.Visible = false
	C.corner(badge, Theme.radius.pill)
	C.stroke(badge, col.navy, Theme.stroke.normal)
	badge.Parent = b
	if props.onClick then
		b.Activated:Connect(props.onClick)
	end
	b.Parent = props.parent
	return b
end

function C.setBadge(b: Instance, on: boolean)
	local badge = b:FindFirstChild("Badge") :: GuiObject?
	if badge then
		badge.Visible = on
	end
end

-- pill: rounded chip with text (child "Text"), optional leading glyph (child "Lead") --------------------------------
-- props: parent, text, lead (glyph text), leadColor, color (surface), alpha, textColor, size, position, anchor,
-- autoX, textSize, font, stroke (Color3), name, layoutOrder
function C.pill(props: Props): Frame
	local f = Instance.new("Frame")
	f.BackgroundColor3 = props.color or col.surface
	f.BackgroundTransparency = props.alpha or Theme.alpha.panel
	f.BorderSizePixel = 0
	f.Size = UDim2.fromOffset(80, 28)
	place(f, props)
	C.corner(f, Theme.radius.pill)
	C.stroke(f, props.stroke or col.line, Theme.stroke.thin, 0.2)
	local list = Instance.new("UIListLayout")
	list.FillDirection = Enum.FillDirection.Horizontal
	list.VerticalAlignment = Enum.VerticalAlignment.Center
	list.HorizontalAlignment = Enum.HorizontalAlignment.Center
	list.Padding = UDim.new(0, 6)
	list.SortOrder = Enum.SortOrder.LayoutOrder
	list.Parent = f
	C.padding(f, {12, 12, 0, 0})
	local ts = props.textSize or Theme.size.label
	if props.lead then
		local lead = C.label({parent = f, name = "Lead", text = props.lead, font = "display", textSize = ts,
			color = props.leadColor or col.green, autoX = true, size = UDim2.new(0, 0, 1, 0), layoutOrder = 1})
		lead.TextTruncate = Enum.TextTruncate.None
	end
	local t = C.label({parent = f, name = "Text", text = props.text or "", font = props.font or "bold", textSize = ts,
		color = props.textColor or col.text, autoX = true, size = UDim2.new(0, 0, 1, 0), layoutOrder = 2})
	t.TextTruncate = Enum.TextTruncate.None
	if props.autoX then
		f.AutomaticSize = Enum.AutomaticSize.X
		f.Size = UDim2.new(0, 0, f.Size.Y.Scale, f.Size.Y.Offset)
	end
	f.Parent = props.parent
	return f
end

function C.setPill(f: Instance, text: string)
	local t = f:FindFirstChild("Text") :: TextLabel?
	if t then
		t.Text = text
	end
end

-- divider: 1 px hairline (horizontal by default) -----------------------------------------------------------------
-- props: parent, vertical, size, position, anchor, color, transparency, name, layoutOrder
function C.divider(props: Props): Frame
	local d = Instance.new("Frame")
	d.Name = props.name or "Divider"
	d.BackgroundColor3 = props.color or col.line
	d.BackgroundTransparency = props.transparency or 0.2
	d.BorderSizePixel = 0
	d.Size = if props.vertical then UDim2.new(0, 1, 1, 0) else UDim2.new(1, 0, 0, 1)
	place(d, props)
	d.Parent = props.parent
	return d
end

-- toastCard: right-side notification like the mockup's "Near Miss +25 / Clean Driving!" card (CanvasGroup, so the
-- whole card fades). props: parent, title (rich text allowed), body, kind ("info"|"reward"|"warn"|"pb"|"levelup"|
-- "nearmiss"), icon, size, name, layoutOrder. setToast(card, title, body, kind, icon) re-fills a pooled card.
local KIND_ICON = {info = "info", reward = "coin", money = "coin", warn = "warn", pb = "trophy", levelup = "star",
	nearmiss = "garage", nitro = "nitro"}
function C.toastCard(props: Props): GuiObject
	local f = C.panel({name = props.name or "Toast", size = props.size or UDim2.fromOffset(280, 64),
		alpha = Theme.alpha.panel, glow = true, canvas = true, layoutOrder = props.layoutOrder})
	local iconHolder = Instance.new("Frame")
	iconHolder.Name = "IconHolder"
	iconHolder.BackgroundTransparency = 1
	iconHolder.AnchorPoint = Vector2.new(0, 0.5)
	iconHolder.Position = UDim2.new(0, 14, 0.5, 0)
	iconHolder.Size = UDim2.fromOffset(32, 32)
	iconHolder.Parent = f
	C.label({parent = f, name = "Title", text = "", font = "bold", textSize = Theme.size.body + 1, rich = true,
		position = UDim2.fromOffset(58, 10), size = UDim2.new(1, -68, 0, 22), fit = true, minSize = 11, truncate = true})
	C.label({parent = f, name = "Body", text = "", font = "body", textSize = Theme.size.caption, color = col.textDim,
		position = UDim2.fromOffset(58, 34), size = UDim2.new(1, -68, 0, 18), fit = true, minSize = 9, truncate = true})
	C.setToast(f, props.title or "", props.body or "", props.kind, props.icon)
	f.Parent = props.parent
	return f
end

function C.setToast(f: Instance, title: string, body: string?, kind: string?, icon: string?)
	local accent = C.kindColor(kind)
	local stroke = C.panelStroke(f)
	if stroke then
		stroke.Color = accent
	end
	local holder = f:FindFirstChild("IconHolder")
	if holder then
		local want = icon or KIND_ICON[kind or "info"] or "info"
		local key = want .. "|" .. accent:ToHex()
		if holder:GetAttribute("Icon") ~= key then -- rebuilt only when the icon changes (per toast, never per frame)
			holder:ClearAllChildren()
			local ic = C.icon(want, holder, 32, accent)
			ic.Size = UDim2.fromScale(1, 1)
			holder:SetAttribute("Icon", key)
		end
	end
	local t = f:FindFirstChild("Title") :: TextLabel?
	local b = f:FindFirstChild("Body") :: TextLabel?
	if t then
		t.Text = title
	end
	if b then
		b.Text = body or ""
		b.Visible = (body or "") ~= ""
	end
	if t and b then
		t.Position = if b.Visible then UDim2.fromOffset(58, 10) else UDim2.new(0, 58, 0.5, -11)
	end
end

-- toggle: label + switch (Activated toggles; gamepad selectable; 72x44 touch target). Returns frame, set(value) ------
-- props: parent, label, value, onChange(bool), size, layoutOrder, name
function C.toggle(props: Props): (Frame, (boolean) -> ())
	local f = Instance.new("Frame")
	f.BackgroundTransparency = 1
	f.Size = UDim2.new(1, 0, 0, 48)
	place(f, props)
	C.label({parent = f, text = props.label or "", font = "bold", textSize = Theme.size.body,
		size = UDim2.new(1, -90, 1, 0), fit = true, minSize = 10})
	local sw = Instance.new("TextButton")
	sw.Name = "Switch"
	sw.Text = ""
	sw.AnchorPoint = Vector2.new(1, 0.5)
	sw.Position = UDim2.new(1, 0, 0.5, 0)
	sw.Size = UDim2.fromOffset(72, 44)
	sw.BackgroundTransparency = 1
	sw.Selectable = true
	sw.SelectionImageObject = C.selectionImage()
	sw.Parent = f
	local track = Instance.new("Frame")
	track.AnchorPoint = Vector2.new(0.5, 0.5)
	track.Position = UDim2.fromScale(0.5, 0.5)
	track.Size = UDim2.fromOffset(56, 28)
	track.BorderSizePixel = 0
	track.Parent = sw
	C.corner(track, Theme.radius.pill)
	C.stroke(track, col.line, Theme.stroke.thin, 0.2)
	local knob = Instance.new("Frame")
	knob.AnchorPoint = Vector2.new(0, 0.5)
	knob.Size = UDim2.fromOffset(22, 22)
	knob.BackgroundColor3 = col.text
	knob.BorderSizePixel = 0
	knob.Parent = track
	C.corner(knob, Theme.radius.pill)
	local value = props.value == true
	local function render(animate: boolean)
		local goalTrack = {BackgroundColor3 = if value then col.cyan else col.navy}
		local goalKnob = {Position = if value then UDim2.new(1, -25, 0.5, 0) else UDim2.new(0, 3, 0.5, 0)}
		if animate then
			C.tween(track, goalTrack, "fast")
			C.tween(knob, goalKnob, "fast")
		else
			track.BackgroundColor3 = goalTrack.BackgroundColor3
			knob.Position = goalKnob.Position
		end
	end
	render(false)
	sw.Activated:Connect(function()
		value = not value
		render(true)
		if props.onChange then
			props.onChange(value)
		end
	end)
	f.Parent = props.parent
	return f, function(v: boolean)
		value = v
		render(false)
	end
end

-- slider: label + value text, then "-" button, track (click / drag), "+" button. Gamepad uses -/+ (selectable).
-- props: parent, label, min, max, step, value, format (string.format pattern), onChange(number), layoutOrder, name
-- Returns frame, set(value) (set does not call onChange).
function C.slider(props: Props): (Frame, (number) -> ())
	local lo, hi, step = props.min or 0, props.max or 1, props.step or 0.05
	local fmt = props.format or "%.2f"
	local f = Instance.new("Frame")
	f.BackgroundTransparency = 1
	f.Size = UDim2.new(1, 0, 0, 76)
	place(f, props)
	C.label({parent = f, text = props.label or "", font = "bold", textSize = Theme.size.body,
		size = UDim2.new(1, -80, 0, 24), fit = true, minSize = 10})
	local valueText = C.label({parent = f, name = "Value", text = "", font = "mono", textSize = Theme.size.body,
		color = col.cyan, align = "right", anchor = Vector2.new(1, 0), position = UDim2.new(1, 0, 0, 0),
		size = UDim2.fromOffset(80, 24)})
	local row = Instance.new("Frame")
	row.BackgroundTransparency = 1
	row.Position = UDim2.fromOffset(0, 30)
	row.Size = UDim2.new(1, 0, 0, 44)
	row.Parent = f
	local minus = C.button({parent = row, name = "Minus", text = "-", size = UDim2.fromOffset(44, 44),
		textSize = Theme.size.title})
	local plus = C.button({parent = row, name = "Plus", text = "+", size = UDim2.fromOffset(44, 44),
		textSize = Theme.size.title, anchor = Vector2.new(1, 0), position = UDim2.fromScale(1, 0)})
	local hit = Instance.new("TextButton")
	hit.Name = "Track"
	hit.Text = ""
	hit.BackgroundTransparency = 1
	hit.Position = UDim2.fromOffset(56, 0)
	hit.Size = UDim2.new(1, -112, 1, 0)
	hit.Selectable = false
	hit.Parent = row
	local bar = C.bar({parent = hit, size = UDim2.new(1, 0, 0, 8), anchor = Vector2.new(0, 0.5),
		position = UDim2.fromScale(0, 0.5)})
	local value = math.clamp(props.value or lo, lo, hi)
	local function render()
		valueText.Text = string.format(fmt, value)
		C.setBar(bar, (value - lo) / (hi - lo), false)
	end
	local function set(v: number, fire: boolean)
		v = math.clamp(math.floor((v - lo) / step + 0.5) * step + lo, lo, hi)
		local changed = math.abs(v - value) >= 1e-6
		value = v
		render()
		if fire and changed and props.onChange then
			props.onChange(value)
		end
	end
	minus.Activated:Connect(function() set(value - step, true) end)
	plus.Activated:Connect(function() set(value + step, true) end)
	local dragging = false
	local function fromX(x: number)
		local a, w = hit.AbsolutePosition.X, hit.AbsoluteSize.X
		if w > 0 then
			set(lo + (hi - lo) * math.clamp((x - a) / w, 0, 1), true)
		end
	end
	hit.InputBegan:Connect(function(input)
		if input.UserInputType == Enum.UserInputType.MouseButton1 or input.UserInputType == Enum.UserInputType.Touch then
			dragging = true
			fromX(input.Position.X)
		end
	end)
	-- drag: these input connections only do work while `dragging`; they die with the slider's frame via `alive`
	local c1, c2
	c1 = UserInputService.InputChanged:Connect(function(input)
		if dragging and (input.UserInputType == Enum.UserInputType.MouseMovement
			or input.UserInputType == Enum.UserInputType.Touch) then
			fromX(input.Position.X)
		end
	end)
	c2 = UserInputService.InputEnded:Connect(function(input)
		if input.UserInputType == Enum.UserInputType.MouseButton1 or input.UserInputType == Enum.UserInputType.Touch then
			dragging = false
		end
	end)
	f.Destroying:Connect(function()
		c1:Disconnect()
		c2:Disconnect()
	end)
	render()
	f.Parent = props.parent
	return f, function(v: number)
		set(v, false)
	end
end

return C
