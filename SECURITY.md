# Security boundaries

The supervisor serves a trusted local operator. It validates Host, Origin and
browser fetch metadata, requires a custom header for reads and a process CSRF
token for JSON mutations. It limits state and session operations to projects
enrolled in its policy file. Those checks are not authentication for other local
accounts, nor do they secure the separate upstream native API.

Native requests require IPv4 loopback HTTP, bypass proxy environment variables
and reject redirects. Private prompts must not be forwarded to external origins.
GitHub commands use argument arrays, not a shell; PR URLs are parsed before use.

Gate reports live under the explicitly configured local state directory.
Session IDs used in report filenames and API routes must match the ASCII
identifier allowlist, cannot start with a dot and cannot contain separators.
Private writes reject linked paths, use mode-0600 temporary files, flush them
and atomically replace the destination entry. The state directory must be owned
and controlled by the operator; Windows protection relies on its ACL.

CodeQL path-injection findings on this deliberate state-file capability are
reviewed against the identifier allowlist and local state ownership. They are
not a reason to disable scanning or permit arbitrary request-supplied paths.

Conversation history and daemon logs persist in upstream state. Use native
lifecycle controls and backup retention settings to remove sensitive data.
The Python tests exercise real local HTTP and filesystem boundaries, but do not
prove the safety of the upstream binary or run live provider jobs.
