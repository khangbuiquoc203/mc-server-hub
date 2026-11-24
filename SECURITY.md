# Security

MC Server Hub starts local BAT files and can write to their console input. Treat a server entry as a command you are willing to run.

## Supported use

- Run the hub only with BAT files you wrote or trust.
- Keep the app directory on a user account you control. `data/supervisor.json` contains the local supervisor token while the supervisor is running.
- The supervisor listens on `127.0.0.1` only.

## Reporting a vulnerability

Please do not open a public GitHub issue for a security problem.

Use the repository's **Security** tab and open a private advisory. If the project has not enabled advisories yet, email khangbuiquoc203@gmail.com and wait for a reply before disclosing the details.

Include the version, the Windows version, and a description that does not require sharing a live server or player data.
