# Professorsack cloud exporter starter

**This starter is NOT a complete working exporter by itself.** You must add the same original exporter Python files and `export_windows.bat` that currently run on your PC. Adjust the BAT file so it works in a clean Windows runner and reads private ESPN cookies from environment variables `ESPN_S2` and `ESPN_SWID` (never from hard-coded cookies or local-only files). Add `requirements.txt` if extra Python packages are needed.

## 1. Create GitHub private repo
Create an empty *private* repository such as `professorsack-espn` on GitHub. Unzip this starter. Upload the **contents** of the starter (not the ZIP itself) and your exporter into that repo, preserving `.github/workflows/espn-daily.yml`, `.github/scripts/prepare_export.py`, and `.gitignore`. Do not upload previously exported JSON, logs containing secrets, `.env` or `rclone.conf`.

## 2. Store ESPN secrets
Repo > Settings > Secrets and variables > Actions > New repository secret. Add `ESPN_S2` and `ESPN_SWID` with values from your existing private ESPN setup. Keep the curly braces on SWID if present. NEVER send credentials in chat.

## 3. Set up rclone on your own PC (once)
Download from https://rclone.org/downloads/ and extract the Windows binary. Open PowerShell in its directory and run `./rclone.exe config`. Create a remote named `gdrive`, choose Google Drive, leave client ID and secret blank unless you have your own, choose a Drive scope with upload permission, authorize in browser with the SAME Google account as the connected ChatGPT Drive folder, leave advanced configuration blank, and select My Drive.

Check from PowerShell:

    ./rclone.exe lsf "gdrive:Professorsack ESPN Exports"

Locate the config path with `./rclone.exe config file`. Open that file in Notepad. Copy the entire text into GitHub's `RCLONE_CONFIG_TEXT` repository secret. **This contains a private OAuth token, equivalent to a login credential. Do NOT add it to the repo or share it in chat.** The workflow reads the secret into a temporary config.

## 4. Test on GitHub
Repo > Actions > Professorsack ESPN Cloud Export > Run workflow. Watch the steps. If it fails at `Run existing Windows exporter`, the original BAT or Python script needs adjusting. Do not resume scheduled ChatGPT reports until you see success and the two files in your Google Drive folder.

## 5. Enable review
After one successful run, resume your existing 7:00 AM America/Toronto Daily Fantasy Roster Review ChatGPT automation. It will read `professorsack_latest.json` and `professorsack_breakout_latest.txt` from the connected Drive folder.

## Notes
- GitHub is configured to trigger the export at 6:17 AM Toronto daily, with automatic daylight saving time adjustment. Scheduled GitHub Actions can be delayed and aren't guaranteed to finish before 7:00 AM; the ChatGPT task must reject stale files.
- The GitHub runner is a *different computer*. Local paths, saved browser cookies, virtual environments, and Google Drive Desktop mounts do NOT come with it.
- `RCLONE_CONFIG_TEXT` may contain full Google Drive OAuth access including a refresh token. Only use in a private repo and review access scopes. You can revoke Google's app access later.
- If you don't see the two files in the folder or ChatGPT can't read them, troubleshoot those separately before relying on automation.
