param(
    [switch]$SkipDocker,
    [switch]$EnableReranker,
    [string]$RerankerRevision = '',
    [string]$ProjectRoot = (Join-Path $PSScriptRoot '..')
)

$ErrorActionPreference = 'Stop'
$projectRoot = [IO.Path]::GetFullPath($ProjectRoot)
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
    $supervisorScript = Join-Path $PSScriptRoot 'supervise_ollama.ps1'
    $supervisorArgs = @('-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File',
        ('"' + $supervisorScript + '"'), '-ProjectRoot', ('"' + $projectRoot + '"'))
    $supervisor = Start-Process -FilePath (Join-Path $PSHOME 'powershell.exe') -ArgumentList $supervisorArgs `
        -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru
    $deadline = (Get-Date).AddSeconds(45)
    $serverProcess = $null
    do {
        if ($supervisor.HasExited) { throw 'Ollama log supervisor exited during startup.' }
        $supervisorRecord = Join-Path $ollamaCache 'supervisor.json'
        if (Test-Path -LiteralPath $supervisorRecord) {
            $supervisorState = Get-Content -LiteralPath $supervisorRecord -Raw | ConvertFrom-Json
            if ($supervisorState.supervisor_pid -eq $supervisor.Id) { $serverProcess = Get-Process -Id $supervisorState.child_pid -ErrorAction SilentlyContinue }
        }
        if (-not $serverProcess) { Start-Sleep -Milliseconds 100 }
    } while (-not $serverProcess -and (Get-Date) -lt $deadline)
    if (-not $serverProcess) { throw 'Ollama did not publish a child process record.' }
    $version = $null
    do {
        if ($serverProcess.HasExited) { throw 'Ollama exited during startup; inspect .cache/ollama/server.stderr.log.' }
        try { $version = (Get-LocalJson "$ollamaUrl/api/version").version } catch { Start-Sleep -Milliseconds 250 }
    } while (-not $version -and (Get-Date) -lt $deadline)
    if (-not $version) { throw 'Ollama did not become ready within 45 seconds; inspect its logs.' }
    $ownedListener = @(Get-NetTCPConnection -LocalPort 11434 -State Listen -ErrorAction SilentlyContinue)
    if ($serverProcess.HasExited -or $ownedListener.OwningProcess -notcontains $serverProcess.Id) {
        throw 'Another process acquired port 11434 during startup; its ownership record was not changed.'
    }
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
    if ($EnableReranker) {
        $modelManifest = Join-Path $projectRoot '.cache/reranker/model-manifest.json'
        if (-not (Test-Path -LiteralPath $modelManifest -PathType Leaf)) { throw 'Prepare and verify the pinned reranker model first. Desktop startup never downloads weights.' }
        $modelRecord = Get-Content -LiteralPath $modelManifest -Raw | ConvertFrom-Json
        if ($modelRecord.model -ne 'BAAI/bge-reranker-v2-m3' -or
            ($RerankerRevision -and $modelRecord.revision -ne $RerankerRevision)) { throw 'Reranker model revision does not match the saved application configuration.' }
        foreach ($modelFile in @('config.json', 'tokenizer.json', 'model.safetensors')) {
            if (-not (Test-Path -LiteralPath (Join-Path $projectRoot ".cache/reranker/models/bge-reranker-v2-m3/$modelFile") -PathType Leaf)) { throw 'Verified reranker model files are missing.' }
        }
        & docker image inspect 'ghcr.io/huggingface/text-embeddings-inference:89-1.9' 2>$null | Out-Null
        if ($LASTEXITCODE -ne 0) { throw 'Prepare the pinned TEI image first. Desktop startup does not pull it automatically.' }
        & docker compose --project-directory $projectRoot --file (Join-Path $projectRoot 'docker-compose.yml') --profile rerank up -d --no-deps --pull never reranker
        if ($LASTEXITCODE -ne 0) { throw 'Reranker could not start. Check Docker GPU support and the local port; no other service was stopped.' }
        $deadline = (Get-Date).AddSeconds(60)
        $reranker = $null
        do {
            try { $reranker = Get-LocalJson 'http://127.0.0.1:18081/info' } catch { Start-Sleep -Milliseconds 250 }
        } while (-not $reranker -and (Get-Date) -lt $deadline)
        if (-not $reranker) { throw 'Reranker is not ready; inspect the reranker container logs.' }
        Write-Host 'Local reranker ready at http://127.0.0.1:18081/. No inference was requested.'
    }
}
Write-Host 'Open the existing PersonalAiMemoryOs desktop. No model request or application restart was triggered by this script.'
