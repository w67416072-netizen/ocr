param(
    [Parameter(Mandatory = $true)]
    [ValidateScript({ Test-Path -LiteralPath $_ -PathType Leaf })]
    [string]$SplashMedia,

    [string]$LoadingImage,

    [string]$Icon
)

$ErrorActionPreference = 'Stop'
$ProjectDir = $PSScriptRoot
$MediaSource = (Resolve-Path -LiteralPath $SplashMedia).Path
$MediaExtension = [IO.Path]::GetExtension($MediaSource).ToLowerInvariant()
if ($MediaExtension -notin @('.png', '.mp4')) {
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
elseif ($MediaExtension -eq '.png') {
    # A PNG-only preview should remain visible until the preview is closed,
    # matching the image-only launcher behavior after packaging.
    $LoadingSource = $MediaSource
}

$CscCandidates = @(
    (Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'),
    (Join-Path $env:WINDIR 'Microsoft.NET\Framework\v4.0.30319\csc.exe')
)
$CscExe = $CscCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $CscExe) {
    throw '未找到 Windows .NET Framework C# 编译器。'
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
    throw '当前 Windows 未安装 WPF 运行组件。'
}

$PreviewDir = Join-Path $ProjectDir 'build\launcher-preview'
New-Item -ItemType Directory -Path $PreviewDir -Force | Out-Null
$PreviewExe = Join-Path $PreviewDir '启动器预览.exe'
$CscArgs = @(
    '/nologo', '/target:winexe', '/platform:anycpu',
    "/out:$PreviewExe",
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
    throw '启动器预览编译失败。'
}

$TargetName = if ($MediaExtension -eq '.mp4') { 'opening.mp4' } else { 'opening.png' }
$OtherTargetName = if ($TargetName -eq 'opening.mp4') { 'opening.png' } else { 'opening.mp4' }
Remove-Item -LiteralPath (Join-Path $PreviewDir $OtherTargetName) -Force -ErrorAction SilentlyContinue
Copy-Item -LiteralPath $MediaSource -Destination (Join-Path $PreviewDir $TargetName) -Force

$LoadingDestination = Join-Path $PreviewDir 'loading.png'
Remove-Item -LiteralPath $LoadingDestination -Force -ErrorAction SilentlyContinue
if ($LoadingSource) {
    Copy-Item -LiteralPath $LoadingSource -Destination $LoadingDestination -Force
}

Write-Host '启动器预览已打开；单击窗口或按 Esc 即可关闭。' -ForegroundColor Green
Start-Process -FilePath $PreviewExe -ArgumentList '--preview' -WorkingDirectory $PreviewDir
