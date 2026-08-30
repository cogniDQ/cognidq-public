# Documentation assets

This directory holds visual assets referenced from the documentation.

```
assets/
├── screenshots/    # UI screenshots (PNG, < 500 KB each)
└── diagrams/       # Architecture / flow diagrams (SVG preferred)
```

## Conventions

- **Screenshots**
  - PNG, 1280×800 viewport, taken in light mode.
  - Filename: `<area>-<feature>.png`, e.g. `rules-create.png`.
  - Synthetic / demo data only. No real customer data.
  - Update the screenshot when the corresponding UI ships a visible
    change.
- **Diagrams**
  - SVG preferred; PNG accepted at 2× density.
  - Source files (`.drawio`, `.excalidraw`, `.mermaid`) live next to
    the export, named `<diagram>.drawio` etc.
  - Mermaid diagrams that can be inlined into markdown should stay
    inlined; this folder is for diagrams too complex for inline
    Mermaid.

## Status

No screenshots exist yet. Below is the prioritized wishlist — capture
these first (all on the demo tenant/workspace from
`scripts/seed_demo_data.py`, synthetic data only, light mode,
1280×800):

| Priority | Filename | Page | What to show |
|---|---|---|---|
| P0 | `dashboard-overview.png` | Workspace dashboard | KQI trend, open issues/incidents summary, recent executions |
| P0 | `rules-nl-builder.png` | NL Rule Builder | A prompt entered + the compiled rule proposal/preview panel |
| P0 | `issues-list.png` | Issues list | A populated table with mixed severities/statuses, filters visible |
| P1 | `rules-list.png` | Rules list | A populated table of rules across a few dimensions (completeness, validity, etc.) |
| P1 | `flow-builder.png` | Flow Builder | A simple multi-node flow with a check node |
| P1 | `incident-detail.png` | Incident detail | SLA/evidence/linked-issues sections visible |
| P2 | `connections-list.png` | Data source connections | A few connector types, test-connection status |
| P2 | `datasets-detail.png` | Dataset detail | Profiling / field samples panel |

If you spot a doc page that would benefit from a screenshot or
diagram beyond this list, open a PR adding the asset here and a
reference from the relevant doc page. Synthetic data only — see
[../testing.md](../testing.md) for the test-data policy.
