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

# Proxy ingest preset (REQUIRED for auto Create Proxies + Media Encoder)

This must match: Right-click clips > Proxy > Create Proxies
  Frame size: Quarter
  Preset: ProRes QuickTime Proxy
  Watermark: Proxy Icon
  Location: Next to Original Media, in Proxy folder

Steps (one time per PC):
1. Open Adobe Media Encoder
2. Preset Browser > + > Create Ingest Preset
3. Turn ON: Transcode / Create Proxies (same options as above)
4. Right-click the new preset > Reveal Preset File
5. Copy that .epr file to this folder as:
   templates/NDP_Proxy_Ingest.epr

Test:
  python main.py list-proxy-presets

Without this file, Premiere opens but Media Encoder has no jobs.

# Automatic Premiere (required one-time on each PC)

PowerShell (as Administrator if normal user fails):
  python main.py install-premiere

That creates extendscriptprqe.txt next to Adobe Premiere Pro.exe.
Close Premiere completely, then:
  python main.py workflow --number 003

If Premiere opens but does nothing, double-click in the project folder:
  OPEN_PREMIERE_AUTOMATION.bat
