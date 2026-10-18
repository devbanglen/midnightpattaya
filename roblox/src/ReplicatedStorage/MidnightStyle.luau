-- MIDNIGHT PATTAYA UI style: one visual language for every HUD panel, taken from the loading screen
-- (ReplicatedFirst.MidnightLoading). Styling only: these helpers add decoration children to a panel and never move,
-- resize or hide it, so the HUD scripts keep their own layout and logic.
--   accent(panel, inset?)  a thin neon line (cyan to pink) along the top edge of a panel
--   wordmark(panel)        a small "MIDNIGHT PATTAYA" tag in the panel's top-right corner, for titled panels
--   title(label)           the shared title look: GothamBlack in neon cyan
local MidnightStyle = {}

MidnightStyle.CYAN = Color3.fromRGB(0, 220, 255) -- loading screen title glow and road line
MidnightStyle.PINK = Color3.fromRGB(255, 70, 140) -- loading screen horizon
MidnightStyle.SOFT_PINK = Color3.fromRGB(255, 150, 210) -- loading screen tagline
MidnightStyle.TITLE_FONT = Enum.Font.GothamBlack
MidnightStyle.WORDMARK = "MIDNIGHT PATTAYA"

-- inset keeps the line clear of a panel's rounded corners (pass the UICorner radius in pixels)
function MidnightStyle.accent(panel: GuiObject, inset: number?): Frame
	local pad = inset or 10
	local line = Instance.new("Frame")
	line.Name = "MidnightAccent"
	line.Position = UDim2.fromOffset(pad, 0)
	line.Size = UDim2.new(1, -2 * pad, 0, 2)
	line.BackgroundColor3 = Color3.new(1, 1, 1)
	line.BorderSizePixel = 0
	line.ZIndex = panel.ZIndex + 5
	local grad = Instance.new("UIGradient")
	grad.Color = ColorSequence.new(MidnightStyle.CYAN, MidnightStyle.PINK)
	grad.Parent = line
	line.Parent = panel
	return line
end

function MidnightStyle.wordmark(panel: GuiObject): TextLabel
	local t = Instance.new("TextLabel")
	t.Name = "MidnightWordmark"
	t.AnchorPoint = Vector2.new(1, 0)
	t.Position = UDim2.new(1, -10, 0, 5)
	t.Size = UDim2.fromOffset(140, 11)
	t.BackgroundTransparency = 1
	t.Font = MidnightStyle.TITLE_FONT
	t.TextSize = 10
	t.TextColor3 = MidnightStyle.SOFT_PINK
	t.TextTransparency = 0.15
	t.TextXAlignment = Enum.TextXAlignment.Right
	t.Text = MidnightStyle.WORDMARK
	t.ZIndex = panel.ZIndex + 5
	t.Parent = panel
	return t
end

function MidnightStyle.title(label: TextLabel)
	label.Font = MidnightStyle.TITLE_FONT
	label.TextColor3 = MidnightStyle.CYAN
end

return MidnightStyle
