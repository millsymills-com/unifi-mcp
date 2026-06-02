# Security Policy

## Supported Versions

The latest minor release on PyPI receives security fixes. Older minors are not supported.

| Version | Supported          |
| ------- | ------------------ |
| 0.3.x   | :white_check_mark: |

## Reporting a Vulnerability

Please report security vulnerabilities **privately**. Do **not** open a public GitHub issue.

Two private disclosure channels:

1. **GitHub Security Advisories** (preferred). Open a private advisory at
   <https://github.com/millsymills-com/unifi-mcp/security/advisories/new>.
2. **Email**: `andyandymillsmills@gmail.com` with subject prefix `[unifi-mcp security]`.

Please include:

- A description of the issue and the impact you observed.
- Steps to reproduce, including any relevant configuration.
- Affected version(s) of `unifi-mcp` and any client / runtime details.
- Whether the issue is already public anywhere.

We aim to acknowledge reports within **3 business days** and to ship a fix or
mitigation for confirmed High/Critical issues within **30 days** of triage.

## Disclosure Process

1. Triage and reproduce the report on a supported version.
2. Develop and test a fix on a private branch.
3. Coordinate a release date with the reporter.
4. Publish the fix, a GitHub Security Advisory, and a release-notes entry
   crediting the reporter (unless they ask to remain anonymous).

## Scope

In scope:

- Code in this repository (`src/unifi_mcp/`, tests, packaging).
- Documented configuration surfaces (env vars in `README.md` / `.env.example`).
- The published `unifi-mcp` PyPI package.

Out of scope:

- Vulnerabilities in upstream UniFi firmware or APIs; please report those to
  Ubiquiti directly.
- Issues that require an attacker who already has shell access on the host
  running the server.
- Findings against unsupported versions.
