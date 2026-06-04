"""Generate Adobe Premiere ExtendScript for project setup, import, and proxies."""

from __future__ import annotations

from pathlib import Path

from .project_paths import video_folder_name


def _jsx_path(path: Path) -> str:
    return str(path).replace("\\", "/")


def generate_premiere_setup_script(
    cfg: dict,
    project_root: Path,
    folder_name: str,
    prproj_path: Path,
) -> str:
    """
    JSX run inside Premiere (File > Scripts > Run Script File):
    - Create/open project on SSD with script-based name
    - Import everything under Video/ (PRIVATE, M4ROOT, CLIP, etc.)
    - Queue proxy creation (uses your Ingest preset on the template project)
    """
    video_dir = project_root / video_folder_name(cfg)
    video_jsx = _jsx_path(video_dir)
    prproj_jsx = _jsx_path(prproj_path)
    project_root_jsx = _jsx_path(project_root)

    return f"""// Auto-generated — Nathan Doan Productions workflow
// Run: File > Scripts > Run Script File > automate_premiere.jsx
// Best with templates/project_template.prproj that has Ingest/Proxy settings saved.

(function () {{
    var PROJECT_PATH = "{prproj_jsx}";
    var VIDEO_DIR = "{video_jsx}";
    var PROJECT_ROOT = "{project_root_jsx}";

    var FOOTAGE_EXT = /\\.(mp4|mov|mxf|avi|mkv|r3d|braw|m4v)$/i;

    function alertMsg(msg) {{
        try {{ alert(msg); }} catch (e) {{ $.writeln(msg); }}
    }}

    function collectMediaFiles(folder, list) {{
        if (!folder || !folder.exists) return;
        var items = folder.getFiles();
        for (var i = 0; i < items.length; i++) {{
            if (items[i] instanceof Folder) {{
                collectMediaFiles(items[i], list);
            }} else if (items[i] instanceof File && FOOTAGE_EXT.test(items[i].name)) {{
                list.push(items[i].fsName);
            }}
        }}
    }}

    // --- 1. Create or open project on SSD ---
    var prprojFile = new File(PROJECT_PATH);
    if (prprojFile.exists) {{
        app.openDocument(PROJECT_PATH);
    }} else {{
        app.newProject(PROJECT_PATH);
    }}
    app.project.save();

    // --- 2. Import Video folder into project (root bin) ---
    var videoFolder = new Folder(VIDEO_DIR);
    if (!videoFolder.exists) {{
        alertMsg("Video folder not found:\\n" + VIDEO_DIR + "\\n\\nRun: python main.py daily --number XXX");
        return;
    }}

    var mediaPaths = [];
    collectMediaFiles(videoFolder, mediaPaths);

    if (mediaPaths.length === 0) {{
        alertMsg("No video files found in:\\n" + VIDEO_DIR);
        return;
    }}

    var importThese = [];
    for (var j = 0; j < mediaPaths.length; j++) {{
        importThese.push(mediaPaths[j]);
    }}

    app.project.importFiles(
        importThese,
        1,  // suppress UI
        app.project.rootItem,
        0
    );

    app.project.save();
    alertMsg(
        "Imported " + mediaPaths.length + " file(s) from Video folder.\\n\\n" +
        "NEXT (if proxies did not start automatically):\\n" +
        "1. Select all clips in the Project panel\\n" +
        "2. Right-click > Proxy > Create Proxies\\n" +
        "3. Preset: ProRes QuickTime Proxy, Quarter, Next to Original in Proxy folder\\n" +
        "4. Media Encoder will open and process\\n\\n" +
        "When done, run: python main.py upload-drive --number XXX"
    );

    // --- 3. Try to launch Media Encoder (Premiere may already open it when using Create Proxies) ---
    try {{
        if (app.encoder) {{
            app.encoder.launchEncoder();
        }}
    }} catch (encErr) {{
        // Encoder API varies by Premiere version
    }}
}})();
"""


def write_premiere_setup_script(
    cfg: dict,
    project_root: Path,
    folder_name: str,
    prproj_path: Path,
) -> Path:
    jsx_path = project_root / "automate_premiere.jsx"
    jsx_path.write_text(
        generate_premiere_setup_script(cfg, project_root, folder_name, prproj_path),
        encoding="utf-8",
    )
    return jsx_path
