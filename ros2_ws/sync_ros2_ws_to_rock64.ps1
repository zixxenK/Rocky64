param(
    [string]$HostName = "rock64",
    [string]$UserName = "",
    [string]$TargetDir = "~/Rock64 Robot/ros2_ws",
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

function ConvertTo-RemotePathToken {
    # Produce a remote-shell-safe path token where a leading ~ still expands
    # but spaces and other characters are quoted. e.g.
    #   ~/Rock64 Robot/ros2_ws -> ~/'Rock64 Robot/ros2_ws'
    #   /opt/foo bar           -> '/opt/foo bar'
    param(
        [Parameter(Mandatory=$true)][string]$Path
    )

    $p = $Path -replace '\\', '/'
    if ($p -eq '~') {
        return '~'
    } elseif ($p -like '~/*') {
        return "~/'" + $p.Substring(2) + "'"
    } elseif ($p -like '~*') {
        $slash = $p.IndexOf('/')
        if ($slash -ge 0) {
            return $p.Substring(0, $slash) + "/'" + $p.Substring($slash + 1) + "'"
        }
        return $p
    } else {
        return "'" + $p + "'"
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
$remoteTarget = ConvertTo-RemotePathToken -Path $TargetDir
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
    $cmd = "mkdir -p $remoteTarget"
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
            Invoke-External -FilePath "scp" -Arguments @("-P", "$Port", "-r", "$localPath", "$remote`:$remoteTarget/")
        }
    }
}

$chmodList = @(
    "fix_bashrc_ros_overlay.sh",
    "robot_start.sh"
)

Invoke-Logged -Label "Set executable bits for shell scripts" -Action {
    # cd into the synced directory (tilde must expand, so it is not fully
    # single-quoted) and chmod only the scripts that actually arrived.
    $scripts = ($chmodList -join " ")
    $cmd = "cd $remoteTarget && for f in $scripts; do if [ -f ""`$f"" ]; then chmod +x ""`$f""; fi; done"
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
Write-Host "  ./robot_start.sh --role rock64"
