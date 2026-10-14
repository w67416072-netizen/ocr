param(
    [Parameter(Mandatory = $true)]
    [ValidateScript({ Test-Path -LiteralPath $_ -PathType Leaf })]
    [string]$SplashImage,

    # MP4 解码期间显示的可选占位图片
    [string]$LoadingImage,

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

# 检查启动图片或视频
$SplashSource = (Resolve-Path -LiteralPath $SplashImage).Path
$SplashExtension = [IO.Path]::GetExtension($SplashSource).ToLowerInvariant()

if ($SplashExtension -notin @('.png', '.mp4')) {
    throw '启动素材必须是 PNG 图片或 MP4 视频。'
}

$LoadingSource = $null
if ($LoadingImage) {
    if (-not (Test-Path -LiteralPath $LoadingImage -PathType Leaf)) {
        throw "未找到载入占位图片：$LoadingImage"
    }
    $LoadingSource = (Resolve-Path -LiteralPath $LoadingImage).Path
    if ([IO.Path]::GetExtension($LoadingSource).ToLowerInvariant() -notin @('.png', '.jpg', '.jpeg', '.bmp')) {
        throw '载入占位图片必须是 PNG、JPG 或 BMP 文件。'
    }
}
elseif ($SplashExtension -eq '.png') {
    # Image-only mode: a PNG supplied as the splash is also the default
    # loading picture, so it remains visible until the main program is ready.
    $LoadingSource = $SplashSource
}

# ============================================================
# 1. 按照 spec 文件打包主程序
# ============================================================

& $PythonExe -m PyInstaller --noconfirm --clean .\ocr_qt.spec

if ($LASTEXITCODE -ne 0) {
    throw 'ocr_qt.spec 打包失败。'
}

# ============================================================
# 2. 编译 Windows 原生视频启动器并应用图标
# ============================================================

$CscCandidates = @(
    (Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'),
    (Join-Path $env:WINDIR 'Microsoft.NET\Framework\v4.0.30319\csc.exe')
)
$CscExe = $CscCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $CscExe) {
    throw '未找到 Windows .NET Framework C# 编译器，无法编译原生视频启动器。'
}
$DotNetFrameworkDir = Split-Path -Parent $CscExe
$WpfDir = Join-Path $DotNetFrameworkDir 'WPF'
$WpfAssemblies = @(
    (Join-Path $WpfDir 'WindowsBase.dll'),
    (Join-Path $WpfDir 'PresentationCore.dll'),
    (Join-Path $WpfDir 'PresentationFramework.dll'),
    (Join-Path $DotNetFrameworkDir 'System.Xaml.dll')
)
if ($WpfAssemblies | Where-Object { -not (Test-Path -LiteralPath $_) }) {
    throw '当前 Windows 未安装 WPF 运行组件，无法编译原生视频启动器。'
}

$Target = Join-Path $ProjectDir 'dist\ocr_qt'
$LauncherExe = Join-Path $Target '启动软件.exe'
$CscArgs = @(
    '/nologo', '/target:winexe', '/platform:anycpu',
    "/out:$LauncherExe",
    "/r:$($WpfAssemblies[0])", "/r:$($WpfAssemblies[1])", "/r:$($WpfAssemblies[2])", "/r:$($WpfAssemblies[3])",
    (Join-Path $ProjectDir 'startup_launcher.cs')
)

if ($Icon) {
    $IconPath = (Resolve-Path -LiteralPath $Icon).Path
    if ([IO.Path]::GetExtension($IconPath).ToLowerInvariant() -ne '.ico') {
        throw '启动图标必须是 ICO 文件。'
    }
    $CscArgs += "/win32icon:$IconPath"
}

& $CscExe @CscArgs
if ($LASTEXITCODE -ne 0) {
    throw '原生视频启动器编译失败。'
}

# ============================================================
# 3. 定义输出目录
# ============================================================

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
# 6. 复制启动图片或视频
# ============================================================

 $SplashDestination = if ($SplashExtension -eq '.mp4') { 'opening.mp4' } else { 'opening.png' }
 $OtherSplashDestination = if ($SplashDestination -eq 'opening.mp4') { 'opening.png' } else { 'opening.mp4' }
 Remove-Item -LiteralPath (Join-Path $Target $OtherSplashDestination) -Force -ErrorAction SilentlyContinue
Copy-Item `
    -LiteralPath $SplashSource `
    -Destination (Join-Path $Target $SplashDestination) `
    -Force

# loading.png is displayed immediately while Windows loads an MP4 decoder.
# Remove an older image when none was chosen for this build.
$LoadingDestination = Join-Path $Target 'loading.png'
Remove-Item -LiteralPath $LoadingDestination -Force -ErrorAction SilentlyContinue
if ($LoadingSource) {
    Copy-Item -LiteralPath $LoadingSource -Destination $LoadingDestination -Force
}

# ============================================================
# 7. 完成
# ============================================================

Write-Host ''
Write-Host '========================================' -ForegroundColor Cyan
Write-Host ' Build completed successfully!' -ForegroundColor Green
Write-Host '========================================' -ForegroundColor Cyan
Write-Host ''

Write-Host "Output: $Target" -ForegroundColor Green
Write-Host "Launch: $(Join-Path $Target '启动软件.exe')" -ForegroundColor Green
Write-Host "Splash: $(Join-Path $Target $SplashDestination)" -ForegroundColor Yellow
if ($LoadingSource) {
    Write-Host "Loading image: $LoadingDestination" -ForegroundColor Yellow
}
Write-Host ''
Write-Host 'Replace opening.mp4 or opening.png to change the opening media.' -ForegroundColor Yellow
```
