# Security policy

## Reporting a vulnerability

**Please do not open public GitHub issues for security vulnerabilities.**

If you believe you have found a security vulnerability in CogniDQ,
report it privately through one of these channels:

1. **Preferred:** [GitHub Security Advisories](https://github.com/cogniDQ/cognidq-public/security/advisories/new)
   on this repository. This creates a private advisory only the
   maintainers can see.
2. **Email:** open a placeholder issue asking for a contact address;
   maintainers will reply with a private channel. (A dedicated
   `security@` mailbox will be set up before the v0.1.0-alpha public
   release.)

Please include:

- A description of the issue and the impact you believe it has.
- Steps to reproduce, including the exact version / commit SHA.
- Any proof-of-concept code, logs, or HTTP traces (with secrets
  redacted).
- Whether the issue is currently public anywhere else.

We will acknowledge your report on a best-effort basis. We aim to
respond within **5 business days** for the initial response, and to
provide a fix or mitigation plan within **30 days** for confirmed
high-severity issues. These are best-effort targets, not contractual
commitments.

We will credit you in the advisory and the release notes unless you
ask to remain anonymous.

## Supported versions

CogniDQ is in early-stage open-source development. Until v1.0.0, only
the latest minor release will receive security fixes.

| Version | Supported |
|---|---|
| `0.1.x-alpha` and later pre-1.0 releases | Latest only |
| Older pre-releases | No |

## Default deployment is **not** production-ready

The `docker-compose.yml` shipped in this repository is for local
development and demos. **Do not** expose it to a public network
without applying the hardening steps in
[docs/production-hardening.md](docs/production-hardening.md). Specifically:

- Default passwords for PostgreSQL, MinIO, Grafana, Flower, etc. must be
  rotated.
- HTTPS / TLS termination must be added.
- Demo seed users must be disabled.
- Encryption keys (`DATASOURCE_ENCRYPTION_KEY`,
  `CREDENTIAL_ENCRYPTION_KEY`) must be generated locally and stored in
  a secret manager.

A misconfigured deployment is your responsibility, not a security
vulnerability in CogniDQ. We will help with hardening guidance on
public issues.

## Out-of-scope

The following are out of scope for our vulnerability program:

- Issues in the demo seed data or in synthetic test fixtures.
- Issues that require an attacker to already have administrative
  access to the host.
- Theoretical vulnerabilities without a concrete exploit path.
- Vulnerabilities in third-party services (GitHub, npm, PyPI, base
  Docker images) — please report those upstream.

## Disclosure

We follow a coordinated disclosure model:

1. Reporter contacts maintainers privately.
2. Maintainers confirm and develop a fix.
3. Fix lands in a release.
4. Maintainers and reporter publish an advisory describing the issue,
   affected versions, and the fix.

Embargo periods are negotiable for serious issues but should not exceed
**90 days** without mutual agreement.

## Hall of fame

A list of researchers credited with reports will be added here once the
project has its first public advisory.

## Cryptography note

CogniDQ uses standard cryptographic primitives via well-maintained
libraries (`cryptography` for Fernet, JWT via PyJWT, bcrypt for password
hashing). We do not implement custom cryptography. If you find a
weakness in our **use** of these libraries, please report it.
