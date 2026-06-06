# Premiere project template (IMPORTANT)

Save ONE blank Premiere project here as: project_template.prproj

Before saving, set scratch disks to your SSD (Soju).

Optional — Ingest can stay OFF. The Python workflow queues proxies via
Media Encoder (templates/NDP_Proxy_Encode.epr), not Premiere Ingest.

If you turn Ingest ON in the template, use a preset that exists on every PC
or the project will show "Missing Preset" on re-open.

When the template exists, new-project copies it so proxy settings
match your workflow every time.

# Proxy ENCODING preset (REQUIRED for auto proxies into Video/Proxies/)

The script queues Media Encoder with an explicit output path on the SSD.
You need a normal encoding preset (not only an ingest preset).

Match your Create Proxies look:
  ProRes QuickTime Proxy, Quarter (Proxy Icon optional in Premiere UI)

Steps (one time per PC):
1. Open Adobe Media Encoder
2. Preset Browser > + > Create Preset (NOT "Create Ingest Preset")
3. Format: QuickTime, ProRes QuickTime Proxy, frame size Quarter
4. Right-click preset > Reveal Preset File
5. Copy to: templates/NDP_Proxy_Encode.epr

Optional (ingest / manual Create Proxies only):
  templates/NDP_Proxy_Ingest.epr — from Create Ingest Preset in AME

Test:
  python main.py list-proxy-presets

Without NDP_Proxy_Encode.epr, Premiere imports clips but Video/Proxies stays empty
until you run Create Proxies manually or add the encode preset.

# Automatic Premiere (required one-time on each PC)

PowerShell (as Administrator if normal user fails):
  python main.py install-premiere

That creates extendscriptprqe.txt next to Adobe Premiere Pro.exe.
Close Premiere completely, then:
  python main.py workflow --number 003

If Premiere opens but does nothing, double-click in the project folder:
  OPEN_PREMIERE_AUTOMATION.bat
