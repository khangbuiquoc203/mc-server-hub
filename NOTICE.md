# Notices

The source code in this repository is licensed under the MIT License. See [LICENSE](LICENSE).

That license applies to MC Server Hub itself. It does not change the license of any third-party library, and it does not grant any rights to Minecraft.

## Minecraft

Minecraft is a trademark of Mojang Synergies AB. This project is not affiliated with, endorsed by, or sponsored by Mojang or Microsoft.

The repository does not contain Minecraft, a Minecraft server, server jars, game assets, or account data. A person who runs a server with this tool is responsible for complying with Mojang's Minecraft EULA and with the license of any mod or plugin they add.

## Third-party software

These components are used by the application. Their licenses stay with them.

| Component | Role | License |
| --- | --- | --- |
| [PySide6](https://doc.qt.io/qtforpython/) | Desktop window, Qt bindings | GNU LGPL v3 |
| Qt, as shipped with PySide6 | UI toolkit used by those bindings | GNU LGPL v3 |
| [psutil](https://github.com/giampaolo/psutil) | Process, CPU, and memory readings | BSD 3-Clause |
| [pywinpty](https://github.com/andfoy/pywinpty) | Windows ConPTY console | MIT |
| [PyInstaller](https://pyinstaller.org/) | Builds the Windows executable | Bootloader is GPL-2.0-only with the [Bootloader exception](https://github.com/pyinstaller/pyinstaller/blob/develop/COPYING.txt) |

Installing the Python packages installs their own license texts. A packaged `MCServerHub.exe` includes the PySide6 and Qt binaries under the LGPL and the PyInstaller bootloader under its exception. Replacing those libraries, or rebuilding the executable from this source, is how those terms are satisfied. The MIT license on this repository does not relicense Qt or the bootloader.
