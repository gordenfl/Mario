from jump_constants import (
    JUMP_VERTICAL_SPEED,
    apply_jump_trait_end_of_frame,
    jump_deacceleration_height,
)


class JumpTrait:
    def __init__(self, entity):
        self.verticalSpeed = JUMP_VERTICAL_SPEED
        self.entity = entity
        self.initalHeight = 384
        self.deaccelerationHeight = jump_deacceleration_height(entity.gravity)

    def jump(self, jumping):
        if jumping and self.entity.onGround:
            self.entity.sound.play_sfx(self.entity.sound.jump)
            self.entity.inAir = True
        (
            self.entity.vel.y,
            self.entity.onGround,
            self.initalHeight,
            self.entity.inJump,
            self.entity.obeyGravity,
        ) = apply_jump_trait_end_of_frame(
            jumping=jumping,
            on_ground=self.entity.onGround,
            rect_y=self.entity.rect.y,
            jump_start_y=self.initalHeight,
            vel_y=self.entity.vel.y,
            in_jump=self.entity.inJump,
            obey_gravity=self.entity.obeyGravity,
            deaccel_height=self.deaccelerationHeight,
        )

    def reset(self):
        self.entity.inAir = False
