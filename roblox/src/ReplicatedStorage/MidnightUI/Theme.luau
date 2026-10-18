-- MIDNIGHT PATTAYA UI design tokens (owner directive 2026-10-19, "PREMIUM GAME UI / UX MASTER DIRECTIVE").
-- Every HUD script reads colours, fonts, radii and motion from here; nothing hard-codes a colour. Fonts are Roblox's
-- own licensed Gotham family. Studio location: ReplicatedStorage.MidnightUI.Theme (ModuleScript).
local Theme = {}

local function hex(h: string): Color3
	return Color3.fromHex(h)
end

Theme.color = {
	navy = hex("#0B1020"), -- deep background
	surface = hex("#151D30"), -- panel surface
	surface2 = hex("#1C2740"), -- raised panel / hover
	cyan = hex("#00DFFF"), -- primary accent, speed, GPS route
	purple = hex("#A855F7"), -- secondary accent, titles, wordmark
	yellow = hex("#FFD54A"), -- racing yellow: position, best lap, rewards
	red = hex("#FF4858"), -- warning, wrong way, penalties
	green = hex("#3DDC84"), -- money gain, valid lap, "GO"
	text = hex("#FFFFFF"),
	textDim = hex("#9FB0CC"),
	textMuted = hex("#6B7A99"),
	line = hex("#2A3A5C"), -- hairlines / dividers
}

Theme.font = {
	display = Enum.Font.GothamBlack, -- big numbers, titles, wordmark
	bold = Enum.Font.GothamBold, -- labels, buttons
	body = Enum.Font.GothamMedium, -- body text
	mono = Enum.Font.RobotoMono, -- times (fixed width digits)
}

Theme.size = { -- text sizes at HUD scale 1 (the Responsive module multiplies)
	caption = 12, label = 14, body = 16, title = 20, big = 34, huge = 56,
}

Theme.radius = {panel = 12, pill = 999, button = 10, small = 6}
Theme.stroke = {thin = 1, normal = 1.5, thick = 2}
Theme.alpha = { -- BackgroundTransparency values
	panel = 0.22, panelDim = 0.4, overlay = 0.55, glass = 0.6,
}
Theme.pad = {xs = 4, s = 8, m = 12, l = 16, xl = 24}
Theme.motion = { -- seconds; Responsive.reducedMotion() shortens all of these to 0
	fast = 0.12, normal = 0.22, slow = 0.4,
	ease = Enum.EasingStyle.Quad, easeOut = Enum.EasingDirection.Out,
}

-- gradient helper: cyan -> purple accent line used on panel tops (same as ReplicatedStorage.MidnightStyle)
function Theme.accentGradient(): ColorSequence
	return ColorSequence.new(Theme.color.cyan, Theme.color.purple)
end

-- z-order bands inside the MidnightHUD ScreenGui (DisplayOrder) and other ScreenGuis
Theme.layer = {hud = 10, overlay = 20, modal = 30, toast = 40, loading = 100}

return Theme
