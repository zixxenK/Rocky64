from typing import Tuple


def clamp_speed(value: float, limit: int = 255) -> int:
    return int(max(-limit, min(limit, value)))


def motor_command_fields(speed: int) -> Tuple[str, int]:
    constrained_speed = clamp_speed(speed)
    if constrained_speed > 0:
        return 'F', constrained_speed
    if constrained_speed < 0:
        return 'B', abs(constrained_speed)
    return 'S', 0


def motor_packet(motor_id: int, speed: int) -> str:
    direction, magnitude = motor_command_fields(speed)
    return f'<{motor_id},{direction},{magnitude}>\n'


def twist_to_wheel_speeds(
    linear_x: float,
    angular_z: float,
    linear_scale: float = 200.0,
    angular_scale: float = 100.0,
    limit: int = 255,
) -> Tuple[int, int]:
    left_raw = linear_x * linear_scale + angular_z * angular_scale
    right_raw = linear_x * linear_scale - angular_z * angular_scale

    # Scale both wheels together when over the PWM limit so the turn ratio is
    # preserved. Clamping each wheel independently would distort arcs at speed.
    max_raw = max(abs(left_raw), abs(right_raw))
    if max_raw > limit:
        scale = limit / max_raw
        left_raw *= scale
        right_raw *= scale

    return clamp_speed(left_raw, limit), clamp_speed(right_raw, limit)