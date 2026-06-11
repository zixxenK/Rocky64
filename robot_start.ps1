#!/usr/bin/env pwsh
# =============================================================================
#  robot_start.ps1  -  Windows PowerShell startup for Rock64 Robot
#
#  Usage (Windows host):
#    .\robot_start.ps1 [OPTIONS]
#
#  Options:
#    --role         <windows|rock64>   Which machine you're running on (default: windows)
#    --script       <ps5|agent|control|unified>  Which control script to run (default: ps5)
#    --host         <ip>                Rock64 IP address (default: 192.168.1.159)
#    --serial-port  <port>              Serial port on Rock64 (default: /dev/ttyUSB0)
#    --baud-rate    <baud>              Serial baud rate (default: 115200)
#    --ssh-key      <path>              SSH key path (default: ~/.ssh/rock64_sync)
#    --camera       <index>             Camera index for agent mode (default: 0)
#    --port         <port>              Web server port for control center (default: 5000)
#    --skip-deps                        Skip dependency installation
#    --help
#
#  Examples:
#    # Windows PS5 controller bridge:
#    .\robot_start.ps1 --script ps5
#    .\robot_start.ps1 --script ps5 --host 192.168.1.159
#
#    # Windows agent controller:
#    .\robot_start.ps1 --script agent
#
#    # Windows control center web UI:
#    .\robot_start.ps1 --script control
#
#    # Unified Windows control (keyboard + controller):
#    .\robot_start.ps1 --script unified
# =============================================================================

param(
    [string]$Role = "windows",
    [string]$Script = "ps5",
    [string]$Host = "192.168.1.159",
    [string]$SerialPort = "/dev/ttyUSB0",
    [int]$BaudRate = 115200,
    [string]$SshKey = "",
    [int]$Camera = 0,
    [int]$Port = 5000,
    [switch]$SkipDeps,
    [switch]$Help
)

# Show help
if ($Help) {
    Get-Content $PSCommandPath | Select-String -Pattern "#  (Usage|Options|Examples)" -Context 0,10
    exit 0
}

# Color output functions
function Write-ColorOutput($ForegroundColor) {
    $fc = $host.UI.RawUI.ForegroundColor
    $host.UI.RawUI.ForegroundColor = $ForegroundColor
    if ($args) {
        Write-Output $args
    }
    $host.UI.RawUI.ForegroundColor = $fc
}

function Write-Info { Write-ColorOutput Green "[INFO]  $args" }
function Write-Warn { Write-ColorOutput Yellow "[WARN]  $args" }
function Write-Error { Write-ColorOutput Red "[ERROR] $args" }

# Banner
function Show-Banner {
    Write-Output ""
    Write-Output "=========================================================="
    Write-Output "  $args"
    Write-Output "=========================================================="
    Write-Output ""
}

# Get script directory
$ScriptDir = Split-Path -Parent $PSCommandPath
$HostControlDir = Join-Path $ScriptDir "host_control"

Show-Banner "Rock64 Robot - Windows Startup (role=$Role, script=$Script)"
Write-Info "Script directory: $ScriptDir"
Write-Info "Host control dir: $HostControlDir"
Write-Info "Rock64 host: $Host"
Write-Info "Serial port: $SerialPort @ $BaudRate baud"
Write-Output ""

# Check if host_control directory exists
if (-not (Test-Path $HostControlDir)) {
    Write-Error "host_control directory not found: $HostControlDir"
    exit 1
}

# Check Python
Write-Info "[1/5] Checking Python installation"
try {
    $pythonVersion = python --version 2>&1
    Write-Info "Python version: $pythonVersion"
} catch {
    Write-Error "Python not found in PATH. Install Python 3.8+ from python.org"
    exit 1
}

# Check virtual environment
Write-Info "[2/5] Checking virtual environment"
$VenvDir = Join-Path $ScriptDir ".venv"
if (-not (Test-Path $VenvDir)) {
    Write-Warn "Virtual environment not found at $VenvDir"
    Write-Info "Creating virtual environment..."
    try {
        python -m venv $VenvDir
        Write-Info "Virtual environment created"
    } catch {
        Write-Error "Failed to create virtual environment"
        exit 1
    }
}

# Activate virtual environment
$ActivateScript = Join-Path $VenvDir "Scripts\Activate.ps1"
if (Test-Path $ActivateScript) {
    Write-Info "Activating virtual environment..."
    & $ActivateScript
} else {
    Write-Error "Virtual environment activation script not found: $ActivateScript"
    exit 1
}

# Install dependencies
if (-not $SkipDeps) {
    Write-Info "[3/5] Installing dependencies"
    $RequirementsFile = Join-Path $ScriptDir "requirements.txt"
    if (Test-Path $RequirementsFile) {
        Write-Info "Installing from $RequirementsFile..."
        pip install -r $RequirementsFile
        if ($LASTEXITCODE -ne 0) {
            Write-Warn "Some dependencies may have failed to install"
        }
    } else {
        Write-Warn "requirements.txt not found at $RequirementsFile"
        Write-Info "Installing core dependencies manually..."
        pip install pygame opencv-python numpy flask flask-socketio pyserial paramiko
    }
} else {
    Write-Info "[3/5] Skipping dependency installation (--skip-deps)"
}

# Determine SSH key path
if ([string]::IsNullOrEmpty($SshKey)) {
    $SshKey = Join-Path $env:USERPROFILE ".ssh\rock64_sync"
    if (-not (Test-Path $SshKey)) {
        Write-Warn "SSH key not found at $SshKey"
        Write-Info "You may need to specify --ssh-key or create the key"
    }
}

# Select and run the appropriate script
Write-Info "[4/5] Selecting control script"
$ScriptPath = $null

switch ($Script) {
    "ps5" {
        $ScriptPath = Join-Path $HostControlDir "ps5_windows_bridge.py"
        if (Test-Path $ScriptPath) {
            Write-Info "Launching PS5 Windows bridge..."
            $args = @(
                "--host", $Host,
                "--port", $SerialPort,
                "--baud", $BaudRate,
                "--ssh-key", $SshKey
            )
            python $ScriptPath @args
        } else {
            Write-Error "Script not found: $ScriptPath"
            exit 1
        }
    }
    "agent" {
        $ScriptPath = Join-Path $HostControlDir "agent_controller.py"
        if (Test-Path $ScriptPath) {
            Write-Info "Launching agent controller..."
            $args = @(
                "--rock64-host", $Host,
                "--rock64-port", $SerialPort,
                "--ssh-key", $SshKey,
                "--camera", $Camera
            )
            python $ScriptPath @args
        } else {
            Write-Error "Script not found: $ScriptPath"
            exit 1
        }
    }
    "control" {
        $ScriptPath = Join-Path $HostControlDir "control_center.py"
        if (Test-Path $ScriptPath) {
            Write-Info "Launching control center web server..."
            $args = @(
                "--host", "0.0.0.0",
                "--port", $Port,
                "--serial-port", $SerialPort,
                "--baud", $BaudRate
            )
            python $ScriptPath @args
        } else {
            Write-Error "Script not found: $ScriptPath"
            exit 1
        }
    }
    "unified" {
        $ScriptPath = Join-Path $HostControlDir "windows_control.py"
        if (Test-Path $ScriptPath) {
            Write-Info "Launching unified Windows control..."
            $args = @(
                "--host", $Host,
                "--port", $SerialPort,
                "--baud", $BaudRate,
                "--ssh-key", $SshKey
            )
            python $ScriptPath @args
        } else {
            Write-Error "Script not found: $ScriptPath"
            exit 1
        }
    }
    default {
        Write-Error "Unknown script type: $Script"
        Write-Info "Valid options: ps5, agent, control, unified"
        exit 1
    }
}

Write-Info "[5/5] Script execution completed"
