# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the GAIA desktop build.

Run via `pyinstaller packaging/gaia.spec` from the repository root, after
`npm run build` in web/ has produced web/dist. Produces a single
double-clickable executable on Windows/Linux, and a .app bundle on macOS.
"""

import sys
from pathlib import Path

ROOT = Path(SPECPATH).parent  # noqa: F821 - injected by PyInstaller
SRC = ROOT / "src"
WEB_DIST = ROOT / "web" / "dist"

if not WEB_DIST.is_dir():
    raise SystemExit("web/dist is missing - run `npm run build` in web/ first")

a = Analysis(  # noqa: F821
    [str(ROOT / "packaging" / "gaia_app.py")],
    pathex=[str(SRC)],
    datas=[
        (str(SRC / "gaia" / "schema.sql"), "gaia"),
        (str(WEB_DIST), "web/dist"),
        (str(ROOT / "TERMS_OF_SERVICE.md"), "."),
        (str(ROOT / "PRIVACY.md"), "."),
    ],
    hiddenimports=[
        # uvicorn picks its protocol/loop implementations by string name at
        # runtime, so static analysis alone will not find these modules.
        "uvicorn.logging",
        "uvicorn.loops",
        "uvicorn.loops.auto",
        "uvicorn.protocols",
        "uvicorn.protocols.http",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.http.h11_impl",
        "uvicorn.protocols.websockets",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.protocols.websockets.websockets_impl",
        "uvicorn.lifespan",
        "uvicorn.lifespan.on",
    ],
)
pyz = PYZ(a.pure)  # noqa: F821

exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="GAIA",
    console=True,
)

if sys.platform == "darwin":
    app = BUNDLE(  # noqa: F821
        exe,
        name="GAIA.app",
        bundle_identifier="com.bingkil.gaia",
        info_plist={"NSHighResolutionCapable": True},
    )
