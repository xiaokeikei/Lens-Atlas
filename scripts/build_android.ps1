param([switch]$IncludeInstrumentation)
$ErrorActionPreference = 'Stop'
$repositoryRoot = Split-Path $PSScriptRoot -Parent
$androidSource = Join-Path $repositoryRoot 'android'
$androidTools = Join-Path $repositoryRoot '.runtime/android-tools'
$androidStageRoot = Join-Path $env:PUBLIC 'LensAtlasAndroidBuild'
$androidWork = Join-Path $androidStageRoot ('project-' + [Guid]::NewGuid().ToString('N'))
$androidCache = Join-Path $androidStageRoot 'gradle-home'
$previousJavaHome = $env:JAVA_HOME
$previousAndroidHome = $env:ANDROID_HOME
$previousGradleHome = $env:GRADLE_USER_HOME
try {
    Push-Location (Join-Path $repositoryRoot 'frontend')
    try {
        & npm.cmd run build:mobile
        if ($LASTEXITCODE -ne 0) { throw '手机 React 界面构建失败' }
    } finally { Pop-Location }
    $androidAssets = Join-Path $androidSource 'app/src/main/assets'
    if (Test-Path -LiteralPath $androidAssets) {
        $resolvedAssets = (Resolve-Path -LiteralPath $androidAssets).Path
        $expectedAssets = [System.IO.Path]::GetFullPath((Join-Path $repositoryRoot 'android/app/src/main/assets'))
        if ($resolvedAssets -ne $expectedAssets -or ((Get-Item -LiteralPath $resolvedAssets).Attributes -band [System.IO.FileAttributes]::ReparsePoint)) { throw '界面资源目录超出预期工作区或是链接，停止清理' }
        Remove-Item -LiteralPath $resolvedAssets -Recurse -Force
    }
    New-Item -ItemType Directory -Force $androidAssets | Out-Null
    & robocopy (Join-Path $repositoryRoot 'frontend/dist-mobile') $androidAssets /E /NFL /NDL /NJH /NJS
    if ($LASTEXITCODE -ge 8) { throw '复制手机界面资源失败' }
    New-Item -ItemType Directory -Force $androidWork | Out-Null
    & robocopy $androidSource $androidWork /E /XD .gradle build /NFL /NDL /NJH /NJS
    if ($LASTEXITCODE -ge 8) { throw '复制 Android 源码失败' }
    $androidJdk = $env:JAVA_HOME
    if (!$androidJdk) {
        $androidJdk = (Get-ChildItem -LiteralPath $androidTools -Directory -Filter 'jdk-*' | Select-Object -First 1).FullName
    }
    $androidSdk = $env:ANDROID_HOME
    if (!$androidSdk) { $androidSdk = Join-Path $androidTools 'sdk' }
    if (!(Test-Path (Join-Path $androidJdk 'bin/java.exe'))) { throw '需要 JDK 17：设置 JAVA_HOME' }
    if (!(Test-Path (Join-Path $androidSdk 'platforms/android-35/android.jar'))) { throw '需要 Android SDK 35：设置 ANDROID_HOME' }
    New-Item -ItemType Junction -Path (Join-Path $androidWork 'jdk') -Target $androidJdk | Out-Null
    New-Item -ItemType Junction -Path (Join-Path $androidWork 'sdk') -Target $androidSdk | Out-Null
    $env:JAVA_HOME = Join-Path $androidWork 'jdk'
    $env:ANDROID_HOME = Join-Path $androidWork 'sdk'
    $env:GRADLE_USER_HOME = $androidCache
    $androidGradle = Join-Path $androidTools 'gradle-8.11.1/bin/gradle.bat'
    if (!(Test-Path -LiteralPath $androidGradle)) { $androidGradle = Join-Path $androidWork 'gradlew.bat' }
    $androidTasks = @('testDebugUnitTest', 'lintDebug', 'assembleDebug')
    if ($IncludeInstrumentation) { $androidTasks += 'assembleDebugAndroidTest' }
    & $androidGradle -p $androidWork @androidTasks --console plain
    if ($LASTEXITCODE -ne 0) { throw 'Android 构建或验证失败' }
    $androidOutput = Join-Path $repositoryRoot 'dist/android'
    New-Item -ItemType Directory -Force $androidOutput | Out-Null
    Copy-Item -LiteralPath (Join-Path $androidWork 'app/build/outputs/apk/debug/app-debug.apk') -Destination (Join-Path $androidOutput 'LensAtlas-0.1.3-android-debug.apk')
    Copy-Item -LiteralPath (Join-Path $androidWork 'app/build/reports/lint-results-debug.txt') -Destination $androidOutput
    if ($IncludeInstrumentation) {
        Copy-Item -LiteralPath (Join-Path $androidWork 'app/build/outputs/apk/androidTest/debug/app-debug-androidTest.apk') -Destination $androidOutput
    }
    (Get-FileHash -LiteralPath (Join-Path $androidOutput 'LensAtlas-0.1.3-android-debug.apk') -Algorithm SHA256).Hash | Set-Content (Join-Path $androidOutput 'SHA256.txt')
    Write-Host "APK：$androidOutput"
    Write-Host "构建记录与测试报告：$androidWork/app/build/reports"
} finally {
    $env:JAVA_HOME = $previousJavaHome
    $env:ANDROID_HOME = $previousAndroidHome
    $env:GRADLE_USER_HOME = $previousGradleHome
}
