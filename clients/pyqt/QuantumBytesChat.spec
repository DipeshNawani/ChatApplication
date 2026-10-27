# PyInstaller entry point; run from the repository root.
from PyInstaller.utils.hooks import collect_submodules

hiddenimports = collect_submodules("socketio") + collect_submodules("engineio")

a = Analysis(
    ["app.py"],
    pathex=["../.."],
    binaries=[],
    datas=[],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name="QuantumBytesChat", console=False)
