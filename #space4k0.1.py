"""AC's Space Invaders v0.1 — single-file pygame (files=off). Famicom @ 60 FPS. P/R.

Main menu • Play / Exit. ESC or P → main menu. R reset wave.
Procedural beep-n-boop SFX — no external files.
"""
import array
import math
import random

import pygame

# ---------------- CONFIG ----------------
WIDTH, HEIGHT = 640, 480
FPS = 60
SAMPLE_RATE = 22050

# Famicom / arcade palette
FC_BG = (0, 0, 0)
FC_GREEN = (0, 200, 0)
FC_YELLOW = (220, 220, 0)
FC_CYAN = (0, 220, 220)
FC_RED = (220, 40, 40)
FC_WHITE = (240, 240, 240)
FC_MAGENTA = (220, 0, 180)

PLAY_TOP = 48
GROUND_Y = HEIGHT - 56
BUNKER_Y = GROUND_Y - 44
ALIEN_ROWS = 5
ALIEN_COLS = 11
ALIEN_W, ALIEN_H = 24, 20
ALIEN_GAP_X, ALIEN_GAP_Y = 14, 14
FORMATION_TOP = 72

PLAYER_W, PLAYER_H = 26, 14
BULLET_W, BULLET_H = 3, 10
UFO_W, UFO_H = 32, 14
BUNKER_CELL = 4

MENU_OPTIONS = ("PLAY GAME", "EXIT GAME")

# Famicom step cadence — frames between formation moves (55 aliens → 1)
def _invader_delay(alive: int) -> int:
    alive = max(1, alive)
    return max(6, int(44 * alive / 55) + 4)

# March tones cycle (classic 4-note descending beeps)
_MARCH_HZ = (880.0, 660.0, 550.0, 440.0)


# ---------------- SFX (beep n boop, files=off) ----------------
class Sfx:
    def __init__(self) -> None:
        self.enabled = True

    @staticmethod
    def _square(freq: float, t: float, duty: float = 0.5) -> float:
        if freq <= 0:
            return 0.0
        return 1.0 if (freq * t) % 1.0 < duty else -1.0

    def _tone(self, freq: float, duration: float, duty: float = 0.5, vol: float = 0.35) -> pygame.mixer.Sound:
        n = max(1, int(SAMPLE_RATE * duration))
        mono = array.array("h")
        for i in range(n):
            t = i / SAMPLE_RATE
            env = min(1.0, min(t * 200, (duration - t) * 120))
            s = self._square(freq, t, duty) * env * vol
            mono.append(int(max(-32767, min(32767, s * 32767))))
        stereo = array.array("h")
        for s in mono:
            stereo.append(s)
            stereo.append(s)
        return pygame.mixer.Sound(buffer=stereo)

    def _play(self, snd: pygame.mixer.Sound) -> None:
        if self.enabled:
            try:
                snd.play()
            except Exception:
                pass

    def build(self) -> None:
        self.shoot = self._tone(990.0, 0.08, 0.25, 0.3)
        self.alien_shoot = self._tone(220.0, 0.12, 0.5, 0.28)
        self.hit = self._tone(140.0, 0.15, 0.5, 0.35)
        self.ufo = self._tone(520.0, 0.35, 0.35, 0.22)
        self.ufo_hit = self._tone(1200.0, 0.2, 0.25, 0.3)
        self.death = self._tone(180.0, 0.55, 0.5, 0.32)
        self.march = [self._tone(h, 0.05, 0.5, 0.22) for h in _MARCH_HZ]
        self.wave_clear = self._tone(660.0, 0.4, 0.4, 0.3)

    def player_shoot(self) -> None:
        self._play(self.shoot)

    def alien_fire(self) -> None:
        self._play(self.alien_shoot)

    def invader_hit(self) -> None:
        self._play(self.hit)

    def ufo_spawn(self) -> None:
        self._play(self.ufo)

    def ufo_destroyed(self) -> None:
        self._play(self.ufo_hit)

    def player_die(self) -> None:
        self._play(self.death)

    def step(self, idx: int) -> None:
        self._play(self.march[idx % 4])

    def cleared(self) -> None:
        self._play(self.wave_clear)


# ---------------- SPRITES (procedural pixels) ----------------
def _blit_pixels(surface, ox: int, oy: int, pattern: str, color, px: int = 2) -> None:
    for y, row in enumerate(pattern):
        for x, ch in enumerate(row):
            if ch == "#":
                pygame.draw.rect(surface, color, (ox + x * px, oy + y * px, px, px))


ALIEN_SPRITES = (
    (  # row 0 — squid (30 pts)
        ("..#...#..", ".#######.", "#.#.#.#.#", "#########", ".#.#.#.#.", ".#.....#."),
        ("..#...#..", ".#######.", "#.#.#.#.#", "#########", "..#...#..", ".##...##."),
    ),
    (  # row 1-2 — crab (20 pts)
        (".#.....#.", "#...#...#", "#.#####.#", "##.#.#.##", "###...###", ".#.....#."),
        ("..#...#..", "#..#.#..#", "#.#####.#", ".##.#.##.", "###...###", ".#.....#."),
    ),
    (  # row 3-4 — octopus (10 pts)
        ("...#.#...", "..#####..", ".#.#.#.#.", ".#######.", ".#.....#.", "..#...#.."),
        ("...#.#...", "..#####..", ".#.#.#.#.", "..#####..", ".#.....#.", "..#...#.."),
    ),
)

PLAYER_SPRITE = (
    "....#####....",
    "...#######...",
    "..#########..",
    ".###########.",
    "#############",
)

UFO_SPRITE = (
    "...#######...",
    "..#########..",
    ".###########.",
    "#############",
    "..#########..",
    "...#######...",
)


def alien_color(row: int) -> tuple[int, int, int]:
    if row == 0:
        return FC_MAGENTA
    if row < 3:
        return FC_CYAN
    return FC_YELLOW


def alien_points(row: int) -> int:
    if row == 0:
        return 30
    if row < 3:
        return 20
    return 10


def draw_alien(surface, x: int, y: int, row: int, frame: int) -> None:
    tier = 0 if row == 0 else (1 if row < 3 else 2)
    pat = ALIEN_SPRITES[tier][frame % 2]
    _blit_pixels(surface, x, y, pat, alien_color(row))


def draw_player(surface, x: int, y: int) -> None:
    _blit_pixels(surface, x, y, PLAYER_SPRITE, FC_GREEN, 2)


def draw_ufo(surface, x: int, y: int) -> None:
    _blit_pixels(surface, x, y, UFO_SPRITE, FC_RED, 2)


def make_bunker() -> list[list[bool]]:
    w, h = 22, 14
    grid = [[False] * w for _ in range(h)]
    for y in range(h):
        for x in range(w):
            if y < 8:
                if 4 <= x < w - 4:
                    grid[y][x] = True
            elif y < 11:
                if 2 <= x < w - 2:
                    grid[y][x] = True
            else:
                grid[y][x] = True
    for y in range(10, h):
        for x in range(0, 6):
            if (x + y) % 3 == 0:
                grid[y][x] = False
        for x in range(w - 6, w):
            if (x + y) % 3 == 0:
                grid[y][x] = False
    return grid


def draw_bunker(surface, ox: int, oy: int, grid: list[list[bool]]) -> None:
    for y, row in enumerate(grid):
        for x, alive in enumerate(row):
            if alive:
                pygame.draw.rect(surface, FC_GREEN, (ox + x * BUNKER_CELL, oy + y * BUNKER_CELL, BUNKER_CELL, BUNKER_CELL))


def bunker_hit(bunkers: list, bx: int, by: int, ox: int, oy: int) -> bool:
    gx = (bx - ox) // BUNKER_CELL
    gy = (by - oy) // BUNKER_CELL
    if 0 <= gy < len(bunkers) and 0 <= gx < len(bunkers[0]):
        if bunkers[gy][gx]:
            for dy in range(-1, 2):
                for dx in range(-1, 2):
                    yy, xx = gy + dy, gx + dx
                    if 0 <= yy < len(bunkers) and 0 <= xx < len(bunkers[0]):
                        bunkers[yy][xx] = False
            return True
    return False


# ---------------- MENU ----------------
def draw_menu_logo(surface) -> None:
    surface.fill(FC_BG)
    title_font = pygame.font.SysFont("consolas", 36, bold=True)
    sub_font = pygame.font.SysFont("consolas", 18, bold=True)
    tag_font = pygame.font.SysFont("consolas", 15)

    # Mini invader logo
    draw_alien(surface, WIDTH // 2 - 40, 36, 0, 0)
    draw_alien(surface, WIDTH // 2 + 10, 36, 2, 1)
    draw_player(surface, WIDTH // 2 - 13, 70)

    title = title_font.render("AC'S SPACE INVADERS", True, FC_GREEN)
    surface.blit(title, (WIDTH // 2 - title.get_width() // 2, 100))
    take = sub_font.render("MY TAKE v0.1 • FAMICOM SPEED", True, FC_CYAN)
    surface.blit(take, (WIDTH // 2 - take.get_width() // 2, 142))
    tag = tag_font.render("FILES=OFF • BEEP N BOOP SFX • 60 FPS", True, FC_YELLOW)
    surface.blit(tag, (WIDTH // 2 - tag.get_width() // 2, 168))


def draw_main_menu(surface, selected: int) -> None:
    draw_menu_logo(surface)
    font = pygame.font.SysFont("consolas", 24, bold=True)
    for i, opt in enumerate(MENU_OPTIONS):
        color = FC_WHITE if i == selected else FC_GREEN
        prefix = "> " if i == selected else "  "
        text = font.render(prefix + opt, True, color)
        surface.blit(text, (WIDTH // 2 - text.get_width() // 2, 220 + i * 40))
    hint = pygame.font.SysFont("consolas", 16).render("↑↓ SELECT   ENTER   P/R IN GAME", True, FC_CYAN)
    surface.blit(hint, (WIDTH // 2 - hint.get_width() // 2, HEIGHT - 32))


# ---------------- GAME STATE ----------------
class Invader:
    __slots__ = ("col", "row", "alive")

    def __init__(self, col: int, row: int) -> None:
        self.col = col
        self.row = row
        self.alive = True


def formation_origin(cols_alive: int) -> tuple[int, int]:
    fw = ALIEN_COLS * (ALIEN_W + ALIEN_GAP_X)
    return (WIDTH // 2 - fw // 2, FORMATION_TOP)


def reset_wave() -> dict:
    invaders = [Invader(c, r) for r in range(ALIEN_ROWS) for c in range(ALIEN_COLS)]
    bunkers = [make_bunker() for _ in range(4)]
    bx = [80, 200, 360, 480]
    return {
        "invaders": invaders,
        "dir": 1,
        "form_x": 0,
        "form_y": 0,
        "step_timer": 0,
        "march_idx": 0,
        "anim": 0,
        "player_x": WIDTH // 2 - PLAYER_W // 2,
        "player_bullet": None,
        "alien_bullets": [],
        "ufo": None,
        "ufo_timer": random.randint(400, 900),
        "bunkers": bunkers,
        "bunker_x": bx,
        "score": 0,
        "lives": 3,
        "alive_count": ALIEN_ROWS * ALIEN_COLS,
        "over": False,
        "win_flash": 0,
    }


def alive_invaders(invaders: list[Invader]) -> list[Invader]:
    return [i for i in invaders if i.alive]


def lowest_row_per_col(invaders: list[Invader]) -> dict[int, int]:
    low: dict[int, int] = {}
    for inv in invaders:
        if inv.alive:
            low[inv.col] = max(low.get(inv.col, -1), inv.row)
    return low


def draw_playfield(surface, state: dict) -> None:
    surface.fill(FC_BG)
    pygame.draw.line(surface, FC_GREEN, (0, GROUND_Y + 20), (WIDTH, GROUND_Y + 20), 1)

    ox, oy = formation_origin(ALIEN_COLS)
    fx, fy = ox + state["form_x"], oy + state["form_y"]
    for inv in state["invaders"]:
        if inv.alive:
            ax = fx + inv.col * (ALIEN_W + ALIEN_GAP_X)
            ay = fy + inv.row * (ALIEN_H + ALIEN_GAP_Y)
            draw_alien(surface, ax, ay, inv.row, state["anim"])

    for i, grid in enumerate(state["bunkers"]):
        draw_bunker(surface, state["bunker_x"][i], BUNKER_Y, grid)

    if state["ufo"] is not None:
        draw_ufo(surface, int(state["ufo"][0]), int(state["ufo"][1]))

    draw_player(surface, int(state["player_x"]), GROUND_Y)

    if state["player_bullet"]:
        bx, by = state["player_bullet"]
        pygame.draw.rect(surface, FC_WHITE, (bx, by, BULLET_W, BULLET_H))

    for bx, by in state["alien_bullets"]:
        pygame.draw.rect(surface, FC_YELLOW, (bx, by, BULLET_W, BULLET_H))

    font = pygame.font.SysFont("consolas", 20, bold=True)
    surface.blit(font.render(f"SCORE {state['score']:05d}", True, FC_WHITE), (16, 12))
    surface.blit(font.render(f"LIVES {state['lives']}", True, FC_GREEN), (WIDTH - 120, 12))


def move_formation(state: dict, sfx: Sfx) -> None:
    invs = alive_invaders(state["invaders"])
    if not invs:
        return

    ox, oy = formation_origin(ALIEN_COLS)
    fx = state["form_x"]
    fw = ALIEN_COLS * (ALIEN_W + ALIEN_GAP_X)
    edge = False
    if fx + fw >= WIDTH - 40 and state["dir"] > 0:
        edge = True
    if fx <= 20 and state["dir"] < 0:
        edge = True

    if edge:
        state["dir"] *= -1
        state["form_y"] += ALIEN_H // 2
    else:
        state["form_x"] += 8 * state["dir"]

    state["anim"] ^= 1
    state["march_idx"] = (state["march_idx"] + 1) % 4
    sfx.step(state["march_idx"])

    # invasion line
    fy = oy + state["form_y"]
    for inv in invs:
        if fy + inv.row * (ALIEN_H + ALIEN_GAP_Y) + ALIEN_H >= GROUND_Y:
            state["over"] = True


def try_alien_shot(state: dict, sfx: Sfx) -> None:
    if len(state["alien_bullets"]) >= 3:
        return
    if random.random() > 0.02:
        return
    invs = alive_invaders(state["invaders"])
    if not invs:
        return
    low = lowest_row_per_col(invs)
    col = random.choice(list(low.keys()))
    row = low[col]
    ox, oy = formation_origin(ALIEN_COLS)
    fx, fy = ox + state["form_x"], oy + state["form_y"]
    ax = fx + col * (ALIEN_W + ALIEN_GAP_X) + ALIEN_W // 2
    ay = fy + row * (ALIEN_H + ALIEN_GAP_Y) + ALIEN_H
    state["alien_bullets"].append([ax, ay])
    sfx.alien_fire()


def spawn_ufo(state: dict, sfx: Sfx) -> None:
    side = random.choice([-1, 1])
    x = -UFO_W if side < 0 else WIDTH + UFO_W
    state["ufo"] = [float(x), 36.0, float(2.5 * side)]
    sfx.ufo_spawn()


def update_ufo(state: dict, sfx: Sfx) -> None:
    if state["ufo"] is None:
        state["ufo_timer"] -= 1
        if state["ufo_timer"] <= 0:
            spawn_ufo(state, sfx)
            state["ufo_timer"] = random.randint(500, 1200)
        return
    state["ufo"][0] += state["ufo"][2]
    if state["ufo"][0] < -UFO_W - 20 or state["ufo"][0] > WIDTH + UFO_W + 20:
        state["ufo"] = None


def collide_bullets(state: dict, sfx: Sfx) -> None:
    ox, oy = formation_origin(ALIEN_COLS)
    fx, fy = ox + state["form_x"], oy + state["form_y"]

    # player bullet
    if state["player_bullet"]:
        bx, by = state["player_bullet"]
        by -= 6
        state["player_bullet"][1] = by
        if by < PLAY_TOP:
            state["player_bullet"] = None
        else:
            hit = False
            if state["ufo"] and bx < state["ufo"][0] + UFO_W and bx + BULLET_W > state["ufo"][0] and by < 60:
                state["score"] += random.choice((50, 100, 150))
                state["ufo"] = None
                sfx.ufo_destroyed()
                state["player_bullet"] = None
                hit = True
            if not hit:
                for inv in state["invaders"]:
                    if not inv.alive:
                        continue
                    ax = fx + inv.col * (ALIEN_W + ALIEN_GAP_X)
                    ay = fy + inv.row * (ALIEN_H + ALIEN_GAP_Y)
                    if ax <= bx <= ax + ALIEN_W and ay <= by <= ay + ALIEN_H:
                        inv.alive = False
                        state["score"] += alien_points(inv.row)
                        state["alive_count"] -= 1
                        sfx.invader_hit()
                        state["player_bullet"] = None
                        hit = True
                        break
            if not hit:
                for i, grid in enumerate(state["bunkers"]):
                    if bunker_hit(grid, bx, by, state["bunker_x"][i], BUNKER_Y):
                        state["player_bullet"] = None
                        break

    # alien bullets
    px = state["player_x"]
    new_bullets = []
    for ab in state["alien_bullets"]:
        ab[1] += 4
        bx, by = ab
        if by > HEIGHT:
            continue
        hit = False
        if px <= bx <= px + PLAYER_W and GROUND_Y <= by <= GROUND_Y + PLAYER_H:
            state["lives"] -= 1
            sfx.player_die()
            state["alien_bullets"] = []
            if state["lives"] <= 0:
                state["over"] = True
            hit = True
        if not hit:
            for i, grid in enumerate(state["bunkers"]):
                if bunker_hit(grid, bx, by, state["bunker_x"][i], BUNKER_Y):
                    hit = True
                    break
        if not hit:
            new_bullets.append(ab)
    state["alien_bullets"] = new_bullets


def update_play(state: dict, keys, sfx: Sfx) -> None:
    if state["over"]:
        return

    if keys[pygame.K_LEFT]:
        state["player_x"] = max(10, state["player_x"] - 5)
    if keys[pygame.K_RIGHT]:
        state["player_x"] = min(WIDTH - PLAYER_W - 10, state["player_x"] + 5)

    alive = state["alive_count"]
    if alive > 0:
        state["step_timer"] += 1
        if state["step_timer"] >= _invader_delay(alive):
            state["step_timer"] = 0
            move_formation(state, sfx)
        try_alien_shot(state, sfx)

    update_ufo(state, sfx)
    collide_bullets(state, sfx)

    if alive == 0:
        state["win_flash"] += 1
        if state["win_flash"] == 1:
            sfx.cleared()
        if state["win_flash"] > 90:
            fresh = reset_wave()
            fresh["score"] = state["score"]
            fresh["lives"] = state["lives"]
            state.clear()
            state.update(fresh)


def draw_game_over(surface, state: dict) -> None:
    font = pygame.font.SysFont("consolas", 32, bold=True)
    msg = "GAME OVER" if state["lives"] <= 0 else "INVADERS LANDED"
    text = font.render(msg, True, FC_RED)
    surface.blit(text, (WIDTH // 2 - text.get_width() // 2, HEIGHT // 2 - 20))
    sub = pygame.font.SysFont("consolas", 18).render("ESC / P → MAIN MENU   R → RETRY", True, FC_WHITE)
    surface.blit(sub, (WIDTH // 2 - sub.get_width() // 2, HEIGHT // 2 + 24))


# ---------------- MAIN ----------------
def main() -> None:
    pygame.init()
    pygame.mixer.init(frequency=SAMPLE_RATE, size=-16, channels=2, buffer=512)
    win = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("AC's Space Invaders v0.1 — files=off")
    clock = pygame.time.Clock()
    sfx = Sfx()
    sfx.build()

    screen = "menu"
    selected = 0
    state = reset_wave()
    running = True

    while running:
        clock.tick(FPS)

        if screen == "menu":
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                if event.type == pygame.KEYDOWN:
                    if event.key in (pygame.K_UP, pygame.K_w):
                        selected = (selected - 1) % len(MENU_OPTIONS)
                    if event.key in (pygame.K_DOWN, pygame.K_s):
                        selected = (selected + 1) % len(MENU_OPTIONS)
                    if event.key in (pygame.K_RETURN, pygame.K_SPACE):
                        if selected == 0:
                            state = reset_wave()
                            screen = "play"
                        else:
                            running = False
                    if event.key == pygame.K_p:
                        state = reset_wave()
                        screen = "play"
            draw_main_menu(win, selected)
            pygame.display.flip()
            continue

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            if event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_ESCAPE, pygame.K_p):
                    screen = "menu"
                if event.key == pygame.K_r:
                    state = reset_wave()
                if event.key == pygame.K_SPACE and not state["over"] and state["player_bullet"] is None:
                    bx = state["player_x"] + PLAYER_W // 2 - BULLET_W // 2
                    state["player_bullet"] = [bx, GROUND_Y - BULLET_H]
                    sfx.player_shoot()

        keys = pygame.key.get_pressed()
        if not state["over"]:
            update_play(state, keys, sfx)

        draw_playfield(win, state)
        if state["over"]:
            draw_game_over(win, state)
        pygame.display.flip()

    pygame.quit()


if __name__ == "__main__":
    main()
