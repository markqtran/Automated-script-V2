"""Generate Adobe Premiere ExtendScript for project setup, import, and proxies."""

from __future__ import annotations

import json
from pathlib import Path

from .premiere_proxy import auto_create_proxies, proxy_subfolder_name, resolve_proxy_preset_path
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
    - Scratch disks -> SSD project folder
    - Create/open project named like the folder
    - Import all clips under Video/
    - Create proxies (Quarter / ProRes QT Proxy / Proxies subfolder) when preset available
    """
    video_dir = project_root / video_folder_name(cfg)
    video_jsx = _jsx_path(video_dir)
    prproj_jsx = _jsx_path(prproj_path)
    project_root_jsx = _jsx_path(project_root)
    script_num = script_number or ""
    proxy_preset = resolve_proxy_preset_path(cfg)
    proxy_sub = proxy_subfolder_name(cfg)
    do_proxies = auto_create_proxies(cfg)

    literals = {
        "prproj": prproj_jsx,
        "video": video_jsx,
        "root": project_root_jsx,
        "folder": folder_name,
        "script": script_num,
        "preset": proxy_preset,
        "proxy_sub": proxy_sub,
        "auto_proxies": "true" if do_proxies else "false",
    }
    lit = {k: json.dumps(v) for k, v in literals.items()}

    return f"""// Auto-generated — Nathan Doan Productions
// Proxy target: Quarter, ProRes QuickTime Proxy, Proxy Icon, Video/{proxy_sub}/

(function () {{
    var PROJECT_PATH = {lit["prproj"]};
    var VIDEO_DIR = {lit["video"]};
    var PROJECT_ROOT = {lit["root"]};
    var FOLDER_NAME = {lit["folder"]};
    var SCRIPT_NUMBER = {lit["script"]};
    var PROXY_PRESET_PATH = {lit["preset"]};
    var PROXY_SUBFOLDER = {lit["proxy_sub"]};
    var AUTO_CREATE_PROXIES = {lit["auto_proxies"]} === "true";

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
                if (mp && mp.length > 0 && child.canProxy && child.canProxy()) {{
                    clips.push(child);
                }}
            }}
        }}
    }}

    function proxyOutputPath(mediaPath) {{
        var src = new File(mediaPath);
        var parent = src.parent;
        var proxyDir = new Folder(parent.fsName + pathSep() + PROXY_SUBFOLDER);
        if (!proxyDir.exists) proxyDir.create();
        var dot = src.name.lastIndexOf(".");
        var base = dot > 0 ? src.name.substring(0, dot) : src.name;
        return proxyDir.fsName + pathSep() + base + "_Proxy.mov";
    }}

    function findPresetInFolder(folder, matches) {{
        if (!folder || !folder.exists) return "";
        var files = folder.getFiles("*.epr", true);
        for (var i = 0; i < files.length; i++) {{
            var n = files[i].name.toLowerCase();
            if (n.indexOf("prores") >= 0 && n.indexOf("proxy") >= 0) {{
                return files[i].fsName;
            }}
            if (n.indexOf("proxy") >= 0 && n.indexOf("ingest") >= 0) {{
                return files[i].fsName;
            }}
        }}
        return "";
    }}

    function resolveProxyPreset() {{
        if (PROXY_PRESET_PATH && PROXY_PRESET_PATH.length > 0) {{
            var f = new File(PROXY_PRESET_PATH);
            if (f.exists) return f.fsName;
        }}
        var bundled = new File(PROJECT_ROOT + pathSep() + "NDP_Proxy_Ingest.epr");
        if (bundled.exists) return bundled.fsName;

        var userHome = Folder.userData.fsName;
        var ameRoot = new Folder(userHome + pathSep() + "Adobe");
        if (ameRoot.exists) {{
            var ameChildren = ameRoot.getFiles();
            for (var a = 0; a < ameChildren.length; a++) {{
                if (ameChildren[a] instanceof Folder && ameChildren[a].name.indexOf("Media Encoder") >= 0) {{
                    var presets = new Folder(ameChildren[a].fsName + pathSep() + "Presets");
                    var hit = findPresetInFolder(presets, null);
                    if (hit) return hit;
                }}
            }}
        }}
        return "";
    }}

    function onProxyJobComplete(jobID, outputFilePath) {{
        var item = proxyJobs[jobID];
        if (!item) return;
        try {{
            if (item.canProxy() && !item.hasProxy()) {{
                item.attachProxy(outputFilePath, 0);
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

    function queueProxiesForClips(clips, presetPath) {{
        if (!app.encoder || !presetPath || clips.length === 0) return 0;

        try {{
            app.encoder.bind("onEncoderJobComplete", onProxyJobComplete);
            app.encoder.bind("onEncoderJobError", onProxyJobError);
            app.encoder.bind("onEncoderJobQueued", onProxyJobQueued);
        }} catch (bindErr) {{}}

        var queued = 0;
        var workArea = 0;
        var removeOnComplete = 0;

        try {{
            if (app.encoder.createProxyJob && AUTO_CREATE_PROXIES) {{
                var job = app.encoder.createProxyJob(clips, presetPath);
                if (job) {{
                    if (app.encoder.launchEncoder) app.encoder.launchEncoder();
                    if (app.encoder.startBatch) app.encoder.startBatch();
                    return clips.length;
                }}
            }}
        }} catch (cpErr) {{}}

        for (var c = 0; c < clips.length; c++) {{
            var clip = clips[c];
            if (clip.hasProxy && clip.hasProxy()) continue;
            var mediaPath = clip.getMediaPath();
            if (!mediaPath) continue;
            var outPath = proxyOutputPath(mediaPath);
            try {{
                var jobID = app.encoder.encodeProjectItem(
                    clip, outPath, presetPath, workArea, removeOnComplete
                );
                if (jobID && jobID !== "0" && jobID !== 0) {{
                    proxyJobs[jobID] = clip;
                    queued++;
                }}
            }} catch (encErr) {{}}
        }}

        if (queued > 0) {{
            try {{
                if (app.encoder.launchEncoder) app.encoder.launchEncoder();
                if (!batchStarted && app.encoder.startBatch) app.encoder.startBatch();
            }} catch (launchErr) {{}}
        }}
        return queued;
    }}

    // --- 1. Project on SSD ---
    setScratchDisks(PROJECT_ROOT);

    var prprojFile = new File(PROJECT_PATH);
    var opened = prprojFile.exists
        ? app.openDocument(PROJECT_PATH, 1, 1, 1, 1)
        : app.newProject(PROJECT_PATH);

    if (!opened) {{
        alertMsg("Could not create/open project:\\n" + PROJECT_PATH);
        return;
    }}
    app.project.save();

    // --- 2. Enable ingest proxies (uses settings saved in project_template.prproj) ---
    if (AUTO_CREATE_PROXIES) {{
        try {{ app.project.setEnableTranscodeOnIngest(true); }} catch (ingestErr) {{}}
    }}

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
        var clips = [];
        collectClipItems(app.project.rootItem, clips);

        var presetPath = resolveProxyPreset();
        var queued = 0;
        if (presetPath) {{
            queued = queueProxiesForClips(clips, presetPath);
        }}

        if (queued > 0) {{
            proxyMsg =
                "Proxy jobs queued: " + queued + " clip(s).\\n" +
                "Preset: ProRes QuickTime Proxy (Quarter in ingest template)\\n" +
                "Output: next to originals in " + PROXY_SUBFOLDER + " folder\\n" +
                "Media Encoder is processing.\\n\\n";
        }} else if (!presetPath) {{
            proxyMsg =
                "No proxy .epr preset found.\\n\\n" +
                "ONE-TIME SETUP:\\n" +
                "1. In Media Encoder: Preset Browser > + > Create Ingest Preset\\n" +
                "   - Create Proxies, ProRes QuickTime Proxy, Quarter, Proxy Icon\\n" +
                "   - Location: Next to Original Media, in Proxy folder\\n" +
                "2. Export/save as templates/NDP_Proxy_Ingest.epr\\n" +
                "   OR set premiere.proxy_ingest_preset in config.yaml\\n\\n" +
                "OR save templates/project_template.prproj with Ingest settings, re-run workflow.\\n\\n";
        }} else {{
            proxyMsg = "Clips imported. If proxies did not start, use File > Scripts > Run Script File again.\\n\\n";
        }}
    }}

    alertMsg(
        "Project: " + FOLDER_NAME + "\\n" +
        "Location: " + PROJECT_ROOT + "\\n" +
        "Imported " + mediaPaths.length + " clip(s) from Video/.\\n\\n" +
        proxyMsg +
        "When proxies finish:\\n" +
        "python main.py upload-drive --number " + (SCRIPT_NUMBER || "XXX")
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
