# DictatorShipping - Shortcut Fix Script
# This script creates a CORRECTED desktop shortcut
# Run this to fix the crashing issue caused by incorrect shortcut configuration

$AppDir = $PSScriptRoot
$VbsPath = Join-Path $AppDir "launch.vbs"
$IcoPath = Join-Path $AppDir "DictatorShipping.ico"
$Desktop = [Environment]::GetFolderPath("Desktop")
$ShortcutPath = Join-Path $Desktop "DictatorShipping.lnk"

Write-Host "Creating corrected desktop shortcut..." -ForegroundColor Cyan
Write-Host "App Directory: $AppDir"
Write-Host "VBS Script: $VbsPath"
Write-Host "Shortcut: $ShortcutPath"
Write-Host ""

# Remove old shortcut if it exists
if (Test-Path $ShortcutPath) {
    Write-Host "Removing old shortcut..." -ForegroundColor Yellow
    Remove-Item $ShortcutPath -Force
}

# Create shell object
$WScriptShell = New-Object -ComObject WScript.Shell

# Create the shortcut
$Shortcut = $WScriptShell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = $VbsPath
$Shortcut.WorkingDirectory = $AppDir
$Shortcut.Description = "DictatorShipping - Voice Dictation"
$Shortcut.WindowStyle = 1  # Normal window

# Set icon if it exists
if (Test-Path $IcoPath) {
    $Shortcut.IconLocation = $IcoPath
    Write-Host "Icon: $IcoPath" -ForegroundColor Green
} else {
    Write-Host "Icon not found (will use default)" -ForegroundColor Yellow
}

# Save the shortcut
$Shortcut.Save()

Write-Host ""
Write-Host "Shortcut created successfully!" -ForegroundColor Green
Write-Host ""
Write-Host "IMPORTANT: The old shortcut was pointing to 'launch.vbs main.py'" -ForegroundColor Red
Write-Host "           which caused system crashes." -ForegroundColor Red
Write-Host ""
Write-Host "The new shortcut CORRECTLY points to just 'launch.vbs'" -ForegroundColor Green
Write-Host ""
Write-Host "You can now safely use the desktop shortcut." -ForegroundColor Cyan
Write-Host ""
Write-Host "Press any key to exit..."
$null = $Host.UI.RawUI.ReadKey('NoEcho,IncludeKeyDown')
