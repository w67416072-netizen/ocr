param(
    [Parameter(Mandatory = $true)]
    [ValidateScript({ Test-Path -LiteralPath $_ -PathType Leaf })]
    [string]$SplashImage,

    # 接收图标文件的可选参数
    [string]$Icon
)

$ErrorActionPreference = 'Stop'

# 当前脚本所在目录
$ProjectDir = $PSScriptRoot
Set-Location $ProjectDir

# Always build from the project virtual environment. This prevents an active
# shell environment from accidentally omitting optional runtime packages.
$PythonExe = Join-Path $ProjectDir 'ocr_env\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $PythonExe)) {
    $PythonExe = 'python'
}

& $PythonExe -c "import pandas, openpyxl, opencc"
if ($LASTEXITCODE -ne 0) {
    throw '缺少打包依赖。请运行：.\ocr_env\Scripts\python.exe -m pip install pandas openpyxl opencc-python-reimplemented'
}

# 检查启动图片
$SplashSource = (Resolve-Path -LiteralPath $SplashImage).Path

if ([IO.Path]::GetExtension($SplashSource).ToLowerInvariant() -ne '.png') {
    throw '启动图片必须是 PNG 文件。'
}

# ============================================================
# 1. 按照 spec 文件打包主程序
# ============================================================

& $PythonExe -m PyInstaller --noconfirm --clean .\ocr_qt.spec

if ($LASTEXITCODE -ne 0) {
    throw 'ocr_qt.spec 打包失败。'
}

# ============================================================
# 2. 打包启动器并应用图标
# ============================================================

if ($Icon) {

    $IconPath = (Resolve-Path -LiteralPath $Icon).Path

    if ([IO.Path]::GetExtension($IconPath).ToLowerInvariant() -ne '.ico') {
        throw '启动图标必须是 ICO 文件。'
    }

    & $PythonExe -m PyInstaller `
        --noconfirm `
        --clean `
        --onedir `
        --windowed `
        --icon="$IconPath" `
        --name ocr_launcher `
        --contents-directory launcher_runtime `
        .\startup_launcher.py

} else {

    & $PythonExe -m PyInstaller `
        --noconfirm `
        --clean `
        --onedir `
        --windowed `
        --name ocr_launcher `
        --contents-directory launcher_runtime `
        .\startup_launcher.py
}

if ($LASTEXITCODE -ne 0) {
    throw 'ocr_launcher 打包失败。'
}

# ============================================================
# 3. 定义输出目录
# ============================================================

$Target = Join-Path $ProjectDir 'dist\ocr_qt'
$LauncherOutput = Join-Path $ProjectDir 'dist\ocr_launcher'

# ============================================================
# 4. 复制配置文件
# ============================================================

foreach ($Name in @('ocr_data.json', '.env')) {

    $Source = Join-Path $ProjectDir $Name

    if (Test-Path -LiteralPath $Source) {

        Copy-Item `
            -LiteralPath $Source `
            -Destination (Join-Path $Target $Name) `
            -Force
    }
}

# ============================================================
# 5. 复制历史导出文件
# ============================================================

$ExportHistory = Join-Path $ProjectDir 'export_history_files'

if (Test-Path -LiteralPath $ExportHistory) {

    Copy-Item `
        -LiteralPath $ExportHistory `
        -Destination $Target `
        -Recurse `
        -Force
}

# ============================================================
# 6. 复制启动器并重命名
# ============================================================

Copy-Item `
    -LiteralPath (Join-Path $LauncherOutput 'ocr_launcher.exe') `
    -Destination (Join-Path $Target '启动软件.exe') `
    -Force

# ============================================================
# 7. 复制 launcher_runtime
# ============================================================

Copy-Item `
    -LiteralPath (Join-Path $LauncherOutput 'launcher_runtime') `
    -Destination $Target `
    -Recurse `
    -Force

# ============================================================
# 8. 复制启动图片
# ============================================================

Copy-Item `
    -LiteralPath $SplashSource `
    -Destination (Join-Path $Target 'opening.png') `
    -Force

# ============================================================
# 9. 完成
# ============================================================

Write-Host ''
Write-Host '========================================' -ForegroundColor Cyan
Write-Host ' Build completed successfully!' -ForegroundColor Green
Write-Host '========================================' -ForegroundColor Cyan
Write-Host ''

Write-Host "Output: $Target" -ForegroundColor Green
Write-Host "Launch: $(Join-Path $Target '启动软件.exe')" -ForegroundColor Green
Write-Host "Splash: $(Join-Path $Target 'opening.png')" -ForegroundColor Yellow
Write-Host ''
Write-Host 'Replace opening.png with another PNG to change the opening image.' -ForegroundColor Yellow
```
