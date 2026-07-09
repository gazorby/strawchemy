## `auto-bump`

- Depends: uv:install

- **Usage**: `auto-bump`

Auto bump the version

## `ci:install`

- **Usage**: `ci:install`

Install dependencies and pre-commit hooks

## `ci:lint`

- **Usage**: `ci:lint`

Lint CI yaml files

## `ci:test`

Run tests in CI


- Depends: ci:install

- **Usage**: `ci:test <session>`

### Arguments

#### `<session>`

## `ci:test-matrix`

- Depends: ci:install

- **Usage**: `ci:test-matrix`

Output test matrix for CI

## `ci:test-sessions`

- Depends: ci:install

- **Usage**: `ci:test-sessions`

Output test session names for CI

## `clean`

- **Usage**: `clean`
- **Aliases**: `c`

Clean working directory

## `format`

- Depends: ruff:format, tombi

- **Usage**: `format`
- **Aliases**: `f`

Lint the code

## `install`

- Depends: install:pre-commit, uv:install

- **Usage**: `install`
- **Aliases**: `i`

Install dependencies and pre-commit hooks

## `install:pre-commit`

- **Usage**: `install:pre-commit`

Install pre-commit hooks

## `lint`

- Depends: vulture, ty, ruff:check, ruff:format:check, slotscheck, unasyncd:check

- **Usage**: `lint`
- **Aliases**: `l`

Lint the code

## `pre-commit`

- Depends: install:pre-commit

- **Usage**: `pre-commit`

Run pre-commit checks

## `render:usage`

- **Usage**: `render:usage`

Generate tasks documentation

## `ruff:check`

- **Usage**: `ruff:check`

Check ruff formatting

## `ruff:fix`

- **Usage**: `ruff:fix`

Fix ruff errors

## `ruff:format`

- **Usage**: `ruff:format`

Format code

## `ruff:format:check`

- **Usage**: `ruff:format:check`

Format code

## `slotscheck`

- **Usage**: `slotscheck`

Run slotscheck

## `test`

Run tests


- Depends: uv:install

- **Usage**: `test [test]…`
- **Aliases**: `t`

### Arguments

#### `[test]…`

## `test:add-new-snapshots`

- Depends: uv:install

- **Usage**: `test:add-new-snapshots`

Run snapshot-based tests and add new snapshots

## `test:coverage`

Run tests with coverage


- Depends: uv:install

- **Usage**: `test:coverage [test]…`
- **Aliases**: `tc`

### Arguments

#### `[test]…`

## `test:integration`

Run integration tests


- Depends: uv:install

- **Usage**: `test:integration [--python <python>] [test]…`
- **Aliases**: `ti`

### Arguments

#### `[test]…`

### Flags

#### `--python <python>`

**Default:** `3.13`

## `test:integration-all`

Run integration tests on all supported python versions


- Depends: uv:install

- **Usage**: `test:integration-all [--python <python>] [test]…`
- **Aliases**: `tia`

### Arguments

#### `[test]…`

### Flags

#### `--python <python>`

**Default:** `3.13`

## `test:integration-mysql`

Run integration tests


- Depends: uv:install

- **Usage**: `test:integration-mysql [--python <python>] [test]…`
- **Aliases**: `ti-mysql`

### Arguments

#### `[test]…`

### Flags

#### `--python <python>`

**Default:** `3.13`

## `test:integration-postgres`

Run integration tests


- Depends: uv:install

- **Usage**: `test:integration-postgres [--python <python>] [test]…`
- **Aliases**: `ti-postgres`

### Arguments

#### `[test]…`

### Flags

#### `--python <python>`

**Default:** `3.13`

## `test:integration-sqlite`

Run integration tests


- Depends: uv:install

- **Usage**: `test:integration-sqlite [--python <python>] [test]…`
- **Aliases**: `ti-sqlite`

### Arguments

#### `[test]…`

### Flags

#### `--python <python>`

**Default:** `3.13`

## `test:integration:coverage`

Run integration tests with coverage


- Depends: uv:install

- **Usage**: `test:integration:coverage [--python <python>] [test]…`
- **Aliases**: `tic`

### Arguments

#### `[test]…`

### Flags

#### `--python <python>`

**Default:** `3.13`

## `test:patch-coverage`

Run tests and report coverage on changed lines only (vs a branch)


- Depends: uv:install

- **Usage**: `test:patch-coverage [--branch <branch>] [--fail-under <fail_under>] [test]…`
- **Aliases**: `tpc`

### Arguments

#### `[test]…`

### Flags

#### `--branch <branch>`

**Default:** `main`

#### `--fail-under <fail_under>`

**Default:** `100`

## `test:unit`

Run unit tests


- Depends: uv:install

- **Usage**: `test:unit [--python <python>] [test]…`
- **Aliases**: `tu`

### Arguments

#### `[test]…`

### Flags

#### `--python <python>`

**Default:** `3.13`

## `test:unit-all`

Run unit tests on all supported python versions


- Depends: uv:install

- **Usage**: `test:unit-all [--python <python>] [test]…`
- **Aliases**: `tua`

### Arguments

#### `[test]…`

### Flags

#### `--python <python>`

**Default:** `3.13`

## `test:unit:coverage`

Run unit tests with coverage


- Depends: uv:install

- **Usage**: `test:unit:coverage [--python <python>] [test]…`
- **Aliases**: `tuc`

### Arguments

#### `[test]…`

### Flags

#### `--python <python>`

**Default:** `3.13`

## `test:unit:no-extras`

Run unit tests without extras dependencies


- Depends: uv:install

- **Usage**: `test:unit:no-extras [--python <python>] [test]…`
- **Aliases**: `tug`

### Arguments

#### `[test]…`

### Flags

#### `--python <python>`

**Default:** `3.13`

## `test:update-snapshots`

- Depends: uv:install

- **Usage**: `test:update-snapshots`

Run snapshot-based tests and update snapshots

## `tombi`

- **Usage**: `tombi`

Run tombi

## `ty`

- **Usage**: `ty`

Run ty

## `unasyncd`

- **Usage**: `unasyncd`

Generate synchronous code from asynchronous version

## `unasyncd:check`

- **Usage**: `unasyncd:check`

Check synchronous code from asynchronous version

## `uv:install`

- **Usage**: `uv:install`

Install dependencies

## `vulture`

- **Usage**: `vulture`

Run vulture
