# Licensing

CogniDQ is published under the **Apache License, Version 2.0**. The full
license text is in [LICENSE](../LICENSE) at the repository root, and the
project attribution notice is in [NOTICE](../NOTICE).

This document explains, in plain language, what that means for typical
users. It is informational only and is **not legal advice**. When in
doubt, consult a lawyer.

---

## What you can do

Under Apache-2.0 you may, free of charge:

- Use the software for any purpose, including commercial purposes.
- Modify the software.
- Distribute copies of the original or modified software.
- Sublicense and sell products that include the software.
- Use the patents granted by contributors with respect to their
  contributions.

You do **not** need to ask permission, pay royalties, or share your
modifications.

## What you must do

When you distribute the software (modified or not), you must:

1. Include a copy of the Apache-2.0 license.
2. Include the `NOTICE` file content (or equivalent attribution).
3. State any significant changes you made to the original code.
4. Preserve copyright, patent, trademark, and attribution notices in the
   source you redistribute.

You do **not** have to release your modifications as open-source, and you
do **not** have to use Apache-2.0 for code you build on top of CogniDQ.

## What is not granted

- **No warranty.** The software is provided "as is".
- **No trademark rights.** "CogniDQ" and any associated logos are not
  licensed for use as your product name. You may reference the project
  factually (e.g. "based on CogniDQ"), but you may not imply endorsement.
- **No support obligation.** Maintainers may help on a best-effort basis
  through GitHub issues; there is no SLA. Commercial support may be
  offered separately in the future — see [SUPPORT.md](../SUPPORT.md).

## Open-core model

CogniDQ uses an **open-core** strategy.

- The contents of this repository are the open-source **core**, available
  under Apache-2.0.
- Future enterprise / managed-service features (advanced multi-tenant
  administration, customer-side execution agents, advanced evidence
  workflows, managed cloud, dedicated support, etc.) may be offered under
  a separate commercial license. Those features are **not** included in
  this repository.

See [open-source-strategy.md](open-source-strategy.md) and
[enterprise-edition.md](enterprise-edition.md) for the feature
classification.

## Third-party software

CogniDQ depends on many open-source libraries. Their licenses apply to
those libraries individually:

- Python backend dependencies: see `backend/requirements.txt`.
- Frontend dependencies: see `frontend/package.json`.
- Container base images (PostgreSQL, Redis, Spark, MinIO, etc.) are
  provided by their respective projects under their own licenses.

If you redistribute CogniDQ, you must comply with each of those licenses
in addition to Apache-2.0.

## Contributions

By submitting a contribution (pull request, patch, etc.) you agree that
your contribution is licensed under Apache-2.0 to the project, per
Section 5 of the license. See [CONTRIBUTING.md](../CONTRIBUTING.md).

We do not currently require a separate Contributor License Agreement
(CLA), but this may change as the project grows.

## Reporting license issues

If you believe a file in this repository is misattributed, missing
required notices, or includes code under an incompatible license, please
open a GitHub issue or contact the maintainers privately as described in
[SECURITY.md](../SECURITY.md) for sensitive cases.
