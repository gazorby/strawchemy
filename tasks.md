## `auto-bump`

- Depends: _install

- **Usage**: `auto-bump`

Auto bump the version

## `ci:install`

- **Usage**: `ci:install`

Install dependencies and pre-commit hooks

## `ci:lint`

- **Usage**: `ci:lint`

Lint CI yaml files

## `ci:test`

- Depends: ci:install

- **Usage**: `ci:test <session>`

Run tests in CI

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

## `install`

- Depends: install:pre-commit, _install

- **Usage**: `install`
- **Aliases**: `i`

Install dependencies and pre-commit hooks

## `install:pre-commit`

- **Usage**: `install:pre-commit`

Install pre-commit hooks

## `lint`

- Depends: vulture, pyright, ruff:check, ruff:format:check

- **Usage**: `lint`
- **Aliases**: `l`

Lint the code

## `lint:pre-commit`

- Depends: vulture, pyright

- **Usage**: `lint:pre-commit`

Lint the code in pre-commit hook

## `pre-commit`

- Depends: install:pre-commit

- **Usage**: `pre-commit`

Run pre-commit checks

## `pyright`

- Depends: _install

- **Usage**: `pyright`

Run basedpyright

## `render:usage`

- **Usage**: `render:usage`

Generate tasks documentation

## `ruff:check`

- Depends: _install

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

## `test`

- Depends: _install

- **Usage**: `test [test]`
- **Aliases**: `t`

Run tests

### Arguments

#### `[test]`

## `test:coverage`

- Depends: _install

- **Usage**: `test:coverage [test]`
- **Aliases**: `tc`

Run tests with coverage

### Arguments

#### `[test]`

## `test:integration`

- Depends: _install

- **Usage**: `test:integration [--python [python]] <test>…`
- **Aliases**: `ti`

Run integration tests

### Arguments

#### `<test>…`

### Flags

#### `--python [python]`

**Default:** `3.13`

## `test:integration-all`

- Depends: _install

- **Usage**: `test:integration-all [--python [python]] [test]`
- **Aliases**: `tia`

Run integration tests on all supported python versions

### Arguments

#### `[test]`

### Flags

#### `--python [python]`

**Default:** `3.13`

## `test:integration-mysql`

- Depends: _install

- **Usage**: `test:integration-mysql [--python [python]] <test>…`
- **Aliases**: `ti-mysql`

Run integration tests

### Arguments

#### `<test>…`

### Flags

#### `--python [python]`

**Default:** `3.13`

## `test:integration-postgres`

- Depends: _install

- **Usage**: `test:integration-postgres [--python [python]] <test>…`
- **Aliases**: `ti-postgres`

Run integration tests

### Arguments

#### `<test>…`

### Flags

#### `--python [python]`

**Default:** `3.13`

## `test:integration-sqlite`

- Depends: _install

- **Usage**: `test:integration-sqlite [--python [python]] <test>…`
- **Aliases**: `ti-sqlite`

Run integration tests

### Arguments

#### `<test>…`

### Flags

#### `--python [python]`

**Default:** `3.13`

## `test:integration:coverage`

- Depends: _install

- **Usage**: `test:integration:coverage [--python [python]] [test]`
- **Aliases**: `tic`

Run integration tests with coverage

### Arguments

#### `[test]`

### Flags

#### `--python [python]`

**Default:** `3.13`

## `test:unit`

- Depends: _install

- **Usage**: `test:unit [--python [python]] [test]`
- **Aliases**: `tu`

Run unit tests

### Arguments

#### `[test]`

### Flags

#### `--python [python]`

**Default:** `3.13`

## `test:unit-all`

- Depends: _install

- **Usage**: `test:unit-all [--python [python]] [test]`
- **Aliases**: `tua`

Run unit tests on all supported python versions

### Arguments

#### `[test]`

### Flags

#### `--python [python]`

**Default:** `3.13`

## `test:unit:coverage`

- Depends: _install

- **Usage**: `test:unit:coverage [--python [python]] [test]`
- **Aliases**: `tuc`

Run unit tests with coverage

### Arguments

#### `[test]`

### Flags

#### `--python [python]`

**Default:** `3.13`

## `test:unit:no-extras`

- Depends: _install

- **Usage**: `test:unit:no-extras [--python [python]] <test>…`
- **Aliases**: `tug`

Run unit tests without extras dependencies

### Arguments

#### `<test>…`

### Flags

#### `--python [python]`

**Default:** `3.13`

## `test:update-snapshots`

- Depends: _install

- **Usage**: `test:update-snapshots`

Run snapshot-based tests and update snapshots

## `vulture`

- **Usage**: `vulture`

Run vulture
