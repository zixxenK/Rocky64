DEFAULT_LINEAR_SPEED = 0.6
DEFAULT_ANGULAR_SPEED = 1.0
DEFAULT_SERVO_STEP = 5


def axis_from_keys(positive: bool, negative: bool, magnitude: float) -> float:
    if positive == negative:
        return 0.0
    return float(magnitude if positive else -magnitude)


def compute_twist_components(
    forward: bool,
    backward: bool,
    turn_left: bool,
    turn_right: bool,
    linear_speed: float = DEFAULT_LINEAR_SPEED,
    angular_speed: float = DEFAULT_ANGULAR_SPEED,
):
    linear_x = axis_from_keys(forward, backward, linear_speed)
    angular_z = axis_from_keys(turn_left, turn_right, angular_speed)
    return linear_x, angular_z


def next_servo_position(
    current_position: int,
    move_left: bool,
    move_right: bool,
    step: int = DEFAULT_SERVO_STEP,
) -> int:
    if move_left == move_right:
        return current_position
    if move_left:
        return max(0, current_position - step)
    return min(180, current_position + step)
