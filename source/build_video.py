#!/usr/bin/env python3
"""Build a 30-second Swarm Pepe film from recorded on-chain SVG bytes."""

import hashlib
import json
import math
from pathlib import Path
import shutil
import struct
import subprocess
import wave
from xml.etree import ElementTree

from font5x7 import FONT

ROOT = Path(__file__).resolve().parent.parent
W, H, FPS, SECONDS = 960, 540, 30, 30
FRAMES = FPS * SECONDS
BG = (9, 16, 26)
PANEL = (18, 29, 38)
GRID = (19, 31, 42)
LINE = (52, 74, 75)
CREAM = (239, 233, 205)
LIME = (204, 244, 99)
ORANGE = (250, 136, 77)
MUTED = (127, 154, 151)

FONT.update({
    '+': ('00000','00100','00100','11111','00100','00100','00000'),
    '>': ('10000','01000','00100','00010','00100','01000','10000'),
    "'": ('00100','00100','00000','00000','00000','00000','00000'),
    ',': ('00000','00000','00000','00000','00100','00100','01000'),
})


class Canvas:
    def __init__(self, base):
        self.pixels = bytearray(base)

    def rect(self, x, y, width, height, color):
        if width <= 0 or height <= 0:
            return
        x0, y0 = max(0, x), max(0, y)
        x1, y1 = min(W, x + width), min(H, y + height)
        if x1 <= x0 or y1 <= y0:
            return
        row = bytes(color) * (x1 - x0)
        for yy in range(y0, y1):
            start = (yy * W + x0) * 3
            self.pixels[start:start + len(row)] = row

    def border(self, x, y, width, height, color, thickness=1):
        self.rect(x, y, width, thickness, color)
        self.rect(x, y + height - thickness, width, thickness, color)
        self.rect(x, y, thickness, height, color)
        self.rect(x + width - thickness, y, thickness, height, color)

    def text(self, message, x, y, scale, color):
        for letter in message:
            glyph = FONT.get(letter, FONT[' '])
            for gy, row in enumerate(glyph):
                for gx, bit in enumerate(row):
                    if bit == '1':
                        self.rect(x + gx * scale, y + gy * scale, scale, scale, color)
            x += 6 * scale

    def sprite(self, sprites, token_id, x, y, size):
        pixels = sprites[token_id][size]
        for yy in range(size):
            if not 0 <= y + yy < H:
                continue
            x0, x1 = max(0, x), min(W, x + size)
            if x1 <= x0:
                continue
            src = (yy * size + x0 - x) * 3
            dst = ((y + yy) * W + x0) * 3
            self.pixels[dst:dst + (x1 - x0) * 3] = pixels[src:src + (x1 - x0) * 3]


def text_width(message, scale):
    return len(message) * 6 * scale


def base_frame():
    c = Canvas(bytes(BG) * W * H)
    for x in range(0, W, 24):
        c.rect(x, 0, 1, H, GRID)
    for y in range(0, H, 24):
        c.rect(0, y, W, 1, GRID)
    c.border(18, 18, 924, 504, LINE)
    c.rect(32, 51, 896, 1, LINE)
    c.rect(32, 486, 896, 1, LINE)
    c.text('SWARM / PEPE', 41, 29, 2, LIME)
    c.text('ETHEREUM MAINNET', 714, 29, 2, MUTED)
    c.text('ON CHAIN / 24 X 24', 41, 499, 2, MUTED)
    return bytes(c.pixels)


def load_sprites():
    data = json.loads((ROOT / 'assets/provenance.json').read_text())
    if data['total_minted'] != 1053 or data['max_supply'] != 5000:
        raise RuntimeError('Unexpected supply snapshot; review the copy before building')
    records = {entry['id']: entry for entry in data['tokens']}
    if set(records) != set(range(1, 13)):
        raise RuntimeError('The film needs exactly the verified tokens 1 through 12')
    sprites = {}
    for token_id, record in records.items():
        svg = (ROOT / 'assets' / record['svg']).read_bytes()
        if hashlib.sha256(svg).hexdigest() != record['sha256']:
            raise RuntimeError(f'SVG hash mismatch for token #{token_id}')
        root = ElementTree.fromstring(svg)
        if root.attrib.get('viewBox') != '0 0 24 24':
            raise RuntimeError(f'Unexpected dimensions for token #{token_id}')
        pixels = bytearray(24 * 24 * 3)
        for element in root:
            if element.tag.rsplit('}', 1)[-1] != 'rect':
                raise RuntimeError('Renderer returned a non-rect pixel element')
            x, y, width, height = (int(element.attrib[name]) for name in ('x', 'y', 'width', 'height'))
            color = bytes.fromhex(element.attrib['fill'].lstrip('#'))
            if len(color) != 3 or min(x, y, width, height) < 0 or x + width > 24 or y + height > 24:
                raise RuntimeError(f'Invalid renderer rectangle for #{token_id}')
            for yy in range(y, y + height):
                for xx in range(x, x + width):
                    start = (yy * 24 + xx) * 3
                    pixels[start:start + 3] = color
        sprites[token_id] = {}
        for size in (96, 144, 240, 288, 336):
            step = size // 24
            rows = []
            for yy in range(24):
                row = b''.join(pixels[(yy * 24 + xx) * 3:(yy * 24 + xx + 1) * 3] * step for xx in range(24))
                rows.extend([row] * step)
            sprites[token_id][size] = b''.join(rows)
    return sprites, data


def common(c, frame, section):
    c.rect(33, 485, round(894 * (frame + 1) / FRAMES), 3, LIME)
    c.text(f'00:{frame // FPS:02d} / 00:30', 745, 499, 2, CREAM)
    c.rect(914, 31, 8, 8, ORANGE if frame // 12 % 2 == 0 else LINE)
    c.text(section, 42, 466, 2, ORANGE)


def portrait_card(c, sprites, token_id, x, y, size=288, color=LIME):
    c.rect(x, y, size + 28, size + 65, PANEL)
    c.border(x, y, size + 28, size + 65, color)
    c.sprite(sprites, token_id, x + 14, y + 14, size)
    c.text(f'#{token_id:04d}', x + 15, y + size + 27, 3, CREAM)
    c.text('ON CHAIN', x + size - 98, y + size + 35, 2, MUTED)


def scene_intro(c, sprites, frame):
    c.text('WE BUILT', 61, 127, 6, CREAM)
    c.text('THIS SITE.', 61, 196, 6, LIME)
    c.rect(62, 272, 401, 3, ORANGE)
    c.text('FROM ONE WRITTEN BRIEF', 63, 305, 3, CREAM)
    c.text('SWARM PEPE / ETHEREUM', 63, 352, 2, MUTED)
    portrait_card(c, sprites, 1, 552, 87, 288)


def scene_build(c, sprites, frame):
    c.text('WE USED', 62, 100, 4, CREAM)
    c.text('REACT + VIEM', 62, 151, 5, LIME)
    c.rect(64, 215, 445, 3, ORANGE)
    c.text('STATIC BUILD', 62, 243, 4, CREAM)
    for i, label in enumerate(('BACKEND  0', 'DATABASE 0', 'SERVER   0')):
        c.text(label, 64, 319 + i * 38, 3, MUTED if i < 2 else ORANGE)
    portrait_card(c, sprites, 2, 552, 87, 288)


def scene_chain(c, sprites, frame):
    c.text('WE READ CONTRACTS', 60, 87, 4, CREAM)
    c.text('LIVE IN THE BROWSER', 60, 134, 3, LIME)
    c.rect(62, 182, 490, 3, ORANGE)
    c.text('NO METADATA API', 62, 215, 3, CREAM)
    c.text('NO IMAGE HOST', 62, 261, 3, CREAM)
    c.text('PIXELART DRAWS THE ART.', 62, 339, 2, MUTED)
    c.text('THERE IS NOTHING TO HOST.', 62, 370, 2, MUTED)
    portrait_card(c, sprites, 3, 552, 87, 288)


def scene_supply(c, sprites, frame, provenance):
    c.text('01 / HOME', 61, 82, 3, ORANGE)
    c.text('WE SHOW LIVE SUPPLY', 61, 128, 4, CREAM)
    c.text('1,053', 60, 212, 10, LIME)
    c.text('/ 5,000 MINTED', 62, 314, 3, CREAM)
    c.rect(62, 374, 430, 3, LINE)
    c.rect(62, 374, round(430 * 1053 / 5000), 3, ORANGE)
    c.text(f"READ AT BLOCK {provenance['block_decimal']:,}", 62, 410, 2, MUTED)
    portrait_card(c, sprites, 4, 552, 87, 288)


def scene_allocation(c, sprites, frame):
    c.text('01 / HOME', 61, 82, 3, ORANGE)
    c.text('WE CHECK ALLOCATION', 61, 129, 4, CREAM)
    c.rect(62, 188, 446, 3, ORANGE)
    c.text('PASTE ANY ADDRESS', 62, 227, 3, LIME)
    c.text('SEE SLOTS LEFT', 62, 277, 3, CREAM)
    c.text('NO WALLET CONNECTION', 62, 354, 2, MUTED)
    c.text('READ ONLY / IN THE BROWSER', 62, 387, 2, MUTED)
    portrait_card(c, sprites, 5, 552, 87, 288)


def scene_gallery(c, sprites, frame):
    c.text('02 / GALLERY', 52, 82, 3, ORANGE)
    c.text('WE READ EVERY MINTED TOKENURI', 52, 127, 3, CREAM)
    c.text('TRAIT FILTERS / ON-CHAIN METADATA', 52, 165, 2, LIME)
    for index, token_id in enumerate(range(6, 12)):
        x = 51 + index * 143
        c.rect(x, 214, 130, 185, PANEL)
        c.border(x, 214, 130, 185, LIME if index == (frame // 14) % 6 else LINE)
        c.sprite(sprites, token_id, x + 17, 229, 96)
        c.text(f'#{token_id:04d}', x + 25, 342, 2, CREAM)
        c.rect(x + 17, 383, 96, 2, ORANGE)
    c.text('EVERY PORTRAIT COMES FROM ITS TOKENURI.', 53, 425, 2, MUTED)


def scene_reveal(c, sprites, frame):
    portrait_card(c, sprites, 11, 52, 87, 288, ORANGE)
    c.text('02 / GALLERY', 410, 94, 3, ORANGE)
    c.text('WE ENABLE', 410, 147, 4, CREAM)
    c.text('BATCH REVEAL', 410, 205, 4, LIME)
    c.rect(411, 265, 438, 3, ORANGE)
    c.text('ANYONE CAN REVEAL', 411, 302, 3, CREAM)
    c.text('ANYONE ELSE\'S TOKEN', 411, 339, 3, CREAM)
    c.text('PENDING IDS / ONE TRANSACTION', 411, 411, 2, MUTED)


def scene_about(c, sprites, frame):
    c.text('03 / ABOUT', 61, 82, 3, ORANGE)
    c.text('WE EXPLAIN', 61, 129, 4, CREAM)
    c.text('THE REVEAL', 61, 178, 4, LIME)
    c.rect(63, 236, 430, 3, ORANGE)
    c.text('MINT COMMITS TO NEXT BLOCK', 62, 271, 2, CREAM)
    c.text('HASH UNKNOWN AT MINT', 62, 308, 2, CREAM)
    c.text('SEED AND ART FIXED ON REVEAL', 62, 345, 2, MUTED)
    c.text('NO SECOND RANDOM BLOCK', 62, 400, 2, MUTED)
    portrait_card(c, sprites, 12, 552, 87, 288)


def scene_end(c, sprites, frame):
    c.text('WE BUILT WHAT THE BRIEF ASKED FOR.', 116, 117, 3, CREAM)
    c.rect(172, 187, 616, 3, ORANGE)
    title = 'SWARMPEPE.XYZ'
    c.text(title, (W - text_width(title, 6)) // 2, 219, 6, LIME)
    c.text('ETHEREUM MAINNET / LIVE FROM THE CONTRACTS', 220, 320, 2, MUTED)
    c.text('generated by $IMD swarm', 330, 406, 2, CREAM)


def mix_audio(path):
    with wave.open(str(ROOT / 'assets/narration.wav'), 'rb') as voice:
        if (voice.getnchannels(), voice.getsampwidth(), voice.getframerate()) != (1, 2, 22050):
            raise RuntimeError('Unexpected narration WAV format')
        speech = voice.readframes(voice.getnframes())
    samples = len(speech) // 2
    rate = 22050
    notes = (196.0, 246.94, 293.66, 246.94, 174.61, 220.0, 261.63, 220.0)
    pcm = bytearray()
    for i in range(rate * SECONDS):
        t = i / rate
        beat = t * 2
        step = int(beat * 2)
        note = notes[(step // 2) % len(notes)]
        age = beat * 2 - step
        phase = (t * note) % 1
        triangle = 1 - 4 * abs(phase - 0.5)
        lead = triangle * math.exp(-age * 5) * 0.075
        bass = math.sin(2 * math.pi * (note / 4) * t) * math.exp(-(beat % 1) * 4) * 0.055
        tick = math.sin(i * 17.13) * math.sin(i * 73.7) * math.exp(-((beat * 2) % 1) * 24) * 0.012
        bed = lead + bass + tick
        if i < samples:
            sample = struct.unpack_from('<h', speech, 2 * i)[0] / 32768
        else:
            sample = 0
        master = min(1, t / 0.2, (SECONDS - t) / 0.3)
        sample = max(-1, min(1, (sample * 0.82 + bed) * master))
        pcm.extend(struct.pack('<h', int(sample * 30000)))
    with wave.open(str(path), 'wb') as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(rate)
        output.writeframes(pcm)


def ffmpeg_binary(name):
    installed = shutil.which(name)
    if installed:
        return Path(installed)
    local = ROOT / 'test/scratch' / name
    if local.is_file():
        return local
    raise FileNotFoundError(f'{name} is required to build or check the video')


def main():
    (ROOT / 'artifacts').mkdir(exist_ok=True)
    (ROOT / 'test/scratch').mkdir(parents=True, exist_ok=True)
    sprites, provenance = load_sprites()
    ffmpeg = ffmpeg_binary('ffmpeg')
    audio = ROOT / 'test/scratch/mix.wav'
    mix_audio(audio)
    output = ROOT / 'artifacts/video.mp4'
    command = [str(ffmpeg), '-hide_banner', '-loglevel', 'error', '-y',
               '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{W}x{H}',
               '-r', str(FPS), '-i', '-', '-i', str(audio),
               '-c:v', 'libx264', '-preset', 'medium', '-crf', '16',
               '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '160k',
               '-movflags', '+faststart', '-t', str(SECONDS), str(output)]
    process = subprocess.Popen(command, stdin=subprocess.PIPE)
    base = base_frame()
    try:
        for frame in range(FRAMES):
            c = Canvas(base)
            if frame < 84:
                scene_intro(c, sprites, frame)
                name = '01 / BRIEF'
            elif frame < 195:
                scene_build(c, sprites, frame)
                name = '02 / BUILD'
            elif frame < 300:
                scene_chain(c, sprites, frame)
                name = '03 / ON CHAIN'
            elif frame < 390:
                scene_supply(c, sprites, frame, provenance)
                name = '04 / HOME'
            elif frame < 468:
                scene_allocation(c, sprites, frame)
                name = '05 / HOME'
            elif frame < 612:
                scene_gallery(c, sprites, frame)
                name = '06 / GALLERY'
            elif frame < 705:
                scene_reveal(c, sprites, frame)
                name = '07 / REVEAL'
            elif frame < 810:
                scene_about(c, sprites, frame)
                name = '08 / ABOUT'
            else:
                scene_end(c, sprites, frame)
                name = '09 / SITE'
            common(c, frame, name)
            process.stdin.write(c.pixels)
            if frame % 150 == 0:
                print(f'frame {frame}/{FRAMES}', flush=True)
    finally:
        process.stdin.close()
    if process.wait() != 0:
        raise RuntimeError('FFmpeg failed')
    print(output)


if __name__ == '__main__':
    main()
