# Contributing

Thanks for looking at MC Server Hub. The useful changes are the ones that keep process ownership and crash detection accurate.

## Setup

Windows 10 or 11, 64-bit, Python 3.11 or newer.

```bat
python -m pip install -r requirements.txt
python -m mc_server_hub.main
```

Tests do not need the GUI packages:

```bat
python -m pip install psutil pywinpty
python -m unittest discover -s tests -t .
```

## What to know before changing process code

- A server BAT must stay attached to the console. Do not launch Java with `start`.
- The supervisor process owns the consoles. The window is a client.
- Crash detection follows process exit. A quiet console is not a crash.
- A user stop, including the console commands `stop` and `end`, must not schedule a restart.
- Closing the supervisor must not leave `java.exe` running. The job object is what makes that true.

Please add or extend a test in `tests/` when you change that behavior. The lifecycle tests start real BAT files.

## Pull requests

- Keep the public package name `mc_server_hub`.
- Match the surrounding style: type hints, snake_case functions, PascalCase classes.
- Do not commit `dist/`, `build/`, `logs/`, `data/`, or a `servers.json` that contains your own paths.
- Describe how you tested the change in the pull request.

## Reporting bugs

Use the bug report template. Include the BAT shape and the hub version. Remove player names, IP addresses, and session tokens.
