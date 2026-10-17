# Concept images via OpenAI gpt-image, logged.
# Usage: powershell -File tools/pipeline/gen_concepts.ps1 <prompts.json> <out dir>
# prompts.json = [{id, size, quality, prompt, ref?: [png paths from the project root]}]; skips ids whose PNG exists (delete a PNG to redraw it).
# Keys come from .env (OPENAI_API_KEY, optional OPENAI_IMAGE_MODEL) and are never printed.
param(
    [Parameter(Mandatory = $true)][string]$Prompts,
    [Parameter(Mandatory = $true)][string]$Out
)
$ErrorActionPreference = 'Stop'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
Add-Type -AssemblyName System.Net.Http

$root = Resolve-Path (Join-Path $PSScriptRoot '..\..')
$envVars = @{}
foreach ($line in Get-Content (Join-Path $root '.env')) {
    $p = $line.Trim() -split '=', 2
    if ($p.Count -eq 2 -and $p[0] -notmatch '^#') { $envVars[$p[0].Trim()] = $p[1].Trim() }
}
$key = $envVars['OPENAI_API_KEY']
if (-not $key) { throw 'OPENAI_API_KEY missing in .env' }
$model = $envVars['OPENAI_IMAGE_MODEL']
if (-not $model) { $model = 'gpt-image-1' }

function Scrub([string]$s) { if ($s) { $s.Replace($key, '***') -replace 'sk-[A-Za-z0-9_\-]{8,}', 'sk-***' } }

New-Item -ItemType Directory -Force $Out | Out-Null
$log = Join-Path $Out 'log.jsonl'
$items = Get-Content $Prompts -Raw -Encoding UTF8 | ConvertFrom-Json
$ok = 0; $skip = 0; $err = 0

foreach ($it in $items) {
    $png = Join-Path $Out "$($it.id).png"
    if (Test-Path $png) { $skip++; continue }
    $size = if ($it.size) { $it.size } else { '1536x1024' }
    $quality = if ($it.quality) { $it.quality } else { 'high' }
    $t0 = Get-Date
    try {
        if ($it.ref) {
            # reference images (e.g. the chosen concept) go to /images/edits as multipart
            $form = New-Object System.Net.Http.MultipartFormDataContent
            foreach ($kv in @{ model = $model; prompt = $it.prompt; size = $size; quality = $quality; n = '1' }.GetEnumerator()) {
                $form.Add((New-Object System.Net.Http.StringContent([string]$kv.Value, [Text.Encoding]::UTF8)), $kv.Key)
            }
            foreach ($r in $it.ref) {
                $file = New-Object System.Net.Http.ByteArrayContent(, [IO.File]::ReadAllBytes((Join-Path $root $r)))
                $file.Headers.ContentType = [System.Net.Http.Headers.MediaTypeHeaderValue]::Parse('image/png')
                $form.Add($file, 'image[]', [IO.Path]::GetFileName($r))
            }
            $http = New-Object System.Net.Http.HttpClient
            $http.Timeout = [TimeSpan]::FromSeconds(600)
            $http.DefaultRequestHeaders.Authorization = New-Object System.Net.Http.Headers.AuthenticationHeaderValue('Bearer', $key)
            $resp = $http.PostAsync('https://api.openai.com/v1/images/edits', $form).Result
            $text = $resp.Content.ReadAsStringAsync().Result
            $http.Dispose()
            if (-not $resp.IsSuccessStatusCode) { throw "HTTP $([int]$resp.StatusCode): $text" }
            $res = $text | ConvertFrom-Json
        } else {
            $body = @{ model = $model; prompt = $it.prompt; size = $size; quality = $quality; n = 1 } | ConvertTo-Json -Compress
            $res = Invoke-RestMethod -Method Post -Uri 'https://api.openai.com/v1/images/generations' `
                -Headers @{ Authorization = "Bearer $key" } -ContentType 'application/json; charset=utf-8' `
                -Body ([Text.Encoding]::UTF8.GetBytes($body)) -TimeoutSec 600
        }
        [IO.File]::WriteAllBytes($png, [Convert]::FromBase64String($res.data[0].b64_json))
        $ok++; $status = 'ok'; $msg = ''
        Write-Host "ok    $($it.id)"
    } catch {
        $err++; $status = 'error'
        $msg = Scrub ($_.ErrorDetails.Message + ' ' + $_.Exception.Message)
        Write-Host "error $($it.id): $msg"
    }
    $entry = @{ id = $it.id; status = $status; model = $model; size = $size; quality = $quality
        secs = [math]::Round(((Get-Date) - $t0).TotalSeconds, 1); error = $msg; at = (Get-Date).ToString('s') }
    Add-Content -Path $log -Value ($entry | ConvertTo-Json -Compress) -Encoding UTF8
}
Write-Host "done: ok=$ok skipped=$skip error=$err"
