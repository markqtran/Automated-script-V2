"""Generate Adobe Premiere ExtendScript for project setup, import, and proxies."""

from __future__ import annotations

import json
from pathlib import Path

from .project_paths import video_folder_name


def _jsx_path(path: Path) -> str:
    return str(path).replace("\\", "/")


def generate_premiere_setup_script(
    cfg: dict,
    project_root: Path,
    folder_name: str,
    prproj_path: Path,
    *,
    script_number: str = "",
) -> str:
    """
    JSX run inside Premiere (auto via /C es.processFile or File > Scripts):
    - Scratch disks -> SSD project folder from config
    - Create/open project named like the folder (e.g. [003] Title.prproj)
    - Import everything under Video/
    """
    video_dir = project_root / video_folder_name(cfg)
    video_jsx = _jsx_path(video_dir)
    prproj_jsx = _jsx_path(prproj_path)
    project_root_jsx = _jsx_path(project_root)
    script_num = script_number or ""
    prproj_jsx_lit = json.dumps(prproj_jsx)
    video_jsx_lit = json.dumps(video_jsx)
    project_root_lit = json.dumps(project_root_jsx)
    folder_lit = json.dumps(folder_name)
    script_lit = json.dumps(script_num)

    return f"""// Auto-generated — project on SSD, name matches folder
// PROJECT: {folder_name}

(function () {{
    var PROJECT_PATH = {prproj_jsx_lit};
    var VIDEO_DIR = {video_jsx_lit};
    var PROJECT_ROOT = {project_root_lit};
    var FOLDER_NAME = {folder_lit};
    var SCRIPT_NUMBER = {script_lit};

    var FOOTAGE_EXT = /\\.(mp4|mov|mxf|avi|mkv|r3d|braw|m4v)$/i;

    function alertMsg(msg) {{
        try {{ alert(msg); }} catch (e) {{ $.writeln(msg); }}
    }}

    function setScratchDisks(rootPath) {{
        var types = [
            ScratchDiskType.FirstVideoCaptureFolder,
            ScratchDiskType.FirstAudioCaptureFolder,
            ScratchDiskType.FirstVideoPreviewFolder,
            ScratchDiskType.FirstAudioPreviewFolder,
            ScratchDiskType.FirstAutoSaveFolder,
            ScratchDiskType.FirstCCLibrariesFolder,
            ScratchDiskType.FirstCapsuleMediaFolder
        ];
        for (var t = 0; t < types.length; t++) {{
            try {{
                app.setScratchDiskPath(rootPath, types[t]);
            }} catch (e) {{}}
        }}
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

    // --- 1. Scratch disks + project on SSD (same name as folder) ---
    setScratchDisks(PROJECT_ROOT);

    var prprojFile = new File(PROJECT_PATH);
    var opened = false;
    if (prprojFile.exists) {{
        opened = app.openDocument(PROJECT_PATH, 1, 1, 1, 1);
    }} else {{
        opened = app.newProject(PROJECT_PATH);
    }}

    if (!opened) {{
        alertMsg("Could not create/open project:\\n" + PROJECT_PATH);
        return;
    }}

    app.project.save();

    // --- 2. Import Video folder ---
    var videoFolder = new Folder(VIDEO_DIR);
    if (!videoFolder.exists) {{
        alertMsg(
            "Project ready at:\\n" + PROJECT_ROOT + "\\n\\n" +
            "Video folder not found yet:\\n" + VIDEO_DIR + "\\n\\n" +
            "Run: python main.py daily --number " + (SCRIPT_NUMBER || "XXX")
        );
        return;
    }}

    var mediaPaths = [];
    collectMediaFiles(videoFolder, mediaPaths);

    if (mediaPaths.length === 0) {{
        alertMsg(
            "Project saved:\\n" + PROJECT_PATH + "\\n\\n" +
            "No video files in Video/ yet. Run ingest, then run this script again."
        );
        return;
    }}

    app.project.importFiles(
        mediaPaths,
        1,
        app.project.rootItem,
        0
    );

    app.project.save();

    alertMsg(
        "Project: " + FOLDER_NAME + "\\n" +
        "Location: " + PROJECT_ROOT + "\\n" +
        "Imported " + mediaPaths.length + " clip(s).\\n\\n" +
        "NEXT: Select clips > Proxy > Create Proxies\\n" +
        "(Quarter, ProRes QuickTime Proxy, next to originals in Proxies folder)\\n\\n" +
        "When done: python main.py upload-drive --number " + (SCRIPT_NUMBER || "XXX")
    );

    try {{
        if (app.encoder) {{
            app.encoder.launchEncoder();
        }}
    }} catch (encErr) {{}}
}})();
"""


def write_premiere_setup_script(
    cfg: dict,
    project_root: Path,
    folder_name: str,
    prproj_path: Path,
    *,
    script_number: str = "",
) -> Path:
    jsx_path = project_root / "automate_premiere.jsx"
    jsx_path.write_text(
        generate_premiere_setup_script(
            cfg,
            project_root,
            folder_name,
            prproj_path,
            script_number=script_number,
        ),
        encoding="utf-8",
    )
    return jsx_path
