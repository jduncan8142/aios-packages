# aios-packages

Package index for the AiOS project, consumed by the `pac` package manager.

## Structure

Each package is one TOML file under `packages/`:

```
packages/
  <name>.toml
```

The file name should match the package's `name` field.

## Package file format

`packages/<name>.toml`:

```toml
name        = "example"
description = "Short, human-readable summary of the package."
source      = "https://github.com/owner/example.git"
rev         = "v1.2.0"
```

| Field         | Description                                                          |
| ------------- | -------------------------------------------------------------------- |
| `name`        | Package name. Should match the file name (`packages/<name>.toml`).   |
| `description` | Short, human-readable summary.                                       |
| `source`      | Git URL the package is cloned from.                                  |
| `rev`         | Git revision to pin. A tag is recommended (over a branch or commit). |

## Adding a package

Create `packages/<name>.toml` with the four fields above and commit it.

## Using the index with `pac`

Point `pac` at this repository by setting `AIOS_PAC_INDEX` to its git URL:

```powershell
# PowerShell (current session)
$env:AIOS_PAC_INDEX = "https://github.com/jduncan8142/aios-packages.git"
```

```sh
# bash / zsh
export AIOS_PAC_INDEX=https://github.com/jduncan8142/aios-packages.git
```
