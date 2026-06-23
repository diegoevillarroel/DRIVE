# DRIVE — GB/day Source Reference

Every number in DRIVE has a provenance. If it's not measured on your machine, it's flagged.

## Confidence Levels

| Badge | Meaning |
|---|---|
| **Live** | Measured by DRIVE's background sampler on *your* SSD in the last 30 s |
| **Measured** | Sampled by DRIVE's live `/api/scan?sample_seconds=N` endpoint |
| **Reported** | Self-reported by the tool's own telemetry or logs |
| **Estimated** | Conservative floor derived from architecture analysis + community reports |

## Per-Tool Sources

| Tool | GB/d | Confidence | Source |
|---|---|---|---|
| Ollama | 8.0 | Estimated | LMCache issue #2739 frame-cache; logicqo S6 community survey |
| Codex CLI | 15.0 | Estimated | Floor based on prompt/response logging patterns similar to Claude Code. No reproducible public measurement. |
| Cursor | 5.0 | Estimated | logicqo S1 — AI indexing cache for large codebases, continuous background writes |
| n8n | 4.0 | Estimated | Per-execution ledger writes; logicqo S6 |
| CrewAI | 3.0 | Estimated | Reasoning trace logs; logicqo S6 |
| AutoGen | 3.0 | Estimated | Reasoning trace logs; logicqo S6 |
| Claude Code | 25.0 | Reported | Anthropic Node.js server logs (self-reported telemetry) |
| Jan | 2.0 | Estimated | Minimal local writes beyond model download; logicqo S6 |
| LM Studio | 6.0 | Estimated | Model cache, config, logs; logicqo S6 |
| ChromaDB | 5.0 | Estimated | Vector persist + WAL; logicqo S6 |
| Hermes Agent | 2.0 | Estimated | Minimal: session DB + skill files; logicqo S6 |
| AutoGPT | 8.0 | Estimated | Heavy agentic loop with tool cache; LMCache #2739 |
| Node.js (AI) | 2.0 | Estimated | Conservative floor for any Node-based AI tool |
| Python (AI) | 2.0 | Estimated | Conservative floor for any Python-based AI tool |

## Citations

- **logicqo S1/S6**: [Local AI SSD TBW Failure](https://www.logicqo.com/2026/02/local-ai-ssd-tbw-failure.html)
- **LMCache #2739**: [github.com/LMCache/LMCache/issues/2739](https://github.com/LMCache/LMCache/issues/2739)
- **Claude Code**: Anthropic self-reported telemetry data

## Methodology

- **Measured values**: DRIVE uses `ProcessInspector.sample_framework_writes()` which counts flushed bytes to framework directories over a configurable time window (default 5 s, background-sampled every 30 s).
- **Reported values**: Tools that expose their own I/O counters (e.g., Ollama `/api/stats`).
- **Estimated values**: When no direct measurement exists, DRIVE uses a conservative floor based on:
  1. Architecture analysis (what the tool writes: model weights, logs, cache, traces)
  2. Community reports (Reddit, GitHub issues, blog posts)
  3. Conservative bias (floor, not ceiling)

All estimates skew *low* so users aren't alarmed by inflated numbers. When DRIVE measures on your machine, the Live badge replaces the estimate automatically.
