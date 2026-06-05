param(
    [string]$HostName = "rock64",
    [string]$UserName = "",
    [string]$TargetDir = "~/rock64_ros2_ws",
    [int]$Port = 22,
    [switch]$WhatIf
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Invoke-Logged {
    param(
        [Parameter(Mandatory=$true)][string]$Label,
        [Parameter(Mandatory=$true)][scriptblock]$Action
    )
    Write-Host "==> $Label"
    & $Action
}

function Invoke-External {
    param(
        [Parameter(Mandatory=$true)][string]$FilePath,
        [Parameter(Mandatory=$true)][string[]]$Arguments,
        [string]$FailureHint = ""
    )

    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        $cmdText = "$FilePath " + ($Arguments -join " ")
        $message = "Command failed (exit $LASTEXITCODE): $cmdText"
        if ($FailureHint) {
            $message += "`n$FailureHint"
        }
        throw $message
    }
}

function Resolve-SshUserName {
    param(
        [Parameter(Mandatory=$true)][string]$HostName,
        [string]$FallbackUserName = "rock64"
    )

    try {
        $sshConfig = & ssh -G $HostName 2>$null
        foreach ($line in $sshConfig) {
            if ($line -match '^user\s+(\S+)$') {
                return $Matches[1]
            }
        }
    } catch {
        # Fall back to the explicit default below.
    }

    return $FallbackUserName
}

$workspace = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not (Test-Path -LiteralPath $workspace)) {
    throw "Workspace path not found: $workspace"
}

if ([string]::IsNullOrWhiteSpace($UserName)) {
    $UserName = Resolve-SshUserName -HostName $HostName
}

$requiredCommands = @("ssh", "scp")
foreach ($cmd in $requiredCommands) {
    if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) {
        throw "Required command '$cmd' not found in PATH. Install OpenSSH client first."
    }
}

$itemsToSync = @(
    "README.md",
    "requirements.txt",
    "fix_bashrc_ros_overlay.sh",
    "robot_start.sh",
    "host_control",
    "src"
)

$remote = "$UserName@$HostName"

# Prepare space-safe variants of the remote target directory.
# scp: backslash-escape spaces so the remote shell treats them as literal.
$scpTargetDir = $TargetDir -replace ' ', '\ '
# ssh commands: replace leading ~ with $HOME so tilde expands inside
# double-quotes, and wrap in double-quotes to protect spaces.
$sshTargetDir = $TargetDir -replace '^~', '$HOME'

Write-Host "Sync source : $workspace"
Write-Host "Sync target : $remote`:$TargetDir (port $Port)"

Invoke-Logged -Label "Validate SSH connectivity" -Action {
    if ($WhatIf) {
        Write-Host "[WhatIf] ssh -p $Port -o BatchMode=yes -o ConnectTimeout=5 $remote echo ok"
    } else {
        Invoke-External -FilePath "ssh" -Arguments @("-p", "$Port", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5", $remote, "echo ok") -FailureHint @"
Unable to connect to Rock64 over SSH.
Checks:
  1) Rock64 IP is correct (hostname '$HostName' may not resolve)
  2) SSH service is running on Rock64 (sudo systemctl status ssh)
  3) Port $Port is reachable from this PC (firewall / network)
Try rerun with explicit IP and port:
  .\sync_ros2_ws_to_rock64.ps1 -HostName <rock64-ip> -Port 22
"@
    }
}

Invoke-Logged -Label "Create target directory" -Action {
    $cmd = "mkdir -p `"$sshTargetDir`""
    if ($WhatIf) {
        Write-Host "[WhatIf] ssh -p $Port $remote $cmd"
    } else {
        Invoke-External -FilePath "ssh" -Arguments @("-p", "$Port", $remote, $cmd)
    }
}

foreach ($item in $itemsToSync) {
    $localPath = Join-Path $workspace $item
    if (-not (Test-Path -LiteralPath $localPath)) {
        Write-Host "WARN: Skipping missing path: $item"
        continue
    }

    Invoke-Logged -Label "Sync $item" -Action {
        if ($WhatIf) {
            Write-Host "[WhatIf] scp -P $Port -r `"$localPath`" `"$remote`:$TargetDir/`""
        } else {
            Invoke-External -FilePath "scp" -Arguments @("-P", "$Port", "-r", "$localPath", "${remote}:${scpTargetDir}/")
        }
    }
}

$chmodList = @(
    "fix_bashrc_ros_overlay.sh",
    "robot_start.sh"
)
$chmodArgs = ($chmodList | ForEach-Object { "`"$sshTargetDir/$_`"" }) -join " "

Invoke-Logged -Label "Set executable bits for shell scripts" -Action {
    $cmd = "chmod +x $chmodArgs"
    if ($WhatIf) {
        Write-Host "[WhatIf] ssh -p $Port $remote $cmd"
    } else {
        Invoke-External -FilePath "ssh" -Arguments @("-p", "$Port", $remote, $cmd)
    }
}

Write-Host ""
Write-Host "Sync complete."
Write-Host "Next on Rock64:"
Write-Host "  cd $TargetDir"
Write-Host "  ./robot_start.sh"
