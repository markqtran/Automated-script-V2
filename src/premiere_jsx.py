"""Generate Adobe Premiere ExtendScript for project setup, import, and proxies."""

from __future__ import annotations

import json
from pathlib import Path

from .premiere_proxy import (
    auto_create_proxies,
    proxy_subfolder_name,
    resolve_encode_preset_path,
    resolve_proxy_preset_path,
)
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
    import_dir: Path | None = None,
    proxies_dir_override: Path | None = None,
    import_label: str = "",
    continue_existing_project: bool = False,
) -> str:
    """
    JSX run inside Premiere (auto via /C es.processFile or File > Scripts):
    - Scratch disks -> SSD project folder
    - Create/open project named like the folder
    - Import all clips under import_dir (Video/ or Pick Up Shots #N/)
    - Create proxies when preset available
    """
    video_name = video_folder_name(cfg)
    video_dir_path = import_dir or (project_root / video_name)
    proxies_dir_path = proxies_dir_override or (video_dir_path / proxy_subfolder_name(cfg))
    import_display = import_label or video_dir_path.name
    video_jsx = _jsx_path(video_dir_path)
    proxies_jsx = _jsx_path(proxies_dir_path)
    prproj_jsx = _jsx_path(prproj_path)
    project_root_jsx = _jsx_path(project_root)
    script_num = script_number or ""
    proxy_preset = resolve_proxy_preset_path(cfg)
    encode_preset = resolve_encode_preset_path(cfg)
    proxy_sub = proxy_subfolder_name(cfg)
    do_proxies = auto_create_proxies(cfg)

    literals = {
        "prproj": prproj_jsx,
        "video": video_jsx,
        "proxies": proxies_jsx,
        "root": project_root_jsx,
        "folder": folder_name,
        "script": script_num,
        "preset": proxy_preset,
        "encode_preset": encode_preset,
        "proxy_sub": proxy_sub,
        "auto_proxies": "true" if do_proxies else "false",
        "import_label": import_display,
        "continue_project": "true" if continue_existing_project else "false",
    }
    lit = {k: json.dumps(v) for k, v in literals.items()}

    return f"""// Auto-generated — Nathan Doan Productions
// Proxy target: Quarter, ProRes QuickTime Proxy, Proxy Icon, Video/{proxy_sub}/

(function () {{
    var PROJECT_PATH = {lit["prproj"]};
    var VIDEO_DIR = {lit["video"]};
    var PROXIES_DIR = {lit["proxies"]};
    var PROJECT_ROOT = {lit["root"]};
    var FOLDER_NAME = {lit["folder"]};
    var SCRIPT_NUMBER = {lit["script"]};
    var PROXY_PRESET_PATH = {lit["preset"]};
    var ENCODE_PRESET_PATH = {lit["encode_preset"]};
    var PROXY_SUBFOLDER = {lit["proxy_sub"]};
    var AUTO_CREATE_PROXIES = {lit["auto_proxies"]} === "true";
    var IMPORT_LABEL = {lit["import_label"]};
    var CONTINUE_PROJECT = {lit["continue_project"]} === "true";

    var FOOTAGE_EXT = /\\.(mp4|mov|mxf|avi|mkv|r3d|braw|m4v)$/i;
    var proxyJobs = {{}};
    var batchStarted = false;

    function alertMsg(msg) {{
        try {{ alert(msg); }} catch (e) {{ $.writeln(msg); }}
    }}

    function pathSep() {{
        return Folder.fs === "Windows" ? "\\\\" : "/";
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
            try {{ app.setScratchDiskPath(rootPath, types[t]); }} catch (e) {{}}
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

    function isUnderVideoDir(mediaPath) {{
        if (!mediaPath) return false;
        var norm = mediaPath.replace(/\\\\/g, "/").toLowerCase();
        var video = VIDEO_DIR.replace(/\\\\/g, "/").toLowerCase();
        return norm.indexOf(video) >= 0;
    }}

    function collectClipItems(bin, clips) {{
        if (!bin || !bin.children) return;
        for (var i = 0; i < bin.children.numItems; i++) {{
            var child = bin.children[i];
            if (!child) continue;
            if (child.children && child.children.numItems > 0) {{
                collectClipItems(child, clips);
            }}
            if (child.getMediaPath) {{
                var mp = child.getMediaPath();
                if (mp && mp.length > 0 && isUnderVideoDir(mp) && child.canProxy && child.canProxy()) {{
                    clips.push(child);
                }}
            }}
        }}
    }}

    function proxyOutputPath(mediaPath) {{
        var proxiesRoot = new Folder(PROXIES_DIR);
        if (!proxiesRoot.exists) proxiesRoot.create();
        var src = new File(mediaPath);
        var dot = src.name.lastIndexOf(".");
        var base = dot > 0 ? src.name.substring(0, dot) : src.name;
        return proxiesRoot.fsName + pathSep() + base + "_Proxy.mov";
    }}

    function resolvePresetPath(configured, fallbackConfigured) {{
        if (configured && configured.length > 0) {{
            var f = new File(configured);
            if (f.exists) return f.fsName;
        }}
        if (fallbackConfigured && fallbackConfigured.length > 0) {{
            var g = new File(fallbackConfigured);
            if (g.exists) return g.fsName;
        }}
        return "";
    }}

    function findClipForMediaPath(bin, targetPath) {{
        if (!bin || !bin.children) return null;
        var target = targetPath.replace(/\\\\/g, "/").toLowerCase();
        for (var i = 0; i < bin.children.numItems; i++) {{
            var child = bin.children[i];
            if (!child) continue;
            if (child.children && child.children.numItems > 0) {{
                var found = findClipForMediaPath(child, targetPath);
                if (found) return found;
            }}
            if (child.getMediaPath) {{
                var mp = child.getMediaPath();
                if (mp && mp.replace(/\\\\/g, "/").toLowerCase() === target) {{
                    return child;
                }}
            }}
        }}
        return null;
    }}

    function onProxyJobComplete(jobID, outputFilePath) {{
        var mediaPath = proxyJobs[jobID];
        if (!mediaPath) return;
        try {{
            var item = findClipForMediaPath(app.project.rootItem, mediaPath);
            if (item && item.canProxy && item.canProxy() && !item.hasProxy()) {{
                var outFile = new File(outputFilePath);
                if (outFile.exists) {{
                    item.attachProxy(outFile.fsName, 0);
                }}
            }}
        }} catch (e) {{}}
        delete proxyJobs[jobID];
    }}

    function onProxyJobError(jobID, errorMessage) {{
        $.writeln("Proxy job error: " + errorMessage);
        delete proxyJobs[jobID];
    }}

    function onProxyJobQueued(jobID) {{
        if (!batchStarted && app.encoder && app.encoder.startBatch) {{
            batchStarted = true;
            app.encoder.startBatch();
        }}
    }}

    function queueProxiesForMediaPaths(mediaPaths, encodePreset) {{
        if (!app.encoder || !encodePreset || mediaPaths.length === 0) return 0;

        try {{
            app.encoder.bind("onEncoderJobComplete", onProxyJobComplete);
            app.encoder.bind("onEncoderJobError", onProxyJobError);
            app.encoder.bind("onEncoderJobQueued", onProxyJobQueued);
        }} catch (bindErr) {{}}

        try {{
            if (app.encoder.launchEncoder) app.encoder.launchEncoder();
        }} catch (launchErr) {{}}

        var queued = 0;
        var workArea = 0;
        var removeOnComplete = 0;

        // encodeFile with explicit output -> always lands in PROXIES_DIR on SSD
        for (var m = 0; m < mediaPaths.length; m++) {{
            var mediaPath = mediaPaths[m];
            if (!mediaPath || !isUnderVideoDir(mediaPath)) continue;
            var outPath = proxyOutputPath(mediaPath);
            var jobID = 0;
            try {{
                jobID = app.encoder.encodeFile(
                    mediaPath, outPath, encodePreset, workArea, removeOnComplete
                );
            }} catch (efErr) {{}}
            if (jobID && jobID !== "0" && jobID !== 0) {{
                proxyJobs[jobID] = mediaPath;
                queued++;
            }}
        }}

        if (queued > 0) {{
            try {{ app.encoder.startBatch(); }} catch (sbErr) {{}}
        }}
        return queued;
    }}

    // --- 1. Project on SSD (pick-up runs always reopen the same .prproj) ---
    setScratchDisks(PROJECT_ROOT);

    var prprojFile = new File(PROJECT_PATH);
    var opened = false;

    if (CONTINUE_PROJECT && !prprojFile.exists) {{
        alertMsg(
            "Pick-up run needs the existing Premiere project:\\n" + PROJECT_PATH + "\\n\\n" +
            "Save the project from the first shoot, then re-run workflow."
        );
        return;
    }}

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

    // --- 2. Ingest OFF — proxies are queued via Media Encoder encodeFile below ---
    try {{ app.project.setEnableTranscodeOnIngest(false); }} catch (ingestErr) {{}}

    // --- 3. Import all video in Video/ ---
    var videoFolder = new Folder(VIDEO_DIR);
    if (!videoFolder.exists) {{
        alertMsg(
            "Project ready at:\\n" + PROJECT_ROOT + "\\n\\n" +
            "Video folder not found:\\n" + VIDEO_DIR + "\\n\\n" +
            "Run: python main.py daily --number " + (SCRIPT_NUMBER || "XXX")
        );
        return;
    }}

    var mediaPaths = [];
    collectMediaFiles(videoFolder, mediaPaths);
    if (mediaPaths.length === 0) {{
        alertMsg("No video files in Video/ yet. Run ingest first.");
        return;
    }}

    app.project.importFiles(mediaPaths, 1, app.project.rootItem, 0);
    app.project.save();

    // --- 4. Create proxies for every imported clip in Video/ ---
    var proxyMsg = "";
    if (AUTO_CREATE_PROXIES) {{
        var encodePreset = resolvePresetPath(ENCODE_PRESET_PATH, "");
        var queued = 0;
        if (encodePreset) {{
            queued = queueProxiesForMediaPaths(mediaPaths, encodePreset);
        }}

        if (queued > 0) {{
            proxyMsg =
                "Encoding " + queued + " proxy file(s) to SSD:\\n" + PROXIES_DIR + "\\n\\n" +
                "Files appear when Media Encoder FINISHES (not instant).\\n" +
                "Then: python main.py watch-backup --number " + (SCRIPT_NUMBER || "XXX") + "\\n\\n";
        }} else if (!encodePreset) {{
            proxyMsg =
                "Could not find ENCODING preset (.epr). No Media Encoder jobs queued.\\n\\n" +
                "ONE-TIME — export encoding preset (not ingest):\\n" +
                "1. Media Encoder > Preset Browser > + > Create Preset\\n" +
                "   Format: QuickTime, ProRes QuickTime Proxy, Quarter\\n" +
                "2. Reveal Preset File > copy to templates\\\\NDP_Proxy_Encode.epr\\n" +
                "3. python main.py list-proxy-presets\\n" +
                "4. Re-run workflow\\n\\n" +
                "Or: Right-click clips > Proxy > Create Proxies\\n" +
                "(Next to original, Proxy folder).\\n\\n";
        }} else {{
            proxyMsg =
                "Could not queue proxy encode jobs.\\n" +
                "Add templates/NDP_Proxy_Encode.epr (encoding preset, ProRes Proxy).\\n" +
                "Or: Right-click clips > Proxy > Create Proxies\\n" +
                "(Destination: Next to original, Proxy folder).\\n\\n";
        }}
    }}

    app.project.save();

    var projectAction = CONTINUE_PROJECT
        ? "Continued existing project (pick-up). Saved.\\n\\n"
        : "";

    alertMsg(
        projectAction +
        "Project: " + FOLDER_NAME + "\\n" +
        "Location: " + PROJECT_ROOT + "\\n" +
        "Imported " + mediaPaths.length + " clip(s) from " + IMPORT_LABEL + "/.\\n\\n" +
        proxyMsg +
        "When proxies finish:\\n" +
        "HDD backup: python main.py watch-backup --number " + (SCRIPT_NUMBER || "XXX") + "\\n" +
        "Drive:      python main.py upload-drive --number " + (SCRIPT_NUMBER || "XXX")
    );
}})();
"""


def write_premiere_setup_script(
    cfg: dict,
    project_root: Path,
    folder_name: str,
    prproj_path: Path,
    *,
    script_number: str = "",
    import_dir: Path | None = None,
    proxies_dir_override: Path | None = None,
    import_label: str = "",
    continue_existing_project: bool = False,
) -> Path:
    jsx_path = project_root / "automate_premiere.jsx"
    jsx_path.write_text(
        generate_premiere_setup_script(
            cfg,
            project_root,
            folder_name,
            prproj_path,
            script_number=script_number,
            import_dir=import_dir,
            proxies_dir_override=proxies_dir_override,
            import_label=import_label,
            continue_existing_project=continue_existing_project,
        ),
        encoding="utf-8",
    )
    return jsx_path
