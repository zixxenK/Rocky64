param(
    [string]$HostName = "rock64",
    [string]$UserName = "",
    [string]$TargetDir = "~/rock64_ros2_ws",
    [int]$Port = 22,
    [switch]$WhatIf,
    [switch]$SetupKey,
    [switch]$NoKeySetup,
    [string]$IdentityFile = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
function Write-Step {
    param([Parameter(Mandatory)][string]$Label)
    Write-Host "==> $Label"
}

function Invoke-External {
    param(
        [Parameter(Mandatory)][string]$FilePath,
        [Parameter(Mandatory)][string[]]$Arguments,
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
        [Parameter(Mandatory)][string]$HostName,
        [string]$FallbackUserName = "rock64"
    )

    try {
        $sshConfig = & ssh -G $HostName 2>$null
        foreach ($line in $sshConfig) {
            if ($line -match '^user\s+(\S+)$') {
                return $Matches[1]
            }
        }
    } catch { }

    return $FallbackUserName
}

# ---------------------------------------------------------------------------
# Workspace & user resolution
# ---------------------------------------------------------------------------
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

$hasRsync = [bool](Get-Command "rsync" -ErrorAction SilentlyContinue)

# ---------------------------------------------------------------------------
# Items to sync and shell scripts that need +x
# ---------------------------------------------------------------------------
$itemsToSync = @(
    "README.md",
    "requirements.txt",
    "fix_bashrc_ros_overlay.sh",
    "robot_start.sh",
    "host_control",
    "src"
)

# Directories that need to be cleaned on the remote before scp to avoid
# the scp -r nesting bug (scp -r dir target/dir -> target/dir/dir).
$directoryItems = @("host_control", "src")

$shellScripts = @(
    "fix_bashrc_ros_overlay.sh",
    "robot_start.sh"
)

$remote = "$UserName@$HostName"

# Prepare path variants for the remote target directory.
# ssh: replace ~ with $HOME so tilde expands inside double-quotes.
$sshTargetDir = $TargetDir -replace '^~', '$HOME'
# scp: backslash-escape spaces so the remote shell treats them as literal.
$scpTargetDir = $TargetDir -replace ' ', '\ '

# ---------------------------------------------------------------------------
# SSH argument builder - centralises port, key, and host-key options
# ---------------------------------------------------------------------------
function Get-SshArgs {
    param([switch]$BatchMode)

    $args_ = @("-p", "$Port", "-o", "StrictHostKeyChecking=accept-new")
    if ($BatchMode) { $args_ += @("-o", "BatchMode=yes") }
    if ($IdentityFile -and (Test-Path -LiteralPath $IdentityFile)) {
        $args_ += @("-i", "$IdentityFile")
    }
    $args_ += $remote
    return $args_
}

Write-Host "Sync source : $workspace"
Write-Host "Sync target : $remote`:$TargetDir (port $Port)"
if ($hasRsync) { Write-Host "Transfer    : rsync (preferred)" }
else           { Write-Host "Transfer    : scp (rsync not found)" }
Write-Host ""

# ---------------------------------------------------------------------------
# STEP 1 - Connectivity & key-based auth
# ---------------------------------------------------------------------------
$keyAuthWorks = $false

Write-Step "Validate SSH connectivity"
if ($WhatIf) {
    Write-Host "[WhatIf] ssh $(Get-SshArgs -BatchMode) echo ok"
} else {
    # Try key/agent auth first (no password prompt).
    try {
        $testArgs = (Get-SshArgs -BatchMode) + @("-o", "ConnectTimeout=5", "echo ok")
        Invoke-External -FilePath "ssh" -Arguments $testArgs
        $keyAuthWorks = $true
        Write-Host "  Key-based auth: OK"
    } catch {
        Write-Host "  Key-based auth: not available (password auth will be used)"

        # Verify the host is actually reachable (allow password prompt).
        try {
            $testArgs = (Get-SshArgs) + @("-o", "ConnectTimeout=10", "echo ok")
            Invoke-External -FilePath "ssh" -Arguments $testArgs -FailureHint @"
Unable to connect to Rock64 over SSH.
Checks:
  1) Rock64 IP is correct (hostname '$HostName' may not resolve)
  2) SSH service is running on Rock64 (sudo systemctl status ssh)
  3) Port $Port is reachable from this PC (firewall / network)
Try rerun with explicit IP and port:
  .\sync_ros2_ws_to_rock64.ps1 -HostName <rock64-ip> -Port 22
"@
        } catch {
            throw $_
        }
    }
}

# ---------------------------------------------------------------------------
# STEP 2 - SSH key bootstrap (optional)
# ---------------------------------------------------------------------------
if (-not $keyAuthWorks -and -not $NoKeySetup) {
    if ($SetupKey -or (-not $WhatIf)) {
        Write-Step "Set up SSH key-based auth (one-time)"

        if ($WhatIf) {
            Write-Host "[WhatIf] Would generate SSH key and install on $remote"
        } else {
            # Find or generate a key pair.
            $keyPath = if ($IdentityFile -and (Test-Path -LiteralPath $IdentityFile)) {
                $IdentityFile
            } else {
                $defaultKey = Join-Path $env:USERPROFILE ".ssh" "id_ed25519"
                if (-not $env:USERPROFILE) {
                    $defaultKey = Join-Path $HOME ".ssh" "id_ed25519"
                }
                if (-not (Test-Path -LiteralPath $defaultKey)) {
                    Write-Host "  No SSH key found - generating ed25519 key pair..."
                    $sshDir = Split-Path $defaultKey
                    if (-not (Test-Path -LiteralPath $sshDir)) {
                        New-Item -ItemType Directory -Path $sshDir -Force | Out-Null
                    }
                    & ssh-keygen -t ed25519 -N '""' -f $defaultKey -q
                    if ($LASTEXITCODE -ne 0) {
                        Write-Host "  WARNING: ssh-keygen failed - continuing with password auth."
                        $defaultKey = ""
                    } else {
                        Write-Host "  Key generated: $defaultKey"
                    }
                }
                $defaultKey
            }

            if ($keyPath -and (Test-Path -LiteralPath "$keyPath.pub")) {
                Write-Host "  Installing public key on $remote (you may be prompted for a password)..."
                $pubKey = Get-Content "$keyPath.pub" -Raw
                $pubKey = $pubKey.Trim()
                $installCmd = "umask 077; mkdir -p ~/.ssh; echo '$pubKey' >> ~/.ssh/authorized_keys; sort -u ~/.ssh/authorized_keys -o ~/.ssh/authorized_keys"
                try {
                    $installArgs = (Get-SshArgs) + @($installCmd)
                    Invoke-External -FilePath "ssh" -Arguments $installArgs
                    Write-Host "  Key installed. Future syncs will not need a password."
                    $keyAuthWorks = $true
                    # Update IdentityFile so subsequent steps use it.
                    if (-not $IdentityFile) { $IdentityFile = $keyPath }
                } catch {
                    Write-Host "  WARNING: Could not install key - continuing with password auth."
                }
            }
        }
    }
}

# ---------------------------------------------------------------------------
# STEP 3 - Create target directory
# ---------------------------------------------------------------------------
Write-Step "Create target directory"
$mkdirCmd = "mkdir -p `"$sshTargetDir`""
if ($WhatIf) {
    Write-Host "[WhatIf] ssh ... $mkdirCmd"
} else {
    Invoke-External -FilePath "ssh" -Arguments ((Get-SshArgs) + @($mkdirCmd))
}

# ---------------------------------------------------------------------------
# STEP 4 - Transfer files
# ---------------------------------------------------------------------------
if ($hasRsync) {
    # rsync: single connection, idempotent, --delete removes stale files.
    Write-Step "Sync files (rsync)"

    # Build rsync ssh command with port and key.
    $rsyncSsh = "ssh -p $Port -o StrictHostKeyChecking=accept-new"
    if ($IdentityFile -and (Test-Path -LiteralPath $IdentityFile)) {
        $rsyncSsh += " -i `"$IdentityFile`""
    }

    # Sync each item individually so --delete applies per-item and
    # directory structure is preserved on the remote.
    foreach ($item in $itemsToSync) {
        $localPath = Join-Path $workspace $item
        if (-not (Test-Path -LiteralPath $localPath)) {
            Write-Host "  WARN: Skipping missing path: $item"
            continue
        }

        $isDir = Test-Path -LiteralPath $localPath -PathType Container
        $rsyncItemArgs = @(
            "-az", "--delete", "--protect-args",
            "-e", $rsyncSsh
        )

        if ($isDir) {
            # Trailing / on source -> sync contents into remote/item/
            $rsyncItemArgs += "$localPath/"
            $rsyncItemArgs += "${remote}:${TargetDir}/${item}/"
        } else {
            $rsyncItemArgs += "$localPath"
            $rsyncItemArgs += "${remote}:${TargetDir}/"
        }

        if ($WhatIf) {
            Write-Host "[WhatIf] rsync $($rsyncItemArgs -join ' ')"
        } else {
            Write-Host "  rsync: $item"
            Invoke-External -FilePath "rsync" -Arguments $rsyncItemArgs
        }
    }
} else {
    # scp fallback: clean remote directories first to avoid scp -r nesting.
    Write-Step "Sync files (scp - rsync not available)"

    # Pre-clean remote directories to avoid scp -r nesting on re-runs.
    $dirsToClean = @()
    foreach ($dir in $directoryItems) {
        $localPath = Join-Path $workspace $dir
        if (Test-Path -LiteralPath $localPath -PathType Container) {
            $dirsToClean += "`"$sshTargetDir/$dir`""
        }
    }
    if ($dirsToClean.Count -gt 0) {
        $cleanCmd = "rm -rf " + ($dirsToClean -join " ")
        if ($WhatIf) {
            Write-Host "[WhatIf] ssh ... $cleanCmd"
        } else {
            Write-Host "  Cleaning stale remote directories..."
            Invoke-External -FilePath "ssh" -Arguments ((Get-SshArgs) + @($cleanCmd))
        }
    }

    # scp each item.
    foreach ($item in $itemsToSync) {
        $localPath = Join-Path $workspace $item
        if (-not (Test-Path -LiteralPath $localPath)) {
            Write-Host "  WARN: Skipping missing path: $item"
            continue
        }

        if ($WhatIf) {
            Write-Host "[WhatIf] scp -P $Port -r `"$localPath`" `"${remote}:${scpTargetDir}/`""
        } else {
            Write-Host "  scp: $item"
            Invoke-External -FilePath "scp" -Arguments @("-P", "$Port", "-r", "$localPath", "${remote}:${scpTargetDir}/")
        }
    }
}

# ---------------------------------------------------------------------------
# STEP 5 - Normalise line endings + set executable bits (single SSH call)
# ---------------------------------------------------------------------------
Write-Step "Fix line endings and set executable bits"

$postCmds = @()
foreach ($sh in $shellScripts) {
    # Guard each file: skip gracefully if it wasn't synced.
    $postCmds += "if [ -f `"$sshTargetDir/$sh`" ]; then sed -i 's/\r$//' `"$sshTargetDir/$sh`" && chmod +x `"$sshTargetDir/$sh`" && echo '  +x $sh'; else echo '  WARN: $sh not found (skipped)'; fi"
}
$postCmd = $postCmds -join "; "

if ($WhatIf) {
    Write-Host "[WhatIf] ssh ... $postCmd"
} else {
    Invoke-External -FilePath "ssh" -Arguments ((Get-SshArgs) + @($postCmd))
}

# ---------------------------------------------------------------------------
# Done
# ---------------------------------------------------------------------------
Write-Host ""
Write-Host "Sync complete."
if (-not $keyAuthWorks -and -not $NoKeySetup) {
    Write-Host ""
    Write-Host "TIP: Re-run with -SetupKey to install your SSH key on the Rock64."
    Write-Host "     After that, syncs will be truly one-click (no password prompts)."
}
Write-Host ""
Write-Host "Next on Rock64:"
Write-Host "  cd $TargetDir"
Write-Host "  ./robot_start.sh"
