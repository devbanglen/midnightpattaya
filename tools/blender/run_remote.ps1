# Local (Windows PowerShell 5.1+): same as run_remote.sh. Binary data is never piped through PowerShell (5.1 would
# corrupt it): archives go via temp files + scp.
#   powershell -ExecutionPolicy Bypass -File tools\blender\run_remote.ps1 [-HostName vast-rtx6000-1]
param([string]$HostName = 'vast-rtx6000-1')
$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$repo = Resolve-Path (Join-Path $here '..\..')
$out = Join-Path $repo 'build\vis_assets'
$tmp = Join-Path $env:TEMP 'mp_vis_tools.tar'
$ssh = @('-o', 'BatchMode=yes', $HostName)
& tar -cf $tmp --exclude=__pycache__ -C (Join-Path $repo 'tools') blender
& ssh @ssh 'mkdir -p /root/robloxrace/vis/tools && rm -rf /root/robloxrace/vis/tools/blender'
& scp -o BatchMode=yes $tmp "${HostName}:/root/robloxrace/vis/tools.tar"
& ssh @ssh 'cd /root/robloxrace/vis && tar -xf tools.tar -C tools && rm tools.tar'
& ssh @ssh 'bash /root/robloxrace/vis/tools/blender/remote_job.sh'
$rc = $LASTEXITCODE
& ssh @ssh 'cd /root/robloxrace/vis && tar -cf fetch.tar -C out/run . && tar -cf logs.tar -C logs .'
New-Item -ItemType Directory -Force $out | Out-Null
foreach ($d in 'buildings', 'roadside', 'racing', 'meta', 'qa', 'logs') {
    $p = Join-Path $out $d
    if (Test-Path $p) { Remove-Item -Recurse -Force $p -Confirm:$false }
}
New-Item -ItemType Directory -Force (Join-Path $out 'logs') | Out-Null
& scp -o BatchMode=yes "${HostName}:/root/robloxrace/vis/fetch.tar" (Join-Path $env:TEMP 'mp_vis_fetch.tar')
& scp -o BatchMode=yes "${HostName}:/root/robloxrace/vis/logs.tar" (Join-Path $env:TEMP 'mp_vis_logs.tar')
& tar -xf (Join-Path $env:TEMP 'mp_vis_fetch.tar') -C $out
& tar -xf (Join-Path $env:TEMP 'mp_vis_logs.tar') -C (Join-Path $out 'logs')
& ssh @ssh 'rm -f /root/robloxrace/vis/fetch.tar /root/robloxrace/vis/logs.tar'
Write-Host "fetched into $out (remote validate rc=$rc)"
Get-Content (Join-Path $out 'logs\timings.txt')
exit $rc
