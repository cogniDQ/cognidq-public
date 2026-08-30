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

The asset directory is currently empty. Screenshots and diagrams will
land alongside the documentation pages that reference them.

If you spot a doc page that would benefit from a screenshot or
diagram, open a PR adding the asset here and a reference from the
relevant doc page. Synthetic data only — see
[../testing.md](../testing.md) for the test-data policy.
