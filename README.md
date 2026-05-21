# aios-packages

The public package index for the **[AiOS](https://github.com/jduncan8142/AiOS)** project — a git repository of per-package TOML manifests that the [`pac`](https://github.com/jduncan8142/AiOSPac) package manager resolves names against. Each manifest pins a package to a git `source` URL and a `rev` (typically a release tag); `pac install <name>` clones the upstream `source` at that `rev`, builds it, and installs the resulting binaries. Updating a `rev` here propagates to every AiOS device that runs `pac update`.

Currently registered: [canvas](packages/canvas.toml), [fss](packages/fss.toml), [pac](packages/pac.toml), [terminal](packages/terminal.toml), [vault](packages/vault.toml).

See [CLAUDE.md](CLAUDE.md) for the manifest schema, the directory layout, and how to point `pac` at this index via `AIOS_PAC_INDEX`.
