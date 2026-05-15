"""
Jump tuning shared by pygame `traits.jump.JumpTrait` and `client_kivy.mario.Mario`.

Edit values here — both clients read these constants and `apply_jump_trait_end_of_frame`.
"""

MARIO_GRAVITY = 0.8
JUMP_VERTICAL_SPEED = -12
JUMP_HEIGHT = 140.0


def jump_deacceleration_height(gravity: float = MARIO_GRAVITY) -> float:
    """Height (px) of constant-speed rise before gravity takes over (JumpTrait formula)."""
    return JUMP_HEIGHT - (
        (JUMP_VERTICAL_SPEED * JUMP_VERTICAL_SPEED) / (2.0 * gravity)
    )


def apply_jump_trait_end_of_frame(
    *,
    jumping: bool,
    on_ground: bool,
    rect_y: float,
    jump_start_y: float,
    vel_y: float,
    in_jump: bool,
    obey_gravity: bool,
    deaccel_height: float | None = None,
) -> tuple[float, bool, float, bool, bool]:
    """
    Pygame `JumpTrait.jump` after move + gravity.

    Returns (vel_y, on_ground, jump_start_y, in_jump, obey_gravity).
    """
    if deaccel_height is None:
        deaccel_height = jump_deacceleration_height()
    if jumping and on_ground:
        vel_y = float(JUMP_VERTICAL_SPEED)
        on_ground = False
        in_jump = True
        jump_start_y = float(rect_y)
        obey_gravity = False
    if in_jump:
        rise = float(jump_start_y) - int(rect_y)
        if rise >= deaccel_height or vel_y == 0:
            in_jump = False
            obey_gravity = True
    return vel_y, on_ground, jump_start_y, in_jump, obey_gravity
