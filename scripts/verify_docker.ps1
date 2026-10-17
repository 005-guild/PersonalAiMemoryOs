param(
    [ValidateRange(10, 600)]
    [int]$HealthTimeoutSeconds = 120
)

$ErrorActionPreference = 'Stop'
$originalProxyEnvironment = @{}
foreach ($proxyVariable in @('HTTP_PROXY', 'HTTPS_PROXY', 'NO_PROXY')) {
    $originalProxyEnvironment[$proxyVariable] = [Environment]::GetEnvironmentVariable($proxyVariable, 'Process')
}

function Initialize-VerificationProxy {
    $destinations = @{
        HTTP_PROXY = [Uri]'http://auth.docker.io/token'
        HTTPS_PROXY = [Uri]'https://auth.docker.io/token'
    }
    if ([Environment]::OSVersion.Platform -eq [PlatformID]::Win32NT) {
        $systemProxy = $null
        try {
            $systemProxy = [System.Net.WebRequest]::GetSystemWebProxy()
        }
        catch {
            Write-Warning 'Windows proxy discovery was unavailable; existing proxy settings were preserved.'
        }
        foreach ($variable in $destinations.Keys) {
            if (-not [string]::IsNullOrEmpty([Environment]::GetEnvironmentVariable($variable, 'Process'))) {
                continue
            }
            if ($null -eq $systemProxy) { continue }
            try {
                $destination = $destinations[$variable]
                if ($systemProxy.IsBypassed($destination)) { continue }
                $proxy = $systemProxy.GetProxy($destination)
                if ($null -ne $proxy -and $proxy.Scheme -in @('http', 'https') -and
                    $proxy.AbsoluteUri -ne $destination.AbsoluteUri) {
                    [Environment]::SetEnvironmentVariable($variable, $proxy.AbsoluteUri, 'Process')
                }
            }
            catch {
                # Exception text and proxy URLs can contain credentials.
                Write-Warning 'A Windows proxy could not be resolved; existing proxy settings were preserved.'
            }
        }
    }
    $bypass = @()
    $existingBypass = [Environment]::GetEnvironmentVariable('NO_PROXY', 'Process')
    if (-not [string]::IsNullOrEmpty($existingBypass)) {
        $bypass += $existingBypass.Split(',') | ForEach-Object { $_.Trim() }
    }
    foreach ($loopback in @('localhost', '127.0.0.1', '::1')) {
        if ($bypass -notcontains $loopback) { $bypass += $loopback }
    }
    [Environment]::SetEnvironmentVariable('NO_PROXY', ($bypass -join ','), 'Process')
}

try {
Initialize-VerificationProxy
$projectRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$cacheRoot = Join-Path $projectRoot '.cache'
$token = [Guid]::NewGuid().ToString('N')
$projectName = 'memory-os-verify-' + $token.Substring(0, 12)
$validationRoot = Join-Path $cacheRoot ('docker-validation-' + $token)
$validationData = Join-Path $validationRoot 'data'
$validationKnowledge = Join-Path $validationRoot 'knowledge'
$validationConfig = Join-Path $validationRoot 'config'
$validationMock = Join-Path $validationRoot 'mock_model_server.py'
$processingState = Join-Path $validationRoot 'processing-state.json'
$composeFile = Join-Path $validationRoot 'compose.json'
$localPython = Join-Path $projectRoot '.venv/Scripts/python.exe'
$composeArgs = @('compose', '--project-name', $projectName, '-f', $composeFile)
$cleanupRequired = $false

function Invoke-Docker {
    param([string[]]$Arguments)
    # Windows PowerShell 5.1 turns native stderr into ErrorRecord objects even
    # for successful Docker progress messages. Check the exit code explicitly.
    $previousPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        $output = & docker @Arguments 2>&1
        $exitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousPreference
    }
    if ($exitCode -ne 0) {
        throw "Docker command failed: docker $($Arguments -join ' ')`n$($output -join [Environment]::NewLine)"
    }
    return $output
}

function Wait-Healthy {
    $deadline = [DateTime]::UtcNow.AddSeconds($HealthTimeoutSeconds)
    $containerId = (Invoke-Docker ($composeArgs + @('ps', '-q', 'api')) | Out-String).Trim()
    if (-not $containerId) {
        throw 'The validation API container was not created.'
    }
    while ([DateTime]::UtcNow -lt $deadline) {
        $inspection = (Invoke-Docker @('inspect', $containerId) | Out-String) | ConvertFrom-Json
        $state = @($inspection)[0].State
        if ($state.Health.Status -eq 'healthy') {
            return
        }
        if ($state.Status -eq 'exited' -or $state.Status -eq 'dead') {
            break
        }
        Start-Sleep -Seconds 2
    }
    $logs = Invoke-Docker ($composeArgs + @('logs', '--no-color', 'api'))
    throw "The validation container did not become healthy.`n$($logs -join [Environment]::NewLine)"
}

function Invoke-Api {
    param([string]$Method, [string]$Path, [object]$Body = $null)
    $encoded = ''
    if ($null -ne $Body) {
        $jsonBody = $Body | ConvertTo-Json -Depth 20 -Compress
        $encoded = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($jsonBody))
    }
    # Base64 keeps JSON quotes intact across Windows PowerShell native arguments.
    $code = "import base64,json,urllib.request; body=base64.b64decode('$encoded') if '$encoded' else None; request=urllib.request.Request('http://127.0.0.1:8000$Path',data=body,headers={'Content-Type':'application/json'},method='$Method'); print(urllib.request.urlopen(request,timeout=10).read().decode())"
    return (Invoke-Docker ($composeArgs + @('exec', '-T', 'api', '/app/.venv/bin/python', '-c', $code)) | Out-String) | ConvertFrom-Json
}

function Set-HostApiAddress {
    $binding = (Invoke-Docker ($composeArgs + @('port', 'api', '8000')) | Out-String).Trim()
    $address = [Uri]('http://' + $binding)
    if ($address.Host -ne '127.0.0.1' -or $address.Port -le 0) {
        throw 'The isolated HTTP import endpoint must use an allocated loopback port.'
    }
    $script:hostApiAddress = $address.GetLeftPart([UriPartial]::Authority)
}

function Invoke-HostImport {
    param([string]$FilePath, [bool]$DryRun)
    $query = $DryRun.ToString().ToLowerInvariant()
    $request = [System.Net.WebRequest]::CreateHttp($hostApiAddress + '/api/v1/imports/zhihu?dry_run=' + $query)
    $request.Method = 'POST'
    $request.ContentType = 'application/json'
    $request.Proxy = $null
    $request.KeepAlive = $false
    $request.Timeout = 10000
    $payload = [System.IO.File]::ReadAllBytes($FilePath)
    $request.ContentLength = $payload.Length
    $stream = $null
    $response = $null
    $reader = $null
    try {
        $stream = $request.GetRequestStream()
        $stream.Write($payload, 0, $payload.Length)
        $stream.Dispose()
        $stream = $null
        $response = $request.GetResponse()
        $reader = [System.IO.StreamReader]::new($response.GetResponseStream(), [Text.Encoding]::UTF8)
        return $reader.ReadToEnd() | ConvertFrom-Json
    }
    finally {
        if ($reader) { $reader.Dispose() }
        if ($response) { $response.Dispose() }
        if ($stream) { $stream.Dispose() }
    }
}

function Assert-ImportReport {
    param([object]$Report, [hashtable]$Expected)
    foreach ($field in $Expected.Keys) {
        if ($Report.PSObject.Properties.Name -notcontains $field -or $Report.$field -ne $Expected[$field]) {
            throw "Unexpected import report field: $field."
        }
    }
}

function Get-SourceSnapshot {
    return (Invoke-Api 'GET' '/api/v1/sources?include_deleted=true&limit=100') | ConvertTo-Json -Depth 30 -Compress
}

function Get-KnowledgeSnapshot {
    return (Invoke-Api 'GET' '/api/v1/knowledge?include_deleted=true&limit=100') | ConvertTo-Json -Depth 30 -Compress
}

function Get-VaultSnapshot {
    $files = @(Get-ChildItem -LiteralPath $validationKnowledge -Recurse -File -Force |
        Sort-Object FullName | ForEach-Object {
            [pscustomobject]@{
                path = $_.FullName.Substring($validationKnowledge.Length + 1).Replace('\', '/')
                hash = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash
            }
        })
    return ConvertTo-Json -InputObject $files -Depth 10 -Compress
}

function Assert-KnowledgeUnchanged {
    if ((Get-KnowledgeSnapshot) -cne $knowledgeBeforeImport -or (Get-VaultSnapshot) -cne $vaultBeforeImport) {
        throw 'Zhihu import unexpectedly created or changed Knowledge or vault files.'
    }
}

function Invoke-ProcessingVerification {
    param([string]$Phase)
    & $localPython (Join-Path $PSScriptRoot 'processing_verification.py') `
        --base-url $hostApiAddress --vault $validationKnowledge --state $processingState --phase $Phase
    if ($LASTEXITCODE -ne 0) { throw "The isolated four-protocol processing check failed: $Phase." }
}

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw 'Docker is unavailable. Install/start Docker Desktop with Linux containers and the Compose plugin, then rerun this script.'
}
if (-not (Test-Path -LiteralPath $localPython -PathType Leaf)) {
    throw 'The project Python environment is missing. Complete the README uv setup first.'
}
if ((Test-Path -LiteralPath $cacheRoot) -and
    ((Get-Item -LiteralPath $cacheRoot -Force).Attributes -band [System.IO.FileAttributes]::ReparsePoint)) {
    throw 'The project verification cache cannot be a symbolic link or junction.'
}

Push-Location $projectRoot
try {
    Invoke-Docker @('info') | Out-Null
    Invoke-Docker @('compose', 'version') | Write-Host
    New-Item -ItemType Directory -Path $validationData -Force | Out-Null
    New-Item -ItemType Directory -Path $validationKnowledge -Force | Out-Null
    New-Item -ItemType Directory -Path $validationConfig -Force | Out-Null
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'mock_model_server.py') -Destination $validationMock
    $prepareCode = "import sys; from pathlib import Path; sys.path.insert(0,'scripts'); from processing_verification import write_profiles; write_profiles(Path(sys.argv[1]),'http://mock_model:8080')"
    & $localPython -c $prepareCode (Join-Path $validationConfig 'ai-providers.yml')
    if ($LASTEXITCODE -ne 0) { throw 'Could not prepare isolated model profiles.' }

    # Resolve the real configuration first, then replace only validation storage
    # and published ports. This avoids Compose version-specific merge tags.
    $baseArgs = @('compose', '--project-name', $projectName, '-f', (Join-Path $projectRoot 'docker-compose.yml'))
    $config = (Invoke-Docker ($baseArgs + @('config', '--format', 'json')) | Out-String) | ConvertFrom-Json
    if (-not $config.services.api) {
        throw 'The project Compose configuration has no api service.'
    }
    $config.PSObject.Properties.Remove('name')
    # Name the one built image explicitly so the stdlib mock uses exactly that
    # image without adding a production service or any extra build dependency.
    $validationImage = $projectName + '-api:verification'
    $config.services.api | Add-Member -NotePropertyName image -NotePropertyValue $validationImage -Force
    $config.services.api | Add-Member -NotePropertyName networks -NotePropertyValue @('default', 'model_backend') -Force
    $config.services.api.ports = @([pscustomobject]@{
        target = 8000
        published = '0'
        host_ip = '127.0.0.1'
        protocol = 'tcp'
    })
    $config.services.api.volumes = @([pscustomobject]@{
        type = 'bind'
        source = $validationData
        target = '/app/data'
    }, [pscustomobject]@{
        type = 'bind'
        source = $validationKnowledge
        target = '/app/knowledge'
    }, [pscustomobject]@{
        type = 'bind'
        source = $validationConfig
        target = '/app/config'
        read_only = $true
    })
    # Isolated acceptance must never inherit a personal provider configuration or
    # credentials from the resolved production Compose environment.
    foreach ($property in @($config.services.api.environment.PSObject.Properties.Name)) {
        if ($property -like 'MEMORY_OS_AI_*') { $config.services.api.environment.PSObject.Properties.Remove($property) }
    }
    foreach ($entry in @{
        MEMORY_OS_AI_ENABLED = 'true'
        MEMORY_OS_AI_CONFIG_FILE = '/app/config/ai-providers.yml'
        MEMORY_OS_AI_DEFAULT_PROFILE = 'openai_chat'
        MEMORY_OS_AI_KEYS__VERIFICATION = 'verification-only-key'
        HTTP_PROXY = ''; HTTPS_PROXY = ''; ALL_PROXY = ''
        NO_PROXY = 'localhost,127.0.0.1,::1,mock_model'
    }.GetEnumerator()) {
        $config.services.api.environment | Add-Member -NotePropertyName $entry.Key -NotePropertyValue $entry.Value -Force
    }
    $config.services | Add-Member -NotePropertyName mock_model -NotePropertyValue ([pscustomobject]@{
        image = $validationImage
        networks = @('model_backend')
        environment = [pscustomobject]@{
            HTTP_PROXY = ''; HTTPS_PROXY = ''; ALL_PROXY = ''
            NO_PROXY = 'localhost,127.0.0.1,::1,mock_model'
        }
        command = @('/app/.venv/bin/python', '/verification/mock_model_server.py', '--host', '0.0.0.0', '--port', '8080')
        volumes = @([pscustomobject]@{
            type = 'bind'; source = $validationMock; target = '/verification/mock_model_server.py'; read_only = $true
        })
        healthcheck = [pscustomobject]@{
            test = @('CMD', '/app/.venv/bin/python', '-c', "import urllib.request; assert urllib.request.urlopen('http://127.0.0.1:8080/health',timeout=2).status == 200")
            interval = '2s'; timeout = '3s'; retries = 20
        }
    }) -Force
    $config | Add-Member -NotePropertyName networks -NotePropertyValue ([pscustomobject]@{
        # Docker Desktop can omit the published port on an internal-only API.
        # Keep host publication on a normal bridge; the model has only its
        # dedicated internal backend and never publishes a host endpoint.
        default = [pscustomobject]@{ driver = 'bridge' }
        model_backend = [pscustomobject]@{ driver = 'bridge'; internal = $true }
    }) -Force
    $json = $config | ConvertTo-Json -Depth 30
    [System.IO.File]::WriteAllText($composeFile, $json, [System.Text.UTF8Encoding]::new($false))

    Write-Host "Building isolated validation project $projectName..."
    $cleanupRequired = $true
    Invoke-Docker ($composeArgs + @('build', 'api')) | Write-Host
    Write-Host 'Running explicit Alembic migrations before service startup...'
    Invoke-Docker ($composeArgs + @('run', '--rm', 'api', '/app/.venv/bin/alembic', 'upgrade', 'head')) | Write-Host
    Invoke-Docker ($composeArgs + @('up', '-d')) | Write-Host
    Wait-Healthy
    Set-HostApiAddress

    Write-Host 'Creating Source and Knowledge through the API and checking automatic Markdown export...'
    $source = Invoke-Api 'POST' '/api/v1/sources' @{ title = 'Docker source'; content = $token }
    $note = Invoke-Api 'POST' '/api/v1/knowledge' @{ title = 'Docker knowledge'; source_id = $source.id; body = 'Initial Docker body.' }
    $deadline = [DateTime]::UtcNow.AddSeconds($HealthTimeoutSeconds)
    $noteFile = $null
    while ([DateTime]::UtcNow -lt $deadline) {
        $noteFile = Get-ChildItem -LiteralPath $validationKnowledge -Recurse -File -Filter '*.md' |
            Where-Object { (Get-Content -LiteralPath $_.FullName -Raw -Encoding UTF8) -match [regex]::Escape($note.id) } |
            Select-Object -First 1
        if ($noteFile) { break }
        Start-Sleep -Seconds 2
    }
    if (-not $noteFile) { throw 'Knowledge was not automatically exported to the temporary vault.' }
    if (-not (Test-Path -LiteralPath (Join-Path $validationKnowledge '.memory-os-vault') -PathType Leaf)) {
        throw 'The temporary vault identity marker was not created.'
    }
    $externalMarker = 'Docker external edit ' + $token
    $markdown = Get-Content -LiteralPath $noteFile.FullName -Raw -Encoding UTF8
    [System.IO.File]::WriteAllText($noteFile.FullName, $markdown + "`n$externalMarker`n", [System.Text.UTF8Encoding]::new($false))
    $deadline = [DateTime]::UtcNow.AddSeconds($HealthTimeoutSeconds)
    $imported = $false
    while ([DateTime]::UtcNow -lt $deadline) {
        $current = Invoke-Api 'GET' ('/api/v1/knowledge/' + $note.id)
        if ($current.body.Contains($externalMarker)) { $imported = $true; break }
        Start-Sleep -Seconds 2
    }
    if (-not $imported) { throw 'The host Markdown edit was not imported automatically.' }

    Write-Host 'Checking host HTTP Zhihu preview/import, mixed invalid input, and unchanged Knowledge/vault...'
    $knowledgeBeforeImport = Get-KnowledgeSnapshot
    $vaultBeforeImport = Get-VaultSnapshot
    $sourcesBeforeImport = Get-SourceSnapshot
    $answerId = [string](900000000000L + [Convert]::ToInt64($token.Substring(0, 8), 16))
    $articleId = [string](910000000000L + [Convert]::ToInt64($token.Substring(8, 8), 16))
    $fixture = @{
        schema_version = 1
        items = @(
            @{ url = "http://WWW.ZHIHU.COM/question/123456/answer/${answerId}?fixture=1#body"; title = 'Synthetic answer'; author = 'Fixture author'; content = "Offline answer fixture $token" },
            @{ url = 'https://example.invalid/not-zhihu'; title = 'Invalid fixture'; content = 'Rejected fixture body.' },
            @{ url = "https://ZHUANLAN.ZHIHU.COM/p/${articleId}/?fixture=1#body"; title = 'Synthetic article'; author = $null; content = "Offline article fixture $token" }
        )
    }
    $fixturePath = Join-Path $validationRoot 'zhihu-fixture.json'
    [System.IO.File]::WriteAllText($fixturePath, ($fixture | ConvertTo-Json -Depth 20), [System.Text.UTF8Encoding]::new($false))
    $preview = Invoke-HostImport $fixturePath $true
    Assert-ImportReport $preview @{ dry_run = $true; total = 3; processed = 3; created = 0; skipped = 0; invalid = 1; would_create = 2; failed = 0 }
    if ((Get-SourceSnapshot) -cne $sourcesBeforeImport) { throw 'Dry-run preview modified Sources.' }
    Assert-KnowledgeUnchanged

    $actualImport = Invoke-HostImport $fixturePath $false
    Assert-ImportReport $actualImport @{ dry_run = $false; total = 3; processed = 3; created = 2; skipped = 0; invalid = 1; would_create = 0; failed = 0 }
    $createdAnswer = Invoke-Api 'GET' ('/api/v1/sources/' + $actualImport.items[0].source_id)
    $createdArticle = Invoke-Api 'GET' ('/api/v1/sources/' + $actualImport.items[2].source_id)
    if ($createdAnswer.url -ne "https://www.zhihu.com/question/123456/answer/$answerId" -or
        $createdArticle.url -ne "https://zhuanlan.zhihu.com/p/$articleId") {
        throw 'Imported Source URLs were not canonicalized.'
    }
    $sourcesAfterImport = Get-SourceSnapshot
    if (($sourcesAfterImport | ConvertFrom-Json).total -ne ($sourcesBeforeImport | ConvertFrom-Json).total + 2) {
        throw 'The import did not create exactly two Sources.'
    }
    Assert-KnowledgeUnchanged

    $repeated = Invoke-HostImport $fixturePath $false
    Assert-ImportReport $repeated @{ dry_run = $false; total = 3; processed = 3; created = 0; skipped = 2; invalid = 1; would_create = 0; failed = 0 }
    if ((Get-SourceSnapshot) -cne $sourcesAfterImport) { throw 'Repeated import modified Sources.' }
    Assert-KnowledgeUnchanged

    Write-Host 'Checking changed duplicate content and soft-deleted-source preservation...'
    $changedFixture = @{ schema_version = 1; items = @(@{
        url = "https://www.zhihu.com/question/654321/answer/$answerId"
        title = 'Changed fixture title'
        author = 'Changed fixture author'
        content = 'Changed fixture content.'
    }) }
    $changedPath = Join-Path $validationRoot 'zhihu-changed.json'
    [System.IO.File]::WriteAllText($changedPath, ($changedFixture | ConvertTo-Json -Depth 20), [System.Text.UTF8Encoding]::new($false))
    $changed = Invoke-HostImport $changedPath $false
    Assert-ImportReport $changed @{ dry_run = $false; total = 1; processed = 1; created = 0; skipped = 1; invalid = 0; would_create = 0; failed = 0 }
    foreach ($field in @('title', 'author', 'content')) {
        if ($changed.items[0].differing_fields -notcontains $field) { throw 'Changed duplicate differences were not reported.' }
    }
    if ($changed.items[0].source_id -ne $createdAnswer.id -or
        $changed.items[0].differing_fields.Count -ne 3 -or (Get-SourceSnapshot) -cne $sourcesAfterImport) {
        throw 'Changed duplicate import overwrote or duplicated an existing Source.'
    }
    Assert-KnowledgeUnchanged

    Invoke-Api 'DELETE' ('/api/v1/sources/' + $createdAnswer.id + '?expected_version=' + $createdAnswer.version) | Out-Null
    $sourcesAfterDeletion = Get-SourceSnapshot
    $deletedRepeat = Invoke-HostImport $fixturePath $false
    Assert-ImportReport $deletedRepeat @{ dry_run = $false; total = 3; processed = 3; created = 0; skipped = 2; invalid = 1; would_create = 0; failed = 0 }
    if ((Get-SourceSnapshot) -cne $sourcesAfterDeletion) { throw 'Import restored or changed a soft-deleted Source.' }
    Assert-KnowledgeUnchanged

    Invoke-ProcessingVerification 'generate'
    # Processing deliberately creates Sources/notes after import-only assertions.
    # Preserve this new baseline while proving a repeated import after recreation
    # still changes neither those drafts/notes nor any vault bytes.
    $sourcesAfterDeletion = Get-SourceSnapshot
    $knowledgeBeforeImport = Get-KnowledgeSnapshot
    $vaultBeforeImport = Get-VaultSnapshot

    Write-Host 'Recreating the container and checking database and Markdown persistence...'
    Invoke-Docker ($composeArgs + @('up', '-d', '--force-recreate')) | Write-Host
    Wait-Healthy
    Set-HostApiAddress
    $persisted = Invoke-Api 'GET' ('/api/v1/knowledge/' + $note.id)
    $persistedSource = Invoke-Api 'GET' ('/api/v1/sources/' + $source.id)
    if (-not $persisted.body.Contains($externalMarker) -or $persistedSource.content -ne $token) {
        throw 'API records did not survive container recreation.'
    }
    if (-not (Test-Path -LiteralPath $noteFile.FullName -PathType Leaf) -or
        -not (Get-Content -LiteralPath $noteFile.FullName -Raw -Encoding UTF8).Contains($externalMarker)) {
        throw 'The edited Markdown did not survive container recreation.'
    }
    $restartRepeat = Invoke-HostImport $fixturePath $false
    Assert-ImportReport $restartRepeat @{ dry_run = $false; total = 3; processed = 3; created = 0; skipped = 2; invalid = 1; would_create = 0; failed = 0 }
    if ((Get-SourceSnapshot) -cne $sourcesAfterDeletion) { throw 'Deduplication did not survive container recreation.' }
    Assert-KnowledgeUnchanged
    Invoke-ProcessingVerification 'persist'

    Write-Host 'Stopping the container before reading the same file on the host...'
    Invoke-Docker ($composeArgs + @('stop', 'api')) | Write-Host
    $databasePath = Join-Path $validationData 'memory.db'
    if (-not (Test-Path -LiteralPath $databasePath -PathType Leaf)) {
        throw 'The shared SQLite file was not created in the validation directory.'
    }
    $hostCode = "import sqlite3,sys; c=sqlite3.connect(sys.argv[1]); assert c.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'; assert '$externalMarker' in '\n'.join(c.iterdump()); assert c.execute('SELECT COUNT(*) FROM source_origins').fetchone()[0] == 2; c.close(); print('Host database and persistent import identity checks passed.')"
    & $localPython -c $hostCode $databasePath
    if ($LASTEXITCODE -ne 0) {
        throw 'The host Python process could not verify the shared SQLite file.'
    }
}
finally {
    $safeToRemove = $true
    $cleanupError = $null
    if ($cleanupRequired) {
        try {
            Invoke-Docker ($composeArgs + @('down', '--remove-orphans')) | Write-Host
        }
        catch {
            $safeToRemove = $false
            $cleanupError = $_.Exception
            Write-Warning "Container cleanup failed; preserving $validationRoot. $($_.Exception.Message)"
        }
    }
    try {
        if ($safeToRemove -and (Test-Path -LiteralPath $validationRoot)) {
            $resolvedRoot = [System.IO.Path]::GetFullPath((Resolve-Path -LiteralPath $validationRoot).Path)
            $expectedRoot = [System.IO.Path]::GetFullPath($validationRoot)
            $allowedPrefix = [System.IO.Path]::GetFullPath($cacheRoot).TrimEnd('\', '/') + [System.IO.Path]::DirectorySeparatorChar
            if (-not $resolvedRoot.StartsWith($allowedPrefix, [StringComparison]::OrdinalIgnoreCase) -or $resolvedRoot -ne $expectedRoot) {
                throw 'Refusing to remove a validation directory outside the project cache.'
            }
            Remove-Item -LiteralPath $resolvedRoot -Recurse -Force
        }
    }
    finally {
        Pop-Location
    }
    if ($cleanupError) {
        throw "Docker validation cleanup failed; temporary files were preserved. $($cleanupError.Message)"
    }
}

Write-Host 'Docker migration, CRUD/sync, Zhihu imports, four model protocols, draft adoption, persistence, shared host read, and cleanup passed.'
}
finally {
    foreach ($proxyVariable in $originalProxyEnvironment.Keys) {
        [Environment]::SetEnvironmentVariable($proxyVariable, $originalProxyEnvironment[$proxyVariable], 'Process')
    }
}
