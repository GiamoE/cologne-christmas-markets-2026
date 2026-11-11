"""Render 茉莉花 (Jasmine Flower), traditional Chinese folk song (public domain melody),
as a guzheng + erhu arrangement with a gong and sleigh bells. Pure Python, writes a WAV.
Usage: python3 render.py out.wav
"""
import math, random, struct, sys, wave

SR = 44100
BEAT = 60 / 66  # quarter = 66 bpm
random.seed(7)

# ---- melody (jianpu, 1 = D5), bars of 2 beats ----
A = ["3:1 3:.5 5:.5", "6:.5 i:.5 i:.5 6:.5", "5:1 5:.5 6:.5", "5:2"]
B = ["5:1 5:1", "5:1 3:.5 5:.5", "6:1 6:1", "5:2"]
C = ["3:1 2:.5 3:.5", "5:1 3:.5 2:.5", "1:1 1:.5 2:.5", "1:2"]
D = ["3:.5 2:.5 1:.5 3:.5", "2:1 1:.5 6,:.5", "5,:1 6,:.5 1:.5", "2:1 3:.5 1:.5",
     "2:.5 1:.5 6,:.5 5,:.5", "5,:2"]
BARS = A + A + B + C + D
SEMI = {"1": 0, "2": 2, "3": 4, "5": 7, "6": 9, "i": 12}
ROOT_OF = {"1": 0, "2": 2, "3": 0, "5": 7, "6": 9, "i": 0}
D5 = 587.33


def deg_freq(tok):
    s = SEMI[tok[0]] - (12 if tok.endswith(",") else 0)
    return D5 * 2 ** (s / 12)


def parse(bar):
    out = []
    for t in bar.split():
        n, d = t.split(":")
        out.append((n, float(d)))
    return out


total_beats = 4 + len(BARS) * 2 * 2 + 6
N = int((total_beats * BEAT + 5) * SR)
mix = [0.0] * N


def add(buf, t, gain):
    i0 = int(t * SR)
    n = min(len(buf), N - i0)
    for i in range(n):
        mix[i0 + i] += buf[i] * gain


# ---- instruments ----
_pluck_cache = {}


def pluck_table(f):
    key = round(f, 2)
    if key in _pluck_cache:
        return _pluck_cache[key]
    L = int(2.6 * SR)
    buf = [0.0] * L
    for k in range(1, 11):
        fk = f * k * math.sqrt(1 + 0.00025 * k * k)
        if fk > 12000:
            break
        amp = abs(math.sin(math.pi * k * 0.17)) / k ** 1.1
        dec = 1.6 * (1 + 0.55 * k ** 1.25)
        w = 2 * math.pi * fk / SR
        for i in range(L):
            buf[i] += amp * math.exp(-dec * i / SR) * math.sin(w * i)
    att = int(0.003 * SR)
    for i in range(att):
        buf[i] *= i / att
    peak = max(abs(x) for x in buf) or 1
    buf = [x / peak for x in buf]
    _pluck_cache[key] = buf
    return buf


def pluck(t, f, length, gain):
    tab = pluck_table(f)
    n = min(len(tab), int((length + 0.9) * SR))
    fade = int(0.06 * SR)
    seg = tab[:n]
    for i in range(max(0, n - fade), n):
        seg[i] = seg[i] * (n - i) / fade
    add(seg, t, gain)


def erhu_phrase(t0, notes, gain):
    """notes: list of (start_sec_rel, dur_sec, freq). Legato bowed line with slides."""
    end = notes[-1][0] + notes[-1][1]
    L = int((end + 0.4) * SR)
    out = [0.0] * L
    phase = 0.0
    lp = 0.0
    bp1 = bp2 = 0.0
    # resonant body around 900 Hz
    fc, q = 900.0, 2.2
    w0 = 2 * math.pi * fc / SR
    alpha = math.sin(w0) / (2 * q)
    b0, a0 = alpha, 1 + alpha
    a1, a2 = -2 * math.cos(w0), 1 - alpha
    x1 = x2 = y1 = y2 = 0.0
    idx = 0
    prev_f = notes[0][2]
    for ni, (st, du, f) in enumerate(notes):
        s0, s1 = int(st * SR), int((st + du) * SR)
        if ni == len(notes) - 1:
            s1 = min(L, s1 + int(0.3 * SR))
        for i in range(s0, s1):
            tt = (i - s0) / SR
            slide = min(1.0, tt / 0.07)
            ff = prev_f + (f - prev_f) * (1 - (1 - slide) ** 2)
            vib_depth = 0.0065 * min(1.0, max(0.0, (tt - 0.12) / 0.25))
            ff *= 1 + vib_depth * math.sin(2 * math.pi * 5.6 * tt)
            phase += ff / SR
            phase -= int(phase)
            saw = 2 * phase - 1
            lp += 0.28 * (saw - lp)
            y = (b0 * lp - b0 * x2 - a1 * y1 - a2 * y2) / a0
            x2, x1 = x1, lp
            y2, y1 = y1, y
            # bow envelope: swell in, slight dip at each bow change
            env = min(1.0, tt / 0.06) * (0.85 + 0.15 * math.sin(math.pi * min(1.0, tt / max(du, 0.01))))
            if ni == len(notes) - 1:
                env *= max(0.0, 1 - max(0.0, tt - du) / 0.3)
            out[i] = (0.55 * lp + 1.6 * y) * env
        prev_f = f
    peak = max(abs(x) for x in out) or 1
    add([x / peak for x in out], t0, gain)


def sleigh(t, gain):
    L = int(0.16 * SR)
    buf = [0.0] * L
    p1 = p2 = 0.0
    pings = [(random.uniform(4200, 8200), random.uniform(0, 6.28)) for _ in range(4)]
    for i in range(L):
        n = random.uniform(-1, 1)
        h = n - p1  # crude high-pass
        p1 = n
        h2 = h - p2
        p2 = h
        e = math.exp(-i / (0.035 * SR))
        s = sum(math.sin(2 * math.pi * f * i / SR + ph) for f, ph in pings) * 0.12
        buf[i] = (0.35 * h2 + s) * e
    add(buf, t, gain)


def gong(t, gain):
    L = int(5 * SR)
    parts = [(73.4, 1.0, 0.9), (110.3, 0.5, 1.3), (161.0, 0.35, 1.8), (226.5, 0.25, 2.4),
             (309.0, 0.15, 3.3), (417.0, 0.1, 4.5)]
    buf = [0.0] * L
    for f, a, d in parts:
        for i in range(L):
            tt = i / SR
            ff = f * (1 + 0.015 * math.exp(-tt * 1.5))
            buf[i] += a * math.exp(-d * tt) * math.sin(2 * math.pi * ff * tt) * min(1.0, tt / 0.02)
    peak = max(abs(x) for x in buf)
    add([x / peak for x in buf], t, gain)


def gliss(t, degrees, step, gain, down=False):
    seq = list(reversed(degrees)) if down else degrees
    for i, d in enumerate(seq):
        pluck(t + i * step, deg_freq(d), 0.8, gain * (0.7 + 0.3 * i / len(seq)))


# ---- arrangement ----
t = 0.0
gong(0.0, 0.55)
gliss(0.35, ["5,", "6,", "1", "2", "3", "5", "6", "i"], 0.085, 0.42)
for k in range(8):
    sleigh(1.6 + k * BEAT / 2, 0.10 + 0.02 * (k % 2 == 0))
t = 4 * BEAT


def bar_root(bar):
    last = parse(bar)[-1][0]
    return D5 / 4 * 2 ** (ROOT_OF[last[0]] / 12)


def accompany(t, bar, busy, gain):
    r = bar_root(bar)
    pattern = [r, r * 1.5, r * 2, r * 1.5] if busy else [r]
    step = 2 * BEAT / len(pattern)
    for i, f in enumerate(pattern):
        pluck(t + i * step, f, step, gain * (1.0 if i == 0 else 0.7))


# pass 1: guzheng melody, sparse accompaniment
for bar in BARS:
    bt = t
    for n, d in parse(bar):
        pluck(bt, deg_freq(n), d * BEAT, 0.5)
        if d >= 1.5:  # guzheng tremolo-ish re-pluck on long notes
            pluck(bt + d * BEAT * 0.5, deg_freq(n), d * BEAT * 0.5, 0.22)
        bt += d * BEAT
    accompany(t, bar, False, 0.32)
    t += 2 * BEAT

# little fill between passes
gliss(t - 0.5, ["1", "2", "3", "5", "6"], 0.07, 0.25)

# pass 2: erhu melody, guzheng broken chords, sleigh bells
notes = []
rel = 0.0
start2 = t
for bar in BARS:
    for n, d in parse(bar):
        notes.append((rel, d * BEAT, deg_freq(n)))
        rel += d * BEAT
erhu_phrase(start2, notes, 0.42)
for bar in BARS:
    accompany(t, bar, True, 0.26)
    for k in range(4):
        sleigh(t + k * BEAT / 2, 0.09 if k % 2 else 0.13)
    t += 2 * BEAT

# ending
gong(t, 0.5)
gliss(t + 0.1, ["5,", "6,", "1", "2", "3", "5", "6", "i"], 0.07, 0.35, down=True)
pluck(t + 0.8, deg_freq("1"), 3.0, 0.4)
pluck(t + 0.8, D5 / 4, 3.0, 0.3)
end = t + 5.0

# ---- write ----
n_out = int(end * SR)
peak = max(abs(x) for x in mix[:n_out]) or 1
with wave.open(sys.argv[1], "wb") as w:
    w.setnchannels(1)
    w.setsampwidth(2)
    w.setframerate(SR)
    w.writeframes(b"".join(struct.pack("<h", int(32000 * 0.9 * x / peak)) for x in mix[:n_out]))
print("seconds", round(end, 1))
