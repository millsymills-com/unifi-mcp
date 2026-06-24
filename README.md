<p align="center">
  <img src="docs/assets/logo.svg" alt="unifi-mcp logo" width="200" />
</p>

# unifi-mcp

Production-grade Python MCP server for UniFi Site Manager, Network, and Protect APIs.

**[Live demo →](https://millsymills.com/unifi)**

## Status

Stage: S3

Actively maintained. 160 tools spanning all three UniFi APIs — complete for the
core Network controller workflows it targets, with documented gaps against the
official Network/Protect/Site Manager API surfaces. See the
[API coverage matrix](docs/api-coverage-matrix.md) for the endpoint-by-endpoint
breakdown. Installed from source, not published to PyPI. See
[CHANGELOG.md](CHANGELOG.md) for release history.

## Features

- **160 MCP tools** covering UniFi Network (106), Protect (45), and Site Manager (9) APIs, all under the `unifi_*` namespace
- **Read/write mode separation**: write tools invisible in readonly mode
- **Graceful per-API degradation**: only registers tools for configured APIs
- **Typed, linted, tested**: strict `ty`, `ruff`, `pytest` with CI on Python 3.13

## Write safety

The server starts in **readonly mode** by default and only exposes read tools.
The 60 write tools are invisible until you explicitly set
`UNIFI_MODE=readwrite`.

> [!WARNING]
> Write tools mutate live controller configuration. UniFi controllers do **not**
> apply config changes transactionally. A rejected create (e.g. a VLAN
> conflict) can leave a partial record on disk. Accumulated bad writes have, in
> testing, corrupted a gateway's on-disk config badly enough to require a
> factory reset. Before enabling `readwrite`:
>
> - Keep an exported controller backup you can restore from.
> - Prefer testing against non-production hardware.
> - Review what an agent is about to do; write tools carry per-tool caveats in
>   their descriptions.
>
> If you only need to query your network, leave the server in readonly mode.

## Quick Start

```bash
# Install from source
git clone https://github.com/millsymills-com/unifi-mcp.git
cd unifi-mcp
uv sync

# Configure
cp .env.example .env
# Edit .env with your UniFi API keys

# Run (readonly mode by default)
uv run unifi-mcp
```

Or run directly from the repo with `uvx`, no clone required:

```bash
uvx --from git+https://github.com/millsymills-com/unifi-mcp.git unifi-mcp
```

## MCP client setup

Drop the snippets below into your MCP client config and replace the env-var
values with your own UniFi API keys.

### Claude Desktop

Edit `~/Library/Application Support/Claude/claude_desktop_config.json`
(macOS) or `%AppData%\Claude\claude_desktop_config.json` (Windows):

```json
{
  "mcpServers": {
    "unifi": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/millsymills-com/unifi-mcp.git", "unifi-mcp"],
      "env": {
        "UNIFI_NETWORK_HOST": "192.168.1.1",
        "UNIFI_NETWORK_API": "<network-key>",
        "UNIFI_PROTECT_HOST": "192.168.1.220",
        "UNIFI_PROTECT_API": "<protect-key>",
        "UNIFI_SITE_MANAGER_API": "<site-manager-key>"
      }
    }
  }
}
```

### Claude Code

Add as a project-scoped MCP server:

```bash
claude mcp add unifi \
  -e UNIFI_NETWORK_HOST=192.168.1.1 \
  -e UNIFI_NETWORK_API=<network-key> \
  -e UNIFI_PROTECT_API=<protect-key> \
  -e UNIFI_SITE_MANAGER_API=<site-manager-key> \
  -- uvx --from git+https://github.com/millsymills-com/unifi-mcp.git unifi-mcp
```

### Cursor

Add to `~/.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "unifi": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/millsymills-com/unifi-mcp.git", "unifi-mcp"],
      "env": {
        "UNIFI_NETWORK_HOST": "192.168.1.1",
        "UNIFI_NETWORK_API": "<network-key>"
      }
    }
  }
}
```

### Continue.dev

Add to `~/.continue/config.json`:

```json
{
  "mcpServers": [
    {
      "name": "unifi",
      "command": "uvx",
      "args": ["--from", "git+https://github.com/millsymills-com/unifi-mcp.git", "unifi-mcp"],
      "env": {
        "UNIFI_NETWORK_HOST": "192.168.1.1",
        "UNIFI_NETWORK_API": "<network-key>"
      }
    }
  ]
}
```

## Configuration

See [.env.example](.env.example) for all configuration options.

| Variable | Default | Description |
|----------|---------|-------------|
| `UNIFI_MODE` | `readonly` | `readonly` or `readwrite`; see [Write safety](#write-safety) before enabling writes |
| `UNIFI_NETWORK_HOST` | none | Hostname or IP of the UniFi Network controller |
| `UNIFI_PROTECT_HOST` | `UNIFI_NETWORK_HOST` | Hostname or IP of the Protect NVR; defaults to the Network host if not set |
| `UNIFI_NETWORK_API` | none | Network API key |
| `UNIFI_PROTECT_API` | none | Protect API key |
| `UNIFI_SITE_MANAGER_API` | none | Site Manager cloud API key |
| `UNIFI_NETWORK_VERIFY_SSL` | `false` | Validate the Network controller's TLS chain |
| `UNIFI_PROTECT_VERIFY_SSL` | `false` | Validate the Protect NVR's TLS chain |
| `UNIFI_NETWORK_CERT_FINGERPRINT` | none | SHA-256 leaf-cert pin (Network); takes precedence over chain verification |
| `UNIFI_PROTECT_CERT_FINGERPRINT` | none | SHA-256 leaf-cert pin (Protect); takes precedence over chain verification |
| `UNIFI_NETWORK_INTEGRATION_ENABLED` | `true` | Register the Network Integration (`/integration/v1`) read tools; set `false` on firmware that predates the Integration API to suppress a startup WARN |
| `UNIFI_NETWORK_INTEGRATION_SITE` | none (auto-discover) | UUID of the Integration-API site. When unset the default/first site is discovered at startup and cached; multi-site controllers should set this. A site added after startup needs a restart |

`.env` is read from the current working directory; run `unifi-mcp` only from a
trusted directory so an unrelated `.env` cannot override your API keys.

Rotating UniFi API keys requires restarting the server process; there is no
hot-reload.

## Troubleshooting

### `Unknown tool: unifi_network_*` (or `unifi_protect_*`)

Tools register only for APIs that are both **configured and reachable**
(graceful per-API degradation). A caller that gets
`Unknown tool: 'unifi_network_get_health'` (or any other `unifi_network_*` /
`unifi_protect_*` name) is hitting an API whose tools were never registered,
almost always because its key is unset:

- `unifi_network_*` tools require `UNIFI_NETWORK_API`, issued under the
  **Network** service in UniFi OS. A Site Manager or Protect key returns 401
  and won't register Network tools ([#131](https://github.com/millsymills-com/unifi-mcp/issues/131)).
- `unifi_protect_*` tools require `UNIFI_PROTECT_API` (and `UNIFI_PROTECT_HOST`
  on split deployments; see Known Issues).
- `unifi_site_manager_*` tools require `UNIFI_SITE_MANAGER_API`.

Call `tools/list` after startup to see what registered, and check the startup
log: a configured-but-unreachable API logs a `tools disabled` line, while
an unconfigured API logs nothing and simply exposes no tools.

## TLS

UniFi controllers ship self-signed certificates, so `UNIFI_*_VERIFY_SSL`
defaults to `false`. That bypasses chain and hostname verification entirely:
anyone on the path between the MCP server and the controller can present
their own cert and harvest the `X-API-Key` header. The server emits a
startup `WARNING` for every service running with `verify_ssl=False`.

When the configured host resolves to a non-private address (anything that is
not RFC1918, loopback, or link-local), `verify_ssl=False` with no pin would
send the key across an untrusted path, so the server **refuses to start**
until you set `UNIFI_*_VERIFY_SSL=true`, pin the cert via
`UNIFI_*_CERT_FINGERPRINT`, or point at a private/loopback host. The
fail-closed check resolves every A and AAAA record and trips if any one is
non-private.

You have three options to satisfy the check safely.

### Option A: pin the controller's leaf cert (recommended for self-signed)

Capture the fingerprint once:

```bash
openssl s_client -connect <host>:443 -servername <host> </dev/null 2>/dev/null \
  | openssl x509 -fingerprint -sha256 -noout
```

Set it in the environment:

```bash
UNIFI_NETWORK_CERT_FINGERPRINT=AA:BB:CC:...      # colons optional, case-insensitive
UNIFI_PROTECT_CERT_FINGERPRINT=DD:EE:FF:...
```

When a pin is set, the client validates the leaf cert's SHA-256 fingerprint
on every response and refuses to talk to any other cert. Chain and hostname
verification are bypassed because the pin replaces them; that's the whole
point of pinning a self-signed cert. If the controller's cert is rotated,
the pin must be updated; mismatched pins fail loudly with the expected vs.
actual fingerprints in the error.

### Option B: install your own CA and enable full verification

If you've configured your controller with a cert signed by your own CA,
point Python at the CA bundle and turn full verification on:

```bash
# Either of these env vars is honored by Python's ssl module
export SSL_CERT_FILE=/path/to/your-ca-bundle.pem
# (httpx/requests also honor REQUESTS_CA_BUNDLE)
export REQUESTS_CA_BUNDLE=/path/to/your-ca-bundle.pem

UNIFI_NETWORK_VERIFY_SSL=true
UNIFI_PROTECT_VERIFY_SSL=true
```

On macOS you can alternatively install the CA into the System keychain and
mark it trusted for SSL; on Linux drop it into `/usr/local/share/ca-certificates/`
and run `update-ca-certificates`. Either path teaches the platform trust
store about your CA so `verify_ssl=true` works without a custom bundle.

### Option C: stay on `verify_ssl=False` (not recommended)

Accept the startup `WARNING`. Only available when the host is private,
loopback, or link-local — a non-private host fails closed at startup instead.
Only safe on a trusted private LAN where you control every hop between the
MCP server and the controller.

## Development

```bash
# Install with dev dependencies
uv sync --extra dev

# Lint and format
uv run ruff check src/ tests/
uv run ruff format --check src/ tests/

# Type check
uv run ty check src/unifi_mcp/

# Test
uv run pytest tests/unit/ -v

# Pre-commit hooks
uv run pre-commit install
```

## Known Issues

- **Protect on a separate device requires explicit `UNIFI_PROTECT_HOST`**
  ([#107](https://github.com/millsymills-com/unifi-mcp/issues/107)). If your
  Protect NVR is on a different IP than your Network controller (common
  with UCK-G2-Plus + UDM/UCG setups), set `UNIFI_PROTECT_HOST` in `.env`.
  The default silently inherits `UNIFI_NETWORK_HOST`, which produces a
  startup WARN (`protect tools disabled`) and no `unifi_protect_*` entries
  in the tool list.

## License

Apache-2.0. See [LICENSE](LICENSE).

## Trademarks

UniFi, UbiOS, and Ubiquiti are trademarks of Ubiquiti Inc. This project is an
independent, third-party MCP server and is not affiliated with, endorsed by, or
sponsored by Ubiquiti Inc. "UniFi" is referenced only to identify the product
this server integrates with. The repo logo (`docs/assets/logo.svg`) is an
original neon-CRT pixel-art "U" mark from the millsymills design system; it does
not use or derive from any Ubiquiti artwork.
