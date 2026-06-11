Win7 runtime offline installers
===============================

Use this folder only if start.bat fails at low-level imports such as:

- import _socket
- import socket
- import _ctypes
- import ctypes
- import _sqlite3
- import sqlite3

Target system:

- Windows 7 SP1 64-bit

Recommended action:

1. Go back to the project root folder.
2. Right-click install_win7_runtime.bat.
3. Choose "Run as administrator".
4. Restart Windows if prompted.
5. Run start.bat again.

Included files:

- Windows6.1-KB2999226-x64.msu
  Universal C Runtime update for Windows 7 SP1 x64.

- vc_redist.x64.exe
  Microsoft Visual C++ 2015 Redistributable x64.
