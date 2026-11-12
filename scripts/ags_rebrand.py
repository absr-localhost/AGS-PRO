#!/usr/bin/env python3
"""
AGS PRO rebrand for a personal fork of jub0t/Concat.

Safe by default: without --apply it only REPORTS what it would change.

What it changes
  * Visible app name "Concat" -> "AGS PRO"
      - .slint   : only inside "double quoted strings" (never identifiers)
      - .xml .iss .desktop .plist .rc .json : whole text, but never on
        copyright / SPDX lines, URLs, file names (Concat.exe, Concat-setup ...)
  * Android applicationId in build.gradle(.kts) (only that one field)
  * Icons / logos: every PNG/ICO whose file name contains icon|logo|mark|launcher
    is regenerated from your logo at the SAME pixel size
    (every .ico file too).

What it never touches
  * Rust code, crate names, Cargo.toml, .github/, models/, LICENSE*, TRADEMARK,
    CLA, THIRD_PARTY_NOTICES, README/docs and any copyright line
    (AGPL requires keeping the original copyright notices).
"""
import argparse
import re
import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
NEW_NAME = "AGS PRO"
BG = (11, 16, 32, 255)  # dark navy behind the white logo

SKIP_DIRS = {".git", ".github", ".claude", "target", "node_modules", "models",
             "test", "build", ".gradle", "docs", "scripts", "vendor", "patches"}
SKIP_NAME_PREFIX = ("LICENSE", "LICENSING", "TRADEMARK", "CLA", "THIRD_PARTY",
                    "CODE_", "SECURITY", "CONTRIBUTING", "README", "TRANSLATING",
                    "package", "Cargo", "flake")
TEXT_EXT = {".xml", ".iss", ".desktop", ".plist", ".rc", ".json"}
ICON_NAME = re.compile(r"(icon|logo|mark|launcher)", re.I)

# "Concat" as a standalone word, not part of a URL/path/file name/identifier.
WORD = re.compile(
    r"(?<![/\w.\-\\])Concat(?![\w\-/\\]|\.(?:exe|app|apk|msi|dmg|AppImage|desktop|so|dll|ico|png|json|toml|rs|slint)\b)"
)
SLINT_STR = re.compile(r'"(?:[^"\\\n]|\\.)*"')
KEEP_LINE = re.compile(r"copyright|spdx|license|https?://", re.I)


def skipped(path: Path) -> bool:
    rel = path.relative_to(ROOT)
    if any(p in SKIP_DIRS for p in rel.parts[:-1]):
        return True
    return rel.name.startswith(SKIP_NAME_PREFIX)


def all_files():
    for p in ROOT.rglob("*"):
        if p.is_file() and not skipped(p):
            yield p


# ---------------------------------------------------------------- text
def rename_text(text: str, slint: bool) -> str:
    if slint:
        return SLINT_STR.sub(
            lambda m: m.group(0) if KEEP_LINE.search(m.group(0))
            else WORD.sub(NEW_NAME, m.group(0)), text)
    out = []
    for line in text.splitlines(keepends=True):
        out.append(line if KEEP_LINE.search(line) else WORD.sub(NEW_NAME, line))
    return "".join(out)


def do_text(apply: bool, log: list):
    for p in all_files():
        ext = p.suffix.lower()
        if ext not in TEXT_EXT and ext != ".slint":
            continue
        if p.stat().st_size > 5_000_000:
            continue
        try:
            old = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        new = rename_text(old, slint=(ext == ".slint"))
        if new != old:
            n = len(WORD.findall(old)) if ext != ".slint" else "some"
            log.append(f"name   {p.relative_to(ROOT)}  ({n} replacement(s))")
            if apply:
                p.write_text(new, encoding="utf-8")


# ---------------------------------------------------------- applicationId
GRADLE_ID = re.compile(r'(applicationId\s*=?\s*)(["\'])app\.concat[^"\']*\2')


def do_app_id(app_id: str, apply: bool, log: list):
    if not app_id:
        return
    for p in ROOT.rglob("build.gradle*"):
        if any(x in SKIP_DIRS for x in p.relative_to(ROOT).parts[:-1]):
            continue
        old = p.read_text(encoding="utf-8", errors="ignore")
        new = GRADLE_ID.sub(lambda m: f'{m.group(1)}{m.group(2)}{app_id}{m.group(2)}', old)
        if new != old:
            log.append(f"app-id {p.relative_to(ROOT)} -> {app_id}")
            if apply:
                p.write_text(new, encoding="utf-8")


# ------------------------------------------------------------------ icons
def load_logo(path: Path) -> Image.Image:
    im = Image.open(path).convert("RGBA")
    # ignore the faint glow: crop to pixels that are clearly visible
    mask = im.getchannel("A").point(lambda a: 255 if a > 20 else 0)
    box = mask.getbbox()
    return im.crop(box) if box else im


def recolor(im: Image.Image, rgb):
    solid = Image.new("RGBA", im.size, rgb + (255,))
    solid.putalpha(im.getchannel("A"))
    return solid


def render(logo: Image.Image, w: int, h: int, name: str) -> Image.Image:
    n = name.lower()
    foreground = "foreground" in n or "monochrome" in n
    light = "light" in n
    launcher = "launcher" in n
    frac = 0.60 if foreground else 0.74
    canvas = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    mark = recolor(logo, (11, 16, 32)) if light else logo
    box = min(w, h) * frac
    s = box / max(mark.size)
    mark = mark.resize((max(1, round(mark.width * s)), max(1, round(mark.height * s))),
                       Image.LANCZOS)
    if not foreground and not light:
        if launcher:
            canvas.paste(BG, (0, 0, w, h))
        else:
            d = ImageDraw.Draw(canvas)
            d.rounded_rectangle((0, 0, w - 1, h - 1), radius=round(min(w, h) * 0.22), fill=BG)
    canvas.alpha_composite(mark, ((w - mark.width) // 2, (h - mark.height) // 2))
    return canvas


def do_icons(logo_path: Path, apply: bool, log: list):
    if not logo_path.exists():
        log.append(f"!! logo not found: {logo_path} (icons skipped)")
        return
    logo = load_logo(logo_path)
    for p in ROOT.rglob("*"):
        if not p.is_file() or p.resolve() == logo_path.resolve():
            continue
        rel = p.relative_to(ROOT)
        if any(x in SKIP_DIRS - {"docs", "scripts"} for x in rel.parts[:-1]):
            continue
        if p.suffix.lower() not in {".png", ".ico"} or p.name.endswith(".9.png"):
            continue
        if p.suffix.lower() != ".ico" and not ICON_NAME.search(p.name):
            continue
        if p.name == logo_path.name:
            continue
        try:
            with Image.open(p) as old:
                w, h = old.size
        except Exception:
            continue
        if w < 16 or h < 16 or w > 2048:
            continue
        log.append(f"icon   {rel}  {w}x{h}")
        if not apply:
            continue
        if p.suffix.lower() == ".ico":
            big = render(logo, 256, 256, p.name)
            big.save(p, format="ICO",
                     sizes=[(s, s) for s in (16, 24, 32, 48, 64, 128, 256)])
        else:
            render(logo, w, h,
