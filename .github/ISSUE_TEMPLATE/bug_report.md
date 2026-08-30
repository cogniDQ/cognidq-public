---
name: Bug report
about: Report a problem so we can fix it
title: "[bug] "
labels: ["bug"]
assignees: []
---

## Summary

A clear, one-line description of the problem.

## Environment

- CogniDQ version / commit SHA:
- Deployment: ☐ local Docker Compose ☐ self-hosted ☐ other (describe)
- Host OS:
- Docker version (`docker --version`):
- Docker Compose version (`docker compose version`):
- Browser + version (if frontend issue):

## Steps to reproduce

1.
2.
3.

## Expected behavior

What you expected to happen.

## Actual behavior

What actually happened. Include error messages verbatim.

## Logs

Paste relevant logs from the affected service. Use fenced code blocks.

```text
# backend logs
docker compose logs --tail=200 backend

# worker logs
docker compose logs --tail=200 worker
```

## Screenshots / recordings

If applicable, drag images here.

## Additional context

Anything else useful — feature flags enabled, custom config, etc.

## Checklist

- [ ] I searched existing issues before opening this one
- [ ] I redacted any sensitive data from logs / screenshots
- [ ] I'm running a reasonably recent version (`main` or latest tagged release)
