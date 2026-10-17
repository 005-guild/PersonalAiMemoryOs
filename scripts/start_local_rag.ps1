param([switch]$SkipDocker)

$ErrorActionPreference = 'Stop'
$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$ollamaExecutable = Join-Path $projectRoot '.tools/ollama/ollama.exe'
$ollamaCache = Join-Path $projectRoot '.cache/ollama'
$modelsDirectory = Join-Path $ollamaCache 'models'
$serviceRecord = Join-Path $ollamaCache 'service.json'
$ollamaUrl = 'http://127.0.0.1:11434'

function Get-LocalJson([string]$Url) {
    $request = [Net.HttpWebRequest]::Create($Url)
    $request.Proxy = $null
    $request.Timeout = 2000
    $request.ReadWriteTimeout = 2000
    $response = $null
    $reader = $null
    try {
        $response = $request.GetResponse()
        $reader = New-Object IO.StreamReader($response.GetResponseStream())
        return ($reader.ReadToEnd() | ConvertFrom-Json)
    } finally {
        if ($reader) { $reader.Dispose() }
        if ($response) { $response.Dispose() }
    }
}

if (-not (Test-Path -LiteralPath $ollamaExecutable -PathType Leaf)) {
    throw 'Ollama is missing. Extract the verified official Windows AMD64 ZIP into .tools/ollama first.'
}
New-Item -ItemType Directory -Path $modelsDirectory -Force | Out-Null

$listener = @(Get-NetTCPConnection -LocalPort 11434 -State Listen -ErrorAction SilentlyContinue)
if ($listener.Count) {
    if (-not (Test-Path -LiteralPath $serviceRecord)) {
        throw 'Port 11434 is occupied by an untracked service. Keep it running and inspect it before changing configuration.'
    }
    $savedService = Get-Content -LiteralPath $serviceRecord -Raw | ConvertFrom-Json
    $serverProcess = Get-Process -Id $savedService.pid -ErrorAction SilentlyContinue
    if (-not $serverProcess -or $serverProcess.Path -ne $ollamaExecutable -or
        $listener.OwningProcess -notcontains $serverProcess.Id -or $savedService.models_directory -ne $modelsDirectory) {
        throw 'The existing listener does not match this project Ollama instance; no process was stopped.'
    }
    $version = (Get-LocalJson "$ollamaUrl/api/version").version
} else {
    $env:OLLAMA_MODELS = $modelsDirectory
    $env:OLLAMA_HOST = '127.0.0.1:11434'
    $env:OLLAMA_NO_CLOUD = '1'
    $bypassEntries = @($env:NO_PROXY -split ',' | Where-Object { $_.Trim() }) + @('localhost', '127.0.0.1', '::1')
    $env:NO_PROXY = ($bypassEntries | Select-Object -Unique) -join ','
    # Use the current Windows proxy for HTTPS model downloads only.
    $registry = [Uri]'https://registry.ollama.ai'
    $proxy = [Net.WebRequest]::DefaultWebProxy.GetProxy($registry)
    if ($proxy -and $proxy -ne $registry) { $env:HTTPS_PROXY = $proxy.GetLeftPart([UriPartial]::Authority) }
    $serverProcess = Start-Process -FilePath $ollamaExecutable -ArgumentList 'serve' -WorkingDirectory $projectRoot `
        -WindowStyle Hidden -RedirectStandardOutput (Join-Path $ollamaCache 'server.stdout.log') `
        -RedirectStandardError (Join-Path $ollamaCache 'server.stderr.log') -PassThru
    $deadline = (Get-Date).AddSeconds(45)
    $version = $null
    do {
        if ($serverProcess.HasExited) { throw 'Ollama exited during startup; inspect .cache/ollama/server.stderr.log.' }
        try { $version = (Get-LocalJson "$ollamaUrl/api/version").version } catch { Start-Sleep -Milliseconds 250 }
    } while (-not $version -and (Get-Date) -lt $deadline)
    if (-not $version) { throw 'Ollama did not become ready within 45 seconds; inspect its logs.' }
    [ordered]@{ pid = $serverProcess.Id; executable = $ollamaExecutable; models_directory = $modelsDirectory;
        url = $ollamaUrl; version = $version; started_at = (Get-Date).ToUniversalTime().ToString('o') } |
        ConvertTo-Json | Set-Content -LiteralPath $serviceRecord -Encoding UTF8
}
Write-Host "Ollama $version ready at $ollamaUrl (PID $($serverProcess.Id))."

if (-not $SkipDocker) {
    $dockerRunning = $false
    try {
        & docker info --format '{{.ServerVersion}}' 2>$null | Out-Null
        $dockerRunning = ($LASTEXITCODE -eq 0)
    } catch { $dockerRunning = $false }
    if (-not $dockerRunning) {
        & docker desktop start
        if ($LASTEXITCODE -ne 0) { throw 'Docker Desktop could not start. Start Linux containers in Docker Desktop and run this script again.' }
    }
    & docker compose --project-directory $projectRoot --file (Join-Path $projectRoot 'docker-compose.yml') --profile rag up -d qdrant
    if ($LASTEXITCODE -ne 0) { throw 'Qdrant could not start. Existing API containers were not recreated.' }
    $deadline = (Get-Date).AddSeconds(45)
    $qdrant = $null
    do {
        try { $qdrant = Get-LocalJson 'http://127.0.0.1:6333/' } catch { Start-Sleep -Milliseconds 250 }
    } while (-not $qdrant -and (Get-Date) -lt $deadline)
    if (-not $qdrant -or $qdrant.version -notmatch '^1\.19\.\d+($|[-+])') { throw 'Qdrant is unavailable or is not the supported 1.19.x version.' }
    Write-Host "Qdrant $($qdrant.version) ready at http://127.0.0.1:6333/."
}
Write-Host 'Open the existing PersonalAiMemoryOs desktop. No model request or application restart was triggered by this script.'
