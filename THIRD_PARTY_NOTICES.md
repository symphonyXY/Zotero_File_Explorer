# Third-party components and corresponding sources

The application code is MIT-licensed. No Zotero, PDF2zh, ZotMoov or PyZotero implementation is copied into the application. Their protocol and naming behavior was studied; repository licenses and commits are recorded in docs/research.md.

Runtime components retain their own licenses:

| Component | Terms and distribution |
|---|---|
| Python 3.13.17 and standard-library modules | PSF and bundled third-party notices, copied from the interpreter LICENSE.txt |
| SQLite | Public domain; Python's sqlite module and notices are included |
| OpenSSL 3.x | Apache-2.0, original license text included; separate compatible copies may be collected for Python and Qt TLS plugins |
| PySide6-Essentials / shiboken6 6.10.2 | LGPL-3.0 option; corresponding PySide source archive includes both bindings and generator/runtime sources |
| Qt 6.10.2 Core, Gui, Widgets, Network, Svg and image plugins | Applicable LGPL-3.0 option and embedded third-party terms; exact QtBase, QtSvg and QtImageFormats sources and their notices are provided |
| PyInstaller bootloader | GPL-2.0-or-later with the bootloader exception permitting distribution of the generated application under its own terms; original notices are included |
| Microsoft Visual C++ runtime components | Microsoft redistributable terms, supplied by the unmodified Python/Qt runtime distributions; not application source |
| Inno Setup | Inno Setup License, original compiler/installer authors Jordan Russell and Martijn Laan; used to create the installer |

Exact dependency versions and actual packaged DLLs appear in dependency-versions.json and docs/evidence/package-1.0.0.json. The development-only pytest, pytest-qt, Ruff, Pillow and psutil packages are not runtime dependencies or bundled libraries.

LGPL-covered shared libraries are left in separate, dynamically loaded files under `_internal`. Recipients may modify or replace these libraries with compatible versions, and may reverse-engineer the application as necessary to debug such modifications. This application imposes no restrictions on those LGPL rights. The application source and build configuration are provided with the delivery. Complete upstream source archives for the distributed Qt modules and PySide/shiboken version are provided beside the installer in `dist/ThirdPartySources/`; retain that directory when redistributing. Original LICENSES, copyright notices and qt_attribution.json files extracted from those exact sources are included in `licenses/`. Nothing in the application MIT license relicenses these components.

The application icon is the user-selected AI-generated concept 06-fusion-minimal. Its retained source is assets/icons/app-source.png; sizes and hashes are recorded in docs/evidence/icon.json. This project artwork is distributed under the project's MIT license. It is not an official Zotero logo and does not imply endorsement by Zotero.

The Inno simplified-Chinese message file is the official project message translation by Zhenghan Yang (Kira), obtained from the upstream Inno Setup main branch, with its original attribution retained in installer/ChineseSimplified.isl.
