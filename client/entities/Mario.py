import pygame

from classes.Animation import Animation
from classes.Camera import Camera
from classes.Collider import Collider
from classes.EntityCollider import EntityCollider
from classes.Input import Input
from classes.Sprites import Sprites
from entities.EntityBase import EntityBase
from entities.Mushroom import RedMushroom
from traits.bounce import bounceTrait
from traits.go import GoTrait
from traits.jump import JumpTrait
from classes.Pause import Pause

spriteCollection = Sprites().spriteCollection
smallAnimation = Animation(
    [
        spriteCollection["mario_run1"].image,
        spriteCollection["mario_run2"].image,
        spriteCollection["mario_run3"].image,
    ],
    spriteCollection["mario_idle"].image,
    spriteCollection["mario_jump"].image,
)
bigAnimation = Animation(
    [
        spriteCollection["mario_big_run1"].image,
        spriteCollection["mario_big_run2"].image,
        spriteCollection["mario_big_run3"].image,
    ],
    spriteCollection["mario_big_idle"].image,
    spriteCollection["mario_big_jump"].image,
)


class Mario(EntityBase):
    def __init__(self, x, y, level, screen, dashboard, sound, gravity=0.8):
        super(Mario, self).__init__(x, y, gravity)
        self.camera = Camera(self.rect, self)
        self.sound = sound
        self.input = Input(self)
        self.inAir = False
        self.inJump = False
        self.powerUpState = 2
        self.invincibilityFrames = 0
        self.hp = 30
        self.traits = {
            "jumpTrait": JumpTrait(self),
            "goTrait": GoTrait(bigAnimation, screen, self.camera, self),
            "bounceTrait": bounceTrait(self),
        }

        self.levelObj = level
        self.collision = Collider(self, level)
        self.screen = screen
        self.EntityCollider = EntityCollider(self)
        self.dashboard = dashboard
        self.restart = False
        self.pause = False
        self.pauseObj = Pause(screen, self, dashboard)
        self.canShoot = True
        self.fireCooldown = 0
        self.fire_button_held = False
        self.spawned_projectiles = []
        self.projectile_speed = 8
        self.is_dying = False
        self.death_timer = 0
        self._set_power_state(self.powerUpState, initialize=True)

    def update(self):
        if self.is_dying:
            self.update_death()
            self.traits["goTrait"].animation.inAir()
            self.traits["goTrait"].drawEntity()
            self.camera.move()
            return
        if self.invincibilityFrames > 0:
            self.invincibilityFrames -= 1
        if self.fireCooldown > 0:
            self.fireCooldown -= 1
        self.updateTraits()
        self.moveMario()
        self.camera.move()
        self.applyGravity()
        self.checkEntityCollision()
        self.input.checkForInput()

    def moveMario(self):
        self.rect.y += self.vel.y
        self.collision.checkY()
        self.rect.x += self.vel.x
        self.collision.checkX()

    def checkEntityCollision(self):
        for ent in self.levelObj.entityList:
            collisionState = self.EntityCollider.check(ent)
            if collisionState.isColliding:
                if ent.type == "Item":
                    self._onCollisionWithItem(ent)
                elif ent.type == "Block":
                    self._onCollisionWithBlock(ent)
                elif ent.type == "Mob":
                    self._onCollisionWithMob(ent, collisionState)

    def _onCollisionWithItem(self, item):
        drop_kind = getattr(item, "drop_type", "coin")
        if item in self.levelObj.entityList:
            self.levelObj.entityList.remove(item)
        item.alive = None
        if drop_kind == "mushroom":
            self.powerup(1)
            try:
                self.sound.play_sfx(self.sound.powerup)
            except AttributeError:
                pass
        else:
            self.dashboard.points += 100
            self.dashboard.coins += 1
            try:
                self.sound.play_sfx(self.sound.coin)
            except AttributeError:
                pass

    def _onCollisionWithBlock(self, block):
        if not block.triggered:
            self.dashboard.coins += 1
            self.sound.play_sfx(self.sound.bump)
        block.triggered = True

    def _onCollisionWithMob(self, mob, collisionState):
        if isinstance(mob, RedMushroom) and mob.alive:
            self.powerup(1)
            self.killEntity(mob)
            self.sound.play_sfx(self.sound.powerup)
        elif collisionState.isTop and (mob.alive or mob.bouncing):
            self.sound.play_sfx(self.sound.stomp)
            self.rect.bottom = mob.rect.top
            self.bounce()
            self.killEntity(mob)
        elif collisionState.isTop and mob.alive and not mob.active:
            self.sound.play_sfx(self.sound.stomp)
            self.rect.bottom = mob.rect.top
            mob.timer = 0
            self.bounce()
            mob.alive = False
        elif collisionState.isColliding and mob.alive and not mob.active and not mob.bouncing:
            mob.bouncing = True
            if mob.rect.x < self.rect.x:
                mob.leftrightTrait.direction = -1
                mob.rect.x += -5
                self.sound.play_sfx(self.sound.kick)
            else:
                mob.rect.x += 5
                mob.leftrightTrait.direction = 1
                self.sound.play_sfx(self.sound.kick)
        elif collisionState.isColliding and mob.alive and not self.invincibilityFrames:
            if self.powerUpState <= 0:
                self.gameOver()
            elif self.powerUpState == 1:
                self._set_power_state(0)
                self.sound.play_sfx(self.sound.pipe)
            else:
                self._set_power_state(1)
                self.sound.play_sfx(self.sound.pipe)

    def bounce(self):
        self.traits["bounceTrait"].jump = True

    def killEntity(self, ent):
        if ent.__class__.__name__ != "Koopa":
            ent.alive = False
        else:
            ent.timer = 0
            ent.leftrightTrait.speed = 1
            ent.alive = True
            ent.active = False
            ent.bouncing = False
        self.dashboard.points += 100

    def gameOver(self):
        srf = pygame.Surface((640, 480))
        srf.set_colorkey((255, 255, 255), pygame.RLEACCEL)
        srf.set_alpha(128)
        self.sound.music_channel.stop()
        try:
            self.sound.music_channel.play(self.sound.death)
        except Exception:
            pass
        self.restart = True

    def getPos(self):
        return self.camera.x + self.rect.x, self.rect.y

    def setPos(self, x, y):
        self.rect.x = x
        self.rect.y = y
        
    def powerup(self, powerupID):
        if powerupID == 1:
            if self.powerUpState <= 0:
                self._set_power_state(1)
        elif powerupID == 2:
            self._set_power_state(2)

    def applyGravity(self):
        if self.obeyGravity:
            self.vel.y += self.gravity

    def handle_fire_input(self, pressed: bool):
        if not self.canShoot:
            self.fire_button_held = pressed
            return
        if pressed:
            if not self.fire_button_held and self.fireCooldown == 0:
                self._queue_fireball()
            self.fire_button_held = True
        else:
            self.fire_button_held = False

    def consume_spawned_projectiles(self):
        if not self.spawned_projectiles:
            return []
        queued = self.spawned_projectiles[:]
        self.spawned_projectiles.clear()
        return queued

    def _queue_fireball(self):
        direction = self.traits['goTrait'].heading or 1
        spawn_x = self.rect.centerx + direction * 20
        spawn_y = self.rect.centery - 10
        self.spawned_projectiles.append(
            {
                "position": [spawn_x, spawn_y],
                "direction": direction,
                "speed": self.projectile_speed,
            }
        )
        self.fireCooldown = 18

    def begin_death(self):
        if self.is_dying:
            return
        self.is_dying = True
        self.death_timer = 180
        self.canShoot = False
        self.fire_button_held = False
        self.traits['goTrait'].direction = 0
        self.vel.x = 0
        self.vel.y = -9
        self._set_power_state(0)
        self.invincibilityFrames = 0
        self.traits['goTrait'].animation.inAir()

    def update_death(self):
        if self.death_timer > 0:
            self.death_timer -= 1
        else:
            self.death_timer = 0
        self.rect.y += self.vel.y
        self.vel.y += self.gravity

    def death_finished(self):
        return self.is_dying and self.death_timer <= 0

    def _set_power_state(self, state, initialize=False):
        state = max(0, min(state, 2))
        self.powerUpState = state
        midbottom = self.rect.midbottom
        if state == 0:
            self.traits['goTrait'].updateAnimation(smallAnimation)
            self.rect = pygame.Rect(0, 0, 32, 32)
            self.canShoot = False
        else:
            self.traits['goTrait'].updateAnimation(bigAnimation)
            self.rect = pygame.Rect(0, 0, 32, 64)
            self.canShoot = state >= 2
        self.rect.midbottom = midbottom
        if not initialize:
            self.invincibilityFrames = 60
        if state >= 2:
            self.fireCooldown = 0
