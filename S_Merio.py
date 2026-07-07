"""
S M-ario - a modernized infinite platformer built on the original game's foundation.

Run:
    python s_mario.py

Optional assets (drop these next to this file, or in an "assets" sub-folder):
    mario_1.png, mario_2.png, mario_3.png, mario_4.png   - playable characters
    bug.png                                              - enemy sprite
    D.png                                                 - boss sprite
    jump.mp3, coin.mp3, stomp.mp3, hurt.mp3, select.mp3,
    "level over.mp3", "game over.mp3", background.mp3     - audio

Every asset is optional. If a file is missing the game falls back to a hand
drawn placeholder, so the game always runs even with zero assets.

Controls:
    Move        : Arrow keys / A-D / Left analog stick / D-Pad / on-screen touch pad
    Jump        : Space / Up / W / Gamepad button 0 / on-screen touch button
    Pause       : Escape / Gamepad button 7 (start)
    Mute        : M          Volume: +/-
    Fullscreen  : F11
    Restart     : R (on the Game Over screen)

The on-screen touch controls appear automatically the first time a finger or
mouse click is detected in the play area, so the game works out of the box
when mirrored to a phone through a PC-remote / USB-debugging tool that only
forwards pointer/touch events.
"""

import os
import sys
import math
import random
import pygame

# ============================================================================
#  BOOTSTRAP
# ============================================================================

pygame.mixer.pre_init(44100, -16, 2, 512)
pygame.init()
pygame.joystick.init()

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ASSET_DIRS = [SCRIPT_DIR, os.path.join(SCRIPT_DIR, "assets"), os.getcwd()]


def find_asset(filename):
    """Look for `filename` in every known asset folder, return the first hit or None."""
    for d in ASSET_DIRS:
        p = os.path.join(d, filename)
        if os.path.exists(p):
            return p
    return None


SOUND_ENABLED = False
try:
    if pygame.mixer.get_init() is None:
        pygame.mixer.init(44100, -16, 2, 512)
    SOUND_ENABLED = True
except pygame.error as e:
    print("[SOUND] Mixer unavailable, sound disabled:", e)

# ============================================================================
#  DISPLAY  (fixed 1280x720 virtual canvas, scaled + letterboxed to real window)
# ============================================================================

SCREEN_W, SCREEN_H = 1280, 720
window = pygame.display.set_mode((SCREEN_W, SCREEN_H), pygame.RESIZABLE)
screen = pygame.Surface((SCREEN_W, SCREEN_H))
pygame.display.set_caption("S M-ario")
clock = pygame.time.Clock()
fullscreen = False


def toggle_fullscreen():
    global window, fullscreen
    fullscreen = not fullscreen
    try:
        if fullscreen:
            window = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
        else:
            window = pygame.display.set_mode((SCREEN_W, SCREEN_H), pygame.RESIZABLE)
    except pygame.error as e:
        fullscreen = not fullscreen
        print("[DISPLAY] Could not toggle fullscreen:", e)


def get_present_rect():
    """Return (offset_x, offset_y, drawn_w, drawn_h, scale) describing where the
    1280x720 canvas currently lands inside the real window (for letterboxing
    and for translating touch/mouse coordinates back to virtual space)."""
    win_w, win_h = window.get_size()
    scale = min(win_w / SCREEN_W, win_h / SCREEN_H)
    drawn_w, drawn_h = max(1, int(SCREEN_W * scale)), max(1, int(SCREEN_H * scale))
    off_x, off_y = (win_w - drawn_w) // 2, (win_h - drawn_h) // 2
    return off_x, off_y, drawn_w, drawn_h, scale


def window_to_virtual(pos):
    """Map a real-window pixel coordinate to the 1280x720 virtual canvas."""
    off_x, off_y, drawn_w, drawn_h, scale = get_present_rect()
    vx = (pos[0] - off_x) / scale if scale > 0 else pos[0]
    vy = (pos[1] - off_y) / scale if scale > 0 else pos[1]
    return vx, vy


def present():
    win_w, win_h = window.get_size()
    if (win_w, win_h) == (SCREEN_W, SCREEN_H):
        window.blit(screen, (0, 0))
    else:
        off_x, off_y, drawn_w, drawn_h, _ = get_present_rect()
        scaled = pygame.transform.smoothscale(screen, (drawn_w, drawn_h))
        window.fill((0, 0, 0))
        window.blit(scaled, (off_x, off_y))
    pygame.display.flip()


# ============================================================================
#  PALETTE
# ============================================================================

SKY_TOP = (36, 62, 130)
SKY_BOTTOM = (152, 205, 247)
SUN_COLOR = (255, 236, 173)
GREEN = (46, 178, 90)
DARK_GREEN = (24, 128, 62)
BROWN = (150, 96, 54)
DARK_BROWN = (94, 56, 28)
BLACK = (10, 10, 14)
YELLOW = (255, 205, 40)
WHITE = (245, 247, 250)
ENEMY_COLOR = (150, 75, 30)
MOUNTAIN_COLOR = (108, 118, 176)
HILL_FAR = (86, 176, 122)
HILL_NEAR = (58, 156, 96)
BUSH_COLOR = (32, 128, 66)
ACCENT = (0, 225, 210)
DANGER = (235, 64, 74)
PANEL_BG = (14, 16, 28)

GROUND_Y = 600
GRAVITY = 0.85
JUMP_STRENGTH = -18
SPEED = 6

font = pygame.font.SysFont("Arial", 28, bold=True)
big_font = pygame.font.SysFont("Arial", 56, bold=True)
mid_font = pygame.font.SysFont("Arial", 34, bold=True)
small_font = pygame.font.SysFont("Arial", 21)


def lerp(a, b, t):
    return a + (b - a) * t


def clamp(v, lo, hi):
    return max(lo, min(v, hi))


def lerp_color(c1, c2, t):
    return tuple(int(lerp(c1[i], c2[i], t)) for i in range(3))


def ease_out(t):
    return 1 - (1 - t) ** 3


# ============================================================================
#  SOUND
# ============================================================================

sounds = {}
MASTER_VOLUME = 0.6
MUSIC_MULT = 0.45
muted = False
volume_hud_timer = 0
using_file_music = False

SOUND_FILES = {
    "jump": "jump.mp3",
    "coin": "coin.mp3",
    "stomp": "stomp.mp3",
    "hurt": "hurt.mp3",
    "level_win": "level over.mp3",
    "game_over": "game over.mp3",
    "select": "select.mp3",
}
MUSIC_FILE = "background.mp3"

if SOUND_ENABLED:
    for event_name, filename in SOUND_FILES.items():
        path = find_asset(filename)
        if path:
            try:
                sounds[event_name] = pygame.mixer.Sound(path)
            except Exception as e:
                print(f"[SOUND] Could not load {path}:", e)

    music_path = find_asset(MUSIC_FILE)
    if music_path:
        try:
            pygame.mixer.music.load(music_path)
            pygame.mixer.music.play(loops=-1)
            pygame.mixer.music.set_volume(MASTER_VOLUME * MUSIC_MULT)
            using_file_music = True
        except Exception as e:
            print(f"[SOUND] Could not play {music_path}:", e)


def play(name):
    if SOUND_ENABLED and name in sounds:
        sounds[name].set_volume(0 if muted else MASTER_VOLUME)
        sounds[name].play()


def apply_volume():
    if not SOUND_ENABLED:
        return
    vol = 0 if muted else MASTER_VOLUME * MUSIC_MULT
    if using_file_music:
        pygame.mixer.music.set_volume(vol)


def change_volume(delta):
    global MASTER_VOLUME, muted, volume_hud_timer
    muted = False
    MASTER_VOLUME = clamp(MASTER_VOLUME + delta, 0.0, 1.0)
    apply_volume()
    volume_hud_timer = 90


def toggle_mute():
    global muted, volume_hud_timer
    muted = not muted
    apply_volume()
    volume_hud_timer = 90


# ============================================================================
#  SAVE SYSTEM
# ============================================================================

HIGH_SCORE_FILE = os.path.join(SCRIPT_DIR, "save.dat")


def load_high_score():
    try:
        if os.path.exists(HIGH_SCORE_FILE):
            with open(HIGH_SCORE_FILE, "r", encoding="utf-8") as f:
                content = f.read().strip()
                return int(content) if content else 0
    except (ValueError, OSError) as e:
        print("[SAVE] Could not read high score:", e)
    return 0


def save_high_score(value):
    try:
        with open(HIGH_SCORE_FILE, "w", encoding="utf-8") as f:
            f.write(str(int(value)))
    except OSError as e:
        print("[SAVE] Could not write high score:", e)


high_score = load_high_score()


# ============================================================================
#  CHARACTERS
# ============================================================================

CHARACTERS = [
    {"name": "Red", "image": "mario_1.png", "cap": (222, 46, 40), "shirt": (222, 46, 40),
     "overall": (18, 84, 196), "skin": (255, 205, 160), "trim": (255, 255, 255)},
    {"name": "Green", "image": "mario_2.png", "cap": (26, 158, 82), "shirt": (26, 158, 82),
     "overall": (66, 44, 24), "skin": (255, 205, 160), "trim": (255, 255, 255)},
    {"name": "Gold", "image": "mario_3.png", "cap": (240, 180, 20), "shirt": (240, 180, 20),
     "overall": (110, 58, 150), "skin": (255, 205, 160), "trim": (255, 255, 255)},
    {"name": "Azure", "image": "mario_4.png", "cap": (18, 175, 220), "shirt": (18, 175, 220),
     "overall": (26, 30, 64), "skin": (255, 220, 190), "trim": (255, 255, 255)},
]
selected_char = 0

mario_w, mario_h = 46, 62
character_images_right = {}
character_images_left = {}

for _ch in CHARACTERS:
    _fname = _ch["image"]
    _path = find_asset(_fname)
    if _path:
        try:
            _img = pygame.image.load(_path).convert_alpha()
            _img = pygame.transform.scale(_img, (mario_w, mario_h))
            character_images_right[_fname] = _img
            character_images_left[_fname] = pygame.transform.flip(_img, True, False)
        except Exception as e:
            print(f"[IMAGE] Failed to load {_path}:", e)

# Enemy ("bug") sprite
ENEMY_W, ENEMY_H = 40, 32
bug_image_right = None
bug_image_left = None
_bug_path = find_asset("bug.png")
if _bug_path:
    try:
        _bimg = pygame.image.load(_bug_path).convert_alpha()
        _bimg = pygame.transform.scale(_bimg, (ENEMY_W, ENEMY_H))
        bug_image_right = _bimg
        bug_image_left = pygame.transform.flip(_bimg, True, False)
    except Exception as e:
        print(f"[IMAGE] Failed to load bug.png:", e)

# Boss sprite
BOSS_W, BOSS_H = 64, 74
boss_image_right = None
boss_image_left = None
_boss_path = find_asset("D.png")
if _boss_path:
    try:
        _bimg = pygame.image.load(_boss_path).convert_alpha()
        _bimg = pygame.transform.scale(_bimg, (BOSS_W, BOSS_H))
        boss_image_right = _bimg
        boss_image_left = pygame.transform.flip(_bimg, True, False)
    except Exception as e:
        print(f"[IMAGE] Failed to load D.png:", e)


# ============================================================================
#  INPUT MANAGER  (keyboard + gamepad + multi-touch / mouse virtual pad)
# ============================================================================

class TouchButton:
    """A translucent circular on-screen button that tracks whichever
    finger/mouse id is currently pressing it, so several buttons can be
    held down at once (true multi-touch)."""

    def __init__(self, cx, cy, radius, label):
        self.cx, self.cy, self.radius, self.label = cx, cy, radius, label
        self.owner = None          # id of the finger/mouse currently holding it
        self.pressed = False
        self.press_anim = 0.0      # 0..1 visual squash on press

    def hit(self, x, y):
        return (x - self.cx) ** 2 + (y - self.cy) ** 2 <= self.radius ** 2

    def try_press(self, pid, x, y):
        if self.owner is None and self.hit(x, y):
            self.owner = pid
            self.pressed = True
            return True
        return False

    def release(self, pid):
        if self.owner == pid:
            self.owner = None
            self.pressed = False

    def update(self):
        target = 1.0 if self.pressed else 0.0
        self.press_anim = lerp(self.press_anim, target, 0.35)

    def draw(self, surface):
        r = self.radius * (1.0 - 0.12 * self.press_anim)
        glow = 90 + int(70 * self.press_anim)
        pad = pygame.Surface((int(r * 2 + 8), int(r * 2 + 8)), pygame.SRCALPHA)
        pygame.draw.circle(pad, (*ACCENT, glow), (pad.get_width() // 2, pad.get_height() // 2), int(r))
        pygame.draw.circle(pad, (255, 255, 255, 160), (pad.get_width() // 2, pad.get_height() // 2), int(r), 3)
        surface.blit(pad, (self.cx - pad.get_width() // 2, self.cy - pad.get_height() // 2))
        txt = font.render(self.label, True, WHITE)
        surface.blit(txt, (self.cx - txt.get_width() / 2, self.cy - txt.get_height() / 2))


class InputManager:
    """Unifies keyboard, gamepad and multi-touch/mouse input into one simple
    (move, jump, pause_pressed) reading per frame."""

    def __init__(self):
        self.joystick = None
        self.mute_btn_last = False
        self.start_btn_last = False
        self.touch_active = False   # becomes True the first time a touch/click lands in the play area
        self.btn_left = TouchButton(90, SCREEN_H - 110, 55, "<")
        self.btn_right = TouchButton(220, SCREEN_H - 110, 55, ">")
        self.btn_jump = TouchButton(SCREEN_W - 110, SCREEN_H - 110, 65, "A")
        self.buttons = [self.btn_left, self.btn_right, self.btn_jump]
        self.try_connect_joystick()

    def try_connect_joystick(self):
        if pygame.joystick.get_count() > 0:
            try:
                self.joystick = pygame.joystick.Joystick(0)
                self.joystick.init()
                print(f"[INPUT] Controller connected: {self.joystick.get_name()}")
            except pygame.error as e:
                print("[INPUT] Could not init joystick:", e)

    def handle_event(self, event):
        """Feed raw pygame events here so multi-touch presses/releases are tracked precisely."""
        if event.type == pygame.JOYDEVICEADDED:
            self.try_connect_joystick()
        elif event.type == pygame.FINGERDOWN:
            self.touch_active = True
            win_w, win_h = window.get_size()
            x, y = window_to_virtual((event.x * win_w, event.y * win_h))
            for b in self.buttons:
                if b.try_press(("finger", event.finger_id), x, y):
                    break
        elif event.type == pygame.FINGERUP:
            for b in self.buttons:
                b.release(("finger", event.finger_id))
        elif event.type == pygame.FINGERMOTION:
            # allow sliding a finger onto a button without lifting first
            win_w, win_h = window.get_size()
            x, y = window_to_virtual((event.x * win_w, event.y * win_h))
            fid = ("finger", event.finger_id)
            for b in self.buttons:
                if b.owner == fid and not b.hit(x, y):
                    b.release(fid)
            for b in self.buttons:
                if b.owner is None:
                    b.try_press(fid, x, y)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self.touch_active = True
            x, y = window_to_virtual(event.pos)
            for b in self.buttons:
                if b.try_press("mouse", x, y):
                    break
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            for b in self.buttons:
                b.release("mouse")
        elif event.type == pygame.MOUSEMOTION and pygame.mouse.get_pressed()[0]:
            x, y = window_to_virtual(event.pos)
            for b in self.buttons:
                if b.owner == "mouse" and not b.hit(x, y):
                    b.release("mouse")
            for b in self.buttons:
                if b.owner is None:
                    b.try_press("mouse", x, y)

    def read(self):
        """Return (move, jump_held, pause_pressed) for the current frame."""
        keys = pygame.key.get_pressed()
        move = 0
        jump = False
        pause = False

        if keys[pygame.K_LEFT] or keys[pygame.K_a]:
            move -= 1
        if keys[pygame.K_RIGHT] or keys[pygame.K_d]:
            move += 1
        if keys[pygame.K_SPACE] or keys[pygame.K_UP] or keys[pygame.K_w]:
            jump = True
        if keys[pygame.K_ESCAPE]:
            pause = True

        if self.btn_left.pressed:
            move -= 1
        if self.btn_right.pressed:
            move += 1
        if self.btn_jump.pressed:
            jump = True
        move = clamp(move, -1, 1)

        if self.joystick is not None:
            try:
                axis_x = self.joystick.get_axis(0)
                hat = self.joystick.get_hat(0) if self.joystick.get_numhats() > 0 else (0, 0)
                if abs(axis_x) > 0.25:
                    move = 1 if axis_x > 0 else -1
                elif hat[0] != 0:
                    move = hat[0]
                if self.joystick.get_numbuttons() > 0 and self.joystick.get_button(0):
                    jump = True
                if self.joystick.get_numbuttons() > 1:
                    mute_btn = self.joystick.get_button(1)
                    if mute_btn and not self.mute_btn_last:
                        toggle_mute()
                    self.mute_btn_last = mute_btn
                if self.joystick.get_numbuttons() > 7:
                    start_btn = self.joystick.get_button(7)
                    if start_btn and not self.start_btn_last:
                        pause = True
                    self.start_btn_last = start_btn
            except pygame.error:
                pass

        for b in self.buttons:
            b.update()

        return move, jump, pause

    def draw(self, surface):
        if self.touch_active:
            for b in self.buttons:
                b.draw(surface)


input_manager = InputManager()


# ============================================================================
#  PARTICLES & CAMERA SHAKE
# ============================================================================

particles = []


def add_particles(x, y, color, count=10, spread=3.0, life=25, glow=False):
    for _ in range(count):
        particles.append({
            "x": x, "y": y,
            "vx": random.uniform(-spread, spread),
            "vy": random.uniform(-spread * 1.5, -0.5),
            "life": life, "max_life": life,
            "color": color, "size": random.randint(2, 5),
            "glow": glow,
        })


def update_particles():
    for p in particles[:]:
        p["x"] += p["vx"]
        p["y"] += p["vy"]
        p["vy"] += 0.2
        p["life"] -= 1
        if p["life"] <= 0:
            particles.remove(p)


def draw_particles(surface, cam_x):
    for p in particles:
        t = p["life"] / p["max_life"]
        size = max(1, int(p["size"] * t))
        pos = (int(p["x"] - cam_x), int(p["y"]))
        if p["glow"]:
            glow_surf = pygame.Surface((size * 6, size * 6), pygame.SRCALPHA)
            pygame.draw.circle(glow_surf, (*p["color"], int(120 * t)),
                                (size * 3, size * 3), size * 3)
            surface.blit(glow_surf, (pos[0] - size * 3, pos[1] - size * 3))
        pygame.draw.circle(surface, p["color"], pos, size)


shake_timer = 0
shake_strength = 0


def trigger_shake(strength=6, duration=10):
    global shake_timer, shake_strength
    shake_timer = duration
    shake_strength = strength


class Camera:
    """Smoothly interpolates toward the player instead of snapping, for a
    modern, cinematic scroll feel."""

    def __init__(self):
        self.x = 0.0

    def update(self, target_x, level_width):
        desired = clamp(target_x - SCREEN_W // 3, 0, max(0, level_width - SCREEN_W))
        self.x = lerp(self.x, desired, 0.12)
        return self.x


camera = Camera()


# ============================================================================
#  UI HELPERS
# ============================================================================

def draw_panel(surface, x, y, w, h, color=PANEL_BG, alpha=170, radius=14, border=(255, 255, 255, 40)):
    panel = pygame.Surface((w, h), pygame.SRCALPHA)
    pygame.draw.rect(panel, (*color, alpha), panel.get_rect(), border_radius=radius)
    pygame.draw.rect(panel, border, panel.get_rect(), 2, border_radius=radius)
    surface.blit(panel, (x, y))


def draw_text_shadow(surface, text, fnt, color, x, y, shadow_color=(0, 0, 0, 160)):
    shadow = fnt.render(text, True, shadow_color[:3])
    shadow.set_alpha(shadow_color[3] if len(shadow_color) > 3 else 160)
    surface.blit(shadow, (x + 2, y + 3))
    surface.blit(fnt.render(text, True, color), (x, y))


def draw_hearts(surface, x, y, lives, max_lives=3):
    for i in range(max_lives):
        full = i < lives
        cx, cy = x + i * 34, y
        color = DANGER if full else (70, 70, 80)
        size = 12
        pygame.draw.circle(surface, color, (cx - size // 2, cy), size // 2 + 2)
        pygame.draw.circle(surface, color, (cx + size // 2, cy), size // 2 + 2)
        pygame.draw.polygon(surface, color, [(cx - size - 1, cy), (cx + size + 1, cy), (cx, cy + size + 4)])


def draw_volume_hud(surface):
    bar_x, bar_y, bar_w, bar_h = SCREEN_W - 230, 20, 180, 18
    draw_panel(surface, bar_x - 10, bar_y - 8, bar_w + 20, bar_h + 34, alpha=130)
    pygame.draw.rect(surface, (35, 35, 45), (bar_x, bar_y, bar_w, bar_h), border_radius=8)
    fill_w = 0 if muted else int(bar_w * MASTER_VOLUME)
    pygame.draw.rect(surface, ACCENT if not muted else DANGER, (bar_x, bar_y, fill_w, bar_h), border_radius=8)
    pygame.draw.rect(surface, WHITE, (bar_x, bar_y, bar_w, bar_h), 2, border_radius=8)
    label = "MUTED" if muted else f"Vol {int(MASTER_VOLUME * 100)}%"
    surface.blit(small_font.render(label, True, WHITE), (bar_x, bar_y + bar_h + 4))


# ============================================================================
#  LUCKY BOX
# ============================================================================

class LuckyBox:
    SIZE = 34

    def __init__(self, x, y):
        self.x = float(x)
        self.y = float(y)
        self.width = LuckyBox.SIZE
        self.height = LuckyBox.SIZE
        self.hit = False
        self.bump_timer = 0.0
        self.glow_phase = random.uniform(0, math.tau)

    def get_rect(self):
        return pygame.Rect(int(self.x), int(self.y), self.width, self.height)

    def trigger(self):
        global score, speed_boost_timer
        if self.hit:
            return
        self.hit = True
        self.bump_timer = 8.0
        cx, cy = self.x + self.width / 2, self.y - 6

        event = random.choice(["coin", "speed", "enemy"])
        if event == "coin":
            score += 10
            play("coin")
            add_particles(cx, cy, YELLOW, count=12, spread=3, life=26, glow=True)
        elif event == "speed":
            speed_boost_timer = 300
            play("select")
            add_particles(cx, cy, ACCENT, count=16, spread=3.5, life=30, glow=True)
        else:
            ex = self.x + self.width / 2
            patrol = 90
            level["enemies"].append(make_enemy(ex, ex - patrol, ex + patrol, "patrol"))
            add_particles(cx, cy, ENEMY_COLOR, count=10, spread=3, life=24)

    def update(self):
        if self.bump_timer > 0:
            self.bump_timer -= 1

    def draw(self, surface, cam_x, t):
        sx = self.x - cam_x
        if sx < -60 or sx > SCREEN_W + 60:
            return
        bump_offset = -6 * math.sin(min(1.0, self.bump_timer / 8.0) * math.pi) if self.bump_timer > 0 else 0
        ry = self.y + bump_offset
        rect = (sx, ry, self.width, self.height)
        if self.hit:
            pygame.draw.rect(surface, (96, 70, 48), rect, border_radius=5)
            pygame.draw.rect(surface, DARK_BROWN, rect, 3, border_radius=5)
        else:
            glow = 0.5 + 0.5 * math.sin(t * 3 + self.glow_phase)
            top_color = lerp_color((255, 196, 40), (255, 230, 130), glow)
            pygame.draw.rect(surface, top_color, rect, border_radius=6)
            pygame.draw.rect(surface, (150, 90, 0), rect, 3, border_radius=6)
            q = font.render("?", True, WHITE)
            surface.blit(q, (sx + self.width / 2 - q.get_width() / 2,
                              ry + self.height / 2 - q.get_height() / 2))


# ============================================================================
#  ENEMIES  ("bugs")
# ============================================================================

def make_enemy(x, start, end, kind="patrol", speed=1.8):
    """kind: 'patrol' (walks back and forth), 'charger' (rushes the player
    when close), or 'jumper' (hops periodically)."""
    return {
        "x": float(x), "start": start, "end": end, "dir": 1, "speed": speed,
        "alive": True, "squash": 0.0, "kind": kind,
        "jump_timer": random.uniform(60, 140), "vy": 0.0, "y_offset": 0.0,
        "charge_phase": False,
    }


def update_enemy(e, player_x):
    if not e["alive"]:
        return

    if e["kind"] == "patrol":
        e["x"] += e["dir"] * e["speed"]
        if e["x"] <= e["start"] or e["x"] >= e["end"]:
            e["dir"] *= -1

    elif e["kind"] == "charger":
        close = abs(player_x - e["x"]) < 260
        e["charge_phase"] = close
        spd = e["speed"] * (2.2 if close else 1.0)
        e["dir"] = 1 if player_x > e["x"] else -1
        e["x"] += e["dir"] * spd
        e["x"] = clamp(e["x"], e["start"], e["end"])

    elif e["kind"] == "jumper":
        e["x"] += e["dir"] * e["speed"]
        if e["x"] <= e["start"] or e["x"] >= e["end"]:
            e["dir"] *= -1
        e["jump_timer"] -= 1
        if e["jump_timer"] <= 0 and e["y_offset"] == 0.0:
            e["vy"] = -9.0
            e["jump_timer"] = random.uniform(90, 160)
        if e["y_offset"] < 0 or e["vy"] != 0:
            e["vy"] += 0.5
            e["y_offset"] += e["vy"]
            if e["y_offset"] >= 0:
                e["y_offset"] = 0.0
                e["vy"] = 0.0

    if e["squash"] > 0:
        e["squash"] -= 0.05


def draw_enemy(surface, e, cam_x, t):
    if not e["alive"]:
        return
    bob = math.sin(t * 6 + e["x"] * 0.1) * 2
    squash = max(0.0, e["squash"])
    ex = int(e["x"] - cam_x)
    h = ENEMY_H - squash * 14
    y = GROUND_Y - h + bob + e.get("y_offset", 0.0)

    base_img = bug_image_right if e["dir"] >= 0 else bug_image_left
    if base_img is not None:
        h_i = max(4, int(round(h)))
        frame = base_img if h_i == ENEMY_H else pygame.transform.scale(base_img, (ENEMY_W, h_i))
        if e.get("charge_phase"):
            flash = frame.copy()
            flash.fill((255, 80, 80, 60), special_flags=pygame.BLEND_RGBA_ADD)
            surface.blit(flash, (ex, y))
        else:
            surface.blit(frame, (ex, y))
        return

    color = (220, 70, 60) if e.get("charge_phase") else ENEMY_COLOR
    pygame.draw.ellipse(surface, color, (ex, y, ENEMY_W, h))
    pygame.draw.ellipse(surface, BLACK, (ex, y, ENEMY_W, h), 2)
    eye_y = int(y + h * 0.4)
    pygame.draw.circle(surface, BLACK, (ex + 11, eye_y), 3)
    pygame.draw.circle(surface, BLACK, (ex + ENEMY_W - 11, eye_y), 3)


def get_enemy_rect(e):
    h = ENEMY_H
    y = GROUND_Y - h + e.get("y_offset", 0.0)
    return pygame.Rect(int(e["x"]), int(y), ENEMY_W, h)


# ============================================================================
#  BOSS
# ============================================================================

class Boss:
    WIDTH, HEIGHT = BOSS_W, BOSS_H
    MAX_HEALTH = 3

    def __init__(self, x, ground_y, patrol_start, patrol_end):
        self.x = float(x)
        self.y = float(ground_y - Boss.HEIGHT)
        self.start = patrol_start
        self.end = patrol_end
        self.dir = 1
        self.speed = 2.2
        self.health = Boss.MAX_HEALTH
        self.alive = True
        self.hurt_timer = 0.0
        self.invuln_timer = 0.0
        self.squash = 0.0
        self.enrage = False

    def get_rect(self):
        return pygame.Rect(int(self.x), int(self.y), Boss.WIDTH, Boss.HEIGHT)

    def update(self):
        if not self.alive:
            return
        self.enrage = self.health <= 1
        spd = self.speed * (1.6 if self.enrage else 1.0)
        self.x += self.dir * spd
        if self.x <= self.start or self.x >= self.end:
            self.dir *= -1
            self.x = clamp(self.x, self.start, self.end)
        if self.invuln_timer > 0:
            self.invuln_timer -= 1
        if self.hurt_timer > 0:
            self.hurt_timer -= 1
        if self.squash > 0:
            self.squash -= 0.05

    def take_hit(self):
        if not self.alive or self.invuln_timer > 0:
            return False
        self.health -= 1
        self.hurt_timer = 20
        self.invuln_timer = 45
        self.squash = 1.0
        if self.health <= 0:
            self.alive = False
        return True

    def draw(self, surface, cam_x, t):
        if not self.alive:
            return
        sx = self.x - cam_x
        if sx < -140 or sx > SCREEN_W + 140:
            return
        bob = math.sin(t * 4) * 3
        h = Boss.HEIGHT - self.squash * 20
        y = self.y + (Boss.HEIGHT - h) + bob

        if self.enrage:
            aura = pygame.Surface((Boss.WIDTH + 40, int(h) + 40), pygame.SRCALPHA)
            pulse = 60 + int(40 * math.sin(t * 8))
            pygame.draw.ellipse(aura, (255, 70, 70, pulse), aura.get_rect())
            surface.blit(aura, (sx - 20, y - 20))

        base_img = boss_image_right if self.dir >= 0 else boss_image_left
        if base_img is not None:
            w_i, h_i = int(round(Boss.WIDTH)), max(4, int(round(h)))
            frame = base_img if (w_i, h_i) == (Boss.WIDTH, Boss.HEIGHT) else pygame.transform.scale(base_img, (w_i, h_i))
            if self.hurt_timer > 0:
                flash = frame.copy()
                flash.fill((255, 255, 255, 100), special_flags=pygame.BLEND_RGBA_ADD)
                surface.blit(flash, (sx, y))
            else:
                surface.blit(frame, (sx, y))
        else:
            color = (255, 150, 150) if self.hurt_timer > 0 else ((235, 70, 70) if self.enrage else (200, 60, 60))
            pygame.draw.ellipse(surface, color, (sx, y, Boss.WIDTH, h))
            pygame.draw.ellipse(surface, BLACK, (sx, y, Boss.WIDTH, h), 3)
            eye_y = int(y + h * 0.35)
            for ex_off in (0.3, 0.7):
                pygame.draw.circle(surface, WHITE, (int(sx + Boss.WIDTH * ex_off), eye_y), 8)
                pygame.draw.circle(surface, BLACK, (int(sx + Boss.WIDTH * ex_off), eye_y), 4)

        bar_w = 96
        bar_x = sx + Boss.WIDTH / 2 - bar_w / 2
        bar_y = y - 24
        pygame.draw.rect(surface, (30, 30, 36), (bar_x, bar_y, bar_w, 12), border_radius=5)
        fill = bar_w * (self.health / Boss.MAX_HEALTH)
        fill_color = DANGER if self.enrage else (0, 220, 120)
        pygame.draw.rect(surface, fill_color, (bar_x, bar_y, fill, 12), border_radius=5)
        pygame.draw.rect(surface, WHITE, (bar_x, bar_y, bar_w, 12), 2, border_radius=5)


# ============================================================================
#  LEVEL GENERATION
# ============================================================================

def in_pit_range(a1, b1, pits):
    for (a, b) in pits:
        if b1 > a and a1 < b:
            return True
    return False


def generate_level(level_num):
    rng = random.Random()
    level_width = 2800 + level_num * 300
    difficulty = min(level_num, 12)

    pits = []
    x_cursor = 600
    for _ in range(2 + difficulty // 2):
        if x_cursor > level_width - 500:
            break
        gap_w = rng.randint(70, 110 + difficulty * 4)
        pits.append((x_cursor, x_cursor + gap_w))
        x_cursor += gap_w + rng.randint(300, 460)

    platforms = []
    x_cursor = 420
    py_choices = [430, 460, 490, 520]
    for _ in range(6 + difficulty):
        if x_cursor > level_width - 350:
            break
        pw = rng.randint(100, 180)
        py = rng.choice(py_choices)
        platforms.append((x_cursor, py, pw, 22))
        x_cursor += pw + rng.randint(170, 360)

    coins = []
    for (px, py, pw, ph) in platforms:
        coins.append((px + pw // 2, py - 34))
    for _ in range(4 + difficulty // 2):
        cx = rng.randint(250, level_width - 250)
        coins.append((cx, GROUND_Y - 50))

    enemies = []
    enemy_kinds = ["patrol"] * 3 + ["charger"] * min(3, difficulty // 2) + ["jumper"] * min(3, difficulty // 3)
    for _ in range(1 + difficulty):
        ex = rng.randint(600, level_width - 350)
        if any(a - 40 <= ex <= b + 40 for (a, b) in pits):
            continue
        patrol = rng.randint(70, 160)
        kind = rng.choice(enemy_kinds)
        spd = 1.6 + difficulty * 0.1
        enemies.append(make_enemy(ex, ex - patrol, ex + patrol, kind, spd))

    decor = []
    dx = 200
    while dx < level_width - 100:
        if not in_pit_range(dx, dx + 40, pits):
            decor.append((dx, rng.choice([0, 1])))
        dx += rng.randint(180, 320)

    flag_x = level_width - 150

    lucky_boxes = []
    lb_count = 2 + difficulty // 3
    x_cursor = 500
    for _ in range(lb_count):
        if x_cursor > level_width - 400:
            break
        if not in_pit_range(x_cursor - 30, x_cursor + 30, pits):
            lucky_boxes.append(LuckyBox(x_cursor, GROUND_Y - 150))
        x_cursor += rng.randint(380, 560)

    boss_x = flag_x - 260
    boss_start = max(300, boss_x - 140)
    boss_end = min(flag_x - 90, boss_x + 140)
    if in_pit_range(boss_start - 20, boss_end + 20, pits) or boss_end <= boss_start:
        boss_start = max(300, flag_x - 300)
        boss_end = flag_x - 100
    boss = Boss(boss_x, GROUND_Y, boss_start, boss_end)
    boss.speed = 1.8 + difficulty * 0.15

    return {"width": level_width, "pits": pits, "platforms": platforms,
            "coins": coins, "enemies": enemies, "flag_x": flag_x, "decor": decor,
            "lucky_boxes": lucky_boxes, "boss": boss}


# ============================================================================
#  GAME STATE
# ============================================================================

level_num = 1
level = generate_level(level_num)

start_x = 120
mario_x, mario_y = float(start_x), float(GROUND_Y - mario_h)
vel_x, vel_y = 0.0, 0.0
on_ground = False
was_on_ground = True
facing_right = True
score = 0
displayed_score = 0.0
lives = 3
speed_boost_timer = 0
walk_phase = 0.0
squash_timer = 0.0
game_state = "char_select"
win_timer = 0
pause_prev = False
damage_flash = 0.0
cloud_shapes = [(i * 37) % 40 for i in range(8)]


def reset_at_level_start():
    global mario_x, mario_y, vel_x, vel_y
    mario_x, mario_y = float(start_x), float(GROUND_Y - mario_h)
    vel_x, vel_y = 0.0, 0.0


def next_level():
    global level_num, level, game_state
    level_num += 1
    level = generate_level(level_num)
    reset_at_level_start()
    game_state = "playing"
    play("level_win")


def trigger_lose_life():
    global lives, game_state, damage_flash
    play("hurt")
    trigger_shake(9, 14)
    damage_flash = 1.0
    lives -= 1
    if lives <= 0:
        game_state = "game_over"
        play("game_over")
    else:
        reset_at_level_start()


def in_pit(x_left, x_right):
    return in_pit_range(x_left, x_right, level["pits"])


def check_high_score():
    global high_score
    if score > high_score:
        high_score = score
        save_high_score(high_score)


def get_mario_rect():
    return pygame.Rect(int(mario_x), int(mario_y), mario_w, mario_h)


# ============================================================================
#  BACKGROUND / WORLD DRAWING
# ============================================================================

def draw_sky(surface):
    for i in range(0, SCREEN_H, 3):
        t = i / SCREEN_H
        color = lerp_color(SKY_TOP, SKY_BOTTOM, t)
        pygame.draw.rect(surface, color, (0, i, SCREEN_W, 3))
    glow = pygame.Surface((200, 200), pygame.SRCALPHA)
    pygame.draw.circle(glow, (*SUN_COLOR, 90), (100, 100), 100)
    surface.blit(glow, (SCREEN_W - 250, 10))
    pygame.draw.circle(surface, SUN_COLOR, (SCREEN_W - 150, 110), 46)


def draw_mountains(surface, cam_x):
    parallax = 0.12
    spacing = 620
    offset = (cam_x * parallax) % spacing
    count = SCREEN_W // spacing + 3
    for i in range(-1, count):
        mx = i * spacing - offset
        pygame.draw.polygon(surface, MOUNTAIN_COLOR,
                             [(mx - 140, GROUND_Y), (mx + 60, GROUND_Y - 210), (mx + 260, GROUND_Y)])
        pygame.draw.polygon(surface, (255, 255, 255),
                             [(mx + 10, GROUND_Y - 170), (mx + 60, GROUND_Y - 210), (mx + 110, GROUND_Y - 170)])


def draw_cloud(surface, cx, cy, scale=1.0):
    puffs = [(0, 0, 28), (24, -10, 22), (-24, -8, 20), (42, 3, 18), (-40, 5, 17)]
    for (dx, dy, r) in puffs:
        pygame.draw.circle(surface, WHITE, (int(cx + dx * scale), int(cy + dy * scale)), int(r * scale))


def draw_clouds(surface, cam_x):
    parallax = 0.25
    spacing = 420
    offset = (cam_x * parallax) % spacing
    count = SCREEN_W // spacing + 3
    for i in range(-1, count):
        cx = i * spacing - offset
        cy = 80 + (cloud_shapes[i % len(cloud_shapes)])
        draw_cloud(surface, cx, cy, scale=0.9 + 0.3 * (i % 3))


def draw_hills(surface, cam_x):
    parallax = 0.5
    spacing = 560
    offset = (cam_x * parallax) % spacing
    count = SCREEN_W // spacing + 3
    for i in range(-1, count):
        hx = i * spacing - offset
        pygame.draw.circle(surface, HILL_FAR, (int(hx), GROUND_Y + 20), 160)
        pygame.draw.circle(surface, HILL_NEAR, (int(hx + 300), GROUND_Y + 30), 125)


def draw_decor(surface, cam_x):
    for (dx, kind) in level["decor"]:
        sx = dx - cam_x
        if -60 < sx < SCREEN_W + 60:
            if kind == 0:
                pygame.draw.circle(surface, BUSH_COLOR, (int(sx), GROUND_Y - 10), 18)
                pygame.draw.circle(surface, BUSH_COLOR, (int(sx) - 16, GROUND_Y - 4), 14)
                pygame.draw.circle(surface, BUSH_COLOR, (int(sx) + 16, GROUND_Y - 4), 14)
            else:
                pygame.draw.ellipse(surface, (130, 130, 130), (sx - 16, GROUND_Y - 14, 32, 20))


def draw_ground_segment(surface, start_x_world, end_x_world, cam_x):
    sx = start_x_world - cam_x
    ex = end_x_world - cam_x
    if ex < 0 or sx > SCREEN_W:
        return
    sx_c, ex_c = max(sx, 0), min(ex, SCREEN_W)
    if ex_c <= sx_c:
        return
    pygame.draw.rect(surface, GREEN, (sx_c, GROUND_Y, ex_c - sx_c, SCREEN_H - GROUND_Y))
    pygame.draw.rect(surface, DARK_GREEN, (sx_c, GROUND_Y, ex_c - sx_c, 10))


def draw_ground(surface, cam_x):
    boundaries = sorted(level["pits"])
    cursor = 0
    for (a, b) in boundaries:
        draw_ground_segment(surface, cursor, a, cam_x)
        cursor = b
    draw_ground_segment(surface, cursor, level["width"], cam_x)


def draw_platform(surface, px, py, pw, ph, cam_x):
    rect = (px - cam_x, py, pw, ph)
    pygame.draw.rect(surface, BROWN, rect, border_radius=4)
    pygame.draw.rect(surface, DARK_BROWN, rect, 3, border_radius=4)


def draw_coin(surface, cx, cy, cam_x, t):
    wobble = abs(math.sin(t * 4 + cx * 0.05))
    w = max(5, int(12 * wobble) + 5)
    pygame.draw.ellipse(surface, YELLOW, (int(cx - cam_x - w / 2), cy - 12, w, 24))
    pygame.draw.ellipse(surface, (200, 160, 0), (int(cx - cam_x - w / 2), cy - 12, w, 24), 2)


def draw_flag(surface, fx, cam_x, t):
    pole_x = fx - cam_x
    pygame.draw.rect(surface, WHITE, (pole_x, GROUND_Y - 220, 7, 220))
    wave = math.sin(t * 5) * 5
    pygame.draw.polygon(
        surface, (216, 40, 0),
        [(pole_x + 7, GROUND_Y - 220), (pole_x + 55 + wave, GROUND_Y - 202), (pole_x + 7, GROUND_Y - 184)]
    )


def draw_character(surface, x, y, facing_right, walk_phase, on_ground, vel_y, char, moving):
    stretch = 1.0
    if not on_ground:
        stretch = 1.12 if vel_y < 0 else 0.95
    elif squash_timer > 0:
        stretch = 1.0 - 0.25 * (squash_timer / 6)

    h = mario_h * (1 / stretch) if stretch < 1 else mario_h
    w = mario_w * stretch if stretch < 1 else mario_w
    draw_y = y + (mario_h - h)
    draw_x = x - (w - mario_w) / 2

    img_key = char.get("image")
    base_img = character_images_right.get(img_key) if facing_right else character_images_left.get(img_key)
    if base_img is not None:
        bob = math.sin(walk_phase) * 4 if (moving and on_ground) else 0
        w_i, h_i = max(4, int(round(w))), max(4, int(round(h)))
        frame = base_img if (w_i, h_i) == (mario_w, mario_h) else pygame.transform.scale(base_img, (w_i, h_i))
        surface.blit(frame, (draw_x, draw_y + bob))
        return

    c = char
    leg_offset = math.sin(walk_phase) * 8 if (moving and on_ground) else 0
    leg_w = 18
    pygame.draw.rect(surface, DARK_BROWN, (draw_x - 2, draw_y + h - 10 + max(0, leg_offset), leg_w, 10))
    pygame.draw.rect(surface, DARK_BROWN, (draw_x + w - leg_w + 2, draw_y + h - 10 + max(0, -leg_offset), leg_w, 10))
    pygame.draw.rect(surface, c["overall"], (draw_x, draw_y + 26, w, h - 36))
    pygame.draw.rect(surface, c["shirt"], (draw_x, draw_y + 13, w, 18))
    pygame.draw.rect(surface, c["skin"], (draw_x + 8, draw_y, w - 16, 20))
    pygame.draw.rect(surface, c["cap"], (draw_x + 3, draw_y - 8, w - 6, 13))
    cap_dir = 5 if facing_right else -5
    pygame.draw.rect(surface, c["cap"], (draw_x + w / 2 - 3 + cap_dir, draw_y - 3, 10, 8))
    eye_x = draw_x + w - 16 if facing_right else draw_x + 6
    pygame.draw.circle(surface, BLACK, (int(eye_x), int(draw_y + 10)), 3)
    pygame.draw.rect(surface, DARK_BROWN, (draw_x - 3, draw_y + h - 10, 20, 10))
    pygame.draw.rect(surface, DARK_BROWN, (draw_x + w - 17, draw_y + h - 10, 20, 10))


# ============================================================================
#  MENU / OVERLAY SCREENS
# ============================================================================

def draw_char_select(surface, t):
    draw_sky(surface)
    draw_mountains(surface, 0)
    draw_clouds(surface, 0)

    title_y = 60 + math.sin(t * 1.5) * 3
    draw_text_shadow(surface, "S MARIO", big_font, ACCENT,
                      SCREEN_W // 2 - big_font.size("S MARIO")[0] // 2, title_y)
    sub = mid_font.render("Choose Your Hero", True, WHITE)
    surface.blit(sub, (SCREEN_W // 2 - sub.get_width() // 2, title_y + 62))

    spacing = 240
    start_x_disp = SCREEN_W // 2 - (len(CHARACTERS) - 1) * spacing // 2
    for i, ch in enumerate(CHARACTERS):
        cx = start_x_disp + i * spacing
        cy = 380
        bob = math.sin(t * 3 + i) * 5
        is_selected = (i == selected_char)
        if is_selected:
            pulse = 0.5 + 0.5 * math.sin(t * 4)
            glow_rect = pygame.Rect(cx - 64, cy - 100, 128, 210)
            glow_surf = pygame.Surface((glow_rect.w + 20, glow_rect.h + 20), pygame.SRCALPHA)
            pygame.draw.rect(glow_surf, (*ACCENT, int(70 + 50 * pulse)), glow_surf.get_rect(), border_radius=20)
            surface.blit(glow_surf, (glow_rect.x - 10, glow_rect.y - 10))
            pygame.draw.rect(surface, (255, 255, 255, 230), glow_rect, 3, border_radius=18)
        draw_character(surface, cx - mario_w // 2, cy - 30 + bob, True, t * 4, True, 0, ch, True)
        name_text = font.render(ch["name"], True, WHITE if is_selected else (200, 200, 210))
        surface.blit(name_text, (cx - name_text.get_width() // 2, cy + 90))

    hint = small_font.render("<-/-> choose   |   Space/Jump confirm   |   +/- volume   M mute   F11 fullscreen",
                              True, WHITE)
    draw_panel(surface, SCREEN_W // 2 - hint.get_width() // 2 - 14, SCREEN_H - 62, hint.get_width() + 28, 36, alpha=140)
    surface.blit(hint, (SCREEN_W // 2 - hint.get_width() // 2, SCREEN_H - 54))

    hs_text = font.render(f"High Score: {high_score}", True, YELLOW)
    draw_panel(surface, 20, 20, hs_text.get_width() + 24, 44, alpha=150)
    surface.blit(hs_text, (32, 30))

    draw_volume_hud(surface)
    input_manager.draw(surface)


def draw_fullscreen_overlay(surface, alpha=170):
    panel = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
    panel.fill((6, 6, 14, alpha))
    surface.blit(panel, (0, 0))


def draw_pause_menu(surface):
    draw_fullscreen_overlay(surface, alpha=190)
    draw_text_shadow(surface, "PAUSED", big_font, WHITE,
                      SCREEN_W // 2 - big_font.size("PAUSED")[0] // 2, SCREEN_H // 2 - 110)
    lines = ["Esc / Start - Resume", "R - Restart Run", "M - Mute", "F11 - Fullscreen"]
    for i, line in enumerate(lines):
        t_surf = font.render(line, True, (220, 220, 230))
        surface.blit(t_surf, (SCREEN_W // 2 - t_surf.get_width() // 2, SCREEN_H // 2 - 20 + i * 38))


# ============================================================================
#  MAIN LOOP
# ============================================================================

def main():
    global mario_x, mario_y, vel_x, vel_y, on_ground, was_on_ground, facing_right
    global score, displayed_score, lives, speed_boost_timer, walk_phase, squash_timer
    global game_state, win_timer, selected_char, volume_hud_timer, level_num, level
    global shake_timer, shake_strength, pause_prev, damage_flash, fullscreen, window

    running = True
    jump_held_last_frame = False
    select_move_cooldown = 0
    t = 0.0
    prev_game_state = None

    while running:
        dt = clock.tick(60) / 1000.0
        t += dt

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            if event.type == pygame.VIDEORESIZE and not fullscreen:
                window = pygame.display.set_mode((event.w, event.h), pygame.RESIZABLE)
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_r and game_state in ("game_over", "paused"):
                    level_num = 1
                    level = generate_level(level_num)
                    score = 0
                    displayed_score = 0.0
                    lives = 3
                    reset_at_level_start()
                    game_state = "char_select"
                if event.key in (pygame.K_EQUALS, pygame.K_PLUS, pygame.K_KP_PLUS):
                    change_volume(0.1)
                if event.key in (pygame.K_MINUS, pygame.K_KP_MINUS):
                    change_volume(-0.1)
                if event.key == pygame.K_m:
                    toggle_mute()
                if event.key == pygame.K_F11:
                    toggle_fullscreen()
            input_manager.handle_event(event)

        move, jump_now, pause_now = input_manager.read()

        # ---- pause toggle (edge-triggered) ----
        if pause_now and not pause_prev and game_state in ("playing", "paused"):
            game_state = "paused" if game_state == "playing" else "playing"
        pause_prev = pause_now

        # ---- character select ----
        if game_state == "char_select":
            if select_move_cooldown > 0:
                select_move_cooldown -= 1
            else:
                if move < 0:
                    selected_char = (selected_char - 1) % len(CHARACTERS)
                    play("select")
                    select_move_cooldown = 12
                elif move > 0:
                    selected_char = (selected_char + 1) % len(CHARACTERS)
                    play("select")
                    select_move_cooldown = 12
            if jump_now:
                game_state = "playing"
                play("select")

            draw_char_select(screen, t)
            if volume_hud_timer > 0:
                volume_hud_timer -= 1
            present()
            continue

        # ---- paused ----
        if game_state == "paused":
            draw_pause_menu(screen)
            present()
            continue

        # ---- gameplay ----
        if game_state == "playing":
            current_speed = SPEED * 1.6 if speed_boost_timer > 0 else SPEED
            vel_x = move * current_speed
            moving = move != 0
            if move > 0:
                facing_right = True
            elif move < 0:
                facing_right = False

            walk_phase += 0.35 if (moving and on_ground) else 0.0

            was_on_ground = on_ground

            if jump_now and not jump_held_last_frame and on_ground:
                vel_y = JUMP_STRENGTH
                on_ground = False
                play("jump")
                add_particles(mario_x + mario_w / 2, GROUND_Y, (255, 255, 255, ), count=6, spread=1.5, life=14)
            jump_held_last_frame = jump_now

            vel_y += GRAVITY
            vel_y = min(vel_y, 22)

            mario_x += vel_x
            mario_x = clamp(mario_x, 0, level["width"] - mario_w)

            prev_vel_y = vel_y
            mario_y += vel_y
            on_ground = False

            if mario_y + mario_h >= GROUND_Y:
                if in_pit(mario_x, mario_x + mario_w):
                    if mario_y > SCREEN_H + 150:
                        trigger_lose_life()
                else:
                    mario_y = GROUND_Y - mario_h
                    vel_y = 0
                    on_ground = True

            mario_rect = get_mario_rect()
            for (px, py, pw, ph) in level["platforms"]:
                plat_rect = pygame.Rect(px, py, pw, ph)
                if mario_rect.colliderect(plat_rect) and vel_y >= 0:
                    if mario_rect.bottom - vel_y <= plat_rect.top + 1:
                        mario_y = plat_rect.top - mario_h
                        vel_y = 0
                        on_ground = True

            mario_rect = get_mario_rect()
            for box in level["lucky_boxes"]:
                box.update()
                box_rect = box.get_rect()
                if mario_rect.colliderect(box_rect):
                    if vel_y < 0 and mario_rect.top - vel_y >= box_rect.bottom - 4:
                        if not box.hit:
                            box.trigger()
                        vel_y = 2
                        mario_y = box_rect.bottom
                    elif vel_y >= 0 and mario_rect.bottom - vel_y <= box_rect.top + 1:
                        mario_y = box_rect.top - mario_h
                        vel_y = 0
                        on_ground = True

            if on_ground and not was_on_ground and prev_vel_y > 9:
                squash_timer = 6
                add_particles(mario_x + mario_w / 2, GROUND_Y, (200, 200, 200), count=8, spread=2.5, life=16)
            if squash_timer > 0:
                squash_timer -= 1

            mario_rect = get_mario_rect()
            remaining = []
            for (cx, cy) in level["coins"]:
                coin_rect = pygame.Rect(cx - 12, cy - 12, 24, 24)
                if mario_rect.colliderect(coin_rect):
                    score += 10
                    play("coin")
                    add_particles(cx, cy, YELLOW, count=8, spread=2.5, life=20, glow=True)
                else:
                    remaining.append((cx, cy))
            level["coins"] = remaining

            mario_rect = get_mario_rect()
            for e in level["enemies"]:
                update_enemy(e, mario_x)
                if not e["alive"]:
                    continue
                enemy_rect = get_enemy_rect(e)
                if mario_rect.colliderect(enemy_rect):
                    if vel_y > 0 and mario_rect.bottom - vel_y <= enemy_rect.top + 6:
                        e["alive"] = False
                        e["squash"] = 1.0
                        vel_y = JUMP_STRENGTH / 1.6
                        score += 50
                        play("stomp")
                        add_particles(e["x"] + ENEMY_W / 2, GROUND_Y - 10, ENEMY_COLOR, count=10, spread=3, life=22)
                    else:
                        trigger_lose_life()

            boss = level["boss"]
            if boss is not None:
                boss.update()
                if boss.alive:
                    mario_rect = get_mario_rect()
                    boss_rect = boss.get_rect()
                    if mario_rect.colliderect(boss_rect):
                        if vel_y > 0 and mario_rect.bottom - vel_y <= boss_rect.top + 10 and boss.invuln_timer <= 0:
                            boss.take_hit()
                            vel_y = JUMP_STRENGTH / 1.4
                            score += 100
                            play("stomp")
                            trigger_shake(5, 8)
                            add_particles(boss.x + Boss.WIDTH / 2, boss.y + 10, (220, 60, 60),
                                          count=14, spread=3.5, life=26)
                            if not boss.alive:
                                score += 300
                                add_particles(boss.x + Boss.WIDTH / 2, boss.y + 20, YELLOW,
                                              count=26, spread=5, life=40, glow=True)
                                trigger_shake(10, 16)
                        elif boss.invuln_timer <= 0:
                            trigger_lose_life()

            boss_cleared = (level["boss"] is None) or (not level["boss"].alive)
            if boss_cleared and mario_x + mario_w >= level["flag_x"]:
                game_state = "won_level"
                win_timer = pygame.time.get_ticks()

        elif game_state == "won_level":
            if pygame.time.get_ticks() - win_timer > 1200:
                next_level()

        update_particles()
        check_high_score()
        if shake_timer > 0:
            shake_timer -= 1
        if volume_hud_timer > 0:
            volume_hud_timer -= 1
        if speed_boost_timer > 0:
            speed_boost_timer -= 1
        if damage_flash > 0:
            damage_flash = max(0.0, damage_flash - 0.06)
        displayed_score = lerp(displayed_score, score, 0.15)

        cam_x = camera.update(mario_x, level["width"])
        shake_x = random.uniform(-shake_strength, shake_strength) if shake_timer > 0 else 0
        shake_y = random.uniform(-shake_strength, shake_strength) if shake_timer > 0 else 0
        cam_draw = cam_x - shake_x

        draw_sky(screen)
        draw_mountains(screen, cam_draw)
        draw_clouds(screen, cam_draw)
        draw_hills(screen, cam_draw)
        draw_ground(screen, cam_draw)
        draw_decor(screen, cam_draw)

        for (px, py, pw, ph) in level["platforms"]:
            draw_platform(screen, px, py, pw, ph, cam_draw)
        for box in level["lucky_boxes"]:
            box.draw(screen, cam_draw, t)
        for (cx, cy) in level["coins"]:
            draw_coin(screen, cx, cy, cam_draw, t)
        for e in level["enemies"]:
            draw_enemy(screen, e, cam_draw, t)
        if level["boss"] is not None:
            level["boss"].draw(screen, cam_draw, t)
        draw_flag(screen, level["flag_x"], cam_draw, t)
        draw_particles(screen, cam_draw)

        moving_now = (move != 0) and game_state == "playing"
        draw_character(screen, mario_x - cam_draw, mario_y + shake_y, facing_right, walk_phase,
                        on_ground, vel_y, CHARACTERS[selected_char], moving_now)

        # ---- HUD ----
        panel_w = 260
        draw_panel(screen, 14, 14, panel_w, 96, alpha=150)
        draw_text_shadow(screen, f"Score {int(displayed_score)}", font, WHITE, 28, 22)
        draw_hearts(screen, 30, 66, lives)
        draw_text_shadow(screen, f"Lvl {level_num}", small_font, ACCENT, 150, 68)
        hs_surf = small_font.render(f"Best {high_score}", True, YELLOW)
        screen.blit(hs_surf, (28, 90))

        if speed_boost_timer > 0:
            boost_txt = small_font.render("SPEED BOOST", True, ACCENT)
            draw_panel(screen, 14, 118, boost_txt.get_width() + 24, 32, alpha=140)
            screen.blit(boost_txt, (26, 124))

        hint_text = ("Touch: bottom-left move, bottom-right jump" if input_manager.touch_active
                     else "WASD/Arrows + Space jump | Esc pause | F11 fullscreen")
        if input_manager.joystick is not None:
            hint_text = f"Controller: {input_manager.joystick.get_name()}"
        hint = small_font.render(hint_text, True, WHITE)
        draw_panel(screen, 14, SCREEN_H - 50, hint.get_width() + 24, 40, alpha=140)
        screen.blit(hint, (26, SCREEN_H - 40))

        draw_volume_hud(screen)
        input_manager.draw(screen)

        if damage_flash > 0:
            flash = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
            flash.fill((*DANGER, int(90 * damage_flash)))
            screen.blit(flash, (0, 0))

        if game_state == "won_level":
            draw_fullscreen_overlay(screen, alpha=150)
            msg = big_font.render(f"Level {level_num} Complete!", True, YELLOW)
            screen.blit(msg, (SCREEN_W // 2 - msg.get_width() // 2, SCREEN_H // 2 - 30))

        if game_state == "game_over":
            draw_fullscreen_overlay(screen, alpha=190)
            msg = big_font.render("GAME OVER", True, DANGER)
            sub = font.render("Press R to restart", True, WHITE)
            hs_msg = font.render(f"High Score: {high_score}", True, YELLOW)
            screen.blit(msg, (SCREEN_W // 2 - msg.get_width() // 2, SCREEN_H // 2 - 60))
            screen.blit(hs_msg, (SCREEN_W // 2 - hs_msg.get_width() // 2, SCREEN_H // 2 - 5))
            screen.blit(sub, (SCREEN_W // 2 - sub.get_width() // 2, SCREEN_H // 2 + 35))

        present()

    pygame.quit()


if __name__ == "__main__":
    main()