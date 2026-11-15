"""Bounded external logs and parseable native startup scripts."""
from pathlib import Path
import subprocess
import os
import pytest


def test_startup_helper_log_is_bounded_while_draining(tmp_path):
    import sys
    from app.desktop.service_logs import capture_output
    process=subprocess.Popen([sys.executable,'-c',"import sys;sys.stdout.write('record '+('x'*100)+'\\n'*1);sys.stdout.write('x'*100000);sys.stdout.write('LAST RECORD')"],
        stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    path=tmp_path/'startup.log'
    reader=capture_output(process,path,max_bytes=8192,backups=3)
    assert process.wait(timeout=15)==0
    reader.join(timeout=5)
    assert not reader.is_alive()
    assert 'LAST RECORD' in path.read_text(encoding='utf-8')
    files=list(tmp_path.glob('startup.log*'))
    assert len(files)==4 and all(file.stat().st_size<=8192 for file in files)


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


@pytest.mark.skipif(os.name!='nt',reason='Windows PowerShell supervisor')
def test_supervisor_drains_both_streams_and_exits_with_child(tmp_path):
    root=Path(__file__).resolve().parents[1]
    (tmp_path/'.tools/ollama').mkdir(parents=True)
    (tmp_path/'.cache/ollama').mkdir(parents=True)
    script=tmp_path/'exercise.ps1'
    script.write_text('''param([string]$Supervisor,[string]$Directory)
$ErrorActionPreference='Stop'
$exe=Join-Path $Directory '.tools/ollama/ollama.exe'
$source='public class SyntheticLogger { public static void Main() { for(int i=0;i<1000;i++){System.Console.WriteLine("out-"+i);System.Console.Error.WriteLine("err-"+i);} } }'
Add-Type -TypeDefinition $source -OutputAssembly $exe -OutputType ConsoleApplication
& $Supervisor -ProjectRoot $Directory
if ($LASTEXITCODE -ne 0) { throw 'Child supervisor failed' }
$logs=Join-Path $Directory '.cache/ollama'
if ((Get-Content -LiteralPath (Join-Path $logs 'server.stdout.log') -Tail 1) -ne 'out-999') { throw 'stdout incomplete' }
if ((Get-Content -LiteralPath (Join-Path $logs 'server.stderr.log') -Tail 1) -ne 'err-999') { throw 'stderr incomplete' }
''',encoding='utf-8')
    powershell=Path(os.environ['SystemRoot'])/'System32/WindowsPowerShell/v1.0/powershell.exe'
    result=subprocess.run([str(powershell),'-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',str(script),
        '-Supervisor',str(root/'scripts/supervise_ollama.ps1'),'-Directory',str(tmp_path)],
        capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stderr
