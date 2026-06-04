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
) -> str:
    """
    JSX run inside Premiere (auto via /C es.processFile or File > Scripts):
    - Scratch disks -> SSD project folder
    - Create/open project named like the folder
    - Import all clips under Video/
    - Create proxies (Quarter / ProRes QT Proxy / Proxies subfolder) when preset available
    """
    video_name = video_folder_name(cfg)
    video_dir = project_root / video_name
    proxies_dir = video_dir / proxy_subfolder_name(cfg)
    video_jsx = _jsx_path(video_dir)
    proxies_jsx = _jsx_path(proxies_dir)
    prproj_jsx = _jsx_path(prproj_path)
    project_root_jsx = _jsx_path(project_root)
    script_num = script_number or ""
    proxy_preset = resolve_proxy_preset_path(cfg)
    encode_preset = resolve_encode_preset_path(cfg) or proxy_preset
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

    function queueProxiesForClips(clips, ingestPreset, encodePreset) {{
        if (!app.encoder || clips.length === 0) return 0;
        var preset = ingestPreset || encodePreset;
        if (!preset) return 0;

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
        var encPreset = encodePreset || ingestPreset;

        // Explicit AME output on SSD: PROJECT_ROOT/Video/Proxies/
        for (var c = 0; c < clips.length; c++) {{
            var clip = clips[c];
            if (clip.hasProxy && clip.hasProxy()) continue;
            var mediaPath = clip.getMediaPath();
            if (!mediaPath || !isUnderVideoDir(mediaPath)) continue;
            var outPath = proxyOutputPath(mediaPath);
            var jobID = 0;
            try {{
                jobID = app.encoder.encodeProjectItem(
                    clip, outPath, encPreset, workArea, removeOnComplete
                );
            }} catch (epiErr) {{}}
            if (!jobID || jobID === "0" || jobID === 0) {{
                try {{
                    jobID = app.encoder.encodeFile(mediaPath, outPath, encPreset, workArea, removeOnComplete);
                }} catch (efErr) {{}}
            }}
            if (jobID && jobID !== "0" && jobID !== 0) {{
                proxyJobs[jobID] = clip;
                queued++;
            }}
        }}

        if (queued > 0) {{
            try {{ app.encoder.startBatch(); }} catch (sb3Err) {{}}
            return queued;
        }}

        for (var p = 0; p < clips.length; p++) {{
            var it = clips[p];
            if (it.hasProxy && it.hasProxy()) continue;
            if (it.createProxy) {{
                try {{
                    if (it.createProxy(ingestPreset || preset)) queued++;
                }} catch (cpItemErr) {{}}
            }}
        }}
        if (queued > 0) {{
            try {{ app.encoder.startBatch(); }} catch (sbErr) {{}}
            return queued;
        }}

        try {{
            if (app.encoder.createProxyJob) {{
                var proxyJob = app.encoder.createProxyJob(clips, ingestPreset || preset);
                if (proxyJob) {{
                    try {{ app.encoder.startBatch(); }} catch (sb2Err) {{}}
                    return clips.length;
                }}
            }}
        }} catch (cpJobErr) {{}}

        return 0;
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

        var ingestPreset = resolvePresetPath(PROXY_PRESET_PATH, "");
        var encodePreset = resolvePresetPath(ENCODE_PRESET_PATH, PROXY_PRESET_PATH);
        var queued = 0;
        if (ingestPreset || encodePreset) {{
            queued = queueProxiesForClips(clips, ingestPreset, encodePreset);
        }}

        if (queued > 0) {{
            proxyMsg =
                "Create Proxies started for " + queued + " clip(s).\\n" +
                "Output folder (SSD):\\n" + PROXIES_DIR + "\\n" +
                "Watch progress in Media Encoder.\\n\\n";
        }} else if (!ingestPreset && !encodePreset) {{
            proxyMsg =
                "Could not find proxy preset (.epr). Media Encoder opened with no jobs.\\n\\n" +
                "ONE-TIME (5 min) — match your Create Proxies settings:\\n" +
                "1. Media Encoder > + > Create Ingest Preset\\n" +
                "   Create Proxies | ProRes QuickTime Proxy | Quarter | Proxy Icon\\n" +
                "   Next to Original Media, in Proxy folder\\n" +
                "2. Right-click preset > Reveal Preset File\\n" +
                "3. Copy to: templates\\\\NDP_Proxy_Ingest.epr\\n" +
                "4. python main.py list-proxy-presets\\n" +
                "5. Re-run workflow\\n\\n" +
                "Until then: select all clips in Project panel >\\n" +
                "Right-click > Proxy > Create Proxies (same settings).\\n\\n";
        }} else {{
            proxyMsg =
                "Preset found but no jobs queued. Select all clips in Video/, then run\\n" +
                "automate_premiere.jsx again, or Create Proxies manually.\\n\\n";
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
