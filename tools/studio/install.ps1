# MIDNIGHT PATTAYA — one-shot Studio installer (disaster recovery / fresh place).
# Bundles every Luau source and data module into JSON files and serves them on localhost; the leader then runs
# tools/studio/install.luau in Studio (execute_luau or the command bar) which pulls the bundle and (re)creates every
# script and ModuleScript. Nothing in the place is deleted; existing instances are updated in place.
#
#   powershell -File tools\studio\install.ps1            # builds the bundles and serves them for 5 minutes
#
# Data modules come from the build outputs (regenerable: tools/mapgen + tools/circuit); scripts from roblox/src.
param([int]$Port = 8765, [int]$Seconds = 300)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$stage = Join-Path $env:TEMP 'midnight_install'
New-Item -ItemType Directory -Force $stage | Out-Null

function Bundle($name, $entries) {
    $b = @{}
    foreach ($e in $entries) { $b[$e.Key] = [IO.File]::ReadAllText($e.Value) }
    [IO.File]::WriteAllText((Join-Path $stage "$name.json"), (ConvertTo-Json $b -Compress -Depth 3), (New-Object Text.UTF8Encoding $false))
    "$name : $($b.Count) modules"
}
function Entries($dir, $prefix, $filter = '*.luau') {
    Get-ChildItem (Join-Path $root $dir) -Filter $filter | ForEach-Object { @{ Key = "$prefix/$($_.BaseName)"; Value = $_.FullName } }
}

# scripts: key = <container>/<name>; the installer maps containers to services and picks the class from the suffix
$scripts = @()
$scripts += Entries 'roblox/src/ServerScriptService' 'ServerScriptService'
$scripts += Entries 'roblox/src/ServerStorage' 'ServerStorage'
$scripts += Entries 'roblox/src/ReplicatedStorage' 'ReplicatedStorage'
$scripts += Entries 'roblox/src/ReplicatedStorage/MidnightUI' 'ReplicatedStorage/MidnightUI'   # UI modules (Folder MidnightUI)
$scripts += Entries 'roblox/src/ReplicatedFirst' 'ReplicatedFirst'
$scripts += @{ Key = 'ReplicatedStorage/VisMeshPalmLOD'; Value = (Join-Path $root 'roblox/src/ServerStorage/VisMeshPalmLOD.luau') }   # client copy of the palm LOD module (VIS-7.1)
$scripts += Entries 'roblox/src/StarterPlayer/StarterPlayerScripts' 'StarterPlayerScripts'
Bundle 'scripts' $scripts

# data: central slice (PattayaData), circuits, corridor, wide world
$data = @()
$data += Entries 'build/central_pattaya/roblox' 'PattayaData'
$data += Entries 'roblox/data/circuits' 'PattayaData/circuits'
$data += Entries 'build/bira/roblox_corridor' 'PattayaDataCorridor' 'chunk_*.luau'
$data += @{ Key = 'PattayaDataCorridor/manifest'; Value = (Join-Path $root 'build/bira/roblox_corridor/manifest.luau') }
$data += @{ Key = 'PattayaData/graph'; Value = (Join-Path $root 'build/bira/roblox_corridor/graph.luau') }
Get-ChildItem (Join-Path $root 'build/bira/roblox_corridor') -Filter 'graph_part_*.luau' | ForEach-Object { $data += @{ Key = "PattayaData/$($_.BaseName)"; Value = $_.FullName } }
$data += @{ Key = 'ReplicatedStorage/PattayaCorridorMap'; Value = (Join-Path $root 'build/bira/roblox_corridor/corridormap.luau') }
$wide = Join-Path $root 'build/pattaya_wide/roblox'
if (Test-Path $wide) {
    $data += Entries 'build/pattaya_wide/roblox' 'PattayaDataWide' 'chunk_*.luau'
    $data += @{ Key = 'PattayaDataWide/manifest'; Value = (Join-Path $wide 'manifest.luau') }
    $data += @{ Key = 'PattayaData/jobs'; Value = (Join-Path $wide 'jobs.luau') }           # wide stands replace the central ones
    $data += @{ Key = 'ReplicatedStorage/PattayaTraffic'; Value = (Join-Path $wide 'traffic.luau') }
    $data += @{ Key = 'ReplicatedStorage/PattayaWorldMap'; Value = (Join-Path $wide 'worldmap.luau') }
}
Bundle 'data' $data
Copy-Item (Join-Path $root 'tools/studio/install.luau') $stage

"serving $stage on http://localhost:$Port/ for $Seconds s — in Studio run the contents of tools/studio/install.luau"
& (Join-Path $PSScriptRoot 'serve.ps1') -Dir $stage -Port $Port -Seconds $Seconds
