param([string]$ProjectRoot, [switch]$LibraryOnly)

$ErrorActionPreference = 'Stop'

function Write-BoundedLog([string]$Path, [string]$Text, [long]$MaxBytes = 8388608, [int]$Backups = 3) {
    if ($Text.Length -gt 65536) { $Text = $Text.Substring(0, 65536) + ' [line truncated]' }
    $encoding = New-Object System.Text.UTF8Encoding($false)
    $bytes = $encoding.GetBytes($Text + [Environment]::NewLine)
    if ((Test-Path -LiteralPath $Path) -and ((Get-Item -LiteralPath $Path).Length + $bytes.Length -gt $MaxBytes)) {
        $oldest = "$Path.$Backups"
        if (Test-Path -LiteralPath $oldest) { Remove-Item -LiteralPath $oldest }
        for ($index = $Backups - 1; $index -ge 1; $index--) {
            $previous = "$Path.$index"
            if (Test-Path -LiteralPath $previous) { Move-Item -LiteralPath $previous -Destination "$Path.$($index + 1)" }
        }
        Move-Item -LiteralPath $Path -Destination "$Path.1"
    }
    $stream = [IO.File]::Open($Path, [IO.FileMode]::Append, [IO.FileAccess]::Write, [IO.FileShare]::Read)
    try { $stream.Write($bytes, 0, $bytes.Length) } finally { $stream.Dispose() }
}

if ($LibraryOnly) { return }
$projectDirectory = [IO.Path]::GetFullPath($ProjectRoot)
$executable = Join-Path $projectDirectory '.tools/ollama/ollama.exe'
$logs = Join-Path $projectDirectory '.cache/ollama'
if (-not (Test-Path -LiteralPath $executable -PathType Leaf)) { throw 'Verified Ollama executable is missing.' }
$start = New-Object Diagnostics.ProcessStartInfo
$start.FileName = $executable
$start.Arguments = 'serve'
$start.WorkingDirectory = $projectDirectory
$start.UseShellExecute = $false
$start.CreateNoWindow = $true
$start.RedirectStandardOutput = $true
$start.RedirectStandardError = $true
$child = New-Object Diagnostics.Process
$child.StartInfo = $start
if (-not $child.Start()) { throw 'Ollama could not start.' }
$state = [ordered]@{ supervisor_pid = $PID; child_pid = $child.Id }
$temporary = Join-Path $logs "supervisor-$PID.tmp"
$state | ConvertTo-Json | Set-Content -LiteralPath $temporary -Encoding UTF8
Move-Item -LiteralPath $temporary -Destination (Join-Path $logs 'supervisor.json') -Force
$stdout = $child.StandardOutput.ReadLineAsync()
$stderr = $child.StandardError.ReadLineAsync()
while ($null -ne $stdout -or $null -ne $stderr) {
    $progress = $false
    if ($null -ne $stdout -and $stdout.IsCompleted) {
        $progress = $true
        $line = $stdout.GetAwaiter().GetResult()
        $stdout = $null
        if ($null -ne $line) { Write-BoundedLog (Join-Path $logs 'server.stdout.log') $line; $stdout = $child.StandardOutput.ReadLineAsync() }
    }
    if ($null -ne $stderr -and $stderr.IsCompleted) {
        $progress = $true
        $line = $stderr.GetAwaiter().GetResult()
        $stderr = $null
        if ($null -ne $line) { Write-BoundedLog (Join-Path $logs 'server.stderr.log') $line; $stderr = $child.StandardError.ReadLineAsync() }
    }
    if (-not $progress) { Start-Sleep -Milliseconds 20 }
}
$child.WaitForExit()
exit $child.ExitCode
