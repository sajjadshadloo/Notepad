$shell = New-Object -ComObject WScript.Shell
$desktop = [System.Environment]::GetFolderPath('Desktop')
$project = Split-Path -Parent $MyInvocation.MyCommand.Path

# Launch pythonw.exe directly (no .bat) so no extra cmd window appears.
# Resolve the REAL interpreter path (sys.executable), not the WindowsApps
# alias stub, because the alias does not work reliably as a shortcut target.
$realPython = (python -c "import sys; print(sys.executable)").Trim()
$pythonw = Join-Path (Split-Path $realPython) 'pythonw.exe'
if (-not (Test-Path $pythonw)) { $pythonw = $realPython }

# Remove any stale/old shortcuts (including the previous launch.bat-based one).
foreach ($name in 'Notepad Plus.lnk', 'Notepad.lnk') {
    $old = Join-Path $desktop $name
    if (Test-Path $old) { Remove-Item $old -Force }
}

$lnk = $shell.CreateShortcut("$desktop\Notepad Plus.lnk")
$lnk.TargetPath = $pythonw
$lnk.Arguments = '"' + (Join-Path $project 'main.py') + '"'
$lnk.WorkingDirectory = $project
$lnk.IconLocation = Join-Path $project "assets\icon.ico"
$lnk.Description = "Notepad Plus"
$lnk.WindowStyle = 1   # normal window
$lnk.Save()
Write-Host "Shortcut 'Notepad Plus' created on Desktop (launches pythonw directly, single window)."
