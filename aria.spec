# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for ARIA (one-folder build).

Heavy ML/Qt packages need their data files, binaries, and submodules pulled in
explicitly via collect_all. Build with:  pyinstaller aria.spec --noconfirm
(or run build.ps1). Output goes to dist/ARIA/ARIA.exe.

Notes:
- One-folder (COLLECT) is used over one-file: it's far more reliable for
  onnxruntime / chromadb / faster-whisper native libs and starts faster.
- Whisper and openwakeword/chroma models are downloaded at first run into
  data/models and the user cache; they are NOT bundled.
"""

from PyInstaller.utils.hooks import collect_all, collect_submodules

datas, binaries, hiddenimports = [], [], []

# Packages with data files / dynamic imports that PyInstaller misses by default.
for pkg in [
    "chromadb", "onnxruntime", "faster_whisper", "tokenizers",
    "edge_tts", "openwakeword", "ddgs", "apscheduler", "PyQt6",
    "huggingface_hub", "ctranslate2",
]:
    try:
        d, b, h = collect_all(pkg)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception:
        # Optional package not installed in this environment; skip.
        pass

hiddenimports += collect_submodules("pydantic")
hiddenimports += ["pyttsx3.drivers", "pyttsx3.drivers.sapi5"]

a = Analysis(
    ["main.py"],
    pathex=["."],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ARIA",
    console=False,
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="ARIA",
)
