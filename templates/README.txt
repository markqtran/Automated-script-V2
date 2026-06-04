# Premiere project template (IMPORTANT)

Save ONE blank Premiere project here as: project_template.prproj

Before saving, set these in Premiere:

File > Project Settings > Ingest Settings:
  - Ingest: ON
  - Action: Create Proxies
  - Preset: ProRes QuickTime Proxy
  - Frame size: Quarter
  - Watermark: Proxy Icon
  - Location: Next to Original Media, in Proxy folder

Also set scratch disks to your SSD (Soju).

When the template exists, new-project copies it so proxy settings
match your workflow every time.

Automatic Premiere (required one-time on each PC):
  PowerShell (as Administrator if normal user fails):
    python main.py install-premiere

  That creates extendscriptprqe.txt next to Adobe Premiere Pro.exe.
  Close Premiere completely, then:
    python main.py workflow --number 003

  If Premiere opens but does nothing, double-click in the project folder:
    OPEN_PREMIERE_AUTOMATION.bat
