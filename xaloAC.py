# xaloAC-x410m1s0
"""
xaloAC — Desktop Command Center
Masaüstü dosya/arşiv/kod/medya yönetim aracı.
Komut: xaloAC
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import mimetypes
import os
import re
import shutil
import struct
import subprocess
import sys
import time
import zipfile
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

# ─── Windows UTF-8 console ───────────────────────────────────────────────────
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    os.system("")  # enable ANSI on older Windows

# ─── Colors (no external deps) ───────────────────────────────────────────────
class C:
    R = "\033[0m"
    B = "\033[1m"
    D = "\033[2m"
    RED = "\033[91m"
    GRN = "\033[92m"
    YEL = "\033[93m"
    BLU = "\033[94m"
    MAG = "\033[95m"
    CYN = "\033[96m"
    WHT = "\033[97m"
    GRY = "\033[90m"

    @staticmethod
    def ok(msg: str) -> str:
        return f"{C.GRN}[+]{C.R} {msg}"

    @staticmethod
    def err(msg: str) -> str:
        return f"{C.RED}[-]{C.R} {msg}"

    @staticmethod
    def info(msg: str) -> str:
        return f"{C.CYN}[*]{C.R} {msg}"

    @staticmethod
    def warn(msg: str) -> str:
        return f"{C.YEL}[!]{C.R} {msg}"

    @staticmethod
    def head(msg: str) -> str:
        return f"{C.B}{C.MAG}{msg}{C.R}"


# ─── Constants ───────────────────────────────────────────────────────────────
VERSION = "1.0.0"
TOOL_NAME = "xaloAC"
DEFAULT_ROOT = Path.home() / "Desktop"
CACHE_DIR = Path.home() / "tools" / "xaloAC" / ".cache"
INDEX_FILE = CACHE_DIR / "desktop_index.json"

# Skip heavy / system noise during deep scans
SKIP_DIR_NAMES = {
    "__pycache__", ".git", ".svn", "node_modules", ".venv", "venv",
    "Snapshots", "$RECYCLE.BIN", "System Volume Information",
}
SKIP_EXT_DEEP = {".vdi", ".vmdk", ".iso", ".img", ".dmg"}  # huge binaries

TEXT_EXTS = {
    ".txt", ".md", ".py", ".js", ".jsx", ".ts", ".tsx", ".json", ".yaml", ".yml",
    ".toml", ".ini", ".cfg", ".conf", ".log", ".csv", ".html", ".htm", ".css",
    ".xml", ".svg", ".lua", ".sh", ".bat", ".ps1", ".php", ".c", ".cpp", ".h",
    ".hpp", ".java", ".go", ".rs", ".rb", ".sql", ".env", ".gitignore",
    ".dockerfile", ".makefile", ".r", ".pl", ".swift", ".kt", ".dart",
    ".vue", ".svelte", ".scss", ".less", ".tex", ".rst", ".org",
    ".powershell", ".template", ".example", ".readme", ".url",
}
CODE_EXTS = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".lua", ".php", ".c", ".cpp", ".h",
    ".java", ".go", ".rs", ".rb", ".sh", ".ps1", ".bat", ".sql", ".html",
    ".css", ".scss", ".vue", ".swift", ".kt",
}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".ico", ".svg", ".tiff", ".tif"}
ARCHIVE_EXTS = {".zip", ".rar", ".7z", ".tar", ".gz", ".tgz", ".bz2", ".xz", ".apk"}
DOC_EXTS = {".pdf", ".docx", ".doc", ".xlsx", ".xls", ".pptx", ".ppt", ".odt", ".rtf"}
MEDIA_EXTS = {".mp4", ".mp3", ".wav", ".avi", ".mkv", ".mov", ".flac", ".ogg", ".webm", ".m4a"}
DATA_EXTS = {".csv", ".json", ".xml", ".sqlite", ".db", ".xlsx", ".xls"}

CATEGORY_MAP = {
    "text": TEXT_EXTS,
    "code": CODE_EXTS,
    "image": IMAGE_EXTS,
    "archive": ARCHIVE_EXTS,
    "document": DOC_EXTS,
    "media": MEDIA_EXTS,
    "data": DATA_EXTS,
}


# ─── Helpers ─────────────────────────────────────────────────────────────────
def human_size(n: int) -> str:
    if n < 0:
        return "?"
    units = ["B", "KB", "MB", "GB", "TB"]
    f = float(n)
    for u in units:
        if f < 1024.0:
            return f"{f:.1f}{u}" if u != "B" else f"{int(f)}B"
        f /= 1024.0
    return f"{f:.1f}PB"


def safe_stat(p: Path) -> Optional[os.stat_result]:
    try:
        return p.stat()
    except (OSError, PermissionError):
        return None


def is_probably_text(path: Path, sample: int = 2048) -> bool:
    ext = path.suffix.lower()
    if ext in TEXT_EXTS:
        return True
    if ext in IMAGE_EXTS | ARCHIVE_EXTS | MEDIA_EXTS | {".exe", ".dll", ".so", ".bin", ".pyc", ".apk", ".vdi"}:
        return False
    try:
        with open(path, "rb") as f:
            chunk = f.read(sample)
        if b"\x00" in chunk:
            return False
        chunk.decode("utf-8")
        return True
    except Exception:
        return False


def read_text_preview(path: Path, max_bytes: int = 64_000, max_lines: int = 80) -> str:
    try:
        with open(path, "rb") as f:
            raw = f.read(max_bytes)
        for enc in ("utf-8", "utf-8-sig", "cp1254", "latin-1"):
            try:
                text = raw.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        else:
            text = raw.decode("utf-8", errors="replace")
        lines = text.splitlines()
        out = "\n".join(lines[:max_lines])
        if len(lines) > max_lines:
            out += f"\n{C.GRY}... ({len(lines) - max_lines} satır daha, toplam ~{len(lines)}+){C.R}"
        return out
    except Exception as e:
        return f"{C.RED}Okunamadı: {e}{C.R}"


def file_hash(path: Path, algo: str = "sha256", chunk: int = 1 << 20) -> str:
    h = hashlib.new(algo)
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def category_of(ext: str) -> str:
    """Priority: code > data > document > image > archive > media > text."""
    ext = ext.lower()
    if not ext:
        return "noext"
    # ordered so code/data win over broad text set
    for cat in ("code", "data", "document", "image", "archive", "media", "text"):
        if ext in CATEGORY_MAP[cat]:
            return cat
    return "other"


def open_with_default(path: Path) -> None:
    path = path.resolve()
    if not path.exists():
        print(C.err(f"Bulunamadı: {path}"))
        return
    try:
        if sys.platform == "win32":
            os.startfile(str(path))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])
        print(C.ok(f"Açıldı: {path.name}"))
    except Exception as e:
        print(C.err(f"Açılamadı: {e}"))


def clear_screen() -> None:
    os.system("cls" if sys.platform == "win32" else "clear")


def pause(msg: str = "Devam için Enter...") -> None:
    try:
        input(f"\n{C.GRY}{msg}{C.R}")
    except (EOFError, KeyboardInterrupt):
        print()


def banner() -> None:
    art = f"""
{C.CYN}{C.B}╔══════════════════════════════════════════════════════════════╗
║  ██╗  ██╗ █████╗ ██╗      ██████╗ ███╗   ███╗██╗███████╗ ██████╗  ║
║  ╚██╗██╔╝██╔══██╗██║     ██╔═══██╗████╗ ████║██║██╔════╝██╔═══██╗ ║
║   ╚███╔╝ ███████║██║     ██║   ██║██╔████╔██║██║███████╗██║   ██║ ║
║   ██╔██╗ ██╔══██║██║     ██║   ██║██║╚██╔╝██║██║╚════██║██║   ██║ ║
║  ██╔╝ ██╗██║  ██║███████╗╚██████╔╝██║ ╚═╝ ██║██║███████║╚██████╔╝ ║
║  ╚═╝  ╚═╝╚═╝  ╚═╝╚══════╝ ╚═════╝ ╚═╝     ╚═╝╚═╝╚══════╝ ╚═════╝  ║
╠══════════════════════════════════════════════════════════════╣
║  {C.WHT}xaloAC Desktop Command Center  v{VERSION}  ·  tek tool, her dosya{C.CYN}     ║
║  {C.GRY}root: {str(DEFAULT_ROOT)[:48]:<48}{C.CYN} ║
╚══════════════════════════════════════════════════════════════╝{C.R}
"""
    print(art)


# ─── Index / Scanner ─────────────────────────────────────────────────────────
@dataclass
class FileRec:
    path: str
    name: str
    ext: str
    size: int
    mtime: float
    category: str
    is_dir: bool = False

    def rel(self, root: Path) -> str:
        try:
            return str(Path(self.path).relative_to(root))
        except ValueError:
            return self.path


class DesktopIndex:
    def __init__(self, root: Path = DEFAULT_ROOT):
        self.root = root.resolve()
        self.files: List[FileRec] = []
        self.dirs: List[FileRec] = []
        self.built_at: Optional[str] = None
        self.errors: int = 0

    def scan(self, deep: bool = True, progress: bool = True) -> "DesktopIndex":
        self.files.clear()
        self.dirs.clear()
        self.errors = 0
        t0 = time.perf_counter()
        count = 0

        if not self.root.exists():
            print(C.err(f"Kök yok: {self.root}"))
            return self

        stack = [self.root]
        while stack:
            current = stack.pop()
            try:
                with os.scandir(current) as it:
                    for entry in it:
                        try:
                            name = entry.name
                            if name in SKIP_DIR_NAMES or name.startswith("."):
                                if name not in (".gitignore", ".env"):
                                    if entry.is_dir(follow_symlinks=False):
                                        continue
                            if entry.is_dir(follow_symlinks=False):
                                p = Path(entry.path)
                                st = entry.stat(follow_symlinks=False)
                                self.dirs.append(FileRec(
                                    path=str(p), name=name, ext="", size=0,
                                    mtime=st.st_mtime, category="dir", is_dir=True,
                                ))
                                if deep:
                                    stack.append(p)
                            elif entry.is_file(follow_symlinks=False):
                                p = Path(entry.path)
                                st = entry.stat(follow_symlinks=False)
                                ext = p.suffix.lower()
                                self.files.append(FileRec(
                                    path=str(p), name=name, ext=ext,
                                    size=st.st_size, mtime=st.st_mtime,
                                    category=category_of(ext),
                                ))
                                count += 1
                                if progress and count % 200 == 0:
                                    print(f"\r{C.CYN}[*] taranıyor... {count} dosya   {C.R}", end="", flush=True)
                        except (OSError, PermissionError):
                            self.errors += 1
            except (OSError, PermissionError):
                self.errors += 1

        if progress and count:
            print(f"\r{C.ok(f'Tarama bitti: {count} dosya, {len(self.dirs)} klasör')}  "
                  f"{C.GRY}({time.perf_counter() - t0:.2f}s, err={self.errors}){C.R}")
        self.built_at = datetime.now().isoformat(timespec="seconds")
        return self

    def save(self, path: Path = INDEX_FILE) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "root": str(self.root),
            "built_at": self.built_at,
            "files": [asdict(f) for f in self.files],
            "dirs": [asdict(d) for d in self.dirs],
        }
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    def load(self, path: Path = INDEX_FILE) -> bool:
        if not path.exists():
            return False
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            cached_root = data.get("root")
            if cached_root is not None:
                if Path(cached_root).resolve() != self.root.resolve():
                    return False
            self.root = Path(cached_root) if cached_root else self.root
            self.built_at = data.get("built_at")
            self.files = [FileRec(**f) for f in data.get("files", [])]
            self.dirs = [FileRec(**d) for d in data.get("dirs", [])]
            return True
        except Exception:
            return False

    def ensure(self, force: bool = False) -> "DesktopIndex":
        if not force and self.load() and self.files:
            age = time.time() - INDEX_FILE.stat().st_mtime if INDEX_FILE.exists() else 9999
            if age < 300:  # 5 min cache
                return self
        self.scan()
        self.save()
        return self

    def by_ext(self) -> Counter:
        return Counter(f.ext or "(yok)" for f in self.files)

    def by_category(self) -> Counter:
        return Counter(f.category for f in self.files)

    def total_size(self) -> int:
        return sum(f.size for f in self.files)

    def largest(self, n: int = 20) -> List[FileRec]:
        return sorted(self.files, key=lambda f: f.size, reverse=True)[:n]

    def newest(self, n: int = 20) -> List[FileRec]:
        return sorted(self.files, key=lambda f: f.mtime, reverse=True)[:n]

    def filter_ext(self, *exts: str) -> List[FileRec]:
        want = {e if e.startswith(".") else f".{e}" for e in exts}
        want = {e.lower() for e in want}
        return [f for f in self.files if f.ext in want]

    def filter_cat(self, cat: str) -> List[FileRec]:
        return [f for f in self.files if f.category == cat.lower()]

    def search_name(self, query: str, regex: bool = False) -> List[FileRec]:
        if regex:
            try:
                rx = re.compile(query, re.I)
            except re.error as e:
                print(C.err(f"Regex hatası: {e}"))
                return []
            return [f for f in self.files if rx.search(f.name) or rx.search(f.path)]
        q = query.lower()
        return [f for f in self.files if q in f.name.lower() or q in f.path.lower()]


# ─── Content search ──────────────────────────────────────────────────────────
def content_search(
    files: Sequence[FileRec],
    query: str,
    max_hits: int = 50,
    max_file_mb: float = 8.0,
    workers: int = 8,
) -> List[Tuple[str, int, str]]:
    """Return list of (path, line_no, line_snippet)."""
    q = query.lower()
    max_bytes = int(max_file_mb * 1024 * 1024)
    hits: List[Tuple[str, int, str]] = []
    lock_count = [0]

    def scan_one(rec: FileRec) -> List[Tuple[str, int, str]]:
        if lock_count[0] >= max_hits:
            return []
        if rec.size > max_bytes or rec.size == 0:
            return []
        p = Path(rec.path)
        if not is_probably_text(p):
            return []
        local: List[Tuple[str, int, str]] = []
        try:
            with open(p, "r", encoding="utf-8", errors="replace") as f:
                for i, line in enumerate(f, 1):
                    if q in line.lower():
                        local.append((rec.path, i, line.rstrip()[:200]))
                        if len(local) >= 5:  # per-file cap
                            break
        except Exception:
            return []
        return local

    candidates = [f for f in files if f.ext in TEXT_EXTS or f.category in ("text", "code", "data")]
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(scan_one, f): f for f in candidates}
        for fut in as_completed(futs):
            for h in fut.result():
                hits.append(h)
                lock_count[0] += 1
                if lock_count[0] >= max_hits:
                    break
            if lock_count[0] >= max_hits:
                break
    return hits[:max_hits]


# ─── Viewers ─────────────────────────────────────────────────────────────────
def png_info(path: Path) -> str:
    try:
        with open(path, "rb") as f:
            sig = f.read(8)
            if sig != b"\x89PNG\r\n\x1a\n":
                return "PNG imzası yok"
            length = struct.unpack(">I", f.read(4))[0]
            ctype = f.read(4)
            if ctype != b"IHDR":
                return "IHDR yok"
            data = f.read(13)
            w, h, bit_depth, color_type = struct.unpack(">IIBB", data[:10])
            return f"PNG  {w}x{h}  bit={bit_depth}  color_type={color_type}  size={human_size(path.stat().st_size)}"
    except Exception as e:
        return f"PNG okunamadı: {e}"


def jpeg_info(path: Path) -> str:
    try:
        with open(path, "rb") as f:
            if f.read(2) != b"\xff\xd8":
                return "JPEG imzası yok"
            while True:
                b = f.read(1)
                if not b:
                    break
                if b != b"\xff":
                    continue
                marker = f.read(1)
                if marker in (b"\xc0", b"\xc1", b"\xc2"):
                    f.read(3)
                    h, w = struct.unpack(">HH", f.read(4))
                    return f"JPEG  {w}x{h}  size={human_size(path.stat().st_size)}"
                elif marker in (b"\xd9", b"\xda"):
                    break
                else:
                    seglen = struct.unpack(">H", f.read(2))[0]
                    f.read(seglen - 2)
        return f"JPEG  size={human_size(path.stat().st_size)} (boyut okunamadı)"
    except Exception as e:
        return f"JPEG okunamadı: {e}"


def pdf_info(path: Path) -> str:
    lines = []
    try:
        size = path.stat().st_size
        lines.append(f"PDF  size={human_size(size)}")
        with open(path, "rb") as f:
            head = f.read(min(size, 512_000))
        if not head.startswith(b"%PDF"):
            lines.append("Uyarı: %PDF imzası yok")
            return "\n".join(lines)
        # page count heuristic
        pages = len(re.findall(rb"/Type\s*/Page[^s]", head))
        if pages:
            lines.append(f"Sayfa (yaklaşık, ilk 512KB): {pages}+")
        # title
        m = re.search(rb"/Title\s*\(([^)]{1,120})\)", head)
        if m:
            try:
                lines.append(f"Title: {m.group(1).decode('utf-8', errors='replace')}")
            except Exception:
                pass
        # try extract a bit of text
        text_bits = re.findall(rb"\(([\x20-\x7E\xC0-\xFF]{4,80})\)", head)
        if text_bits:
            sample = " | ".join(t.decode("latin-1", errors="replace")[:40] for t in text_bits[:5])
            lines.append(f"Metin örneği: {sample}")
    except Exception as e:
        lines.append(f"Hata: {e}")
    return "\n".join(lines)


def zip_list(path: Path, limit: int = 40) -> str:
    try:
        with zipfile.ZipFile(path, "r") as zf:
            infos = zf.infolist()
            total_u = sum(i.file_size for i in infos)
            total_c = sum(i.compress_size for i in infos)
            lines = [
                f"ZIP/APK  entries={len(infos)}  compressed={human_size(total_c)}  "
                f"uncompressed={human_size(total_u)}",
                f"{'NAME':<50} {'SIZE':>10} {'METHOD'}",
                "-" * 72,
            ]
            for i in infos[:limit]:
                name = i.filename
                if len(name) > 50:
                    name = name[:47] + "..."
                lines.append(f"{name:<50} {human_size(i.file_size):>10} {i.compress_type}")
            if len(infos) > limit:
                lines.append(f"... +{len(infos) - limit} daha")
            return "\n".join(lines)
    except zipfile.BadZipFile:
        return "Geçersiz veya bozuk ZIP"
    except Exception as e:
        return f"ZIP hatası: {e}"


def zip_extract(path: Path, dest: Optional[Path] = None) -> Path:
    dest = dest or path.with_suffix("")
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "r") as zf:
        zf.extractall(dest)
    return dest


def _find_7z() -> Optional[str]:
    for cand in (
        shutil.which("7z"),
        shutil.which("7za"),
        r"C:\Program Files\7-Zip\7z.exe",
        r"C:\Program Files (x86)\7-Zip\7z.exe",
    ):
        if cand and Path(cand).exists():
            return cand
    return None


def archive_list(path: Path, limit: int = 40) -> str:
    """List zip/apk natively; rar/7z via 7-Zip if installed."""
    ext = path.suffix.lower()
    if ext in {".zip", ".apk", ".jar"}:
        return zip_list(path, limit=limit)
    seven = _find_7z()
    if not seven:
        return (f"{ext} arşivi için 7-Zip gerekli (https://www.7-zip.org/). "
                f"ZIP/APK için harici araç gerekmez.")
    try:
        r = subprocess.run(
            [seven, "l", "-ba", str(path)],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=60,
        )
        out = (r.stdout or r.stderr or "").strip()
        lines = out.splitlines()
        head = f"7z list  {path.name}  ({human_size(path.stat().st_size)})"
        body = "\n".join(lines[:limit])
        if len(lines) > limit:
            body += f"\n... +{len(lines) - limit} satır"
        return f"{head}\n{body}" if body else head + "\n(boş çıktı)"
    except Exception as e:
        return f"Arşiv listesi hatası: {e}"


def archive_extract(path: Path, dest: Optional[Path] = None) -> Path:
    ext = path.suffix.lower()
    dest = dest or path.with_suffix("")
    if ext in {".zip", ".apk", ".jar"}:
        return zip_extract(path, dest)
    seven = _find_7z()
    if not seven:
        raise RuntimeError(f"{ext} çıkarmak için 7-Zip gerekli")
    dest.mkdir(parents=True, exist_ok=True)
    subprocess.run([seven, "x", f"-o{dest}", "-y", str(path)], check=True, timeout=600)
    return dest


def csv_preview(path: Path, rows: int = 12) -> str:
    try:
        with open(path, "r", encoding="utf-8", errors="replace", newline="") as f:
            # sniff
            sample = f.read(4096)
            f.seek(0)
            try:
                dialect = csv.Sniffer().sniff(sample)
            except csv.Error:
                dialect = csv.excel
            reader = csv.reader(f, dialect)
            lines = []
            for i, row in enumerate(reader):
                if i >= rows:
                    lines.append(f"... (devamı var)")
                    break
                cells = [c[:40] for c in row[:12]]
                lines.append(" | ".join(cells))
            return "\n".join(lines) if lines else "(boş CSV)"
    except Exception as e:
        return f"CSV hatası: {e}"


def view_file(path: Path) -> None:
    path = path.expanduser().resolve()
    if not path.exists():
        print(C.err(f"Yok: {path}"))
        return
    st = safe_stat(path)
    ext = path.suffix.lower()
    print(C.head(f"\n══ VIEW  {path.name} ══"))
    print(C.info(f"path : {path}"))
    if st:
        print(C.info(f"size : {human_size(st.st_size)}  mtime: "
                     f"{datetime.fromtimestamp(st.st_mtime).strftime('%Y-%m-%d %H:%M:%S')}"))
        print(C.info(f"ext  : {ext or '(yok)'}  mime: {mimetypes.guess_type(str(path))[0] or '?'}  "
                     f"cat: {category_of(ext)}"))
    print(f"{C.GRY}{'─' * 60}{C.R}")

    if path.is_dir():
        kids = list(path.iterdir())[:50]
        for k in kids:
            mark = "📁" if k.is_dir() else "📄"
            print(f"  {mark} {k.name}")
        if len(list(path.iterdir())) > 50:
            print(f"  ... +daha fazla")
        return

    if ext in {".png"}:
        print(png_info(path))
        return
    if ext in {".jpg", ".jpeg"}:
        print(jpeg_info(path))
        return
    if ext == ".pdf":
        print(pdf_info(path))
        return
    if ext in {".zip", ".apk", ".jar", ".rar", ".7z", ".tar", ".gz", ".tgz"}:
        print(archive_list(path))
        return
    if ext == ".csv":
        print(csv_preview(path))
        return
    if ext in IMAGE_EXTS:
        print(f"Görsel: {ext}  size={human_size(st.st_size if st else 0)}")
        print(C.info("Varsayılan uygulama ile açmak için: xaloAC open <dosya>"))
        return
    if ext in MEDIA_EXTS:
        print(f"Medya: {ext}  size={human_size(st.st_size if st else 0)}")
        return
    if is_probably_text(path) or ext in TEXT_EXTS:
        print(read_text_preview(path))
        return
    # binary fallback: hex head
    try:
        with open(path, "rb") as f:
            data = f.read(256)
        print(C.warn("İkili dosya — hex önizleme (256 bayt):"))
        for i in range(0, len(data), 16):
            chunk = data[i:i + 16]
            hx = " ".join(f"{b:02x}" for b in chunk)
            asc = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
            print(f"  {i:04x}  {hx:<48}  {asc}")
    except Exception as e:
        print(C.err(str(e)))


# ─── Duplicates ──────────────────────────────────────────────────────────────
def find_duplicates(files: Sequence[FileRec], min_size: int = 1024) -> Dict[str, List[FileRec]]:
    by_size: Dict[int, List[FileRec]] = defaultdict(list)
    for f in files:
        if f.size >= min_size:
            by_size[f.size].append(f)
    candidates = {s: lst for s, lst in by_size.items() if len(lst) > 1}
    groups: Dict[str, List[FileRec]] = defaultdict(list)
    for size, lst in candidates.items():
        hashes: Dict[str, List[FileRec]] = defaultdict(list)
        for rec in lst:
            try:
                # quick partial hash first
                p = Path(rec.path)
                with open(p, "rb") as fh:
                    head = fh.read(65536)
                h = hashlib.md5(head + str(size).encode()).hexdigest()
                # full hash only if head collides
                hashes[h].append(rec)
            except Exception:
                continue
        for h, group in hashes.items():
            if len(group) < 2:
                continue
            # verify full hash
            full: Dict[str, List[FileRec]] = defaultdict(list)
            for rec in group:
                try:
                    full[file_hash(Path(rec.path), "md5")].append(rec)
                except Exception:
                    continue
            for fh, g in full.items():
                if len(g) > 1:
                    groups[fh] = g
    return groups


# ─── Stats ───────────────────────────────────────────────────────────────────
def print_stats(idx: DesktopIndex) -> None:
    print(C.head("\n══ MASAÜSTÜ İSTATİSTİK ══"))
    print(C.info(f"Kök     : {idx.root}"))
    print(C.info(f"İndeks  : {idx.built_at or 'şimdi'}"))
    print(C.info(f"Dosya   : {len(idx.files)}"))
    print(C.info(f"Klasör  : {len(idx.dirs)}"))
    print(C.info(f"Toplam  : {human_size(idx.total_size())}"))
    print()
    print(C.head("Kategoriye göre:"))
    for cat, n in idx.by_category().most_common():
        bar = "█" * min(40, n // max(1, len(idx.files) // 40 or 1))
        print(f"  {cat:<12} {n:>5}  {C.CYN}{bar}{C.R}")
    print()
    print(C.head("En sık uzantılar (top 20):"))
    for ext, n in idx.by_ext().most_common(20):
        print(f"  {ext:<12} {n:>5}")
    print()
    print(C.head("En büyük 10 dosya:"))
    for f in idx.largest(10):
        print(f"  {human_size(f.size):>10}  {f.name[:60]}")
    print()
    print(C.head("En yeni 10 dosya:"))
    for f in idx.newest(10):
        ts = datetime.fromtimestamp(f.mtime).strftime("%Y-%m-%d %H:%M")
        print(f"  {ts}  {f.name[:55]}")


# ─── Tree ────────────────────────────────────────────────────────────────────
def print_tree(root: Path, max_depth: int = 2, max_entries: int = 80) -> None:
    root = root.resolve()
    print(C.head(f"\n══ TREE  {root} ══"))
    shown = [0]

    def walk(p: Path, prefix: str, depth: int) -> None:
        if shown[0] >= max_entries or depth > max_depth:
            return
        try:
            entries = sorted(p.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
        except (OSError, PermissionError):
            return
        # filter skip
        entries = [e for e in entries if e.name not in SKIP_DIR_NAMES]
        for i, e in enumerate(entries):
            if shown[0] >= max_entries:
                print(prefix + "└── ...")
                return
            last = i == len(entries) - 1
            branch = "└── " if last else "├── "
            mark = f"{C.BLU}{e.name}/{C.R}" if e.is_dir() else e.name
            print(f"{prefix}{branch}{mark}")
            shown[0] += 1
            if e.is_dir() and depth < max_depth:
                walk(e, prefix + ("    " if last else "│   "), depth + 1)

    print(str(root))
    walk(root, "", 0)


# ─── Organize (copy/move by category into subfolders) ────────────────────────
def organize_plan(idx: DesktopIndex, only_top: bool = True) -> Dict[str, List[FileRec]]:
    plan: Dict[str, List[FileRec]] = defaultdict(list)
    for f in idx.files:
        p = Path(f.path)
        if only_top and p.parent.resolve() != idx.root.resolve():
            continue
        if f.category in ("other", "noext"):
            plan["_diger"].append(f)
        else:
            plan[f.category].append(f)
    return plan


def organize_run(idx: DesktopIndex, dry_run: bool = True, move: bool = False) -> None:
    plan = organize_plan(idx, only_top=True)
    base = idx.root / "_xaloAC_sorted"
    print(C.head(f"\n══ ORGANIZE  {'(DRY-RUN)' if dry_run else '(APPLY)'} ══"))
    total = 0
    for cat, files in sorted(plan.items()):
        dest = base / cat
        print(f"  {cat}: {len(files)} dosya → {dest}")
        total += len(files)
        if not dry_run:
            dest.mkdir(parents=True, exist_ok=True)
            for rec in files:
                src = Path(rec.path)
                target = dest / src.name
                if target.exists():
                    stem, suf = src.stem, src.suffix
                    target = dest / f"{stem}_{int(time.time())}{suf}"
                try:
                    if move:
                        shutil.move(str(src), str(target))
                    else:
                        shutil.copy2(str(src), str(target))
                except Exception as e:
                    print(C.err(f"  {src.name}: {e}"))
    print(C.ok(f"Toplam {total} dosya planlandı.") +
          (f" {'Taşındı' if move else 'Kopyalandı'} → {base}" if not dry_run else
           f"\n{C.warn('Uygulamak için: xaloAC organize --apply [--move]')}"))


# ─── Export ──────────────────────────────────────────────────────────────────
def export_index(idx: DesktopIndex, fmt: str = "csv", out: Optional[Path] = None) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    if fmt == "json":
        out = out or CACHE_DIR / f"export_{ts}.json"
        data = [asdict(f) for f in idx.files]
        out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        out = out or CACHE_DIR / f"export_{ts}.csv"
        with open(out, "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["path", "name", "ext", "size", "mtime", "category"])
            for rec in idx.files:
                w.writerow([
                    rec.path, rec.name, rec.ext, rec.size,
                    datetime.fromtimestamp(rec.mtime).isoformat(timespec="seconds"),
                    rec.category,
                ])
    print(C.ok(f"Dışa aktarıldı: {out}"))
    return out


# ─── Hash command ────────────────────────────────────────────────────────────
def cmd_hash(paths: Sequence[str], algo: str = "sha256") -> None:
    for s in paths:
        p = Path(s)
        if not p.is_absolute():
            # try desktop
            cand = DEFAULT_ROOT / s
            if cand.exists():
                p = cand
        if not p.exists():
            print(C.err(f"Yok: {s}"))
            continue
        if p.is_dir():
            print(C.warn(f"Klasör atlandı: {p}"))
            continue
        t0 = time.perf_counter()
        try:
            dig = file_hash(p, algo)
            print(f"{C.GRN}{algo}{C.R}  {dig}  {C.GRY}{p.name}  ({human_size(p.stat().st_size)}, "
                  f"{time.perf_counter() - t0:.2f}s){C.R}")
        except Exception as e:
            print(C.err(f"{p}: {e}"))


# ─── Run python script from desktop ──────────────────────────────────────────
def list_scripts(idx: DesktopIndex) -> List[FileRec]:
    return sorted(idx.filter_ext(".py"), key=lambda f: f.name.lower())


def run_script(path: Path, args: Sequence[str] = ()) -> int:
    path = path.resolve()
    if not path.exists() or path.suffix.lower() != ".py":
        print(C.err("Geçerli bir .py dosyası değil"))
        return 1
    print(C.info(f"Çalıştırılıyor: {path}"))
    print(C.GRY + "─" * 50 + C.R)
    try:
        r = subprocess.run([sys.executable, str(path), *args], cwd=str(path.parent))
        return r.returncode
    except KeyboardInterrupt:
        print(C.warn("Kesildi"))
        return 130


# ─── Resolve path helper ─────────────────────────────────────────────────────
def resolve_user_path(s: str, idx: Optional[DesktopIndex] = None) -> Path:
    p = Path(s)
    if p.exists():
        return p.resolve()
    desk = DEFAULT_ROOT / s
    if desk.exists():
        return desk.resolve()
    # fuzzy by name from index
    if idx:
        matches = [f for f in idx.files if f.name.lower() == s.lower()]
        if not matches:
            matches = [f for f in idx.files if s.lower() in f.name.lower()]
        if len(matches) == 1:
            return Path(matches[0].path)
        if len(matches) > 1:
            print(C.warn(f"{len(matches)} eşleşme, ilki kullanılıyor:"))
            for m in matches[:8]:
                print(f"  · {m.path}")
            return Path(matches[0].path)
    return p


# ─── Interactive menu ────────────────────────────────────────────────────────
def interactive(idx: DesktopIndex) -> None:
    while True:
        clear_screen()
        banner()
        if not idx.files:
            print(C.warn("İndeks boş — tarama başlatılıyor..."))
            idx.scan()
            idx.save()
        print(f"  {C.GRY}dosya={len(idx.files)}  klasör={len(idx.dirs)}  "
              f"boyut={human_size(idx.total_size())}  cache={idx.built_at}{C.R}\n")
        menu = f"""
{C.B}  [1]{C.R}  İstatistikler          {C.B}[2]{C.R}  İsimle ara
{C.B}  [3]{C.R}  İçerikte ara           {C.B}[4]{C.R}  Dosya önizle (view)
{C.B}  [5]{C.R}  Uzantıya göre liste    {C.B}[6]{C.R}  En büyük / en yeni
{C.B}  [7]{C.R}  ZIP listele / çıkar    {C.B}[8]{C.R}  Hash hesapla
{C.B}  [9]{C.R}  Yinelenen dosyalar     {C.B}[10]{C.R} Klasör ağacı
{C.B} [11]{C.R}  Organize (plan)        {C.B}[12]{C.R} Export CSV/JSON
{C.B} [13]{C.R}  Python scriptler       {C.B}[14]{C.R} Dosyayı aç
{C.B} [15]{C.R}  Yeniden tara           {C.B}[0]{C.R}  Çıkış
"""
        print(menu)
        try:
            choice = input(f"{C.CYN}xaloAC>{C.R} ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nbye.")
            return

        try:
            if choice in ("0", "q", "exit", "quit"):
                print(C.ok("Görüşürüz."))
                return
            elif choice == "1":
                print_stats(idx)
                pause()
            elif choice == "2":
                q = input("Arama (isim): ").strip()
                if q:
                    hits = idx.search_name(q)
                    print(C.info(f"{len(hits)} sonuç"))
                    for h in hits[:40]:
                        print(f"  {human_size(h.size):>9}  {h.rel(idx.root)}")
                    if len(hits) > 40:
                        print(f"  ... +{len(hits) - 40}")
                pause()
            elif choice == "3":
                q = input("İçerik arama: ").strip()
                if q:
                    print(C.info("Taranıyor (metin dosyaları)..."))
                    hits = content_search(idx.files, q)
                    print(C.info(f"{len(hits)} satır"))
                    for path, ln, snip in hits:
                        print(f"  {C.YEL}{Path(path).name}:{ln}{C.R}  {snip[:100]}")
                pause()
            elif choice == "4":
                s = input("Dosya adı/yolu: ").strip()
                if s:
                    view_file(resolve_user_path(s, idx))
                pause()
            elif choice == "5":
                ext = input("Uzantı (örn py, html, zip): ").strip()
                if ext:
                    hits = idx.filter_ext(ext)
                    print(C.info(f"{len(hits)} dosya"))
                    for h in hits[:50]:
                        print(f"  {human_size(h.size):>9}  {h.rel(idx.root)}")
                pause()
            elif choice == "6":
                print(C.head("En büyükler:"))
                for f in idx.largest(15):
                    print(f"  {human_size(f.size):>10}  {f.rel(idx.root)[:70]}")
                print(C.head("\nEn yeniler:"))
                for f in idx.newest(15):
                    ts = datetime.fromtimestamp(f.mtime).strftime("%m-%d %H:%M")
                    print(f"  {ts}  {f.rel(idx.root)[:70]}")
                pause()
            elif choice == "7":
                s = input("Arşiv (zip/rar/7z/apk): ").strip()
                if s:
                    p = resolve_user_path(s, idx)
                    print(archive_list(p))
                    do = input("Çıkar? [e/H]: ").strip().lower()
                    if do == "e":
                        try:
                            dest = archive_extract(p)
                            print(C.ok(f"Çıkarıldı → {dest}"))
                        except Exception as e:
                            print(C.err(str(e)))
                pause()
            elif choice == "8":
                s = input("Dosya: ").strip()
                if s:
                    cmd_hash([str(resolve_user_path(s, idx))])
                pause()
            elif choice == "9":
                print(C.info("Yinelenenler aranıyor (md5)..."))
                groups = find_duplicates(idx.files)
                if not groups:
                    print(C.ok("Yinelenen bulunamadı (min 1KB)."))
                else:
                    print(C.warn(f"{len(groups)} grup"))
                    for h, g in list(groups.items())[:20]:
                        print(f"\n  hash={h[:12]}...  size={human_size(g[0].size)}")
                        for rec in g:
                            print(f"    · {rec.rel(idx.root)}")
                pause()
            elif choice == "10":
                print_tree(idx.root, max_depth=2)
                pause()
            elif choice == "11":
                organize_run(idx, dry_run=True)
                pause()
            elif choice == "12":
                fmt = input("Format [csv/json]: ").strip().lower() or "csv"
                export_index(idx, fmt=fmt if fmt in ("csv", "json") else "csv")
                pause()
            elif choice == "13":
                scripts = list_scripts(idx)
                # only top-level desktop scripts first
                top = [s for s in scripts if Path(s.path).parent.resolve() == idx.root.resolve()]
                show = top or scripts[:30]
                print(C.head(f"Python scriptler ({len(show)} gösteriliyor / {len(scripts)} toplam):"))
                for i, s in enumerate(show, 1):
                    print(f"  {i:>3}. {s.name:<40} {human_size(s.size)}")
                sel = input("Çalıştır No (boş=iptal): ").strip()
                if sel.isdigit() and 1 <= int(sel) <= len(show):
                    run_script(Path(show[int(sel) - 1].path))
                pause()
            elif choice == "14":
                s = input("Açılacak dosya: ").strip()
                if s:
                    open_with_default(resolve_user_path(s, idx))
                pause()
            elif choice == "15":
                idx.scan()
                idx.save()
                pause()
            else:
                print(C.warn("Geçersiz seçim"))
                time.sleep(0.6)
        except KeyboardInterrupt:
            print()
            pause()
        except Exception as e:
            print(C.err(f"Hata: {e}"))
            pause()


# ─── CLI ─────────────────────────────────────────────────────────────────────
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="xaloAC",
        description="xaloAC — Masaüstü Command Center (dosya, arşiv, arama, hash, organize)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Örnekler:
  xaloAC                    Etkileşimli menü
  xaloAC scan               Masaüstünü tara ve indeksle
  xaloAC stats              İstatistikler
  xaloAC find steam         İsimle ara
  xaloAC grep password      İçerikte ara
  xaloAC ls py              .py dosyalarını listele
  xaloAC view dosya.txt     Önizle
  xaloAC zip list a.zip     ZIP içeriği
  xaloAC zip extract a.zip  ZIP çıkar
  xaloAC hash secret.png    SHA256
  xaloAC open CV.html       Varsayılan app ile aç
  xaloAC tree               Klasör ağacı
  xaloAC dupes              Yinelenen dosyalar
  xaloAC export --fmt csv   İndeksi dışa aktar
  xaloAC organize           Organize planı (dry-run)
  xaloAC scripts            Masaüstü .py listesi
""",
    )
    p.add_argument("-r", "--root", type=str, default=str(DEFAULT_ROOT),
                   help="Kök dizin (varsayılan: Desktop)")
    p.add_argument("-v", "--version", action="version", version=f"%(prog)s {VERSION}")
    p.add_argument("--fresh", action="store_true", help="Önbelleği yok say, yeniden tara")

    sub = p.add_subparsers(dest="cmd")

    sub.add_parser("scan", help="Masaüstünü tara")
    sub.add_parser("stats", help="İstatistikler")
    sub.add_parser("menu", help="Etkileşimli menü")
    sub.add_parser("tree", help="Klasör ağacı")
    sub.add_parser("dupes", help="Yinelenen dosyalar")
    sub.add_parser("scripts", help="Python script listesi")

    pf = sub.add_parser("find", help="İsimle ara")
    pf.add_argument("query")
    pf.add_argument("--re", action="store_true", help="Regex")

    pg = sub.add_parser("grep", help="İçerikte ara")
    pg.add_argument("query")
    pg.add_argument("--max", type=int, default=50)

    pl = sub.add_parser("ls", help="Uzantıya göre liste")
    pl.add_argument("ext", help="Uzantı: py, html, zip...")
    pl.add_argument("-n", type=int, default=100)

    pv = sub.add_parser("view", help="Dosya önizle")
    pv.add_argument("path")

    po = sub.add_parser("open", help="Varsayılan app ile aç")
    po.add_argument("path")

    ph = sub.add_parser("hash", help="Hash hesapla")
    ph.add_argument("paths", nargs="+")
    ph.add_argument("--algo", default="sha256", choices=["md5", "sha1", "sha256", "sha512"])

    pz = sub.add_parser("zip", help="Arşiv işlemleri (zip/apk/rar/7z)")
    pz.add_argument("action", choices=["list", "extract", "ls", "x"])
    pz.add_argument("path")
    pz.add_argument("-o", "--out", default=None)

    # alias
    pa = sub.add_parser("arc", help="zip ile aynı (alias)")
    pa.add_argument("action", choices=["list", "extract", "ls", "x"])
    pa.add_argument("path")
    pa.add_argument("-o", "--out", default=None)

    pe = sub.add_parser("export", help="İndeks export")
    pe.add_argument("--fmt", choices=["csv", "json"], default="csv")
    pe.add_argument("-o", "--out", default=None)

    porg = sub.add_parser("organize", help="Kategoriye göre düzenle")
    porg.add_argument("--apply", action="store_true")
    porg.add_argument("--move", action="store_true")

    plg = sub.add_parser("large", help="En büyük dosyalar")
    plg.add_argument("-n", type=int, default=20)

    pn = sub.add_parser("recent", help="En yeni dosyalar")
    pn.add_argument("-n", type=int, default=20)

    prun = sub.add_parser("run", help="Python script çalıştır")
    prun.add_argument("path")
    prun.add_argument("args", nargs="*")

    sub.add_parser("cats", help="Kategori özeti")
    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    argv = list(argv if argv is not None else sys.argv[1:])
    parser = build_parser()
    args = parser.parse_args(argv)

    root = Path(args.root).expanduser()
    idx = DesktopIndex(root)

    cmd = args.cmd
    if cmd is None:
        # no subcommand → interactive
        idx.ensure(force=args.fresh)
        interactive(idx)
        return 0

    # commands that need index
    need_index = cmd in {
        "stats", "find", "grep", "ls", "dupes", "export", "organize",
        "scripts", "large", "recent", "cats", "menu",
    }
    if cmd == "scan":
        idx.scan()
        idx.save()
        print(C.ok(f"İndeks kaydedildi: {INDEX_FILE}"))
        return 0

    if need_index:
        idx.ensure(force=args.fresh)

    if cmd == "menu":
        interactive(idx)
    elif cmd == "stats":
        print_stats(idx)
    elif cmd == "tree":
        print_tree(root)
    elif cmd == "find":
        hits = idx.search_name(args.query, regex=args.re)
        print(C.info(f"{len(hits)} sonuç — '{args.query}'"))
        for h in hits[:80]:
            print(f"  {human_size(h.size):>9}  {C.GRY}{h.category:<8}{C.R}  {h.rel(idx.root)}")
        if len(hits) > 80:
            print(f"  ... +{len(hits) - 80}")
    elif cmd == "grep":
        print(C.info(f"İçerik araması: '{args.query}'"))
        hits = content_search(idx.files, args.query, max_hits=args.max)
        for path, ln, snip in hits:
            rel = Path(path)
            try:
                rel_s = str(rel.relative_to(idx.root))
            except ValueError:
                rel_s = str(rel)
            print(f"{C.YEL}{rel_s}:{ln}{C.R}: {snip}")
        print(C.info(f"{len(hits)} satır"))
    elif cmd == "ls":
        hits = idx.filter_ext(args.ext)
        print(C.info(f".{args.ext.lstrip('.')} → {len(hits)} dosya"))
        for h in hits[: args.n]:
            print(f"  {human_size(h.size):>9}  {h.rel(idx.root)}")
    elif cmd == "view":
        view_file(resolve_user_path(args.path, idx))
    elif cmd == "open":
        open_with_default(resolve_user_path(args.path, idx))
    elif cmd == "hash":
        cmd_hash(args.paths, algo=args.algo)
    elif cmd in ("zip", "arc"):
        p = resolve_user_path(args.path, idx)
        act = args.action
        if act in ("list", "ls"):
            print(archive_list(p))
        else:
            dest = Path(args.out) if args.out else None
            try:
                out = archive_extract(p, dest)
                print(C.ok(f"Çıkarıldı → {out}"))
            except Exception as e:
                print(C.err(str(e)))
                return 1
    elif cmd == "export":
        out = Path(args.out) if args.out else None
        export_index(idx, fmt=args.fmt, out=out)
    elif cmd == "organize":
        organize_run(idx, dry_run=not args.apply, move=args.move)
    elif cmd == "dupes":
        print(C.info("Yinelenen aranıyor..."))
        groups = find_duplicates(idx.files)
        if not groups:
            print(C.ok("Yinelenen yok (min 1KB)."))
        else:
            for h, g in groups.items():
                print(f"\n{C.YEL}{h[:16]}...{C.R}  {human_size(g[0].size)} x{len(g)}")
                for rec in g:
                    print(f"  · {rec.rel(idx.root)}")
    elif cmd == "scripts":
        scripts = list_scripts(idx)
        top = [s for s in scripts if Path(s.path).parent.resolve() == idx.root.resolve()]
        print(C.head(f"Masaüstü kök .py ({len(top)}):"))
        for s in top:
            print(f"  {s.name:<45} {human_size(s.size)}")
        print(C.head(f"\nTüm .py (alt klasörler dahil, {len(scripts)}):"))
        for s in scripts[:40]:
            print(f"  {s.rel(idx.root)[:70]}")
        if len(scripts) > 40:
            print(f"  ... +{len(scripts) - 40}")
    elif cmd == "large":
        for f in idx.largest(args.n):
            print(f"  {human_size(f.size):>10}  {f.rel(idx.root)}")
    elif cmd == "recent":
        for f in idx.newest(args.n):
            ts = datetime.fromtimestamp(f.mtime).strftime("%Y-%m-%d %H:%M")
            print(f"  {ts}  {f.rel(idx.root)}")
    elif cmd == "cats":
        for cat, n in idx.by_category().most_common():
            print(f"  {cat:<12} {n:>5}")
    elif cmd == "run":
        return run_script(resolve_user_path(args.path, idx), args.args)
    else:
        parser.print_help()
        return 1
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print(f"\n{C.warn('Kesildi.')}")
        raise SystemExit(130)
