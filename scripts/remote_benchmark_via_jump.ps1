param(
  [Parameter(Mandatory = $true)]
  [string]$JumpHost,
  [int]$JumpPort = 8065,
  [Parameter(Mandatory = $true)]
  [string]$JumpUser,
  [Parameter(Mandatory = $true)]
  [string]$TargetHost,
  [int]$TargetPort = 22,
  [Parameter(Mandatory = $true)]
  [string]$TargetUser,
  [string]$TargetPassword = "",
  [string]$PpkPath = "",
  [string]$RemoteProjectDir = "~/xeon-engine",
  [string]$RemoteConfigPath = "configs/xeon6.local.yaml"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if (-not $PSBoundParameters.ContainsKey("JumpPort")) {
  $jumpPortInput = Read-Host "Jump host port [default: 8065]"
  if ($jumpPortInput) {
    $JumpPort = [int]$jumpPortInput
  }
}

if (-not $PSBoundParameters.ContainsKey("PpkPath")) {
  $PpkPath = Read-Host "SSH key .ppk path (optional, press Enter to skip)"
}

function Invoke-RemoteCommand {
  param([string]$Cmd)
  $targetAuthCmd = if ($TargetPassword) {
    "sshpass -p '$TargetPassword' ssh -tt -o StrictHostKeyChecking=no -p $TargetPort $TargetUser@$TargetHost '$Cmd'"
  } else {
    "ssh -tt -o StrictHostKeyChecking=no -p $TargetPort $TargetUser@$TargetHost '$Cmd'"
  }

  if ($PpkPath -and (Test-Path $PpkPath)) {
    & plink -i $PpkPath -P $JumpPort "$JumpUser@$JumpHost" $targetAuthCmd
  } else {
    & ssh -p $JumpPort "$JumpUser@$JumpHost" `
      $targetAuthCmd
  }
}

$remoteCmd = @"
set -e
cd $RemoteProjectDir
python3 -m venv .venv || true
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt
pip install vllm intel-extension-for-pytorch
python scripts/launch_xeon_vllm.py --config $RemoteConfigPath > artifacts/launch.log 2>&1 &
sleep 25
python scripts/benchmark_xeon_vllm.py --config $RemoteConfigPath
python scripts/autotune_xeon_vllm.py --config $RemoteConfigPath
"@

Invoke-RemoteCommand -Cmd $remoteCmd
Write-Host "Remote benchmark and autotune commands dispatched."
