"""Bounded external logs and parseable native startup scripts."""
from pathlib import Path
import subprocess
import os
import pytest


@pytest.mark.skipif(os.name!='nt',reason='Windows PowerShell supervisor')
def test_bounded_log_rotation_and_powershell_syntax(tmp_path):
    root=Path(__file__).resolve().parents[1]
    supervisor=root/'scripts/supervise_ollama.ps1'
    script=tmp_path/'check.ps1'
    # Paths enter as argument values, never as interpolated PowerShell source.
    script.write_text('''param([string]$Supervisor,[string]$Directory,[string]$Startup)
$ErrorActionPreference='Stop'
. $Supervisor -LibraryOnly
$log=Join-Path $Directory 'synthetic.log'
1..200 | ForEach-Object { Write-BoundedLog $log ('test record '+$_) 128 3 }
$files=@(Get-ChildItem -LiteralPath $Directory -Filter 'synthetic.log*')
if ($files.Count -ne 4 -or @($files | Where-Object Length -gt 128).Count) { throw 'Rotation bounds failed' }
if (-not ((Get-Content -LiteralPath $log -Tail 1) -match '200')) { throw 'Latest record lost' }
foreach($path in @($Supervisor,$Startup)) {
    $tokens=$null; $parseErrors=$null
    [System.Management.Automation.Language.Parser]::ParseFile($path,[ref]$tokens,[ref]$parseErrors) | Out-Null
    if ($parseErrors.Count) { throw 'PowerShell syntax error' }
}
''',encoding='utf-8')
    powershell=Path(os.environ['SystemRoot'])/'System32/WindowsPowerShell/v1.0/powershell.exe'
    result=subprocess.run([str(powershell),'-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',str(script),
        '-Supervisor',str(supervisor),'-Directory',str(tmp_path),'-Startup',str(root/'scripts/start_local_rag.ps1')],
        capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stderr
