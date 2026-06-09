# Footage Workflow Automation

Automates the repetitive file work around your filming → edit → backup pipeline. **Adobe Premiere Pro** is still where you edit; this script handles SD card checks, copying footage, proxies, Google Drive uploads, and final backup.

## What you need

| Software | Why |
|----------|-----|
| **Python 3.10+** | Runs the script |
| **Adobe Premiere Pro** | Import footage, edit, save `.prproj` |
| **FFmpeg** | Creates proxy files (optional if you use Premiere’s built-in proxies) |
| **rclone** | Uploads proxies + project file to Google Drive |

**Hardware (example setup — drive letters may differ on each PC):**

| Drive | Device | Role |
|-------|--------|------|
| **G:** | SD card | Camera footage (source) |
| **E:** | Soju SSD | Editing — Premiere, proxies, project files |
| **H:** | Hard drive | Primary backup |
| **I:** | Second hard drive | Mirror of H: (optional) |

Google Drive folders:

| Folder | Link | Used for |
|--------|------|----------|
| **[01] Scripts** | https://drive.google.com/drive/folders/1RUebu5qPaac66hkgrJq5O0fz4guteIHP | PDF scripts — auto-names new projects |
| **[04] Proxies/Project file** | https://drive.google.com/drive/folders/1RWdJVs4LJKNMoDrRUTendfhD0uYy6VVl | Upload proxies + `.prproj` for assistant editor |

---

## Deploy on your friend's PC

Yes — this runs locally on their Windows machine. Nothing is hosted in the cloud except Google Drive uploads via rclone.

### What you send them

Zip the project folder **without** `.venv` (it is huge and machine-specific). Include:

```
Automated-script/
  main.py
  setup.ps1          ← one-click install
  requirements.txt
  config.example.yaml
  README.md
  src/
  templates/
```

**Do not zip** `.venv/` — your friend creates their own with `setup.ps1`.

Ways to transfer: USB drive, Google Drive, Discord, GitHub, etc.

### On their PC (15–20 min one-time setup)

1. **Unzip** to e.g. `C:\Users\TheirName\Automated-script`

2. **Run setup** (PowerShell in that folder):

```powershell
powershell -ExecutionPolicy Bypass -File setup.ps1
```

3. **Edit `config.yaml`** — drive letters may differ on their PC (open File Explorer with drives plugged in)

4. **Install rclone** — they sign in with **their** Google account (must have edit access to both shared folders)

5. **Adobe Premiere Pro** — they install separately via Creative Cloud (not included in this repo)

6. **Test**:

```powershell
cd C:\Users\TheirName\Automated-script
.\.venv\Scripts\Activate.ps1
python main.py list-scripts
python main.py new-project --number 003 --dry-run
```

### What is the same vs different per person

| Same for everyone | Different per PC |
|-------------------|------------------|
| Google Drive folder IDs in config | Drive letters (G:, E:, H:, etc.) |
| Script naming `[001]`, `[002]`, … | rclone Google login (their account) |
| Commands and workflow | Path to Premiere `.exe` (auto-detected usually) |

### Invite them to Google Drive first

Before rclone works, share both folders with their Google email (Editor access):

- [01] Scripts
- [04] Proxies/Project file

---

## First-time setup (new PC)

Do this once when installing on your friend’s computer.

### Step 1 — Get the project folder

Copy the whole `Automated-script` folder onto their PC (USB, Google Drive, GitHub, etc.). Example location:

```
C:\Users\TheirName\Automated-script
```

### Step 2 — Install Python

1. Download Python from https://www.python.org/downloads/
2. During install, check **“Add python.exe to PATH”**
3. Open **PowerShell** and verify:

```powershell
python --version
```

Should show Python 3.10 or newer.

### Step 3 — Install Python dependencies

```powershell
cd C:\Users\TheirName\Automated-script
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

If PowerShell blocks the activate script:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

Then run the activate command again.

**Tip:** Run `.\.venv\Scripts\Activate.ps1` each time you open a new terminal before using the script.

### Step 4 — Find drive letters on *this* PC

Drive letters are **not the same on every computer**. On your friend’s PC:

1. Open **File Explorer**
2. Plug in the SD card, Soju SSD, and backup drive(s)
3. Note each letter (e.g. SD card = `G:`, Soju = `E:`, backup = `H:`)

### Step 5 — Create `config.yaml`

```powershell
copy config.example.yaml config.yaml
notepad config.yaml
```

Edit the paths to match **their** drive letters:

```yaml
sd_cards:
  primary: "G:\\"      # SD card — main slot
  backup: "F:\\"       # SD card — backup slot (update if different)

destinations:
  ssd_editing: "E:\\"              # Soju editing SSD
  hdd_backup: "H:\\"               # Backup hard drive
  hdd_backup_mirror: "I:\\"        # Second HDD (or same letter if they only have one)

google_drive:
  rclone_remote: "gdrive"
  folder_id: "1RWdJVs4LJKNMoDrRUTendfhD0uYy6VVl"

scripts:
  folder_id: "1RUebu5qPaac66hkgrJq5O0fz4guteIHP"
```

**Do not share `config.yaml` if it contains personal paths you care about** — each person keeps their own copy. The shared Google Drive folder ID stays the same for the team.

### Step 6 — Install FFmpeg (for proxies)

1. Download from https://www.gyan.dev/ffmpeg/builds/ (Windows “release full” build is fine)
2. Extract the zip and add the `bin` folder to **PATH**, or place `ffmpeg.exe` somewhere on PATH
3. Restart PowerShell and verify:

```powershell
ffmpeg -version
```

**Alternative:** Skip FFmpeg and use **Premiere Pro’s built-in proxy workflow** (see [Premiere Pro](#premiere-pro) below).

### Step 7 — Install and configure rclone (Google Drive)

1. Download from https://rclone.org/downloads/
2. Extract `rclone.exe` and add it to PATH (or put it in the project folder)
3. Run:

```powershell
rclone config
```

Suggested answers:

| Prompt | Answer |
|--------|--------|
| New remote | `n` |
| Name | `gdrive` (must match `rclone_remote` in config) |
| Storage | `drive` (Google Drive) |
| client_id / client_secret | Press Enter (defaults) |
| scope | `1` (full access) |
| Service account | Enter (none) |
| Edit advanced config | `n` |
| Auto config | `y` (opens browser — sign in with the Google account that has access to the shared folder) |
| Configure as Shared Drive | `n` |
| Keep | `y` |
| Quit | `q` |

4. Test access to both shared folders:

```powershell
rclone lsf gdrive: --drive-root-folder-id 1RUebu5qPaac66hkgrJq5O0fz4guteIHP
rclone lsf gdrive: --drive-root-folder-id 1RWdJVs4LJKNMoDrRUTendfhD0uYy6VVl
```

You should see script PDFs like `[003] Teaching an Ipad Kid.pdf` and project folders like `[001] POV Your Doordash...`.

**Important:** Your friend must be **invited to the shared Google Drive folder** with edit access, or uploads will fail.

### Step 8 — Smoke test

Insert the SD card and run:

```powershell
cd C:\Users\TheirName\Automated-script
.\.venv\Scripts\Activate.ps1
python main.py compare-sd
```

If drive letters are wrong, fix `config.yaml` and try again.

Preview ingest without copying:

```powershell
python main.py daily --dry-run --date "[003] My New Project"
```

---

## Start a new project (enter script number)

Scripts live in **[01] Scripts](https://drive.google.com/drive/folders/1RUebu5qPaac66hkgrJq5O0fz4guteIHP)** on Google Drive as PDFs named like:

- `[001] POV Your Doordash driver stealing your food.pdf`
- `[003] Teaching an Ipad Kid.pdf`

**Enter the 3-digit number** and the script creates matching folders + a Premiere project:

```powershell
python main.py new-project --number 003 --open-premiere
```

| Input | Result |
|-------|--------|
| `003` | Looks up `[003] Teaching an Ipad Kid.pdf` on Drive |
| Creates | `SSD\[003] Teaching an Ipad Kid\` + `Video\` subfolder |
| Creates | Same on backup HDD |
| Creates | `[003] Teaching an Ipad Kid.prproj` at project root |

List all available scripts:

```powershell
python main.py list-scripts
python main.py list-scripts --refresh   # re-fetch from Google Drive
```

### Premiere project template (recommended one-time setup)

For `--open-premiere` to open a ready project instantly:

1. Open Premiere → **File → New → Project**
2. Save as `templates/project_template.prproj` in this repo
3. Future `new-project` commands copy that template automatically

If no template exists, the script writes `create_premiere_project.jsx` in the project folder. In Premiere: **File → Scripts → Run Script File** to create the project.

---

## Your workflow (script + Premiere)

| Step | You do manually | Script command |
|------|-----------------|----------------|
| 1 | — | `python main.py new-project --number 003` |
| 2 | — | Creates `[003] Title\` + `Video\` folder from [01] Scripts on Drive |
| 3 | — | `python main.py daily --number 003` copies SD card → `Video\` |
| 4 | Open Premiere, scratch disks on SSD | — |
| 5 | Import **Video** folder into Media | — |
| 6 | Right-click clips → **Create Proxies** (ProRes / Quarter / your preset) | — |
| 7 | Media Encoder finishes → `Video\Proxies\` appears | — |
| 8 | — | `python main.py upload-drive --number 003` uploads **Proxies + .prproj only** |

### Folder layout on SSD

```
F:\[003] Teaching an Ipad Kid\
  [003] Teaching an Ipad Kid.prproj
  Video\
    DCIM\...                 ← originals (from SD ingest)
    Proxies\...              ← created by Premiere / Media Encoder
```

### Commands (full day)

```powershell
python main.py new-project --number 003
python main.py daily --number 003
# Premiere: import Video, create proxies, save .prproj
python main.py upload-drive --number 003
```

---

## Daily workflow (after filming)

### 1 — Ingest footage (script)

Insert SD card(s), then:

```powershell
.\.venv\Scripts\Activate.ps1
python main.py daily --number 003
```

Or if you already created the project folder with `new-project`:

```powershell
python main.py daily --number 003
```

You can still use a manual folder name instead:

```powershell
python main.py daily --date "[003] Teaching an Ipad Kid"
```

This will:

1. Compare SD cards (or use one card if backup not inserted)
2. Copy footage into **`Video\`** on Soju SSD and backup HDD

### 2 — Adobe Premiere Pro (your proxy settings)

One-time in Premiere: **File → Project Settings → Ingest Settings**

| Setting | Value |
|---------|--------|
| Ingest | On |
| Action | Create Proxies |
| Preset | ProRes QuickTime Proxy |
| Frame size | Quarter |
| Watermark proxy icon | On |
| Location | Next to original media, in Proxy folder |

Then each project:

1. Open `.prproj` on the SSD — set scratch disks to SSD if asked
2. **File → Import** the **`Video`** folder
3. Right-click clips → **Proxy → Create Proxies**
4. Media Encoder finishes — proxies in **`Video\Proxies\`**
5. Save `.prproj` in the project folder

### 3 — Upload for assistant editor (script)

After Media Encoder finishes:

```powershell
python main.py upload-drive --number 003
```

Uploads **only** `Video\Proxies\` and `.prproj` — not original camera files.

### 4 — End of project (script)

When editing is done and the project folder has assets, exports, and extra footage:

```powershell
python main.py finalize -p "E:\[003] My New Project Title"
```

This audits files against the HDD, copies anything missing, and mirrors H: → I: (if configured).

---

## Premiere Pro (reference)

```
SSD\[003] Project Title\
  [003] Project Title.prproj
  Video\
    (camera files)
    Proxies\          ← Premiere / Media Encoder
  Assets\             ← added during edit (finalize backs these up)
```

Optional FFmpeg proxies (not your workflow): set `proxies.enabled: true` in config, then `python main.py proxies -f "SSD\[003] Title"`.

### What stays manual in Premiere

- Timeline editing, effects, color, exports
- Creating the **Assets** folder (sound effects, music, graphics)
- Assistant editor → main editor handoff (download from Google Drive)

---

## All commands

```powershell
.\.venv\Scripts\Activate.ps1    # run first in each new terminal

```powershell
python main.py list-scripts
python main.py list-scripts --refresh
python main.py new-project --number 003
python main.py new-project --number 003 --open-premiere
python main.py daily --number 003
python main.py daily --date "[003] Teaching an Ipad Kid"
python main.py daily --dry-run --number 003
python main.py proxies -f "E:\[003] Project Title"
python main.py upload-drive -f "E:\[003] Project Title" -p "E:\[003] Project Title\MyProject.prproj"
python main.py audit-assets -p "E:\[003] Project Title" --copy
python main.py mirror
python main.py finalize -p "E:\[003] Project Title"
```

| Command | What it does |
|---------|--------------|
| `list-scripts` | Show all script numbers/titles from [01] Scripts on Drive |
| `new-project --number 003` | Create `[003] Title` folders + Premiere project from script PDF name |
| `compare-sd` | Check both SD cards match |
| `daily --number 003` | Compare SD cards + copy to Soju (E:) and backup (H:) using script name |
| `proxies` | FFmpeg low-res copies in `Proxies\` subfolder |
| `upload-drive` | Upload proxies + `.prproj` to Google Drive |
| `audit-assets` | Find project files not yet on backup HDD |
| `mirror` | Copy primary HDD → second HDD |
| `finalize` | Audit + copy missing + mirror (end of project) |

---

## Folder layout (example)

```
G:\                               ← SD card (source, temporary)
E:\[003] My New Project Title\    ← Soju SSD (editing)
  DCIM\...
  Proxies\...
  MyProject.prproj
  Assets\...
H:\[003] My New Project Title\    ← Backup HDD
I:\[003] My New Project Title\    ← Second HDD mirror

Google Drive → [04] Proxies/Project file\
  [001] POV Your Doordash...
  [002] Pokemon Scalpers...
  [003] My New Project Title\
    Proxies\...
    MyProject.prproj
```

---

## SD card mismatch

If the backup card was inserted a few shots late:

- `compare-sd` / `daily` shows files only on one card
- Ingest copies **all unique files from both cards** so nothing is lost

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| `Config not found` | Run `copy config.example.yaml config.yaml` and edit paths |
| SD card not found | Check drive letters in File Explorer; update `config.yaml` |
| `Primary SD card not found: G:\` | SD card not inserted or uses a different letter |
| FFmpeg not found | Install FFmpeg and restart terminal, or use Premiere proxies instead |
| rclone not found | Install rclone and add to PATH |
| Drive upload fails | Confirm Google account has access to the shared folder; re-run `rclone config` |
| Slow ingest | Normal for large files; set `verify_checksum: false` in config to speed up |
| robocopy warnings | Exit codes 0–7 are OK; code 8+ indicates errors |
| PowerShell won’t activate venv | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` |

---

## Quick checklist for your friend

- [ ] Python installed with PATH
- [ ] `pip install -r requirements.txt` in a venv
- [ ] `config.yaml` created with **their** drive letters
- [ ] FFmpeg installed (or using Premiere proxies only)
- [ ] rclone configured as `gdrive` with access to the shared folder
- [ ] `python main.py compare-sd` works with SD card inserted
- [ ] Adobe Premiere Pro installed (separate — Adobe subscription/Creative Cloud)
#   A u t o m a t e d - s c r i p t - V 2  
 