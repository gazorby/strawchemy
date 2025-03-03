# Changelog

All notable changes to this project will be documented in this file.

## [0.5.0](https://github.com/gazorby/strawchemy/compare/v0.4.0..v0.5.0) - 2025-03-03

### 🚀 Features

- *(mapping)* Add pagination setting on config level - ([5e84f4b](https://github.com/gazorby/strawchemy/commit/5e84f4bca54dbf7eab083dc74a5c37a9171c1818))

### ⚙️ Miscellaneous Tasks

- *(release)* Bump to v0.5.0 - ([e15f7c7](https://github.com/gazorby/strawchemy/commit/e15f7c758b3980696cc75e80b5195afaeaf19292))
## [0.4.0](https://github.com/gazorby/strawchemy/compare/v0.3.0..v0.4.0) - 2025-03-03

### 🚀 Features

- *(config)* Add default pagination limit setting - ([808670c](https://github.com/gazorby/strawchemy/commit/808670ccdc7540c6830fd3e3ba13e86c6455079a))
- *(config)* Enable custom id field name - ([8f05899](https://github.com/gazorby/strawchemy/commit/8f0589949238a021d8f967149e5a5d14f0a7199a))
- *(dto)* Add READ_ONLY, WRITE_ONLY and PRIVATE shortcuts - ([5da8660](https://github.com/gazorby/strawchemy/commit/5da86608de2a5336ccfb3a5a9eba85769872dd6a))
- *(dto-config)* Add method to infer include/exclude from base class - ([0ddb6bd](https://github.com/gazorby/strawchemy/commit/0ddb6bd2f8f7e577d54c4529d242bafb6ad2ba8d))
- *(mapping)* Enable custom defaults for child pagination - ([ed00372](https://github.com/gazorby/strawchemy/commit/ed00372d49f9b0d8b45fe62802a52e3446fd2352))
- Add pagination switch and defaults - ([c111cc5](https://github.com/gazorby/strawchemy/commit/c111cc58279229c1f47f73af593945b8f5451723))

### 🐛 Bug Fixes

- *(dto)* Partial default value on several places - ([d3d18e8](https://github.com/gazorby/strawchemy/commit/d3d18e85d079e813fdeea29f1d0cf1ecff40fb05))
- *(dto-factory)* Caching fixes - ([4c1d345](https://github.com/gazorby/strawchemy/commit/4c1d34533eb09aef7ec2a471a7f3c9e969e27c1e))
- *(root-aggregations)* Ensure aggregations are optional - ([a9be792](https://github.com/gazorby/strawchemy/commit/a9be7927ca5cef8c23e0b9e47c659139906f3e67))
- *(root-aggregations)* Set count as optional - ([0bada8b](https://github.com/gazorby/strawchemy/commit/0bada8b7028d236755da78527cf33d4b47c0aa96))
- *(sqlalchemy-inspector)* Mapped classes map not updated - ([6667447](https://github.com/gazorby/strawchemy/commit/66674477a8c222aa40ff38e400149983b72b3026))
- *(strawchemy-field)* Python name for filter input - ([73cca8b](https://github.com/gazorby/strawchemy/commit/73cca8bba6197a2325a1530bf2363e132b009f6b))
- Forgot some partial default updates - ([4df92dd](https://github.com/gazorby/strawchemy/commit/4df92dd621ca6cc0b84d9ef3da4271267cc452b3))

### 🚜 Refactor

- *(dto)* Expose factory instance in pydantic_sqlalchemy.py - ([d4b1793](https://github.com/gazorby/strawchemy/commit/d4b1793bd71ad7abee3d35619508953e1efc355e))
- *(dto)* Add shortcut utilities - ([a3b3a53](https://github.com/gazorby/strawchemy/commit/a3b3a53ffb201df8dbba250b0440daaed460db79))
- *(dto)* Streamline arguments of factory decorator method - ([33557b1](https://github.com/gazorby/strawchemy/commit/33557b1abf5a014a8948cc11ce93412c95580be4))
- *(mapping)* Child options - ([e2277ab](https://github.com/gazorby/strawchemy/commit/e2277ab742041429181be152ffca9f3f20337cea))
- *(pre-commit)* Update config - ([a08c121](https://github.com/gazorby/strawchemy/commit/a08c1216fa065bad1959998d5fdfd433e9e37d00))
- Wip - ([9817a95](https://github.com/gazorby/strawchemy/commit/9817a9574e05cadea46f5bcf1f1ff8d075579758))

### 🧪 Testing

- *(dto)* Add some config tests - ([b8424ee](https://github.com/gazorby/strawchemy/commit/b8424ee1ce08c1992b9e1e895fe0d63b078cb5e7))
- *(test_types.py)* Move to unit/mapping - ([6e19a22](https://github.com/gazorby/strawchemy/commit/6e19a227e6ebe4908b5fcefda8092585328f295f))
- *(unit)* Add test for model field config - ([0a00581](https://github.com/gazorby/strawchemy/commit/0a00581364bd7078c4b5dd2334305f287e2346fe))
- *(unit)* Add missing fixtures - ([cd0face](https://github.com/gazorby/strawchemy/commit/cd0face5427ec6f1d7bb2e16b8a981c54f43bbf7))
- *(unit)* Add geo graphql schemas - ([f0bd5bd](https://github.com/gazorby/strawchemy/commit/f0bd5bd4cb0d80611ad4aeb590f314329137deec))
- *(unit)* Update models - ([0aebc62](https://github.com/gazorby/strawchemy/commit/0aebc624d9f9224c039f858ad5e4cef2069f7690))
- *(unit)* Model config tests - ([c5cd73c](https://github.com/gazorby/strawchemy/commit/c5cd73c3ee64946460f529393ba44c65663d2a01))
- *(unit)* Switch to snapshot testing - ([31ff808](https://github.com/gazorby/strawchemy/commit/31ff808c98c83b818b4c35522c934bd9445cb2b9))
- *(unit)* Use one snapshot file per test - ([7bd9357](https://github.com/gazorby/strawchemy/commit/7bd93577866f65afe6103128cf2c19f476158248))
- *(vscode)* Set pytestEnabled setting - ([9d1cb8a](https://github.com/gazorby/strawchemy/commit/9d1cb8a8fe96b31b64b56b677f2ba7be1e838805))

### ⚙️ Miscellaneous Tasks

- *(lint)* Add sourcery config - ([0ee4bde](https://github.com/gazorby/strawchemy/commit/0ee4bde598781611c9cae9aa135ce3197bd1e76b))
- *(lint)* Execute lint sessions on a single default python version - ([60ac239](https://github.com/gazorby/strawchemy/commit/60ac239cb5d59c683f1a03ec240b6a83ba61503f))
- *(mise)* Add auto-bump task - ([545f3c4](https://github.com/gazorby/strawchemy/commit/545f3c434138413b873ec8c3224fc71fcc4d98dc))
- *(release)* Bump to v0.4.0 - ([ebdbd58](https://github.com/gazorby/strawchemy/commit/ebdbd5877c78642bdaa11786d19eaf30fb41431a))
- *(test)* Fix array membership test - ([25e5672](https://github.com/gazorby/strawchemy/commit/25e567299d5dfdcda2e9cc97087d4c104fa4e0de))
- *(tests)* Upload coverage artifacts - ([bc72252](https://github.com/gazorby/strawchemy/commit/bc72252c1453a015f60f70d7facf57fd3fc7c3d6))
## [0.3.0](https://github.com/gazorby/strawchemy/compare/v0.2.12..v0.3.0) - 2025-02-21

### 🚀 Features

- *(mapping)* Allow strawchemy types to override existing ones - ([c26b495](https://github.com/gazorby/strawchemy/commit/c26b495143049b427311bd76b35af220a159aa1f))

### 📚 Documentation

- Update CONTRIBUTING.md - ([d22f786](https://github.com/gazorby/strawchemy/commit/d22f78617632cf003774b208d019150fd7bf9fd3))
- Add pull request template - ([efcb329](https://github.com/gazorby/strawchemy/commit/efcb329efa66dc89a30fc263e24389515d356e17))
- Add SECURITY.md - ([628cd29](https://github.com/gazorby/strawchemy/commit/628cd297e886af7c0e36ef85f3148d771f150633))
- Update image in SECURITY.md - ([651c4f3](https://github.com/gazorby/strawchemy/commit/651c4f31e86d2cdd66e861cc6aebcda63f5b2b8d))
- Update bug_report issue template - ([e213df1](https://github.com/gazorby/strawchemy/commit/e213df15832595a8c8695bb4312ad990c8a6571e))

### ⚙️ Miscellaneous Tasks

- *(release)* Bump to v0.3.0 - ([6075f54](https://github.com/gazorby/strawchemy/commit/6075f5487462b5fe0595638757a405e758513db5))
- Create dependabot.yml - ([14d2026](https://github.com/gazorby/strawchemy/commit/14d20260c12de5a63d8a72404fe113c3e9e3e78b))
- Add issue/pr templates - ([dc99896](https://github.com/gazorby/strawchemy/commit/dc99896724f1deda7a64768743b6e890c3907d91))
## [0.2.12](https://github.com/gazorby/strawchemy/compare/v0.2.11..v0.2.12) - 2025-02-21

### ⚙️ Miscellaneous Tasks

- *(release)* Bump to v0.2.12 - ([eb32d94](https://github.com/gazorby/strawchemy/commit/eb32d94a6dc85f020a23276a1a963a19a5ccab1a))
- Create separate environment for cd and publish - ([fbcdf34](https://github.com/gazorby/strawchemy/commit/fbcdf3486fb4643c19153ffac7eb6a600a91f938))
## [0.2.11](https://github.com/gazorby/strawchemy/compare/v0.2.10..v0.2.11) - 2025-02-21

### ⚙️ Miscellaneous Tasks

- *(changelog)* Fix incorrect release changelog - ([1a8bf11](https://github.com/gazorby/strawchemy/commit/1a8bf11c5bd883749079128be5614fbdd5a1ab32))
- *(release)* Bump to v0.2.11 - ([4fb6265](https://github.com/gazorby/strawchemy/commit/4fb62651717558632637ff7521fe315d760fffb4))
- Pass GITHUB_TOKEN to git cliff calls - ([cc21aae](https://github.com/gazorby/strawchemy/commit/cc21aae930467c06e1c2d6e1d21274bb2165e3f5))
## [0.2.10](https://github.com/gazorby/strawchemy/compare/v0.2.9..v0.2.10) - 2025-02-21

### ⚙️ Miscellaneous Tasks

- *(release)* Bump to v0.2.10 - ([5fb6215](https://github.com/gazorby/strawchemy/commit/5fb621522c20594291a1ff2340e1b170090d21ba))
- Tweak changelog generation - ([68c6680](https://github.com/gazorby/strawchemy/commit/68c6680fa3db8ffeb52b95680ff3d1e9a6cdcbce))
## [0.2.9](https://github.com/gazorby/strawchemy/compare/v0.2.8..v0.2.9) - 2025-02-21

### ⚙️ Miscellaneous Tasks

- *(publish)* Add missing `contents: write` permission - ([4f881d7](https://github.com/gazorby/strawchemy/commit/4f881d78a0dfb2574ad244c746f7d7d9255ae12a))
- *(release)* Bump to v0.2.9 - ([5e8b5c4](https://github.com/gazorby/strawchemy/commit/5e8b5c4aad50332b89f9594d9f772935c81d137a))
## [0.2.8](https://github.com/gazorby/strawchemy/compare/v0.2.7..v0.2.8) - 2025-02-21

### ⚙️ Miscellaneous Tasks

- *(cd)* Use the pat to create gh release - ([c603955](https://github.com/gazorby/strawchemy/commit/c603955af5446e89c7de42b6f1705b61553f12cf))
- *(release)* Bump to v0.2.8 - ([97d2413](https://github.com/gazorby/strawchemy/commit/97d24130c168dbd2f05d173066ce27d7c11416e3))
## [0.2.7](https://github.com/gazorby/strawchemy/compare/v0.2.6..v0.2.7) - 2025-02-21

### ⚙️ Miscellaneous Tasks

- *(ci)* Fix test matrix not generated on tag - ([ae4720d](https://github.com/gazorby/strawchemy/commit/ae4720dd3aa812c1adf067fedb8c26de3286eb11))
- *(release)* Bump to v0.2.7 - ([be76cf2](https://github.com/gazorby/strawchemy/commit/be76cf262b0bef07a09a0ae0bc299a8f7c8f04de))
## [0.2.6](https://github.com/gazorby/strawchemy/compare/v0.2.5..v0.2.6) - 2025-02-21

### ⚙️ Miscellaneous Tasks

- *(ci)* Always run ci on tag - ([ffd23ff](https://github.com/gazorby/strawchemy/commit/ffd23fff86ed5d832f590ba5dd64f91202c547c1))
- *(release)* Bump to v0.2.6 - ([5174967](https://github.com/gazorby/strawchemy/commit/517496725a74985bffcb59f7030a84dec637ea63))
## [0.2.5](https://github.com/gazorby/strawchemy/compare/v0.2.4..v0.2.5) - 2025-02-21

### ⚙️ Miscellaneous Tasks

- *(ci)* Also run result job if needed step have been skipped - ([474bad3](https://github.com/gazorby/strawchemy/commit/474bad3ba96c8c4d16cec6f0463ea29ba5391406))
- *(release)* Bump to v0.2.5 - ([0b5cc28](https://github.com/gazorby/strawchemy/commit/0b5cc2855463724269a9365d5a0e88dcb90984da))
## [0.2.4](https://github.com/gazorby/strawchemy/compare/v0.2.3..v0.2.4) - 2025-02-21

### ⚙️ Miscellaneous Tasks

- *(ci)* Run result job on tag - ([e93941a](https://github.com/gazorby/strawchemy/commit/e93941a47ce4607d6757f072a60aa43095a4bd6e))
- *(release)* Bump to v0.2.4 - ([d8a4981](https://github.com/gazorby/strawchemy/commit/d8a4981ee1f91a325b6bf669e36232a2e1b6a7dc))
## [0.2.3](https://github.com/gazorby/strawchemy/compare/v0.2.2..v0.2.3) - 2025-02-21

### ⚙️ Miscellaneous Tasks

- *(bump)* Use personal access toekn to enable ci workflow - ([35f190b](https://github.com/gazorby/strawchemy/commit/35f190b22d113cd9a0d471beea2f62c5bb7f8724))
- *(release)* Bump to v0.2.3 - ([c98e0cd](https://github.com/gazorby/strawchemy/commit/c98e0cdc9f62b49704c1b29829640bf79c3d5932))
## [0.2.2](https://github.com/gazorby/strawchemy/compare/v0.2.1..v0.2.2) - 2025-02-21

### 📚 Documentation

- *(readme)* Update badge - ([6171071](https://github.com/gazorby/strawchemy/commit/6171071ae03e6692eaa6681284eab244217018ed))

### ⚙️ Miscellaneous Tasks

- *(bump)* Fix auto bump - ([7251e12](https://github.com/gazorby/strawchemy/commit/7251e12c1ce42724a314556586a41d00baf35f86))
- *(bump)* Add missing --bump-version flag - ([842e831](https://github.com/gazorby/strawchemy/commit/842e831cc99d7653069804d5233488d855ae5306))
- *(bump)* Fix --bumped-version flag - ([edfe14e](https://github.com/gazorby/strawchemy/commit/edfe14e378cf858b23545e4e6378c554bddc9541))
- *(bump)* Use kenji-miyake/setup-git-cliff action - ([93c3a9c](https://github.com/gazorby/strawchemy/commit/93c3a9c48449a2077deffdb1b9668de3fdde96f4))
- *(bump)* Add write permissions - ([6ebae7c](https://github.com/gazorby/strawchemy/commit/6ebae7c0d2f90eafca0a13f985fb83bab31f7b4e))
- *(bump)* Fix GITHUB_TOKEN env var - ([cc43668](https://github.com/gazorby/strawchemy/commit/cc436682becb95e340026244f377f384177c5c67))
- *(release)* Bump to v0.2.2 - ([a8ee5b6](https://github.com/gazorby/strawchemy/commit/a8ee5b62bd3c144e2ea865dede6b85647207bede))
- Add bump and publish workflows - ([e8ab0c8](https://github.com/gazorby/strawchemy/commit/e8ab0c817107f44b499b09e079f95f742c7e0797))
- Pretty workflow names - ([5b467ab](https://github.com/gazorby/strawchemy/commit/5b467abf9ae38577b9cf8196f25716e0098d0ed7))

## New Contributors ❤️

* @github-actions[bot] made their first contribution## [0.2.1](https://github.com/gazorby/strawchemy/compare/v0.2.0..v0.2.1) - 2025-02-20

### ⚙️ Miscellaneous Tasks

- *(release)* Bump to v0.2.1 - ([5e59c22](https://github.com/gazorby/strawchemy/commit/5e59c221011c1f0414b29024a0e60471076225a7))
- Add codeql workflow - ([758dcc0](https://github.com/gazorby/strawchemy/commit/758dcc081a2efa8ddba6e30769ff1a1b85d28c3e))
- Add publish workflow; auto commit CHANGELOG.md when generating changelog - ([6fdd13b](https://github.com/gazorby/strawchemy/commit/6fdd13b2c8b191116814de9e8036ceba4b1b8477))
## [0.2.0](https://github.com/gazorby/strawchemy/compare/v0.1.0..v0.2.0) - 2025-02-20

### 📚 Documentation

- *(readme)* Add badges - ([f1b92a5](https://github.com/gazorby/strawchemy/commit/f1b92a54197caa205eef84614824eaf93c91e4a6))
- Move CONTRIBUTING.md to the correct place - ([ad6bbd1](https://github.com/gazorby/strawchemy/commit/ad6bbd19b9b88cc606d7b18e1d60ff1b24890adc))

### 🧪 Testing

- *(unit)* Add test - ([8a5fb69](https://github.com/gazorby/strawchemy/commit/8a5fb69434a9b450c6ec67b7fc39c33e44ee07c1))
- *(unit)* Add tests for schema generation - ([e5ea09d](https://github.com/gazorby/strawchemy/commit/e5ea09d71b07a5beabdfee193c252f7ca6e4e228))
- Add python 3.9, 3.10, 3.11 and 3.13 to the matrix - ([ed048fa](https://github.com/gazorby/strawchemy/commit/ed048fa62648b55580fa0e517b3daeaa493a0b6d))

### ⚙️ Miscellaneous Tasks

- *(release)* Bump to v0.2.0 - ([2bcb70a](https://github.com/gazorby/strawchemy/commit/2bcb70a8178821fa7bf4047f07e2104e83804b6a))
- *(test)* Add unit test workflow - ([f560d04](https://github.com/gazorby/strawchemy/commit/f560d0426b67bc328a3cd6bcb73a3b144e8457ce))
- *(test)* Remove unneeded step - ([ce18a5a](https://github.com/gazorby/strawchemy/commit/ce18a5a815b249b8d20dd5c196d2338248aec6a7))
- *(test)* Fix result job - ([a12c11d](https://github.com/gazorby/strawchemy/commit/a12c11d44651d69e4f087d2c28616cc4719fa672))
- *(test)* Set COLUMNS env var - ([46b70af](https://github.com/gazorby/strawchemy/commit/46b70afb21ba898c8524ac3f2a09bb632ca990f2))
- *(uv)* Commit uv.lock - ([f7df4f8](https://github.com/gazorby/strawchemy/commit/f7df4f82059f5b5ddf74a08ec73c622ae103198f))
- Add changelog generation workflow - ([b018a78](https://github.com/gazorby/strawchemy/commit/b018a782e8449d25e26440c17e934cc2df7b2440))
## [0.1.0] - 2025-02-19

### 🚀 Features

- Initial commit - ([3a01dc2](https://github.com/gazorby/strawchemy/commit/3a01dc2b31db02507400257e1996fb0c83b177ce))

### ⚙️ Miscellaneous Tasks

- *(release)* Bump to v0.1.0 - ([d72c22a](https://github.com/gazorby/strawchemy/commit/d72c22a88aacb41e1ddafd8004b024629a348430))

## New Contributors ❤️

* @gazorby made their first contribution<!-- generated by git-cliff -->
