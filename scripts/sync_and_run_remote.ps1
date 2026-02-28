param(
    [string]$JumpHost = "134.191.217.242",
    [int]$JumpPort = 8065,
    [string]$JumpUser = "prabhash",
    [string]$TargetHost = "10.0.68.162",
    [string]$TargetUser = "ENTER_XEON_USER",      # e.g., sdp
    [string]$TargetPass = 'ENTER_XEON_PASSWORD',  # e.g., CloU$r#2!
    [string]$PpkPath = "ENTER_PATH_TO_PPK",      # e.g., C:\Users\...\prabhash.ppk"
    [string]$RemoteDir = "/home/ENTER_XEON_USER/xeon-engine"
)

$ErrorActionPreference = "Stop"

# 1. Create a clean archive of the project
$tempZip = Join-Path $env:TEMP "xeon_engine_sync.zip"
if (Test-Path $tempZip) { Remove-Item $tempZip }

Write-Host "[sync] Archiving local project..." -ForegroundColor Cyan
# Filter out venv, git, and large artifacts
$exclude = @(".venv", ".git", "artifacts", "__pycache__", ".vscode", ".gemini")
$files = Get-ChildItem -Path . -Recurse | Where-Object { 
    $path = $_.FullName
    $match = $false
    foreach ($e in $exclude) {
        if ($path -like "*\$e*" -or $path -like "*\$e") { $match = $true; break }
    }
    -not $match
}

# Note: Using a slightly different approach for zip to ensure relative paths
$sourceDir = Get-Location
Add-Type -AssemblyName System.IO.Compression.FileSystem
[System.IO.Compression.ZipFile]::CreateFromDirectory($sourceDir, $tempZip, [System.IO.Compression.CompressionLevel]::Optimal, $false)

# 2. Establish SSH Tunnel via Jump Host
Write-Host "[sync] Establishing tunnel to Xeon 6 ($TargetHost) via jump host ($JumpHost)..." -ForegroundColor Cyan
$tunnelProc = Start-Process plink -ArgumentList "-i", "`"$PpkPath`"", "-P", "$JumpPort", "-L", "2223:$($TargetHost):22", "$JumpUser@$JumpHost", "-N", "-batch" -PassThru -NoNewWindow
Start-Sleep -Seconds 5 # Wait for tunnel to stabilize

try {
    # 3. Create Remote Directory and Upload via Tunnel
    Write-Host "[sync] Ensuring remote directory exists on target..." -ForegroundColor Cyan
    & plink -P 2223 -hostkey "SHA256:u2bTpWBuB50uIFgBCR5j8Laldc6znd0Gy2RnuIvC83I" -pw $TargetPass -batch sdp@127.0.0.1 "mkdir -p $RemoteDir"
    
    Write-Host "[sync] Uploading to target server ($TargetHost) via tunnel..." -ForegroundColor Cyan
    $destPath = "$($RemoteDir)/xeon_engine.zip"
    & pscp -P 2223 -hostkey "SHA256:u2bTpWBuB50uIFgBCR5j8Laldc6znd0Gy2RnuIvC83I" -pw $TargetPass -batch $tempZip "sdp@127.0.0.1:$destPath"
    if ($LASTEXITCODE -ne 0) { throw "Upload failed with exit code $LASTEXITCODE" }

    # 4. Setup and Run on Target
    Write-Host "[sync] Setting up and launching benchmark on Xeon 6..." -ForegroundColor Green
    $remoteCmd = "cd /home/sdp/xeon-engine && python3 -c 'import zipfile; z = zipfile.ZipFile(\`"xeon_engine.zip\`"); z.extractall()' && bash scripts/remote_ops.sh"
    & plink -P 2223 -hostkey "SHA256:u2bTpWBuB50uIFgBCR5j8Laldc6znd0Gy2RnuIvC83I" -pw $TargetPass -batch sdp@127.0.0.1 $remoteCmd
    if ($LASTEXITCODE -ne 0) { throw "Remote execution failed with exit code $LASTEXITCODE" }

    # 5. Fetch Results to Local
    Write-Host "[sync] Fetching results to local machine..." -ForegroundColor Cyan
    $localResultsDir = Join-Path $PWD "artifacts"
    if (-not (Test-Path $localResultsDir)) { New-Item -ItemType Directory -Path $localResultsDir }
    $localZip = Join-Path $localResultsDir "benchmark_results.zip"
    if (Test-Path $localZip) { Remove-Item $localZip }

    $remoteZipPath = "$($RemoteDir)/benchmark_results.zip"
    & pscp -P 2223 -hostkey "SHA256:u2bTpWBuB50uIFgBCR5j8Laldc6znd0Gy2RnuIvC83I" -pw $TargetPass -batch "sdp@127.0.0.1:$remoteZipPath" $localZip
    if ($LASTEXITCODE -ne 0) { throw "Download failed with exit code $LASTEXITCODE" }

    # 6. Unpack and Open Dashboard
    Write-Host "[sync] Extracting results..." -ForegroundColor Cyan
    Expand-Archive -Path $localZip -DestinationPath $localResultsDir -Force

    $latestDashboard = Get-ChildItem -Path $localResultsDir -Filter "dashboard.html" -Recurse | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if ($latestDashboard) {
        Write-Host "[sync] Success! Opening dashboard: $($latestDashboard.FullName)" -ForegroundColor Green
        Start-Process $latestDashboard.FullName
    }
} catch {
    Write-Error "[sync] FAILED: $_"
} finally {
    # Cleanup tunnel
    Write-Host "[sync] Closing tunnel..." -ForegroundColor DarkGray
    if ($tunnelProc) {
        Stop-Process -Id $tunnelProc.Id -Force -ErrorAction SilentlyContinue
    }
}

Write-Host "[sync] Full cycle completed." -ForegroundColor Green
