import math
import random
import sys
import threading
import time

try:
    import serial
    import serial.tools.list_ports
    HAS_SERIAL = True
except ImportError:
    HAS_SERIAL = False

import pygame

# ---------------------------------------------------------------- Bo dieu khien ESP32 qua Serial (USB)
class ESP32Controller:
    def __init__(self, baud=115200):
        self.baud = baud
        self.dx = 0
        self.dy = 0
        self.bomb_pressed = False
        self.connected = False
        self.current_port = None
        self.running = True
        self.thread = threading.Thread(target=self._worker, daemon=True)
        self.thread.start()

    def _find_port(self):
        if not HAS_SERIAL:
            return None
        ports = [p.device for p in serial.tools.list_ports.comports()]
        if "COM3" in ports:
            return "COM3"
        return ports[0] if ports else None

    def _worker(self):
        buffer = ""
        while self.running:
            if not self.connected:
                p = self._find_port()
                if p:
                    try:
                        ser = serial.Serial(p, self.baud, timeout=0.05)
                        self.current_port = p
                        self.connected = True
                        buffer = ""
                        print(f"[ESP32] Da ket noi tay cam tai {p}!")
                        while self.running and self.connected:
                            waiting = ser.in_waiting
                            if waiting > 0:
                                chunk = ser.read(waiting).decode('utf-8', errors='ignore')
                                buffer += chunk
                                if '\n' in buffer:
                                    lines = buffer.split('\n')
                                    buffer = lines[-1]
                                    for line in reversed(lines[:-1]):
                                        parts = line.strip().split(',')
                                        if len(parts) >= 3:
                                            try:
                                                self.dx = int(parts[0])
                                                self.dy = int(parts[1])
                                                self.bomb_pressed = (int(parts[2]) == 1)
                                                break
                                            except ValueError:
                                                pass
                            time.sleep(0.005)
                    except Exception:
                        self.connected = False
                        self.current_port = None
                        buffer = ""
                        time.sleep(1.0)
                else:
                    time.sleep(1.0)
            time.sleep(0.01)

    def get_dir(self):
        if self.dx != 0:
            return (self.dx, 0)
        if self.dy != 0:
            return (0, self.dy)
        return (0, 0)

esp32_ctrl = ESP32Controller()

pygame.init()
 
# ---------------------------------------------------------------- Cau hinh
TILE = 48
COLS, ROWS = 15, 13
HUD = 56
W, H = COLS * TILE, ROWS * TILE + HUD
FPS = 60
 
EMPTY, WALL, BRICK = 0, 1, 2
DIRS = ((1, 0), (-1, 0), (0, 1), (0, -1))
 
BOMB_TIME = 150          # 2.5 giay
FLAME_TIME = 34
PLAYER_HW = 15           # nua kich thuoc hitbox
ENEMY_HW = 14
MAX_RANGE = 8
MAX_BOMBS = 6
MAX_SPEED_LVL = 5
WIN_ROUNDS = 3           # che do Versus: thang bao nhieu round la vo dich
 
SPAWNS = [(1, 1), (COLS - 2, ROWS - 2)]     # cho xuat hien cua nguoi choi 1 va 2
 
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
 
# ---- Phim dieu khien (co the doi tai day) ----
K = pygame
KEYS_SOLO = dict(left=(K.K_a, K.K_LEFT), right=(K.K_d, K.K_RIGHT),
                 up=(K.K_w, K.K_UP), down=(K.K_s, K.K_DOWN),
                 bomb=(K.K_h, K.K_SPACE))
KEYS_P1 = dict(left=(K.K_a,), right=(K.K_d,), up=(K.K_w,), down=(K.K_s,),
               bomb=(K.K_h,))
KEYS_P2 = dict(left=(K.K_LEFT,), right=(K.K_RIGHT,), up=(K.K_UP,), down=(K.K_DOWN,),
               bomb=(K.K_1, K.K_KP1))
 
P1_STYLE = dict(body=(50, 90, 220), foot=(30, 50, 150), ball=(240, 110, 150), tag=(110, 160, 255))
P2_STYLE = dict(body=(220, 60, 60), foot=(140, 30, 30), ball=(90, 220, 240), tag=(255, 110, 110))
 
screen = pygame.display.set_mode((W, H))
pygame.display.set_caption("Bomberman")
clock = pygame.time.Clock()
world = pygame.Surface((COLS * TILE, ROWS * TILE))
 
FONT = "arial,segoeui,tahoma,verdana,dejavusans"
font_huge = pygame.font.SysFont(FONT, 72, bold=True)
font_big = pygame.font.SysFont(FONT, 44, bold=True)
font_mid = pygame.font.SysFont(FONT, 26, bold=True)
font_small = pygame.font.SysFont(FONT, 20, bold=True)
font_tiny = pygame.font.SysFont(FONT, 17, bold=True)
 
 
# ---------------------------------------------------------------- Tien ich
def draw_text(surf, text, font, x, y, color=WHITE, center=True, outline=2):
    main = font.render(text, True, color)
    rect = main.get_rect()
    if center:
        rect.center = (x, y)
    else:
        rect.topleft = (x, y)
    if outline:
        shadow = font.render(text, True, BLACK)
        for dx in (-outline, 0, outline):
            for dy in (-outline, 0, outline):
                if dx or dy:
                    surf.blit(shadow, rect.move(dx, dy))
    surf.blit(main, rect)
 
 
def draw_text_right(surf, text, font, x, y, color=WHITE, outline=2):
    draw_text(surf, text, font, x - font.size(text)[0], y, color, center=False, outline=outline)
 
 
def rect_of(x, y, hw):
    return pygame.Rect(int(math.floor(x - hw)), int(math.floor(y - hw)), 2 * hw, 2 * hw)
 
 
def cell_rect(c, r):
    return pygame.Rect(c * TILE, r * TILE, TILE, TILE)
 
 
def draw_heart(surf, x, y, s, color):
    pygame.draw.circle(surf, color, (x - s // 2, y), s // 2 + 1)
    pygame.draw.circle(surf, color, (x + s // 2, y), s // 2 + 1)
    pygame.draw.polygon(surf, color, [(x - s - 1, y + 1), (x + s + 1, y + 1), (x, y + s + 3)])
 
 
# ---------------------------------------------------------------- Doi tuong
class Bomb:
    def __init__(self, c, r, rng, owner):
        self.c, self.r, self.range, self.owner = c, r, rng, owner
        self.timer = BOMB_TIME
 
 
class Player:
    def __init__(self, idx, keys, style):
        self.idx = idx
        self.keys = keys
        self.style = style
        self.lives = 3
        self.max_bombs = 1
        self.rng = 2
        self.speed_lvl = 0
        self.stack = []
        self.place(*SPAWNS[idx])
 
    def place(self, c, r):
        self.x = c * TILE + TILE / 2
        self.y = r * TILE + TILE / 2
        self.dir = (0, 1)
        self.walk = 0.0
        self.invuln = 0
        self.timer = 0
        self.stack = []
        self.state = "alive"          # alive | dying | out
 
    def cell(self):
        return int(self.x // TILE), int(self.y // TILE)
 
    def rect(self):
        return rect_of(self.x, self.y, PLAYER_HW - 3)
 
    def read_dir(self):
        k = pygame.key.get_pressed()
        cur = set()
        for name, dv in (("left", (-1, 0)), ("right", (1, 0)), ("up", (0, -1)), ("down", (0, 1))):
            if any(k[key] for key in self.keys[name]):
                cur.add(dv)
        if self.idx == 0 and esp32_ctrl and esp32_ctrl.connected:
            dv = esp32_ctrl.get_dir()
            if dv != (0, 0):
                cur.add(dv)
        self.stack = [d for d in self.stack if d in cur]
        for d in cur:
            if d not in self.stack:
                self.stack.append(d)
        return self.stack[-1] if self.stack else (0, 0)
 
 
class Enemy:
    def __init__(self, c, r, speed, smart):
        self.x = c * TILE + TILE / 2
        self.y = r * TILE + TILE / 2
        self.speed = speed
        self.smart = smart
        self.dir = (0, 0)
        self.last = None
        self.phase = random.random() * 6.28
 
    def cell(self):
        return int(self.x // TILE), int(self.y // TILE)
 
    def rect(self):
        return rect_of(self.x, self.y, ENEMY_HW - 2)
 
    def update(self, g):
        self.phase += 0.15
        c, r = self.cell()
        cx, cy = c * TILE + TILE / 2, r * TILE + TILE / 2
        near = abs(self.x - cx) <= self.speed and abs(self.y - cy) <= self.speed
 
        # den giua o -> chon huong moi
        if near and (self.last != (c, r) or self.dir == (0, 0)):
            self.x, self.y = cx, cy
            self.last = (c, r)
            opts = [d for d in DIRS if g.enemy_free(c + d[0], r + d[1])]
            if not opts:
                self.dir = (0, 0)
                self.last = None
                return
            rev = (-self.dir[0], -self.dir[1])
            pool = [d for d in opts if d != rev] or opts
            if self.smart and random.random() < 0.65:
                pc, pr = g.target_cell(self)
                self.dir = min(pool, key=lambda d: abs(c + d[0] - pc) + abs(r + d[1] - pr))
            elif self.dir in pool and random.random() < 0.6:
                pass  # di thang tiep
            else:
                self.dir = random.choice(pool)
 
        if self.dir != (0, 0):
            vx, vy = self.dir[0] * self.speed, self.dir[1] * self.speed
            old = rect_of(self.x, self.y, ENEMY_HW)
            new = rect_of(self.x + vx, self.y + vy, ENEMY_HW)
            if g.blocked(new, old):
                self.dir = (-self.dir[0], -self.dir[1])
                self.last = None
            else:
                self.x += vx
                self.y += vy
 
 
# ---------------------------------------------------------------- Game
class Game:
    MODES = ("solo", "coop", "versus")
 
    def __init__(self):
        self.state = "title"      # title | intro | play | paused | roundend | matchover | gameover
        self.mode = "solo"
        self.menu_sel = 0
        self.timer = 0
        self.tick = 0
        self.best = 0
        self.level = 1
        self.score = 0
        self.wins = [0, 0]
        self.round = 1
        self.msg = ""
        self.msg_color = WHITE
        self.particles = []
        self.setup_players()
        self.make_level()
 
    # ------------------------------------------------------- khoi tao
    def setup_players(self):
        if self.mode == "solo":
            self.players = [Player(0, KEYS_SOLO, P1_STYLE)]
        else:
            self.players = [Player(0, KEYS_P1, P1_STYLE), Player(1, KEYS_P2, P2_STYLE)]
 
    def start(self, mode):
        self.mode = mode
        self.setup_players()
        self.level, self.score = 1, 0
        self.wins, self.round = [0, 0], 1
        self.make_level()
        self.state, self.timer = "intro", 110
 
    def go_menu(self):
        self.state = "title"
        self.make_level()
 
    def make_level(self):
        self.grid = [[EMPTY] * COLS for _ in range(ROWS)]
        for r in range(ROWS):
            for c in range(COLS):
                if r in (0, ROWS - 1) or c in (0, COLS - 1) or (r % 2 == 0 and c % 2 == 0):
                    self.grid[r][c] = WALL
 
        self.hidden = {}
        self.items = {}
        self.exit_cell = None
        self.exit_visible = False
 
        if self.mode == "versus":
            # ban do doi xung de cong bang
            for r in range(1, ROWS - 1):
                for c in range(1, COLS - 1):
                    if self.grid[r][c] != EMPTY:
                        continue
                    mc, mr = COLS - 1 - c, ROWS - 1 - r
                    if (r, c) <= (mr, mc) and random.random() < 0.62:
                        self.grid[r][c] = BRICK
                        self.grid[mr][mc] = BRICK
        else:
            chance = min(0.34 + 0.02 * self.level, 0.5)
            for r in range(1, ROWS - 1):
                for c in range(1, COLS - 1):
                    if self.grid[r][c] == EMPTY and random.random() < chance:
                        self.grid[r][c] = BRICK
 
        # xoa cho xuat hien
        spawns = SPAWNS[:len(self.players)] if self.mode == "solo" else SPAWNS
        for sc, sr in SPAWNS:
            sx = 1 if sc < COLS // 2 else -1
            sy = 1 if sr < ROWS // 2 else -1
            for c, r in ((sc, sr), (sc + sx, sr), (sc, sr + sy)):
                self.grid[r][c] = EMPTY
 
        if self.mode == "versus":
            for r in range(ROWS):
                for c in range(COLS):
                    if self.grid[r][c] == BRICK:
                        mc, mr = COLS - 1 - c, ROWS - 1 - r
                        if (r, c) <= (mr, mc) and random.random() < 0.32:
                            kind = random.choice("FFBSS")
                            self.hidden[(c, r)] = kind
                            if self.grid[mr][mc] == BRICK:
                                self.hidden[(mc, mr)] = kind
        else:
            bricks = [(c, r) for r in range(ROWS) for c in range(COLS) if self.grid[r][c] == BRICK]
            random.shuffle(bricks)
            self.exit_cell = bricks.pop() if bricks else (COLS - 2, ROWS - 2)
            self.grid[self.exit_cell[1]][self.exit_cell[0]] = BRICK
            for cell in bricks:
                if random.random() < 0.2:
                    self.hidden[cell] = random.choice("FFBSS")
 
        self.bombs = []
        self.flames = {}
        self.particles = []
        for p in self.players:
            p.place(*SPAWNS[p.idx])
 
        # quai vat
        self.enemies = []
        if self.mode != "versus":
            free = [(c, r) for r in range(1, ROWS - 1) for c in range(1, COLS - 1)
                    if self.grid[r][c] == EMPTY
                    and all(abs(c - sc) + abs(r - sr) >= 7 for sc, sr in spawns)]
            random.shuffle(free)
            count = min(2 + self.level + (2 if self.mode == "coop" else 0), 10)
            smart_p = min(0.1 + 0.12 * self.level, 0.8)
            speed = min(0.9 + 0.12 * self.level, 2.0)
            for c, r in free[:count]:
                self.enemies.append(Enemy(c, r, speed, random.random() < smart_p))
 
    # ------------------------------------------------------- va cham
    def static_free(self, c, r):
        return 0 <= c < COLS and 0 <= r < ROWS and self.grid[r][c] == EMPTY
 
    def bomb_at(self, c, r):
        for b in self.bombs:
            if b.c == c and b.r == r:
                return b
        return None
 
    def enemy_free(self, c, r):
        return self.static_free(c, r) and not self.bomb_at(c, r) and (c, r) not in self.flames
 
    def target_cell(self, e):
        ec = e.cell()
        alive = [p for p in self.players if p.state == "alive"]
        if not alive:
            return ec
        best = min(alive, key=lambda p: abs(p.cell()[0] - ec[0]) + abs(p.cell()[1] - ec[1]))
        return best.cell()
 
    def blocked(self, new, old):
        c0, c1 = max(0, new.left // TILE), min(COLS - 1, (new.right - 1) // TILE)
        r0, r1 = max(0, new.top // TILE), min(ROWS - 1, (new.bottom - 1) // TILE)
        for r in range(r0, r1 + 1):
            for c in range(c0, c1 + 1):
                if self.grid[r][c] != EMPTY:
                    return True
        for b in self.bombs:
            br = cell_rect(b.c, b.r)
            if new.colliderect(br) and not old.colliderect(br):
                return True
        return False
 
    # ------------------------------------------------------- nguoi choi
    def move_player(self, p, d):
        spd = 2.6 + 0.45 * p.speed_lvl
        vx, vy = d[0] * spd, d[1] * spd
        p.walk += 0.3
        old = rect_of(p.x, p.y, PLAYER_HW)
 
        if not self.blocked(rect_of(p.x + vx, p.y + vy, PLAYER_HW), old):
            p.x += vx
            p.y += vy
            return
        # tien sat tuong
        for k in range(int(spd), 0, -1):
            ax, ay = d[0] * k, d[1] * k
            if not self.blocked(rect_of(p.x + ax, p.y + ay, PLAYER_HW), old):
                p.x += ax
                p.y += ay
                return
        # ho tro lach goc: tu dong truot vao loi di
        if d[0]:
            ahead = int((p.x + d[0] * (PLAYER_HW + 1)) // TILE)
            row = int(p.y // TILE)
            cy = row * TILE + TILE / 2
            for rr in (row, row - 1 if p.y < cy else row + 1):
                if self.static_free(ahead, rr):
                    step = max(-spd, min(spd, rr * TILE + TILE / 2 - p.y))
                    if not self.blocked(rect_of(p.x, p.y + step, PLAYER_HW), old):
                        p.y += step
                    return
        else:
            ahead = int((p.y + d[1] * (PLAYER_HW + 1)) // TILE)
            col = int(p.x // TILE)
            cx = col * TILE + TILE / 2
            for cc in (col, col - 1 if p.x < cx else col + 1):
                if self.static_free(cc, ahead):
                    step = max(-spd, min(spd, cc * TILE + TILE / 2 - p.x))
                    if not self.blocked(rect_of(p.x + step, p.y, PLAYER_HW), old):
                        p.x += step
                    return
 
    def place_bomb(self, p):
        c, r = p.cell()
        mine = sum(1 for b in self.bombs if b.owner is p)
        if mine < p.max_bombs and not self.bomb_at(c, r):
            self.bombs.append(Bomb(c, r, p.rng, p))
 
    # ------------------------------------------------------- no
    def burst(self, x, y, color, n=10, speed=3.0):
        for _ in range(n):
            a = random.random() * 6.283
            s = random.random() * speed
            self.particles.append([x, y, math.cos(a) * s, math.sin(a) * s,
                                   random.randint(18, 34), 34, color, random.randint(2, 5)])
 
    def destroy_brick(self, c, r):
        self.grid[r][c] = EMPTY
        if self.mode != "versus":
            self.score += 10
        self.burst(c * TILE + TILE / 2, r * TILE + TILE / 2, (196, 98, 52), 12)
        if (c, r) == self.exit_cell:
            self.exit_visible = True
        if (c, r) in self.hidden:
            self.items[(c, r)] = self.hidden.pop((c, r))
 
    def detonate(self, b):
        if b not in self.bombs:
            return
        self.bombs.remove(b)
        cells = [(b.c, b.r)]
        for dc, dr in DIRS:
            for i in range(1, b.range + 1):
                c, r = b.c + dc * i, b.r + dr * i
                if self.grid[r][c] == WALL:
                    break
                cells.append((c, r))
                if self.grid[r][c] == BRICK:
                    self.destroy_brick(c, r)
                    break
                other = self.bomb_at(c, r)
                if other:
                    other.timer = 0     # no day chuyen
                    break
        for cell in cells:
            self.flames[cell] = FLAME_TIME
 
    def update_effects(self):
        for b in self.bombs:
            b.timer -= 1
        while True:
            ready = [b for b in self.bombs if b.timer <= 0]
            if not ready:
                break
            for b in ready:
                self.detonate(b)
        for cell in list(self.flames):
            self.flames[cell] -= 1
            if self.flames[cell] <= 0:
                del self.flames[cell]
        for q in self.particles:
            q[0] += q[2]
            q[1] += q[3]
            q[3] += 0.12
            q[4] -= 1
        self.particles = [q for q in self.particles if q[4] > 0]
 
    # ------------------------------------------------------- cap nhat
    def kill_player(self, p):
        self.burst(p.x, p.y, p.style["tag"], 18, 4)
        p.stack = []
        if self.mode == "versus":
            p.state = "out"
        else:
            p.lives -= 1
            p.state = "dying"
            p.timer = 80
 
    def apply_item(self, p, kind):
        if kind == "F":
            p.rng = min(MAX_RANGE, p.rng + 1)
        elif kind == "B":
            p.max_bombs = min(MAX_BOMBS, p.max_bombs + 1)
        else:
            p.speed_lvl = min(MAX_SPEED_LVL, p.speed_lvl + 1)
        if self.mode != "versus":
            self.score += 50
        self.burst(p.x, p.y, (255, 240, 120), 10)
 
    def update_play(self):
        # dieu khien
        for p in self.players:
            if p.state == "alive":
                d = p.read_dir()
                if d != (0, 0):
                    p.dir = d
                    self.move_player(p, d)
 
        self.update_effects()
        for e in self.enemies:
            e.update(self)
 
        # nhat vat pham
        for p in self.players:
            if p.state == "alive" and p.cell() in self.items:
                self.apply_item(p, self.items.pop(p.cell()))
 
        # lua giet quai vat
        for e in self.enemies[:]:
            if e.cell() in self.flames:
                self.enemies.remove(e)
                self.score += 200 if e.smart else 100
                self.burst(e.x, e.y, (230, 60, 110), 16, 4)
 
        # nguoi choi bi trung don
        for p in self.players:
            if p.state != "alive":
                continue
            if p.invuln > 0:
                p.invuln -= 1
                continue
            hit = p.cell() in self.flames
            if not hit:
                pr = p.rect()
                hit = any(e.rect().colliderect(pr) for e in self.enemies)
            if hit:
                self.kill_player(p)
 
        # hoi sinh (Co-op / 1 nguoi)
        for p in self.players:
            if p.state == "dying":
                p.timer -= 1
                if p.timer <= 0:
                    if p.lives > 0:
                        p.place(*SPAWNS[p.idx])
                        p.invuln = 180
                    else:
                        p.state = "out"
 
        if self.mode == "versus":
            self.check_round_end()
        elif all(p.state == "out" for p in self.players):
            self.state = "gameover"
        elif (self.exit_visible and not self.enemies
              and any(p.state == "alive" and p.cell() == self.exit_cell for p in self.players)):
            self.score += 500
            self.level += 1
            for p in self.players:
                p.lives = max(1, p.lives)       # nguoi da het mang duoc hoi sinh
            self.make_level()
            self.state, self.timer = "intro", 110
 
    def check_round_end(self):
        alive = [p for p in self.players if p.state == "alive"]
        if len(alive) > 1:
            return
        if alive:
            w = alive[0]
            self.wins[w.idx] += 1
            self.msg = f"NGUOI CHOI {w.idx + 1} THANG ROUND!"
            self.msg_color = w.style["tag"]
        else:
            self.msg = "HOA!"
            self.msg_color = WHITE
        self.state, self.timer = "roundend", 170
 
    def update(self):
        self.tick += 1
        self.best = max(self.best, self.score)
        if self.state == "play":
            self.update_play()
        elif self.state == "intro":
            self.timer -= 1
            if self.timer <= 0:
                self.state = "play"
        elif self.state == "roundend":
            self.update_effects()
            self.timer -= 1
            if self.timer <= 0:
                if max(self.wins) >= WIN_ROUNDS:
                    self.state = "matchover"
                else:
                    self.round += 1
                    self.make_level()
                    self.state, self.timer = "intro", 110
        elif self.state in ("gameover", "matchover"):
            self.update_effects()
 
    # ------------------------------------------------------- ve
    def draw_world(self):
        t = self.tick
        # nen co
        for r in range(ROWS):
            for c in range(COLS):
                col = (62, 148, 66) if (r + c) % 2 == 0 else (70, 160, 74)
                pygame.draw.rect(world, col, cell_rect(c, r))
 
        # cua thoat
        if self.exit_cell and self.exit_visible:
            ex, ey = self.exit_cell
            rr = cell_rect(ex, ey).inflate(-8, -8)
            pygame.draw.rect(world, (50, 36, 30), rr, border_radius=6)
            pygame.draw.rect(world, (240, 200, 70), rr, 3, border_radius=6)
            open_ = not self.enemies
            inner = (90, 230, 130) if open_ else (200, 60, 60)
            if open_ and (t // 10) % 2:
                inner = (160, 255, 190)
            pygame.draw.rect(world, inner, rr.inflate(-18, -14), border_radius=4)
 
        # vat pham
        for (c, r), kind in self.items.items():
            rr = cell_rect(c, r).inflate(-14, -14)
            rr.y += int(math.sin(t * 0.12 + c) * 2)
            col = {"F": (230, 80, 50), "B": (60, 110, 230), "S": (240, 200, 40)}[kind]
            pygame.draw.rect(world, (30, 30, 30), rr.inflate(4, 4), border_radius=7)
            pygame.draw.rect(world, col, rr, border_radius=6)
            draw_text(world, kind, font_small, rr.centerx, rr.centery, WHITE, outline=1)
 
        # tuong & gach
        for r in range(ROWS):
            for c in range(COLS):
                g = self.grid[r][c]
                rc = cell_rect(c, r)
                if g == WALL:
                    pygame.draw.rect(world, (96, 96, 112), rc)
                    pygame.draw.rect(world, (150, 150, 168), (rc.x, rc.y, TILE, 4))
                    pygame.draw.rect(world, (150, 150, 168), (rc.x, rc.y, 4, TILE))
                    pygame.draw.rect(world, (60, 60, 74), (rc.x, rc.bottom - 4, TILE, 4))
                    pygame.draw.rect(world, (60, 60, 74), (rc.right - 4, rc.y, 4, TILE))
                    pygame.draw.rect(world, (110, 110, 128), rc.inflate(-18, -18))
                elif g == BRICK:
                    pygame.draw.rect(world, (200, 100, 54), rc)
                    mortar = (120, 56, 30)
                    for i in range(1, 4):
                        pygame.draw.line(world, mortar, (rc.x, rc.y + i * 12), (rc.right, rc.y + i * 12), 2)
                    for i in range(4):
                        off = 0 if i % 2 == 0 else 12
                        for x in (rc.x + off + 12, rc.x + off + 36):
                            if rc.x < x < rc.right - 2:
                                pygame.draw.line(world, mortar, (x, rc.y + i * 12), (x, rc.y + i * 12 + 12), 2)
                    pygame.draw.rect(world, (120, 56, 30), rc, 2)
                    pygame.draw.line(world, (230, 150, 100), (rc.x + 2, rc.y + 2), (rc.right - 3, rc.y + 2), 2)
 
        if self.state != "title":
            # bom
            for b in self.bombs:
                cx, cy = b.c * TILE + TILE // 2, b.r * TILE + TILE // 2
                speed = 0.25 if b.timer > 50 else 0.6
                rad = 16 + int(2.5 * math.sin(t * speed))
                pygame.draw.ellipse(world, (40, 110, 44), (cx - 17, cy + 8, 34, 11))
                pygame.draw.circle(world, (20, 20, 28), (cx, cy + 1), rad)
                pygame.draw.circle(world, (80, 80, 100), (cx - 5, cy - 5), 4)
                pygame.draw.line(world, (140, 110, 60), (cx + 4, cy - rad + 3), (cx + 9, cy - rad - 5), 3)
                if (t // 4) % 2:
                    pygame.draw.circle(world, (255, 220, 60), (cx + 10, cy - rad - 6), 4)
                else:
                    pygame.draw.circle(world, (255, 120, 40), (cx + 10, cy - rad - 6), 3)
 
            # lua
            for (c, r), life in self.flames.items():
                rc = cell_rect(c, r)
                shrink = int((1 - life / FLAME_TIME) * 10)
                pygame.draw.rect(world, (240, 110, 30), rc.inflate(-4 - shrink, -4 - shrink), border_radius=10)
                pygame.draw.rect(world, (255, 205, 60), rc.inflate(-14 - shrink, -14 - shrink), border_radius=8)
                pygame.draw.rect(world, (255, 255, 220), rc.inflate(-26 - shrink, -26 - shrink), border_radius=6)
 
            # quai vat
            for e in self.enemies:
                self.draw_enemy(e)
 
            # nguoi choi
            for p in sorted(self.players, key=lambda q: q.y):
                if p.state == "alive" and (p.invuln <= 0 or (p.invuln // 5) % 2 == 0):
                    self.draw_player(p)
 
            # hat
            for q in self.particles:
                a = q[4] / q[5]
                s = max(1, int(q[7] * a))
                pygame.draw.rect(world, q[6], (int(q[0]), int(q[1]), s, s))
 
    def draw_player(self, p):
        x, y = int(p.x), int(p.y)
        st = p.style
        sw = math.sin(p.walk) * 3
        pygame.draw.ellipse(world, (40, 110, 44), (x - 14, y + 8, 28, 12))
        pygame.draw.ellipse(world, st["foot"], (x - 11, int(y + 10 + sw), 10, 7))
        pygame.draw.ellipse(world, st["foot"], (x + 1, int(y + 10 - sw), 10, 7))
        pygame.draw.rect(world, st["body"], (x - 9, y - 4, 18, 16), border_radius=5)
        pygame.draw.circle(world, (235, 235, 245), (x, y - 10), 13)
        pygame.draw.circle(world, (170, 170, 190), (x, y - 10), 13, 2)
        dx, dy = p.dir
        if dy >= 0:
            pygame.draw.rect(world, (255, 214, 184), (x - 8 + dx * 2, y - 16, 16, 12), border_radius=4)
            ex = dx * 2
            pygame.draw.rect(world, BLACK, (x - 5 + ex, y - 13, 3, 5))
            pygame.draw.rect(world, BLACK, (x + 2 + ex, y - 13, 3, 5))
        pygame.draw.line(world, (170, 170, 190), (x, y - 22), (x, y - 27), 2)
        pygame.draw.circle(world, st["ball"], (x, y - 28), 3)
        if self.mode != "solo":
            draw_text(world, f"P{p.idx + 1}", font_tiny, x, y - 40, st["tag"], outline=1)
 
    def draw_enemy(self, e):
        x, y = int(e.x), int(e.y)
        w = 30 + int(math.sin(e.phase * 2) * 2)
        h = 26 - int(math.sin(e.phase * 2) * 2)
        body = (150, 60, 200) if e.smart else (215, 50, 90)
        dark = (90, 30, 130) if e.smart else (140, 25, 55)
        pygame.draw.ellipse(world, (40, 110, 44), (x - 15, y + 8, 30, 11))
        pygame.draw.ellipse(world, dark, (x - w // 2 - 1, y - h // 2 - 3, w + 2, h + 2))
        pygame.draw.ellipse(world, body, (x - w // 2, y - h // 2 - 2, w, h))
        fx = int(math.sin(e.phase * 2) * 3)
        pygame.draw.ellipse(world, dark, (x - 12 + fx, y + 7, 9, 6))
        pygame.draw.ellipse(world, dark, (x + 3 - fx, y + 7, 9, 6))
        ox, oy = e.dir[0] * 2, e.dir[1] * 2
        for ex in (-6, 6):
            pygame.draw.circle(world, WHITE, (x + ex, y - 5), 5)
            pygame.draw.circle(world, BLACK, (x + ex + ox, y - 5 + oy), 2)
        if e.smart:   # long may gian
            pygame.draw.line(world, BLACK, (x - 11, y - 13), (x - 3, y - 10), 2)
            pygame.draw.line(world, BLACK, (x + 11, y - 13), (x + 3, y - 10), 2)
 
    # ------------------------------------------------------- HUD
    def hud_player(self, p, left):
        col = p.style["tag"]
        label = f"P{p.idx + 1}"
        if left:
            draw_text(screen, label, font_small, 10, 4, col, center=False)
        else:
            draw_text_right(screen, label, font_small, W - 10, 4, col)
        if self.mode != "versus":
            for i in range(max(0, p.lives)):
                hx = 52 + i * 28 if left else W - 54 - i * 28
                draw_heart(screen, hx, 17, 8, (235, 60, 80))
        stats = f"BOM {p.max_bombs}  LUA {p.rng}  TD {p.speed_lvl + 1}"
        if left:
            draw_text(screen, stats, font_tiny, 10, 37, (190, 190, 215), center=False, outline=0)
        else:
            draw_text_right(screen, stats, font_tiny, W - 10, 37, (190, 190, 215), outline=0)
 
    def draw_hud(self):
        pygame.draw.rect(screen, (28, 28, 40), (0, 0, W, HUD))
        pygame.draw.line(screen, (90, 90, 120), (0, HUD - 1), (W, HUD - 1), 2)
        if self.mode == "solo":
            p = self.players[0]
            for i in range(max(0, p.lives)):
                draw_heart(screen, 22 + i * 32, 17, 9, (235, 60, 80))
            draw_text(screen, f"DIEM {self.score:06d}", font_mid, 112, 4, (255, 230, 120), center=False)
            draw_text(screen, f"MAN {self.level}", font_mid, 330, 4, WHITE, center=False)
            draw_text(screen, f"QUAI {len(self.enemies)}", font_mid, 450, 4, (255, 140, 170), center=False)
            info = (f"BOM {p.max_bombs}   LUA {p.rng}   TOC DO {p.speed_lvl + 1}"
                    f"   KY LUC {self.best}")
            draw_text(screen, info, font_tiny, 12, 37, (190, 190, 215), center=False, outline=0)
        else:
            self.hud_player(self.players[0], True)
            self.hud_player(self.players[1], False)
            if self.mode == "coop":
                draw_text(screen, f"DIEM {self.score:06d}", font_small, W // 2, 14, (255, 230, 120))
                draw_text(screen, f"MAN {self.level}   QUAI {len(self.enemies)}", font_tiny,
                          W // 2, 40, WHITE, outline=1)
            else:
                draw_text(screen, f"{self.wins[0]}  :  {self.wins[1]}", font_mid, W // 2, 17, WHITE)
                draw_text(screen, f"ROUND {self.round}", font_tiny, W // 2, 41, (200, 200, 225), outline=1)
 
    def overlay(self, alpha=150):
        s = pygame.Surface((W, H), pygame.SRCALPHA)
        s.fill((0, 0, 0, alpha))
        screen.blit(s, (0, 0))
 
    def draw(self):
        self.draw_world()
        screen.fill((0, 0, 0))
        screen.blit(world, (0, HUD))
        self.draw_hud()
 
        if self.state == "title":
            self.draw_menu()
        elif self.state == "intro":
            self.overlay(120)
            if self.mode == "versus":
                draw_text(screen, f"ROUND {self.round}", font_huge, W // 2, H // 2 - 30, (255, 220, 80), outline=4)
                draw_text(screen, f"Ai song sot se thang! (thang {WIN_ROUNDS} round la vo dich)",
                          font_small, W // 2, H // 2 + 40, WHITE)
            else:
                draw_text(screen, f"MAN {self.level}", font_huge, W // 2, H // 2 - 30, (255, 220, 80), outline=4)
                sub = "Hop tac diet het quai vat!" if self.mode == "coop" else "Diet het quai vat de mo cua thoat!"
                draw_text(screen, sub, font_mid, W // 2, H // 2 + 40, WHITE)
        elif self.state == "paused":
            self.overlay(150)
            draw_text(screen, "TAM DUNG", font_big, W // 2, H // 2 - 10, WHITE)
            draw_text(screen, "Nhan P de tiep tuc", font_small, W // 2, H // 2 + 36, (200, 200, 220))
        elif self.state == "roundend":
            s = pygame.Surface((W, 90), pygame.SRCALPHA)
            s.fill((0, 0, 0, 160))
            screen.blit(s, (0, H // 2 - 45))
            draw_text(screen, self.msg, font_big, W // 2, H // 2, self.msg_color, outline=3)
        elif self.state == "matchover":
            self.overlay(175)
            w = 0 if self.wins[0] > self.wins[1] else 1
            col = self.players[w].style["tag"]
            draw_text(screen, f"NGUOI CHOI {w + 1}", font_huge, W // 2, H // 2 - 90, col, outline=4)
            draw_text(screen, "VO DICH!", font_huge, W // 2, H // 2 - 20, (255, 220, 80), outline=4)
            draw_text(screen, f"Ti so  {self.wins[0]} : {self.wins[1]}", font_big, W // 2, H // 2 + 50, WHITE)
            draw_text(screen, "R : tran moi      M : ve menu", font_mid, W // 2, H // 2 + 115, (120, 255, 150))
        elif self.state == "gameover":
            self.overlay(170)
            draw_text(screen, "GAME OVER", font_huge, W // 2, H // 2 - 60, (240, 80, 70), outline=4)
            draw_text(screen, f"Diem: {self.score}", font_big, W // 2, H // 2 + 10, WHITE)
            draw_text(screen, f"Ky luc: {self.best}", font_mid, W // 2, H // 2 + 56, (255, 220, 100))
            draw_text(screen, "R : choi lai      M : ve menu", font_mid, W // 2, H // 2 + 120, (120, 255, 150))
 
        pygame.display.flip()
 
    def draw_menu(self):
        self.overlay(185)
        bob = int(math.sin(self.tick * 0.06) * 6)
        draw_text(screen, "BOMBERMAN", font_huge, W // 2, 130 + bob, (255, 200, 60), outline=4)
        items = ("1.  Choi 1 nguoi", "2.  Co-op: 2 nguoi danh quai", "3.  Versus: 2 nguoi doi dau")
        for i, text in enumerate(items):
            y = 250 + i * 56
            sel = i == self.menu_sel
            if sel:
                box = pygame.Rect(W // 2 - 270, y - 24, 540, 48)
                pygame.draw.rect(screen, (60, 60, 96), box, border_radius=10)
                pygame.draw.rect(screen, (255, 220, 90), box, 3, border_radius=10)
            draw_text(screen, text, font_mid, W // 2, y, (255, 230, 100) if sel else (205, 205, 228))
 
        lines = (
            ("Nguoi 1 :  W A S D di chuyen,  phim H dat bom", P1_STYLE["tag"]),
            ("Nguoi 2 :  Mui ten di chuyen,  phim 1 dat bom", P2_STYLE["tag"]),
            ("Choi 1 nguoi :  WASD hoac mui ten,  SPACE hoac H dat bom", (200, 200, 225)),
        )
        for i, (ln, col) in enumerate(lines):
            draw_text(screen, ln, font_small, W // 2, 450 + i * 30, col, outline=1)
        # Trang thai tay cam ESP32
        if esp32_ctrl and esp32_ctrl.connected:
            draw_text(screen, f"Tay cam ESP32 ({esp32_ctrl.current_port}): DA KET NOI", font_tiny,
                      W // 2, 542, (120, 255, 150), outline=1)
        else:
            draw_text(screen, "Tay cam ESP32: Chua ket noi (cam cap USB)", font_tiny,
                      W // 2, 542, (170, 170, 190), outline=1)

        draw_text(screen, "F = bom no xa hon     B = them bom     S = chay nhanh", font_tiny,
                  W // 2, 570, (190, 190, 215), outline=1)
        if (self.tick // 30) % 2 == 0:
            draw_text(screen, "Len / Xuong de chon, ENTER / NUT BAM de bat dau", font_small, W // 2, 615, (120, 255, 150))
 
    # ------------------------------------------------------- su kien
    def handle_key(self, key):
        if key == pygame.K_ESCAPE:
            if self.state == "title":
                pygame.quit()
                sys.exit()
            self.go_menu()
            return
 
        if self.state == "title":
            if key in (pygame.K_UP, pygame.K_w):
                self.menu_sel = (self.menu_sel - 1) % 3
            elif key in (pygame.K_DOWN, pygame.K_s):
                self.menu_sel = (self.menu_sel + 1) % 3
            elif key in (pygame.K_1, pygame.K_KP1):
                self.start("solo")
            elif key in (pygame.K_2, pygame.K_KP2):
                self.start("coop")
            elif key in (pygame.K_3, pygame.K_KP3):
                self.start("versus")
            elif key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
                self.start(self.MODES[self.menu_sel])
        elif self.state == "play":
            if key == pygame.K_p:
                self.state = "paused"
            else:
                for p in self.players:
                    if p.state == "alive" and key in p.keys["bomb"]:
                        self.place_bomb(p)
        elif self.state == "paused":
            if key == pygame.K_p:
                self.state = "play"
        elif self.state in ("gameover", "matchover"):
            if key in (pygame.K_r, pygame.K_RETURN):
                self.start(self.mode)
            elif key == pygame.K_m:
                self.go_menu()
 
 
def main():
    game = Game()
    last_bomb = False
    menu_timer = 0
    while True:
        clock.tick(FPS)
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            if e.type == pygame.KEYDOWN:
                game.handle_key(e.key)

        # Xu ly tin hieu tu tay cam ESP32
        if esp32_ctrl and esp32_ctrl.connected:
            # 1. Nut bam dat bom / chon menu
            cur_bomb = esp32_ctrl.bomb_pressed
            if cur_bomb and not last_bomb:
                if game.state == "play":
                    game.handle_key(pygame.K_h)
                elif game.state == "title":
                    game.handle_key(pygame.K_RETURN)
                elif game.state in ("gameover", "matchover"):
                    game.handle_key(pygame.K_RETURN)
                elif game.state == "paused":
                    game.handle_key(pygame.K_p)
            last_bomb = cur_bomb

            # 2. Dieu huong Menu bang Joystick
            if game.state == "title":
                if esp32_ctrl.dy < 0 and menu_timer <= 0:
                    game.handle_key(pygame.K_w)
                    menu_timer = 15
                elif esp32_ctrl.dy > 0 and menu_timer <= 0:
                    game.handle_key(pygame.K_s)
                    menu_timer = 15
                elif esp32_ctrl.dy == 0:
                    menu_timer = 0
                else:
                    menu_timer -= 1

        game.update()
        game.draw()
 
 
if __name__ == "__main__":
    main()