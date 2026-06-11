"""
Platform detection utility for Rock64 Robot project.
Provides cross-platform compatibility for Windows and Linux systems.
"""

import sys
from typing import Optional


def get_platform() -> str:
    """Detect the current platform.
    
    Returns:
        'windows' if running on Windows, 'linux' otherwise
    """
    return 'windows' if sys.platform == 'win32' else 'linux'


def is_windows() -> bool:
    """Check if running on Windows."""
    return sys.platform == 'win32'


def is_linux() -> bool:
    """Check if running on Linux."""
    return sys.platform.startswith('linux')


def get_default_serial_port() -> str:
    """Get the default serial port for the current platform.
    
    Returns:
        Windows: 'COM3' (common default, can be overridden)
        Linux: '/dev/ttyUSB0' (Arduino USB serial)
    """
    if is_windows():
        return 'COM3'
    else:
        return '/dev/ttyUSB0'


def list_available_serial_ports() -> list:
    """List available serial ports on the current platform.
    
    Returns:
        List of available serial port names
    """
    if is_windows():
        try:
            import serial.tools.list_ports
            ports = serial.tools.list_ports.comports()
            return [port.device for port in ports]
        except ImportError:
            return []
    else:
        # On Linux, check common serial device paths
        import os
        ports = []
        for path in ['/dev/ttyUSB0', '/dev/ttyUSB1', '/dev/ttyACM0', '/dev/ttyACM1']:
            if os.path.exists(path):
                ports.append(path)
        return ports


def get_ssh_key_path(default_key: str = 'rock64_sync') -> str:
    """Get the default SSH key path for the current platform.
    
    Args:
        default_key: Name of the SSH key file (without extension)
    
    Returns:
        Full path to the SSH key
    """
    if is_windows():
        # Windows: C:\Users\USERNAME\.ssh\key
        import os
        home = os.path.expanduser('~')
        return os.path.join(home, '.ssh', default_key)
    else:
        # Linux: ~/.ssh/key
        import os
        home = os.path.expanduser('~')
        return os.path.join(home, '.ssh', default_key)


def format_serial_command(port: str, baud: int) -> str:
    """Format the serial port configuration command for the current platform.
    
    Args:
        port: Serial port name (e.g., 'COM3' or '/dev/ttyUSB0')
        baud: Baud rate
    
    Returns:
        Platform-specific serial configuration command
    """
    if is_windows():
        # Windows doesn't need stty configuration
        return ''
    else:
        # Linux: use stty to configure serial port
        return f'stty -F {port} {baud} raw -echo'


def validate_serial_port(port: str) -> bool:
    """Validate that a serial port exists and is accessible.
    
    Args:
        port: Serial port name to validate
    
    Returns:
        True if port is valid and accessible, False otherwise
    """
    try:
        import serial
        ser = serial.Serial(port, timeout=1)
        ser.close()
        return True
    except (serial.SerialException, OSError):
        return False
