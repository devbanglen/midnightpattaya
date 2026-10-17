# Cut a turnaround sheet (top row: front | rear, bottom row: left side) into separate view PNGs + a mirrored right side.
# Usage: powershell -File tools/pipeline/split_turn.ps1 <sheet.png> <out dir> <id>
#   -> <out>/<id>_front.png, _back.png, _left.png, _right.png (tight crop + 6 % white margin)
param([string]$Sheet, [string]$Out, [string]$Id)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing
$img = [System.Drawing.Bitmap]::FromFile((Resolve-Path $Sheet))
$w = $img.Width; $h = $img.Height

# lock bits once, read as bytes (32bpp BGRA)
$rect = New-Object System.Drawing.Rectangle 0, 0, $w, $h
$bd = $img.LockBits($rect, 'ReadOnly', [System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
$buf = New-Object byte[] ($bd.Stride * $h)
[Runtime.InteropServices.Marshal]::Copy($bd.Scan0, $buf, 0, $buf.Length)
$img.UnlockBits($bd)
$stride = $bd.Stride

function IsInk([int]$x, [int]$y) {
    $i = $y * $stride + $x * 4
    return ($buf[$i] -lt 235 -or $buf[$i + 1] -lt 235 -or $buf[$i + 2] -lt 235)
}
function InkCount-Row([int]$y, [int]$x0, [int]$x1) { $c = 0; for ($x = $x0; $x -lt $x1; $x += 2) { if (IsInk $x $y) { $c++ } }; $c }
function InkCount-Col([int]$x, [int]$y0, [int]$y1) { $c = 0; for ($y = $y0; $y -lt $y1; $y += 2) { if (IsInk $x $y) { $c++ } }; $c }

# row split: the emptiest row band in the middle third
$best = 0; $bestC = [int]::MaxValue
for ($y = [int]($h * 0.35); $y -lt [int]($h * 0.65); $y += 2) { $c = InkCount-Row $y 0 $w; if ($c -lt $bestC) { $bestC = $c; $best = $y } }
$split = $best
# column split of the top row: emptiest column in the middle third
$bestX = 0; $bestC = [int]::MaxValue
for ($x = [int]($w * 0.35); $x -lt [int]($w * 0.65); $x += 2) { $c = InkCount-Col $x 0 $split; if ($c -lt $bestC) { $bestC = $c; $bestX = $x } }

function Tight([int]$x0, [int]$y0, [int]$x1, [int]$y1) {
    $minX = $x1; $minY = $y1; $maxX = $x0; $maxY = $y0
    for ($y = $y0; $y -lt $y1; $y += 2) { for ($x = $x0; $x -lt $x1; $x += 2) {
        if (IsInk $x $y) { if ($x -lt $minX) { $minX = $x }; if ($x -gt $maxX) { $maxX = $x }; if ($y -lt $minY) { $minY = $y }; if ($y -gt $maxY) { $maxY = $y } } } }
    return @($minX, $minY, $maxX, $maxY)
}
function Save-View($box, [string]$name, [bool]$mirror) {
    $bw = $box[2] - $box[0] + 1; $bh = $box[3] - $box[1] + 1
    $m = [int]([Math]::Max($bw, $bh) * 0.06)
    $dst = New-Object System.Drawing.Bitmap ($bw + 2 * $m), ($bh + 2 * $m)
    $g = [System.Drawing.Graphics]::FromImage($dst)
    $g.Clear([System.Drawing.Color]::White)
    $src = New-Object System.Drawing.Rectangle $box[0], $box[1], $bw, $bh
    $g.DrawImage($img, (New-Object System.Drawing.Rectangle $m, $m, $bw, $bh), $src, [System.Drawing.GraphicsUnit]::Pixel)
    $g.Dispose()
    if ($mirror) { $dst.RotateFlip([System.Drawing.RotateFlipType]::RotateNoneFlipX) }
    $dst.Save((Join-Path $Out "$($Id)_$name.png"), [System.Drawing.Imaging.ImageFormat]::Png)
    $dst.Dispose()
}
New-Item -ItemType Directory -Force $Out | Out-Null
$front = Tight 0 0 $bestX $split
$back = Tight $bestX 0 $w $split
$side = Tight 0 $split $w $h
Save-View $front 'front' $false
Save-View $back 'back' $false
Save-View $side 'left' $false
Save-View $side 'right' $true
$img.Dispose()
Write-Host "$Id split row=$split col=$bestX"
