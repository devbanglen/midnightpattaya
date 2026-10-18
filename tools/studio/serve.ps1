param([string]$Dir, [int]$Port = 8765, [int]$Seconds = 240)
# Serves files from $Dir on localhost for Studio's HttpService (GET /name). Exits after $Seconds.
$l = New-Object System.Net.HttpListener
$l.Prefixes.Add("http://localhost:$Port/")
$l.Start()
$deadline = (Get-Date).AddSeconds($Seconds)
while ((Get-Date) -lt $deadline) {
    $task = $l.GetContextAsync()
    while (-not $task.Wait(500)) { if ((Get-Date) -ge $deadline) { break } }
    if (-not $task.IsCompleted) { break }
    $ctx = $task.Result
    $name = [Uri]::UnescapeDataString($ctx.Request.Url.AbsolutePath.TrimStart('/'))
    $path = Join-Path $Dir $name
    if ($name -eq 'quit') { $ctx.Response.Close(); break }
    if (Test-Path -LiteralPath $path -PathType Leaf) {
        $bytes = [IO.File]::ReadAllBytes($path)
        $ctx.Response.ContentType = 'text/plain; charset=utf-8'
        $ctx.Response.OutputStream.Write($bytes, 0, $bytes.Length)
    } else { $ctx.Response.StatusCode = 404 }
    $ctx.Response.Close()
    Write-Output "served $name"
}
$l.Stop()
