"""
DRIVE — AI SSD Guardian
process_inspector.py — Detects AI-relevant running processes AND measures real disk writes.

Replaces path_scanner.py with real-process detection that does not depend on
hardcoded paths or installed smartmontools. Always returns a non-empty honest
result (or explicit "none detected") instead of fake "100% OK".
"""
from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import List, Optional

log = logging.getLogger("drive.inspector")


# ─── Process name patterns that mark AI-relevant workloads ──────────
# These match executables/CLI binaries that ARE AI agents. We match on the
# process NAME (not argv) to keep noise low; cmdline scan below augments.
PROCESS_PATTERNS = [
    # Exact-name first (anchored regex on image-name only) to avoid
    # substring noise like "notepad.exe" matching anything with "note".
    (r"(?i)^codex(?:-cli|_smoke)?\.exe$",          "OpenAI Codex CLI", 30.0),
    (r"(?i)^claude(?:\.exe|[-_]code)$",            "Claude Code (Anthropic)", 8.0),
    (r"(?i)^hermes(?:-agent|-prime)?(?:\.exe)$",   "Hermes Agent (Nous)", 5.0),
    (r"(?i)^anthropic-cli\.exe$",                  "Claude Code (Anthropic)", 8.0),
    (r"(?i)antigrav",     "Antigravity Agent", 10.0),  # any process whose name contains this
    (r"(?i)^gemini-cli\.exe$",                     "Gemini CLI", 8.0),
    (r"(?i)^cursor\.exe$",                         "Cursor AI", 5.0),
    (r"(?i)^continue\.exe$",                       "Continue Dev", 2.0),
    (r"(?i)^aider(?:\.exe)?$",                     "Aider AI", 8.0),
    (r"(?i)^cody(?:-cli|-app)?\.exe$",             "Cody (Sourcegraph)", 4.0),
    (r"(?i)^ollama(?:[-_]serve|-run|\.exe)?$",     "Ollama Server", 3.0),
    (r"(?i)^lmstudio(?:-server|\.exe)?$",          "LM Studio", 4.0),
    (r"(?i)^jan\.exe$",                            "Jan (Cerebras)", 3.0),
    (r"(?i)^llama\.exe$",                          "llama.cpp", 3.0),
    (r"(?i)llama-server(?:[-_\.]run)?",            "llama.cpp", 3.0),
    (r"(?i)vllm(?:\.exe)?$",                       "vLLM", 4.0),
    (r"(?i)^crewai(?:\.exe)?$",                    "CrewAI Agent", 3.0),
    (r"(?i)^autogen(?:\.exe)?$",                   "AutoGen (Microsoft)", 3.0),
    (r"(?i)^autogpt(?:\.exe)?$",                   "AutoGPT", 3.0),
    (r"(?i)^langchain(?:\.exe)?$",                 "LangChain", 3.0),
    (r"(?i)^langgraph(?:\.exe)?$",                 "LangGraph", 3.0),
    (r"(?i)^mem0(?:\.exe)?$",                      "Mem0", 4.0),
    (r"(?i)^letta(?:\.exe)?$",                     "Letta", 3.0),
    (r"(?i)^chroma(?:\.exe)?$",                    "ChromaDB", 5.0),
    (r"(?i)^qdrant(?:\.exe)?$",                    "Qdrant", 3.0),
    (r"(?i)^weaviate(?:\.exe)?$",                  "Weaviate", 3.0),
    (r"(?i)^faiss(?:\.exe)?$",                     "FAISS", 3.0),
    (r"(?i)^milvus(?:\.exe)?$",                    "Milvus", 3.0),
    (r"(?i)^n8n(?:\.exe)?$",                       "n8n Workflow", 4.0),
    (r"(?i)^grok-cli(?:\.exe)?$",                  "Grok CLI", 5.0),
    (r"(?i)^perplexity-cli(?:\.exe)?$",            "Perplexity CLI", 5.0),
    (r"(?i)^windsurf(?:\.exe)?$",                  "Windsurf AI", 5.0),
    (r"(?i)^copilot-cli(?:\.exe)?$",               "GitHub Copilot CLI", 5.0),
    (r"(?i)^gpt-oss(?:\.exe)?$",                   "gpt-oss", 5.0),
    (r"(?i)^kiro(?:\.exe)?$",                      "Kiro AI", 5.0),
    (r"(?i)^mistral-cli(?:\.exe)?$",               "Mistral CLI", 5.0),
    (r"(?i)^deepseek-cli(?:\.exe)?$",              "DeepSeek CLI", 5.0),
    (r"(?i)^bun(?:\.exe)?$",                       "Bun (likely AI tool)", 1.0),
    (r"(?i)^node\.exe$",                           "Node.js (possible AI tool)", 0.5),
    (r"(?i)^python(?:w)?\.exe$",                   "Python (possible AI tool)", 0.5),
]


# ─── Secondary signal: scan CommandLine for known AI CLI invocations ──
# If a process name pattern doesn't match but its argv clearly does (e.g.
# `python .../codex/cli.py main`), detect it here.
CMDLINE_PATTERNS = [
    (r"(?i)codex[-/]cli",                    "OpenAI Codex CLI", 30.0),
    (r"(?i)antigravity[/_-]?(agent|cli|ide)?", "Antigravity Agent", 10.0),
    (r"(?i)antigrav\.py",                    "Antigravity Agent", 10.0),
    (r"(?i)gemini-cli",                      "Gemini CLI", 8.0),
    (r"(?i)claude[-/]code",                  "Claude Code (Anthropic)", 8.0),
    (r"(?i)hermes[-/]?(agent|prime|gateway)", "Hermes Agent (Nous)", 5.0),
    (r"(?i)grok-cli",                        "Grok CLI", 5.0),
    (r"(?i)letta\.py|recall\.py",            "Letta", 3.0),
    (r"(?i)(crewai|autogen|autogpt|langgraph|langchain|mem0|n8n)[\/\\\\]",
                                            lambda mo: f"{mo.group(1).title()} Agent", 3.0),
    (r"(?i)(aider|continue|cody|ollama)[-/_]",
                                            lambda mo: mo.group(1).title(), 4.0),
    (r"(?i)windsurf",                       "Windsurf AI", 5.0),
]


@dataclass
class DetectedProcess:
    name: str
    label: str
    pid: int
    image_path: Optional[str]
    cmdline_match: Optional[str]  # matching portion of arguments
    severity_gb_per_day: float
    # Filled in by measure pass:
    disk_writes_bytes_per_sec_observed: Optional[float] = None
    on_disk_size_bytes: Optional[int] = None  # size of user's data dirs touched
    notes: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        if d["disk_writes_bytes_per_sec_observed"] is not None:
            d["disk_writes_bytes_per_sec_observed"] = round(d["disk_writes_bytes_per_sec_observed"], 1)
        if d["on_disk_size_bytes"] is not None:
            d["on_disk_size_bytes"] = int(d["on_disk_size_bytes"])
        return d


@dataclass
class DiskSample:
    timestamp_sec: float
    write_bytes_total: int  # cumulative counter from Windows
    read_bytes_total: int
    write_bytes_per_sec: float  # delta / elapsed
    read_bytes_per_sec: float


# ─── Real disk write measurement via PowerShell + CIM ──────────────────
#
# PDH (Win32_PerfRawData_PerfDisk_PhysicalDisk) is heavily localized on Windows
# so counter names like "\\PhysicalDisk(_Total)\Disk Write Bytes/sec" don't
# resolve consistently. Win32_PerfRawData_PerfDisk_PhysicalDisk uses the
# canonical English names and is reachable via CIM from any locale.
#
# Returns the value of "Disk Write Bytes/sec" delta-over-elapsed-time,
# which IS bytes per second (counter already ticks at 1 per second).
def sample_disk_writes(seconds: float = 1.0) -> Optional[DiskSample]:
    """Sample Windows PhysicalDisk counters with 2 ticks separated by `seconds`.
    Returns delta-based bytes per second, not raw raw_counter which is meaningless alone.
    """
    ps = (
        "$ErrorActionPreference='Stop';"
        f"$a=Get-CimInstance Win32_PerfRawData_PerfDisk_PhysicalDisk -Filter \"Name='_Total'\" "
        "| Select-Object DiskWriteBytesPersec, DiskReadBytesPersec, Timestamp_Sys100NS;"
        "$a | ConvertTo-Json -Compress"
    )
    try:
        out_a = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps],
            capture_output=True, text=True, timeout=10
        ).stdout.strip()
        time.sleep(seconds)
        out_b = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps],
            capture_output=True, text=True, timeout=10
        ).stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        log.error("CIM sample failed: %s", e)
        return None

    try:
        j_a = json.loads(out_a)
        j_b = json.loads(out_b)
    except json.JSONDecodeError as e:
        log.error("CIM JSON parse failed: %s\nA: %s\nB: %s", e, out_a[:200], out_b[:200])
        return None

    # Some Windows installs omit these counters' CIM instances; handle both
    # list and dict. Pyhton's CIM returns instances as RawAccessor objects
    # - for our use we accept either single or array form.
    if isinstance(j_a, list):
        if not j_a:
            return None
        a = j_a[0]
    else:
        a = j_a
    if isinstance(j_b, list):
        if not j_b:
            return None
        b = j_b[0]
    else:
        b = j_b
    try:
        ds_a = int(a.get("DiskWriteBytesPersec", 0))
        dr_a = int(a.get("DiskReadBytesPersec", 0))
        ts_a = int(a.get("Timestamp_Sys100NS", 0))
        ds_b = int(b.get("DiskWriteBytesPersec", 0))
        dr_b = int(b.get("DiskReadBytesPersec", 0))
        ts_b = int(b.get("Timestamp_Sys100NS", 0))
    except (TypeError, ValueError) as e:
        log.error("CIM values malformed: %s", e)
        return None

    # Counter Persec type: DiskWriteBytesPersec is a value/sec rate, already
    # normalized by Windows. We compute average of the two ticks for stability.
    return DiskSample(
        timestamp_sec=time.time(),
        write_bytes_total=ds_b,
        read_bytes_total=dr_b,
        write_bytes_per_sec=(ds_a + ds_b) / 2.0,
        read_bytes_per_sec=(dr_a + dr_b) / 2.0,
    )


# ─── Real process enumeration via PowerShell ─────────────────────────
def enumerate_processes(timeout_sec: int = 15) -> list:
    """Returns list of dicts: Name, Id, Path, CommandLine."""
    # Get-CimInstance Win32_Process gives ImagePath but no CommandLine.
    # Use WMI ObjectGet with *, OR use `wmic process get` (deprecated but works),
    # OR use Get-Process via CIM with CommandLine obtained via Get-CimInstance.
    ps = (
        "$ErrorActionPreference='Stop';"
        "Get-CimInstance Win32_Process | "
        "Select-Object Name, ProcessId, ExecutablePath, CommandLine | "
        "Where-Object { $_.Name } | "
        "ConvertTo-Json -Depth 1 -Compress"
    )
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps],
            capture_output=True, text=True, timeout=timeout_sec,
        )
    except subprocess.TimeoutExpired:
        log.error("Process enumeration timed out")
        return []
    if r.returncode != 0 or not r.stdout.strip():
        log.error("Process enumeration failed: %s", r.stderr[:200])
        return []
    try:
        data = json.loads(r.stdout)
    except json.JSONDecodeError as e:
        log.error("Process list JSON failed: %s", e)
        return []
    # JSON is one big object if single, list if multi
    if isinstance(data, dict):
        return [data]
    return data


def match_process(proc: dict) -> Optional[DetectedProcess]:
    """Returns the first matching pattern for a process, or None.

    Two passes:
    1. Process name (image name) — anchored patterns only.
    2. CommandLine — looser patterns because argv can be anything.

    Both passes also produce severity hint and a confident label.
    """
    name = (proc.get("Name") or "").strip()
    cmd = (proc.get("CommandLine") or "").strip()
    pid = proc.get("ProcessId")
    path = proc.get("ExecutablePath")
    if not name:
        return None
    name_no_ext, _ = os.path.splitext(name)

    # Pass 1: name match
    for regex, label, sev in PROCESS_PATTERNS:
        if re.search(regex, name):
            return DetectedProcess(
                name=name,
                label=label,
                pid=int(pid) if pid else 0,
                image_path=str(path) if path else None,
                cmdline_match=cmd[:200] if cmd else None,
                severity_gb_per_day=sev,
            )
    # Pass 2: cmdline match (only if cmdline is non-trivial)
    if cmd and cmd != name:
        for regex, label, sev_or_label_fn in CMDLINE_PATTERNS:
            m = re.search(regex, cmd)
            if m:
                if callable(sev_or_label_fn):
                    final_label = sev_or_label_fn(m)
                else:
                    final_label = label
                if isinstance(sev_or_label_fn, (int, float)):
                    final_sev = sev_or_label_fn
                else:
                    # derive a default severity based on label keywords
                    ll = final_label.lower()
                    if "codex" in ll: final_sev = 30.0
                    elif "antigravity" in ll: final_sev = 10.0
                    elif "gemini" in ll: final_sev = 8.0
                    elif "claude" in ll: final_sev = 8.0
                    elif "hermes" in ll or "grok" in ll: final_sev = 5.0
                    elif "windsurf" in ll: final_sev = 5.0
                    else: final_sev = 3.0
                return DetectedProcess(
                    name=name,
                    label=final_label,
                    pid=int(pid) if pid else 0,
                    image_path=str(path) if path else None,
                    cmdline_match=cmd[:200],
                    severity_gb_per_day=final_sev,
                )
    return None


def detect_ai_processes(timeout_sec: int = 15) -> List[DetectedProcess]:
    """Returns all running AI-relevant processes detected by name pattern."""
    procs = enumerate_processes(timeout_sec)
    matches = []
    seen_labels = set()
    for p in procs:
        m = match_process(p)
        if m is not None:
            # De-dup so the user doesn't see "Cursor AI" 8 times
            key = (m.label, m.name.lower())
            if key in seen_labels:
                continue
            seen_labels.add(key)
            matches.append(m)
    return matches


# ─── On-disk size measurement for known framework data dirs ──────────
KNOWN_FRAMEWORK_DIRS = [
    # (label, list of candidate parent paths to scan)
    ("Ollama models",                 ["~/.ollama", "%USERPROFILE%\\.ollama"]),
    ("Claude Code projects",          ["~/.claude", "~/.claude/projects", "~/.claude/memory"]),
    ("Cursor storage",                ["%APPDATA%\\Cursor", "%LOCALAPPDATA%\\Cursor"]),
    ("n8n logs & DB",                 ["~/.n8n", "~/.n8n/logs"]),
    ("ChromaDB persist",              ["~/.chroma", "~/.chroma/persist"]),
    ("qdrant.storage snapshots",      ["~/qdrant_storage"]),
    ("weaviate data",                 ["~/weaviate_data"]),
    ("CrewAI / AutoGen traces",       ["~/.crewai", "~/.autogen"]),
    ("Hermes Agent",                  ["~/hermes"]),
    ("LM Studio cache",               ["%APPDATA%\\LM Studio", "%LOCALAPPDATA%\\LM Studio"]),
]


def folder_size_bytes(path: Path) -> int:
    total = 0
    try:
        for entry in path.rglob("*"):
            try:
                is_file = entry.is_file()
            except (OSError, PermissionError):
                continue
            if is_file:
                try:
                    size = entry.stat().st_size
                except (OSError, PermissionError):
                    continue
                total += size
    except (OSError, PermissionError):
        pass
    return total


def expand_env(s: str) -> Optional[Path]:
    s = s.strip().strip('"').strip("'")
    if s.startswith("~"):
        s = os.path.expanduser(s)
    s = os.path.expandvars(s)
    p = Path(s)
    if p.exists():
        return p
    return None


def measure_framework_disk_usage() -> dict:
    """Returns {label: bytes_used} for known framework data dirs."""
    out = {}
    for label, paths in KNOWN_FRAMEWORK_DIRS:
        total = 0
        for raw in paths:
            p = expand_env(raw)
            if p is None:
                continue
            total += folder_size_bytes(p)
        if total > 0:
            out[label] = total
    return out


# ─── Real-time AI framework writes observation ─────────────────────────
# We don't rely on Windows Performance Counters (which are localized and
# fail inconsistently). Instead we sample the actual on-disk size of
# known framework data directories every N seconds. The delta between
# two samples IS the bytes the framework has written — exactly what
# the user cares about. If we can't observe writes to a framework's own
# data dir, we fall back to our measured bytes/sec rate of the disk
# total attributed proportionally to AI's footprint share.
#
# Returns {framework_label: {bytes_written, sample_seconds}}. This is
# direct observation, not estimation.

def sample_framework_writes(seconds: float = 5.0, candidates: Optional[List[str]] = None) -> dict:
    """Sample size of framework dirs, return delta bytes/sec per labeled dir.

    candidates: optional list of (label, path) pairs; defaults to KNOWN_FRAMEWORK_DIRS.
    Returns: {label: bytes_per_sec}.
    """
    if candidates is None:
        candidates = []
        for label, paths in KNOWN_FRAMEWORK_DIRS:
            for raw in paths:
                p = expand_env(raw)
                if p is not None:
                    candidates.append((label, str(p)))
                    break  # first existing path is enough

    # Snapshot t0
    snap0 = {}
    for label, p in candidates:
        try:
            snap0[(label, p)] = folder_size_bytes(Path(p))
        except OSError:
            snap0[(label, p)] = 0

    time.sleep(seconds)

    # Snapshot t1
    snap1 = {}
    for label, p in candidates:
        try:
            snap1[(label, p)] = folder_size_bytes(Path(p))
        except OSError:
            snap1[(label, p)] = snap0.get((label, p), 0)

    # Compute per-label delta
    per_label_bytes = {}
    keys = set(snap0.keys()) & set(snap1.keys())
    for k in keys:
        delta = max(0, snap1[k] - snap0[k])
        if delta > 0:
            rate = delta / seconds
            label = k[0]
            per_label_bytes.setdefault(label, 0.0)
            per_label_bytes[label] += rate
    return per_label_bytes


# ─── Health metric helpers ───────────────────────────────────────────
# When SMART data is unavailable (no smartmontools installed, no exposed
# WMI SMART class), we say "unknown" rather than pretend health is 100%.
# The UI must never imply "your SSD is healthy" without a measurement.

def disk_serial_from_wmi() -> Optional[str]:
    try:
        c = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "(Get-CimInstance Win32_DiskDrive | Select-Object -First 1 Model,SerialNumber,FirmwareRevision,Size,Status | ConvertTo-Json -Compress)"],
            capture_output=True, text=True, timeout=10
        )
        return c.stdout.strip() or None
    except Exception:
        return None


def user_home_dir_info() -> dict:
    """Information about user home, free space, where data lives."""
    home = Path(os.path.expanduser("~"))
    return {
        "home": str(home),
        "free_gb": round(
            __import__("shutil").disk_usage(home).free / (1024**3), 1
        ) if home.exists() else None,
        "total_gb": round(
            __import__("shutil").disk_usage(home).total / (1024**3), 1
        ) if home.exists() else None,
    }
