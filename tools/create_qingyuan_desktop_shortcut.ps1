$Target = "C:\MyAgent\Qingyuan.exe"
if (-not (Test-Path $Target)) {
    Write-Host "Qingyuan.exe not found: $Target" -ForegroundColor Red
    exit 1
}

$Desktop = [Environment]::GetFolderPath("Desktop")
$ShortcutPath = Join-Path $Desktop "清渊.lnk"
$Shell = New-Object -ComObject WScript.Shell
$Shortcut = $Shell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = $Target
$Shortcut.WorkingDirectory = "C:\MyAgent"
$Icon = "C:\MyAgent\assets\qingyuan.ico"
if (Test-Path $Icon) {
    $Shortcut.IconLocation = $Icon
}
$Shortcut.Save()
Write-Host "Desktop shortcut created: $ShortcutPath"
