# Third-party notices

Notepad Plus 4.6.0 — Copyright (C) 2026 Sajjad Shadloo.
The original application code is distributed under GNU GPL version 3.
See [LICENSE](LICENSE). Third-party components retain their own licenses.

| Component | Version used | License / notice |
| --- | --- | --- |
| Python runtime | 3.13.12 | PSF license and bundled notices, `licenses/Python-LICENSE.txt` |
| PyQt6 | 6.11.0 | GPLv3, `licenses/GPL-3.0.txt` |
| Qt shared libraries and plugins | 6.11.1 | LGPLv3/GPLv3 and upstream third-party terms, `licenses/LGPL-3.0.txt` and `licenses/GPL-3.0.txt` |
| PyQt6-sip runtime | 13.11.1 | BSD terms, `licenses/PyQt6-sip-BSD.txt` |
| PyInstaller bootloader | 6.21.0 | GPL with bootloader exception, `licenses/PyInstaller-COPYING.txt` |
| Inter font | 4.001, revision 9221beed3 | SIL Open Font License 1.1, `licenses/Inter-OFL.txt` |
| Vazirmatn font | 33.003 | SIL Open Font License 1.1, `licenses/Vazirmatn-OFL.txt` |

Python includes additional components described in its license file. Qt includes
third-party code and notices provided with its upstream source distribution.
The application's Qt libraries are distributed as separate dynamic libraries;
no restriction on replacing them for the purposes allowed by their licenses is
added by this project. Changing runtime libraries can affect application compatibility.

Source locations and pinned versions for rebuilding are listed next to these
notices in [DEPENDENCY-SOURCES.txt](DEPENDENCY-SOURCES.txt). The release also
provides a source archive for the application and its build scripts. Private
notes, service credentials and the production database are not build inputs.

The Inter font name table identifies Copyright 2016 The Inter Project Authors.
The Vazirmatn font name table identifies Copyright 2015 The Vazirmatn Project
Authors. Their upstream license texts and copyright notices are included verbatim.

`pytest` and Wrangler are development tools and are not bundled in the desktop
runtime. The installer is produced by Inno Setup; the Inno Setup engine keeps its
own embedded vendor notices. The licenses above do not imply endorsement by any
upstream author.
