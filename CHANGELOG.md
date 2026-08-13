# Changelog

All notable changes to this project will be documented in this file. See [conventional commits](https://www.conventionalcommits.org/) for commit guidelines.

- - -

## Unreleased ([b9171fd..3b36909](https://github.com/gazorby/strawchemy/compare/b9171fd..3b36909))
#### 🚀 Features
- add per-field default order by ([#196](https://github.com/gazorby/strawchemy/pull/196)) - ([227bc21](https://github.com/gazorby/strawchemy/commit/227bc2111b4b426f613b05fd3d8e584a5331266e)) - [@gazorby](https://github.com/gazorby)
- add field-level alias ([#194](https://github.com/gazorby/strawchemy/pull/194)) - ([e8ef6a3](https://github.com/gazorby/strawchemy/commit/e8ef6a34087708f3118050380ad839217c395459)) - [@gazorby](https://github.com/gazorby)
#### 🐛 Bug Fixes
- (**mutation**) only register sqla events once per mapper ([#201](https://github.com/gazorby/strawchemy/pull/201)) - ([c663958](https://github.com/gazorby/strawchemy/commit/c663958b02b8b894f15aa96a8bdfbc793f784cce)) - [@gazorby](https://github.com/gazorby)
#### ⚡ Performance
- (**transpiler**) small improvements  ([#205](https://github.com/gazorby/strawchemy/pull/205)) - ([f8f03a5](https://github.com/gazorby/strawchemy/commit/f8f03a5d80528d5bf4914ca3019546ddfc7b5830)) - [@gazorby](https://github.com/gazorby)
#### 🚜 Refactor
- (**inspector**) remove sqla private usages ([#203](https://github.com/gazorby/strawchemy/pull/203)) - ([6ca2f19](https://github.com/gazorby/strawchemy/commit/6ca2f19540d09974811fa1d800162cd9fca3383c)) - [@gazorby](https://github.com/gazorby)
- (**schema**) remove duplicated field_map on strawchemy types  ([#200](https://github.com/gazorby/strawchemy/pull/200)) - ([2f67a26](https://github.com/gazorby/strawchemy/commit/2f67a26b0136a6e77b8ef6ab1f44b7b366aa9151)) - [@gazorby](https://github.com/gazorby)
- new transpiler ([#202](https://github.com/gazorby/strawchemy/pull/202)) - ([e000a8e](https://github.com/gazorby/strawchemy/commit/e000a8eca47287c8bb48d03ea822707b9023b92a)) - [@gazorby](https://github.com/gazorby)
#### ⚙️ Miscellaneous Tasks
- (**deps**) extract unasyncd in its own group - ([c3cb4d1](https://github.com/gazorby/strawchemy/commit/c3cb4d18a8e45171af0161369dca581d56e94f82)) - [@gazorby](https://github.com/gazorby)
- (**labelers**) fix quoting - ([ff38da3](https://github.com/gazorby/strawchemy/commit/ff38da3fc409ba99e7f6915f1b91ae51baeedfe3)) - [@gazorby](https://github.com/gazorby)
- (**labelers**) support scope - ([06e701f](https://github.com/gazorby/strawchemy/commit/06e701fb48958abcdc6557cfa0e94120b3be9cb3)) - [@gazorby](https://github.com/gazorby)
- (**labelers**) add perf  tag - ([8c6bc63](https://github.com/gazorby/strawchemy/commit/8c6bc63ff0362b67d47ec326f2d37f1110f43a93)) - [@gazorby](https://github.com/gazorby)
- (**labelers**) fix paths - ([5c29f01](https://github.com/gazorby/strawchemy/commit/5c29f0130c1a2dd37f64642bdfe5897a136a1599)) - [@gazorby](https://github.com/gazorby)
- (**labelers**) fix config paths - ([05492c8](https://github.com/gazorby/strawchemy/commit/05492c8d225554edfe1cb3f64cde6a9264ef2127)) - [@gazorby](https://github.com/gazorby)
- (**pr-labeler**) only take pr title into account - ([3b36909](https://github.com/gazorby/strawchemy/commit/3b36909e4c38fc44288339c44e26034d580173ed)) - [@gazorby](https://github.com/gazorby)
- (**workflows**) remove redundant generate_release_notes option from release action configuration - ([40e080d](https://github.com/gazorby/strawchemy/commit/40e080d0abb255ce3422a773ba7a36303669f7aa)) - [@gazorby](https://github.com/gazorby)
- add issue/pr labeler - ([a01a527](https://github.com/gazorby/strawchemy/commit/a01a52708bff361cc695aba39efbf706f1c0be29)) - [@gazorby](https://github.com/gazorby)
- drop bump-my-version and git-cliff in favour of cocogitto ([#206](https://github.com/gazorby/strawchemy/pull/206)) - ([84f0a82](https://github.com/gazorby/strawchemy/commit/84f0a82e00cf4b58c26a64d319008e714d1b5485)) - [@gazorby](https://github.com/gazorby)
- publish before release to enable immutable releases ([#195](https://github.com/gazorby/strawchemy/pull/195)) - ([2b578bd](https://github.com/gazorby/strawchemy/commit/2b578bd47f37288424824703f8ebf5154de9e240)) - [@gazorby](https://github.com/gazorby)

#### 🤝️ Contributors
- [@gazorby](https://github.com/gazorby)

- - -

## [v0.22.0](https://github.com/gazorby/strawchemy/compare/v0.21.0..v0.22.0) - 2026-06-10
#### 🚀 Features
- (**dto**) make database-resolved defaults optional in GraphQL inputs ([#193](https://github.com/gazorby/strawchemy/pull/193)) - ([4c20ba3](https://github.com/gazorby/strawchemy/commit/4c20ba3df7cf65263fb7ac5a34fea5f705371610)) - [@gazorby](https://github.com/gazorby)
- add field groups ([#168](https://github.com/gazorby/strawchemy/pull/168)) - ([6b936da](https://github.com/gazorby/strawchemy/commit/6b936da340017d3353885a0eea9e0ce0e48cfe8a)) - [@gazorby](https://github.com/gazorby)
- auto-generate is_type_of on output types for GraphQL unions/interfaces ([#191](https://github.com/gazorby/strawchemy/pull/191)) - ([ba7a3dd](https://github.com/gazorby/strawchemy/commit/ba7a3ddee976e4979a0907f0716c4e97ac65e8a1)) - [@gazorby](https://github.com/gazorby)
- add strict mode disallowing graphql-unmappable types ([#160](https://github.com/gazorby/strawchemy/pull/160)) - ([c1c673b](https://github.com/gazorby/strawchemy/commit/c1c673b7f1fc33d5a797e73c4f3b693266233713)) - [@gazorby](https://github.com/gazorby)
#### 🐛 Bug Fixes
- (**dto**) preserve user-defined literal defaults in Strawberry DTOs ([#188](https://github.com/gazorby/strawchemy/pull/188)) - ([6c1a75a](https://github.com/gazorby/strawchemy/commit/6c1a75a58054fa508b6314bf54857801003006d9)) - [@gazorby](https://github.com/gazorby)
- (**schema**) using override=True twice with the same name/model retains previous config ([#173](https://github.com/gazorby/strawchemy/pull/173)) - ([654b352](https://github.com/gazorby/strawchemy/commit/654b35271c07db97603cad86a3d5b78118a3724c)) - [@gazorby](https://github.com/gazorby)
- (**transpiler**) apply `filter_statement` before pagination ([#166](https://github.com/gazorby/strawchemy/pull/166)) - ([3e9bc2b](https://github.com/gazorby/strawchemy/commit/3e9bc2b98920f7c3710beabc96e29cac84a9adf8)) - [@gazorby](https://github.com/gazorby)
- using strawberry.lazy(...) break circular refs ([#169](https://github.com/gazorby/strawchemy/pull/169)) - ([a3aecc2](https://github.com/gazorby/strawchemy/commit/a3aecc2a86e07dd7e66697fbadece5f7099aae31)) - [@gazorby](https://github.com/gazorby)
- ensure user-defined relation fiels take precedence over strawchemy generated ones ([#167](https://github.com/gazorby/strawchemy/pull/167)) - ([580eac9](https://github.com/gazorby/strawchemy/commit/580eac94eafa68887a75c76fa5c84fde6a981903)) - [@gazorby](https://github.com/gazorby)
#### 🚜 Refactor
- (**lint**) update pre-commit ruff config - ([5049268](https://github.com/gazorby/strawchemy/commit/50492687f81ea3325e113a8523832e9e375834b0)) - [@gazorby](https://github.com/gazorby)
- (**lint**) upgrade ruff - ([7251dc2](https://github.com/gazorby/strawchemy/commit/7251dc2fb09b1e050691241be16b5628d188a69a)) - [@gazorby](https://github.com/gazorby)
- (**pre-commit**) upgrade - ([44db5f9](https://github.com/gazorby/strawchemy/commit/44db5f942fdc9fc8d468a1eba4fe1a8113d53d04)) - [@gazorby](https://github.com/gazorby)
- upgrade strawberry ([#155](https://github.com/gazorby/strawchemy/pull/155)) - ([83b2658](https://github.com/gazorby/strawchemy/commit/83b26582b6f50965138f559ba5b04580f049ac2c)) - [@gazorby](https://github.com/gazorby)
- mapper api overhaul ([#147](https://github.com/gazorby/strawchemy/pull/147)) - ([54392fd](https://github.com/gazorby/strawchemy/commit/54392fd84a1e074f59f04b1355aba850b8f43433)) - [@gazorby](https://github.com/gazorby)
- update configuration files - ([8dd16b5](https://github.com/gazorby/strawchemy/commit/8dd16b5b27927fa7a4f47a60908ddf0ee1db2df2)) - [@gazorby](https://github.com/gazorby)
- remove ignored files - ([79c22bc](https://github.com/gazorby/strawchemy/commit/79c22bcb33fa0777bcbc29326c02963edf9709ef)) - [@gazorby](https://github.com/gazorby)
- new project structure ([#140](https://github.com/gazorby/strawchemy/pull/140)) - ([1cd116a](https://github.com/gazorby/strawchemy/commit/1cd116a71038c628370ef2f7fb1756ccb13b46bc)) - [@gazorby](https://github.com/gazorby)
#### 📚 Documentation
- (**readme**) update - ([7c26ae8](https://github.com/gazorby/strawchemy/commit/7c26ae8272f943e2f421542233562978ebf90133)) - [@gazorby](https://github.com/gazorby)
#### ⚙️ Miscellaneous Tasks
- (**deps**) upgrade unsyncd - ([41e6fc5](https://github.com/gazorby/strawchemy/commit/41e6fc593f6bed83c9e1d74fc4a52253941e3e41)) - [@gazorby](https://github.com/gazorby)
- (**release**) bump to v0.22.0 - ([b9171fd](https://github.com/gazorby/strawchemy/commit/b9171fd719f110f2f8d38a46efcbd51a027255d4)) - [@gazorby](https://github.com/gazorby)
- (**renovate**) enable rebasing when behind base branch to keep PRs updated - ([c6c2d60](https://github.com/gazorby/strawchemy/commit/c6c2d60ccf7647dccd311406d45804e0166ab9df)) - [@gazorby](https://github.com/gazorby)
- update skip-duplicate-actions to the official step-security repo ([#186](https://github.com/gazorby/strawchemy/pull/186)) - ([6fd5039](https://github.com/gazorby/strawchemy/commit/6fd50391f8a175866b4ddf81eb03827fd05ef19f)) - [@gazorby](https://github.com/gazorby)
- update codecov action to v7 and specify explicit report types ([#185](https://github.com/gazorby/strawchemy/pull/185)) - ([94e9a3a](https://github.com/gazorby/strawchemy/commit/94e9a3a132d2384b87e8aed67d5b09aae040c303)) - [@gazorby](https://github.com/gazorby)

#### 🤝️ Contributors
- [@gazorby](https://github.com/gazorby)

- - -

## [v0.21.0](https://github.com/gazorby/strawchemy/compare/v0.20.0..v0.21.0) - 2025-12-18
#### 🚀 Features
- support multiple columns unique constraints ([#135](https://github.com/gazorby/strawchemy/pull/135)) - ([19d8bb6](https://github.com/gazorby/strawchemy/commit/19d8bb6d5869c2b3d9afb51cfdce736bd4148aa2)) - [@gazorby](https://github.com/gazorby)
#### 🚜 Refactor
- (**ruff**) disallow relative imports ([#136](https://github.com/gazorby/strawchemy/pull/136)) - ([f7ac6df](https://github.com/gazorby/strawchemy/commit/f7ac6df3500c0261a0bff44997a48811b1958d2d)) - [@gazorby](https://github.com/gazorby)
- small refactors ([#138](https://github.com/gazorby/strawchemy/pull/138)) - ([0be5a15](https://github.com/gazorby/strawchemy/commit/0be5a1511c108e3d4f779fab9a467ea3c687a967)) - [@gazorby](https://github.com/gazorby)
#### ⚙️ Miscellaneous Tasks
- (**cd**) use pat to commit changelog - ([f137678](https://github.com/gazorby/strawchemy/commit/f137678ff018462ffc31bc6c414268605e6ea9d6)) - [@gazorby](https://github.com/gazorby)
- (**release**) bump to v0.21.0 - ([e5819e4](https://github.com/gazorby/strawchemy/commit/e5819e4756db269d62773f3202cd965f6ecfdd59)) - [@gazorby](https://github.com/gazorby)

#### 🤝️ Contributors
- [@gazorby](https://github.com/gazorby)

- - -

## [v0.20.0](https://github.com/gazorby/strawchemy/compare/v0.19.0..v0.20.0) - 2025-12-14
#### 🚀 Features
- add secondary table support ([#106](https://github.com/gazorby/strawchemy/pull/106)) - ([819ee39](https://github.com/gazorby/strawchemy/commit/819ee3976519fc7f797d7572aaad353ecd926deb)) - [@gazorby](https://github.com/gazorby)
#### 🐛 Bug Fixes
- add override=True to PostType, PostFilter, and PostOrderBy to prevent automatic generation ([#98](https://github.com/gazorby/strawchemy/pull/98)) - ([36c75b8](https://github.com/gazorby/strawchemy/commit/36c75b89d7bf92e2ecece014157858c7ce4a5fc9)) - Luis Gustavo
#### 🚜 Refactor
- improve session getter ([#103](https://github.com/gazorby/strawchemy/pull/103)) - ([dae8768](https://github.com/gazorby/strawchemy/commit/dae876831ab9835accc19409311f25edbc66c626)) - [@gazorby](https://github.com/gazorby)
#### ⚙️ Miscellaneous Tasks
- (**deps**) bump astral-sh/setup-uv from 6 to 7 ([#110](https://github.com/gazorby/strawchemy/pull/110)) - ([259926b](https://github.com/gazorby/strawchemy/commit/259926b9eeb93ba7f9afd56151bf3ce171f268bf)) - [@dependabot[bot]](https://github.com/dependabot[bot]), dependabot[bot]
- (**deps**) bump github/codeql-action from 3 to 4 ([#109](https://github.com/gazorby/strawchemy/pull/109)) - ([56a31e9](https://github.com/gazorby/strawchemy/commit/56a31e9cfc690aed2a1404609c46e2de48cf318a)) - [@dependabot[bot]](https://github.com/dependabot[bot]), dependabot[bot]
- (**deps**) remove nox from main dependencies ([#99](https://github.com/gazorby/strawchemy/pull/99)) - ([39951ba](https://github.com/gazorby/strawchemy/commit/39951ba5da0ab167584be31812bd574df608d504)) - [@gazorby](https://github.com/gazorby)
- (**pre-commit**) autoupdate ([#102](https://github.com/gazorby/strawchemy/pull/102)) - ([26eb9df](https://github.com/gazorby/strawchemy/commit/26eb9df87b336ed2944ae35c92c086d5960c95f5)) - [@gazorby](https://github.com/gazorby)
- (**python**) add 3.14 to test matrix ([#126](https://github.com/gazorby/strawchemy/pull/126)) - ([8d097e4](https://github.com/gazorby/strawchemy/commit/8d097e432ca9cd8f4c9c4f10a3ce193a1edde947)) - [@gazorby](https://github.com/gazorby)
- (**release**) bump to v0.20.0 - ([2113d64](https://github.com/gazorby/strawchemy/commit/2113d6456237998354863108dc22d0b8313764f3)) - [@gazorby](https://github.com/gazorby)
- update renovate config ([#115](https://github.com/gazorby/strawchemy/pull/115)) - ([98c9f40](https://github.com/gazorby/strawchemy/commit/98c9f402e7a60a1dcb7c238fc45877f684a663e9)) - [@gazorby](https://github.com/gazorby)
- untrack ruff from mise.toml ([#113](https://github.com/gazorby/strawchemy/pull/113)) - ([9539972](https://github.com/gazorby/strawchemy/commit/953997280f85b2c8a65acb350cee894eb9c4d43e)) - [@gazorby](https://github.com/gazorby)
- move coderabbit ([#105](https://github.com/gazorby/strawchemy/pull/105)) - ([806d0c1](https://github.com/gazorby/strawchemy/commit/806d0c1ad06147b57028492296827d034541fafd)) - [@gazorby](https://github.com/gazorby), coderabbitai[bot], coderabbitai[bot]

#### 🤝️ Contributors
- Luis Gustavo
- [@coderabbitai[bot]](https://github.com/coderabbitai[bot])
- [@dependabot[bot]](https://github.com/dependabot[bot])
- [@gazorby](https://github.com/gazorby)

- - -

## [v0.19.0](https://github.com/gazorby/strawchemy/compare/v0.18.0..v0.19.0) - 2025-09-06
#### 🚀 Features
- (**schema**) add type scope - ([d2bf861](https://github.com/gazorby/strawchemy/commit/d2bf86144212bc30c51e865fbf2aa6a4851ef0b6)) - [@gazorby](https://github.com/gazorby)
#### 🐛 Bug Fixes
- (**input**) set null - ([49679db](https://github.com/gazorby/strawchemy/commit/49679dbb3a25f9f2263824d7ccf52a2bcb288d07)) - [@gazorby](https://github.com/gazorby)
- (**scalars**) add missing calls to new_type() - ([34bcfe2](https://github.com/gazorby/strawchemy/commit/34bcfe27b230898e40b8f7b9683ba4efabb21563)) - [@gazorby](https://github.com/gazorby)
- (**scalars**) cache new_type func - ([2a09122](https://github.com/gazorby/strawchemy/commit/2a091224d6550107411c90011f94657cee61e84e)) - [@gazorby](https://github.com/gazorby)
- (**scalars**) trick pyright when using NewType in scalars - ([037bc41](https://github.com/gazorby/strawchemy/commit/037bc41a26fc3130b1c26d57eeb13acd2034d3fc)) - [@gazorby](https://github.com/gazorby)
- (**schema**) fix recursive fields include/exclude logic when a relation is explicitly included - ([bf7872e](https://github.com/gazorby/strawchemy/commit/bf7872eff84d5ee29ca8666d0f1245eee158c584)) - [@gazorby](https://github.com/gazorby)
- (**schema**) fix excluding identifiers causing upsert types failing to be generated - ([ca7cb9e](https://github.com/gazorby/strawchemy/commit/ca7cb9e722082f260a195449a4d429be7ec0861a)) - [@gazorby](https://github.com/gazorby)
- (**schema**) use UNSET rather than None as default on aggregation filters - ([3c925e4](https://github.com/gazorby/strawchemy/commit/3c925e4295a642640d72f405ced09accbcfcced4)) - [@gazorby](https://github.com/gazorby)
- real support and test for python 3.9 - ([997c2e0](https://github.com/gazorby/strawchemy/commit/997c2e087160ce2b953ade58894f8431144a6bb9)) - [@gazorby](https://github.com/gazorby)
- add missing files - ([9871e80](https://github.com/gazorby/strawchemy/commit/9871e809eea8264d145105b985fbdbff006aa2a6)) - [@gazorby](https://github.com/gazorby)
#### 🚜 Refactor
- (**pyright**) update - ([ae35cfe](https://github.com/gazorby/strawchemy/commit/ae35cfead7f8efc154216b0de5b993fee523560c)) - [@gazorby](https://github.com/gazorby)
- (**schema**) focus on schema scope - ([d9ebc79](https://github.com/gazorby/strawchemy/commit/d9ebc79028a74df0c8f666eba42db22b561f3cc8)) - [@gazorby](https://github.com/gazorby)
- wip - ([8698285](https://github.com/gazorby/strawchemy/commit/86982859e6ef4ec1769913b5b4fd48294771cecb)) - [@gazorby](https://github.com/gazorby)
- fix rebase - ([39139ff](https://github.com/gazorby/strawchemy/commit/39139fff6d59638645777e80df51f2c448a0f878)) - [@gazorby](https://github.com/gazorby)
- update pyproject.toml - ([77c1ce0](https://github.com/gazorby/strawchemy/commit/77c1ce05b15063bcdadfbcb82643e84ebe31050e)) - [@gazorby](https://github.com/gazorby)
- update sentinel types - ([36bf5ad](https://github.com/gazorby/strawchemy/commit/36bf5ad0dfd8a14a832d163ef3adf41c082e51db)) - [@gazorby](https://github.com/gazorby)
- wip - ([e9eb3bb](https://github.com/gazorby/strawchemy/commit/e9eb3bb08e037f0b77d82b8e4b9e2e5bd3e5c790)) - [@gazorby](https://github.com/gazorby)
#### 📚 Documentation
- (**readme**) document type scope feature - ([49ad491](https://github.com/gazorby/strawchemy/commit/49ad491019408ce6148333450d68b72e4e872f3c)) - [@gazorby](https://github.com/gazorby)
- add docstrings to improve code documentation - ([2548771](https://github.com/gazorby/strawchemy/commit/2548771d3082afabd1ccab4dc5e6aa52439f4fb3)) - [@gazorby](https://github.com/gazorby)
#### ⚙️ Miscellaneous Tasks
- (**codeflash**) use uv to run codeflash - ([89b17a9](https://github.com/gazorby/strawchemy/commit/89b17a989204e09876f57d4030d4c2997906d4ba)) - [@gazorby](https://github.com/gazorby)
- (**deps**) bump actions/download-artifact from 4 to 5 ([#90](https://github.com/gazorby/strawchemy/pull/90)) - ([0137dd7](https://github.com/gazorby/strawchemy/commit/0137dd7a77d4a54c3e869b86a8c217a4beab7147)) - [@dependabot[bot]](https://github.com/dependabot[bot]), dependabot[bot]
- (**deps**) bump actions/setup-python from 5 to 6 ([#93](https://github.com/gazorby/strawchemy/pull/93)) - ([cf50e17](https://github.com/gazorby/strawchemy/commit/cf50e177bf5e0e8f2f9e8e47289dba2e238e22d7)) - [@dependabot[bot]](https://github.com/dependabot[bot]), dependabot[bot]
- (**deps**) bump actions/checkout from 4 to 5 ([#91](https://github.com/gazorby/strawchemy/pull/91)) - ([e0f06e3](https://github.com/gazorby/strawchemy/commit/e0f06e3388a6aaf0a316902c3499cb984a515550)) - [@dependabot[bot]](https://github.com/dependabot[bot]), dependabot[bot]
- (**deps**) bump jdx/mise-action from 2 to 3 ([#92](https://github.com/gazorby/strawchemy/pull/92)) - ([7f7e95d](https://github.com/gazorby/strawchemy/commit/7f7e95db97c456d499fb75714848bf5f255d4d1d)) - [@dependabot[bot]](https://github.com/dependabot[bot]), dependabot[bot]
- (**lint**) move to basedpyright - ([d3abcf4](https://github.com/gazorby/strawchemy/commit/d3abcf475e2bbf387653159f1f2f9e1a627ba0ff)) - [@gazorby](https://github.com/gazorby)
- (**mise**) update vulture task - ([2d1daaf](https://github.com/gazorby/strawchemy/commit/2d1daafde542e0f666b9a2aaec712265980ddedd)) - [@gazorby](https://github.com/gazorby)
- (**mise**) allow passing python version to mise test targets - ([d286e63](https://github.com/gazorby/strawchemy/commit/d286e63b9cbb0a07e1f226044248b7dae6767b8f)) - [@gazorby](https://github.com/gazorby)
- (**nox**) bring back cache - ([44084aa](https://github.com/gazorby/strawchemy/commit/44084aadbd397423386c7457ea7779a5f6657db7)) - [@gazorby](https://github.com/gazorby)
- (**nox**) update - ([eae64cf](https://github.com/gazorby/strawchemy/commit/eae64cfd70d96900c0dfc8dbdaf2913ee9f84fc8)) - [@gazorby](https://github.com/gazorby)
- (**nox**) simplify nox invocation - ([d8838de](https://github.com/gazorby/strawchemy/commit/d8838de7103e4ef77ebd310277ffa228d5700607)) - [@gazorby](https://github.com/gazorby)
- (**nox**) disable cache - ([a8541b7](https://github.com/gazorby/strawchemy/commit/a8541b71e62c0b7fe430234eafb5fe742d54bffa)) - [@gazorby](https://github.com/gazorby)
- (**release**) bump to v0.19.0 - ([2869de1](https://github.com/gazorby/strawchemy/commit/2869de1e3b3b8b13fd7cf9f9ef876a7a62db237b)) - [@gazorby](https://github.com/gazorby)
- (**test**) update - ([eb1aa5e](https://github.com/gazorby/strawchemy/commit/eb1aa5eac73e8fdcafc109871aed5d2d74227fc9)) - [@gazorby](https://github.com/gazorby)
- (**test**) try setting uv pref to only-managed - ([478d6d7](https://github.com/gazorby/strawchemy/commit/478d6d7f97175cd44191f0ecf59c138f1312162a)) - [@gazorby](https://github.com/gazorby)
- (**test**) pin 3.12 again - ([f661bed](https://github.com/gazorby/strawchemy/commit/f661beddf960ac1cb106f76c46433caaa18047e7)) - [@gazorby](https://github.com/gazorby)
- (**test**) use uvx to invoke nox - ([a322b48](https://github.com/gazorby/strawchemy/commit/a322b48dce842e853ec5c505a15fdd3f9bc8b31f)) - [@gazorby](https://github.com/gazorby)
- (**test**) update .nox path for action caching - ([680855e](https://github.com/gazorby/strawchemy/commit/680855e07708587ba3675240548421327af0819f)) - [@gazorby](https://github.com/gazorby)
- fix codeflash - ([d791dfc](https://github.com/gazorby/strawchemy/commit/d791dfc4370799f415ca693ce457cf69ccd33062)) - [@gazorby](https://github.com/gazorby)
- update .gitignore - ([96c5e12](https://github.com/gazorby/strawchemy/commit/96c5e124d0c51b628fbe2efc0f93960b59f8cb15)) - [@gazorby](https://github.com/gazorby)
- update .gitignore - ([09d69af](https://github.com/gazorby/strawchemy/commit/09d69afd3f08abfc66837627614d333e6826494d)) - [@gazorby](https://github.com/gazorby)
- add codeflash - ([e8dfdfb](https://github.com/gazorby/strawchemy/commit/e8dfdfbf93ddaa235bf56e5f4be2d329ac08f621)) - [@gazorby](https://github.com/gazorby)
- update .editorconfig - ([0ae1c7a](https://github.com/gazorby/strawchemy/commit/0ae1c7a778d70a36bf825dcd345cc796ecf697d2)) - [@gazorby](https://github.com/gazorby)

#### 🤝️ Contributors
- [@dependabot[bot]](https://github.com/dependabot[bot])
- [@gazorby](https://github.com/gazorby)

- - -

## [v0.18.0](https://github.com/gazorby/strawchemy/compare/v0.17.0..v0.18.0) - 2025-06-07
#### 🚀 Features
- (**mutation**) initial upsert support - ([b45272e](https://github.com/gazorby/strawchemy/commit/b45272e7c12afc6fbc34598bf81830071e6c54f6)) - [@gazorby](https://github.com/gazorby)
#### 🐛 Bug Fixes
- do not rely on literal_column to reference computed column in some distinct on scenarios - ([5ac834f](https://github.com/gazorby/strawchemy/commit/5ac834f5b50441c6f899c6bd4fda5210484c8605)) - [@gazorby](https://github.com/gazorby)
#### 🚜 Refactor
- (**testapp**) disable enable_touch_updated_timestamp_listener as it mess up with integration tests - ([1c4c2c4](https://github.com/gazorby/strawchemy/commit/1c4c2c4ba076d7d4b0097e919864708dba9ddc58)) - [@gazorby](https://github.com/gazorby)
- (**transpiler**) use literal_column less often and use a more reliable method when necessary - ([e0f047f](https://github.com/gazorby/strawchemy/commit/e0f047fe4d125e369c26667ef9dc7c727d5bd6d1)) - [@gazorby](https://github.com/gazorby)
- (**upsert**) restrict conflict constraints to pk, unique and exclude constraints - ([338543b](https://github.com/gazorby/strawchemy/commit/338543b587592ac1d3a37897a917e1cbfbccdc75)) - [@gazorby](https://github.com/gazorby)
#### 📚 Documentation
- (**readme**) add section for upsert mutations - ([99b7096](https://github.com/gazorby/strawchemy/commit/99b709619a38cdef600ec8dd19444371de524007)) - [@gazorby](https://github.com/gazorby)
- (**readme**) update database support - ([7c55100](https://github.com/gazorby/strawchemy/commit/7c55100d2cff009ddae6eb5b52b9ec74ee7679ab)) - [@gazorby](https://github.com/gazorby)
#### ⚙️ Miscellaneous Tasks
- (**release**) bump to v0.18.0 - ([56c2238](https://github.com/gazorby/strawchemy/commit/56c22380db2f8324178e9c7f122c14ccf57bf01a)) - [@gazorby](https://github.com/gazorby)
- (**testapp**) add pydantic - ([48980a2](https://github.com/gazorby/strawchemy/commit/48980a291aab590b96179e85666f4d385aafc18b)) - [@gazorby](https://github.com/gazorby)
- (**uv**) include testapp in dev dependancies - ([79567b6](https://github.com/gazorby/strawchemy/commit/79567b67813233d6e862c178cf36012c1352335c)) - [@gazorby](https://github.com/gazorby)

#### 🤝️ Contributors
- [@gazorby](https://github.com/gazorby)

- - -

## [v0.17.0](https://github.com/gazorby/strawchemy/compare/v0.16.0..v0.17.0) - 2025-06-02
#### 🚀 Features
- (**json**) extract path - ([924d89a](https://github.com/gazorby/strawchemy/commit/924d89a897dec86241728cee2ea1156590453799)) - [@gazorby](https://github.com/gazorby)
- (**sqlite**) add json path extraction - ([3593a07](https://github.com/gazorby/strawchemy/commit/3593a077d8c446560a125f990ac7564784880660)) - [@gazorby](https://github.com/gazorby)
- (**sqlite**) add interval filtering - ([6b81592](https://github.com/gazorby/strawchemy/commit/6b81592cbd9a88d25d4a3267fea5d639ae880cf9)) - [@gazorby](https://github.com/gazorby)
- (**sqlite**) add JSON filtering - ([4b510d8](https://github.com/gazorby/strawchemy/commit/4b510d8df21f56b5088ebcd5caa3f28fe91085ec)) - [@gazorby](https://github.com/gazorby)
- (**sqlite**) initial support - ([e71bcda](https://github.com/gazorby/strawchemy/commit/e71bcda9e446039c2a741b32e49935cf03c56e87)) - [@gazorby](https://github.com/gazorby)
#### 🐛 Bug Fixes
- (**interval**) output serialization - ([7e6e822](https://github.com/gazorby/strawchemy/commit/7e6e822937a598ff25b470282ec9b6a0f9bdb1bd)) - [@gazorby](https://github.com/gazorby)
- (**update-by-id**) do not pass empty where filter to the resolver - ([393970f](https://github.com/gazorby/strawchemy/commit/393970fe4ef469450093e468e8131ab4a1591946)) - [@gazorby](https://github.com/gazorby)
#### 🚜 Refactor
- (**sqlite**) minor fixes - ([387356f](https://github.com/gazorby/strawchemy/commit/387356f15174c8705e0d5ac08abbf4e823a2aad2)) - [@gazorby](https://github.com/gazorby)
- (**typing**) remove unused types - ([cc39392](https://github.com/gazorby/strawchemy/commit/cc393929f76c653b3b7f0e20c87e678ba4ce655b)) - [@gazorby](https://github.com/gazorby)
#### 📚 Documentation
- mention sqlite in the readme - ([46acbec](https://github.com/gazorby/strawchemy/commit/46acbec7c78d4c84f72db66296ad8bd799f90080)) - [@gazorby](https://github.com/gazorby)
#### ⚙️ Miscellaneous Tasks
- (**release**) bump to v0.17.0 - ([cda53ea](https://github.com/gazorby/strawchemy/commit/cda53ea2d2e32f6c772a9e46306203069c600ec2)) - [@gazorby](https://github.com/gazorby)
- upgrade dependencies - ([d8a9dd1](https://github.com/gazorby/strawchemy/commit/d8a9dd1bc2e57ca12d088b0ec58407449a6f865b)) - [@gazorby](https://github.com/gazorby)

#### 🤝️ Contributors
- [@gazorby](https://github.com/gazorby)

- - -

## [v0.16.0](https://github.com/gazorby/strawchemy/compare/v0.15.6..v0.16.0) - 2025-05-27
#### 🚀 Features
- (**mysql**) implements geo comparisons - ([e531ece](https://github.com/gazorby/strawchemy/commit/e531ece1a12a1195b4cf034ae12f9f5ab202b093)) - [@gazorby](https://github.com/gazorby)
- (**mysql**) implement JSON comparison - ([0e3278d](https://github.com/gazorby/strawchemy/commit/0e3278d0c9591bce121840ee6325cb6b0c1ce0a6)) - [@gazorby](https://github.com/gazorby)
- (**mysql**) implement interval comparisons - ([eeb4439](https://github.com/gazorby/strawchemy/commit/eeb44392539a83c0a3152b961229ceacac9de234)) - [@gazorby](https://github.com/gazorby)
- (**mysql**) implement date/time comparisons - ([d566470](https://github.com/gazorby/strawchemy/commit/d56647024b7d1ee422b2a39d64631cbe52326c5b)) - [@gazorby](https://github.com/gazorby)
- (**mysql**) initial support - ([c721666](https://github.com/gazorby/strawchemy/commit/c721666998c748fa29131ff34251c88d1c78bf50)) - [@gazorby](https://github.com/gazorby)
- implement deterministic ordering - ([3c12a0c](https://github.com/gazorby/strawchemy/commit/3c12a0c50615b6d64f720dedcf13493e762b8777)) - [@gazorby](https://github.com/gazorby)
#### 🐛 Bug Fixes
- (**mysql**) do not generate the distinct column when no distinct args is passed - ([8524902](https://github.com/gazorby/strawchemy/commit/852490215b9d6a3536ca48bed35d9fcaed2a7add)) - [@gazorby](https://github.com/gazorby)
- (**ordering**) join ordering not propagated into the root query - ([16e4e30](https://github.com/gazorby/strawchemy/commit/16e4e3058eefe532b189728e9076870053e4a239)) - [@gazorby](https://github.com/gazorby)
#### 🚜 Refactor
- (**config**) require dialect when instantiating strawchemy instance - ([f127fbf](https://github.com/gazorby/strawchemy/commit/f127fbf4dee0a47bab139984d83ed8a8b707a029)) - [@gazorby](https://github.com/gazorby)
- (**config**) restrict aggregation filters to those supported by the database - ([66872d9](https://github.com/gazorby/strawchemy/commit/66872d9db5a35b1aa24716903bf8a268fd700ad5)) - [@gazorby](https://github.com/gazorby)
- (**mysql**) add a distinct on implementation - ([2d5f4b2](https://github.com/gazorby/strawchemy/commit/2d5f4b29f56dc6063adec5d5b807c5569b26bd8a)) - [@gazorby](https://github.com/gazorby)
- (**repository**) allow accessing instances from repository result - ([8a3b861](https://github.com/gazorby/strawchemy/commit/8a3b861642667bbdb80891dd29db034580e91cc3)) - [@gazorby](https://github.com/gazorby)
- (**schema**) generate all types with the strawberry dto backend - ([a4f034b](https://github.com/gazorby/strawchemy/commit/a4f034b5c1318e7c122429c74f9507ac49db5890)) - [@gazorby](https://github.com/gazorby)
- (**transpiler**) prefix literal names generated by strawchemy to minimize conflicts - ([9137411](https://github.com/gazorby/strawchemy/commit/91374112cedc797449c8eaa0f8bec6aa76cd2dc3)) - [@gazorby](https://github.com/gazorby)
- wip - ([4132d1d](https://github.com/gazorby/strawchemy/commit/4132d1d9a075a46c7a4a00bd4406326449964902)) - [@gazorby](https://github.com/gazorby)
- remove more dead batteries - ([84ad8dd](https://github.com/gazorby/strawchemy/commit/84ad8ddc8286e7ff843f77362f8b035be0ed5975)) - [@gazorby](https://github.com/gazorby)
- simplify project structure - ([bae73d9](https://github.com/gazorby/strawchemy/commit/bae73d9eb1263af30a45dd0fc094959771bf6a2f)) - [@gazorby](https://github.com/gazorby)
- make pydantic an optional dependency - ([82df05d](https://github.com/gazorby/strawchemy/commit/82df05dce587f318d66cfdc8273cf47db797074a)) - [@gazorby](https://github.com/gazorby)
- wip - ([5e957c0](https://github.com/gazorby/strawchemy/commit/5e957c047f8a8dea19170c66c19ae85462258ffb)) - [@gazorby](https://github.com/gazorby)
#### 📚 Documentation
- (**readme**) update - ([b1f7b99](https://github.com/gazorby/strawchemy/commit/b1f7b9917c985589c641589db4da540f6e37127e)) - [@gazorby](https://github.com/gazorby)
- update readme - ([d20b2ae](https://github.com/gazorby/strawchemy/commit/d20b2ae8c29b62eb58488d9a2a22fdb49a88c362)) - [@gazorby](https://github.com/gazorby)
#### ⚙️ Miscellaneous Tasks
- (**release**) bump to v0.16.0 - ([58a3bda](https://github.com/gazorby/strawchemy/commit/58a3bdaed9a516f5fd1a556dec784bf0da4b9d19)) - [@gazorby](https://github.com/gazorby)

#### 🤝️ Contributors
- [@gazorby](https://github.com/gazorby)

- - -

## [v0.15.6](https://github.com/gazorby/strawchemy/compare/v0.15.5..v0.15.6) - 2025-04-29
#### 🐛 Bug Fixes
- (**input**) discard attributes set during model init when parsing update inputs - ([62f4327](https://github.com/gazorby/strawchemy/commit/62f432796c0bef4bf4a7767f49cc391954541c6a)) - [@gazorby](https://github.com/gazorby)
#### ⚙️ Miscellaneous Tasks
- (**release**) bump to v0.15.6 - ([bad48a6](https://github.com/gazorby/strawchemy/commit/bad48a6a5932284dd7e41548ebdcdab4176f8046)) - [@gazorby](https://github.com/gazorby)

#### 🤝️ Contributors
- [@gazorby](https://github.com/gazorby)

- - -

## [v0.15.5](https://github.com/gazorby/strawchemy/compare/v0.15.4..v0.15.5) - 2025-04-29
#### 🐛 Bug Fixes
- (**input**) fields on update input were not partial - ([3f94f2e](https://github.com/gazorby/strawchemy/commit/3f94f2e0bd44d079ba3f254951982a1166bb9f84)) - [@gazorby](https://github.com/gazorby)
#### 🚜 Refactor
- (**formatting**) apply ruff - ([8d3375f](https://github.com/gazorby/strawchemy/commit/8d3375f5b63fe36292f9956909c93606581b042a)) - [@gazorby](https://github.com/gazorby)
#### ⚙️ Miscellaneous Tasks
- (**release**) bump to v0.15.5 - ([83487ca](https://github.com/gazorby/strawchemy/commit/83487ca24114bfe7d44fdb10e2218c87f49452e0)) - [@gazorby](https://github.com/gazorby)
- (**uv**) upgrade - ([c973d96](https://github.com/gazorby/strawchemy/commit/c973d96fd0d1dc9ea46cd9f82e453f86cf04309c)) - [@gazorby](https://github.com/gazorby)

#### 🤝️ Contributors
- [@gazorby](https://github.com/gazorby)

- - -

## [v0.15.4](https://github.com/gazorby/strawchemy/compare/v0.15.3..v0.15.4) - 2025-04-29
#### 🐛 Bug Fixes
- (**input**) dataclass models tracking not working - ([14bfe33](https://github.com/gazorby/strawchemy/commit/14bfe33faa5c3619e80150e5ab31e19a1b1410b1)) - [@gazorby](https://github.com/gazorby)
#### ⚙️ Miscellaneous Tasks
- (**release**) bump to v0.15.4 - ([9fc7cde](https://github.com/gazorby/strawchemy/commit/9fc7cdeb8e9fe242baece19b7e8efbc61dbea5a4)) - [@gazorby](https://github.com/gazorby)

#### 🤝️ Contributors
- [@gazorby](https://github.com/gazorby)

- - -

## [v0.15.3](https://github.com/gazorby/strawchemy/compare/v0.15.2..v0.15.3) - 2025-04-29
#### ⚙️ Miscellaneous Tasks
- (**release**) bump to v0.15.3 - ([6c6207e](https://github.com/gazorby/strawchemy/commit/6c6207eb52f31b9f762d2bc8928d5184be757ffc)) - [@gazorby](https://github.com/gazorby)
- fix python 3.13 - ([2b4cf16](https://github.com/gazorby/strawchemy/commit/2b4cf169e317cf4d5d1362fa1e07b3acc4f31ace)) - [@gazorby](https://github.com/gazorby)

#### 🤝️ Contributors
- [@gazorby](https://github.com/gazorby)

- - -

## [v0.15.2](https://github.com/gazorby/strawchemy/compare/v0.15.1..v0.15.2) - 2025-04-29
#### ⚙️ Miscellaneous Tasks
- (**publish**) enable uv cache - ([c1d60ec](https://github.com/gazorby/strawchemy/commit/c1d60ec9f792c4eb0fd60e99050eb35745337a11)) - [@gazorby](https://github.com/gazorby)
- (**release**) bump to v0.15.2 - ([fe3695b](https://github.com/gazorby/strawchemy/commit/fe3695bc24740aff435457e4eddd651a7f3e39d1)) - [@gazorby](https://github.com/gazorby)

#### 🤝️ Contributors
- [@gazorby](https://github.com/gazorby)

- - -

## [v0.15.1](https://github.com/gazorby/strawchemy/compare/v0.15.0..v0.15.1) - 2025-04-28
#### ⚙️ Miscellaneous Tasks
- (**publish**) use python 3.13 - ([1c8754a](https://github.com/gazorby/strawchemy/commit/1c8754a689c05228092a0b70126df086e8e7f943)) - [@gazorby](https://github.com/gazorby)
- (**release**) bump to v0.15.1 - ([c536774](https://github.com/gazorby/strawchemy/commit/c536774cc96d9fc98f485d16c8cbf9edea5267e3)) - [@gazorby](https://github.com/gazorby)

#### 🤝️ Contributors
- [@gazorby](https://github.com/gazorby)

- - -

## [v0.15.0](https://github.com/gazorby/strawchemy/compare/v0.14.2..v0.15.0) - 2025-04-28
#### 🚀 Features
- (**input**) track relationship changes - ([feee547](https://github.com/gazorby/strawchemy/commit/feee5478028556cbc419041b9bfa12dd9712dd0e)) - [@gazorby](https://github.com/gazorby)
#### ⚙️ Miscellaneous Tasks
- (**release**) bump to v0.15.0 - ([aeb1ed3](https://github.com/gazorby/strawchemy/commit/aeb1ed33a6e67803e42f7f85236211cf2edcaafe)) - [@gazorby](https://github.com/gazorby)

#### 🤝️ Contributors
- [@gazorby](https://github.com/gazorby)

- - -

## [v0.14.2](https://github.com/gazorby/strawchemy/compare/v0.14.1..v0.14.2) - 2025-04-24
#### 🐛 Bug Fixes
- (**mutation-input**) override would not be applied in certain cases - ([bbe75a8](https://github.com/gazorby/strawchemy/commit/bbe75a8165d38f21ae9ff4c5195513534f804373)) - [@gazorby](https://github.com/gazorby)
- (**mutation-input**) override would not be applied in certain cases - ([a70791f](https://github.com/gazorby/strawchemy/commit/a70791f09c5bdff38baf14e36943c726d7297407)) - [@gazorby](https://github.com/gazorby)
#### 🚜 Refactor
- update _StrawberryQueryNode method names - ([783855d](https://github.com/gazorby/strawchemy/commit/783855d2add7a155db0ed5c58fd57edc79f7292d)) - [@gazorby](https://github.com/gazorby)
#### ⚙️ Miscellaneous Tasks
- (**deps**) bump astral-sh/setup-uv from 5 to 6 - ([a820ea7](https://github.com/gazorby/strawchemy/commit/a820ea7e9a2b02926c55a8b0b5f41b77f87ab14f)) - [@dependabot[bot]](https://github.com/dependabot[bot])
- (**release**) bump to v0.14.2 - ([d5c6038](https://github.com/gazorby/strawchemy/commit/d5c6038bac18959f5ad0d1e5998bddfa410b044b)) - [@gazorby](https://github.com/gazorby)
- run tests in renovate/dependabot branches - ([9e137f5](https://github.com/gazorby/strawchemy/commit/9e137f5e334241b66164fa49edcfaca440acb82a)) - [@gazorby](https://github.com/gazorby)
- run tests in renovate/dependabot branches - ([17b761f](https://github.com/gazorby/strawchemy/commit/17b761f95af77cf209a803b3e7c95e51b89bafe9)) - [@gazorby](https://github.com/gazorby)

#### 🤝️ Contributors
- [@dependabot[bot]](https://github.com/dependabot[bot])
- [@gazorby](https://github.com/gazorby)

- - -

## [v0.14.1](https://github.com/gazorby/strawchemy/compare/v0.14.0..v0.14.1) - 2025-04-24
#### 🐛 Bug Fixes
- (**dto**) override params passed to .to_mapped() would not apply if they were excluded in dto - ([eb39a92](https://github.com/gazorby/strawchemy/commit/eb39a929249e6a758989cc9539aa7888238e542d)) - [@gazorby](https://github.com/gazorby)
#### 🚜 Refactor
- (**strawchemy-repository**) update `root_type` param to `type` - ([4354c51](https://github.com/gazorby/strawchemy/commit/4354c510c216f42a88bf6b4649aecedcbd17ddfc)) - [@gazorby](https://github.com/gazorby)
#### ⚙️ Miscellaneous Tasks
- (**release**) bump to v0.14.1 - ([cf2c732](https://github.com/gazorby/strawchemy/commit/cf2c73266a3e004f3122098b0e15bfeb1493ff60)) - [@gazorby](https://github.com/gazorby)
- (**renovate**) extend config:semverAllMonthly config - ([063b476](https://github.com/gazorby/strawchemy/commit/063b476c46c1019526cf5f2d0e28f39288069afb)) - [@gazorby](https://github.com/gazorby)

#### 🤝️ Contributors
- [@gazorby](https://github.com/gazorby)

- - -

## [v0.14.0](https://github.com/gazorby/strawchemy/compare/v0.13.7..v0.14.0) - 2025-04-24
#### 🚀 Features
- (**mutation**) expose Input to strawchemy repository - ([fe1d1f5](https://github.com/gazorby/strawchemy/commit/fe1d1f5752e1745d4632ab0f9885f378d6f0636a)) - [@gazorby](https://github.com/gazorby)
- (**schema**) add pydantic input validation - ([580bbef](https://github.com/gazorby/strawchemy/commit/580bbefd610468f8aba47f20198e8331130d1753)) - [@gazorby](https://github.com/gazorby)
#### 🐛 Bug Fixes
- (**validation**) handle nested models - ([1fa7e14](https://github.com/gazorby/strawchemy/commit/1fa7e14b60e7e7de52ae91645036611cbffe1f0b)) - [@gazorby](https://github.com/gazorby)
#### 🚜 Refactor
- (**factory**) remove type/input decorators on _StrawberryFactory - ([de5a75d](https://github.com/gazorby/strawchemy/commit/de5a75d7c3c923b18ec37fae6b65a1f5cd67701b)) - [@gazorby](https://github.com/gazorby)
- (**repository**) move common logic in a base class for sync/async strawchemy repositories - ([4b31d3a](https://github.com/gazorby/strawchemy/commit/4b31d3ab5c8ebf9f9f185f5fc49fdbdcb2ba444c)) - [@gazorby](https://github.com/gazorby)
- (**validation**) update mapper api - ([299fb0a](https://github.com/gazorby/strawchemy/commit/299fb0a32f870482db0aef32260dccffaf677d65)) - [@gazorby](https://github.com/gazorby)
- wip - ([a3b6aef](https://github.com/gazorby/strawchemy/commit/a3b6aef4ea15d7bc355c8c62f4fea756e796279e)) - [@gazorby](https://github.com/gazorby)
#### 📚 Documentation
- (**readme**) add a section for input validation - ([fea65c5](https://github.com/gazorby/strawchemy/commit/fea65c5fda2afebf0663e50a76c52e83f7c487de)) - [@gazorby](https://github.com/gazorby)
- (**readme**) update - ([2ade51e](https://github.com/gazorby/strawchemy/commit/2ade51eb1645c79198af327ec3cc25e678e2eba5)) - [@gazorby](https://github.com/gazorby)
#### ⚙️ Miscellaneous Tasks
- (**release**) bump to v0.14.0 - ([ada7bcb](https://github.com/gazorby/strawchemy/commit/ada7bcb5a5e778599f878bc1619d3e015f1e480d)) - [@gazorby](https://github.com/gazorby)

#### 🤝️ Contributors
- [@gazorby](https://github.com/gazorby)

- - -

## [v0.13.7](https://github.com/gazorby/strawchemy/compare/v0.13.6..v0.13.7) - 2025-04-15
#### 🐛 Bug Fixes
- (**dto**) incorrect forward ref name set in the tracking graph when building recursive dtos - ([ac20b7b](https://github.com/gazorby/strawchemy/commit/ac20b7b1f2e745e7e41ed5ec40ee66ba2d31ec7e)) - [@gazorby](https://github.com/gazorby)
#### ⚙️ Miscellaneous Tasks
- (**release**) bump to v0.13.7 - ([70619a5](https://github.com/gazorby/strawchemy/commit/70619a5b92ad1e837e4bd04fb535537e8acc984b)) - [@gazorby](https://github.com/gazorby)

#### 🤝️ Contributors
- [@gazorby](https://github.com/gazorby)

- - -

## [v0.13.6](https://github.com/gazorby/strawchemy/compare/v0.13.5..v0.13.6) - 2025-04-15
#### 🚜 Refactor
- (**mapper**) more factory reuse - ([1c00afc](https://github.com/gazorby/strawchemy/commit/1c00afce6f1795b11a4e3c30b47560fbaa1f3f70)) - [@gazorby](https://github.com/gazorby)
#### ⚙️ Miscellaneous Tasks
- (**release**) bump to v0.13.6 - ([ac39d47](https://github.com/gazorby/strawchemy/commit/ac39d47bf85a5134c93d1b4fb13f83ee3ae88c8d)) - [@gazorby](https://github.com/gazorby)

#### 🤝️ Contributors
- [@gazorby](https://github.com/gazorby)

- - -

## [v0.13.5](https://github.com/gazorby/strawchemy/compare/v0.13.4..v0.13.5) - 2025-04-15
#### 🐛 Bug Fixes
- (**dto**) reuse order_by factory to generate orderBy args - ([3640dc0](https://github.com/gazorby/strawchemy/commit/3640dc0c509c9a530d0b1b844aa5cd3fe162b581)) - [@gazorby](https://github.com/gazorby)
#### ⚙️ Miscellaneous Tasks
- (**release**) bump to v0.13.5 - ([a379b35](https://github.com/gazorby/strawchemy/commit/a379b35ebf13832a6c2c341fa98950cadbf27d4b)) - [@gazorby](https://github.com/gazorby)

#### 🤝️ Contributors
- [@gazorby](https://github.com/gazorby)

- - -

## [v0.13.4](https://github.com/gazorby/strawchemy/compare/v0.13.3..v0.13.4) - 2025-04-15
#### 🐛 Bug Fixes
- (**dto**) not all unresolved dto would be tracked - ([cb384c4](https://github.com/gazorby/strawchemy/commit/cb384c48995cfeca6bb922dad9a7389cbdeeb23e)) - [@gazorby](https://github.com/gazorby)
#### ⚙️ Miscellaneous Tasks
- (**release**) bump to v0.13.4 - ([3f4da43](https://github.com/gazorby/strawchemy/commit/3f4da43678ac34732bb97b5b28edd2e1ed45577f)) - [@gazorby](https://github.com/gazorby)

#### 🤝️ Contributors
- [@gazorby](https://github.com/gazorby)

- - -

## [v0.13.3](https://github.com/gazorby/strawchemy/compare/v0.13.2..v0.13.3) - 2025-04-15
#### 🐛 Bug Fixes
- (**dto**) track unresolved forward refs - ([57d8bf1](https://github.com/gazorby/strawchemy/commit/57d8bf11d7f44aff91f2ede42ca0d02d1699cb32)) - [@gazorby](https://github.com/gazorby)
- (**testapp**) explictly set StrawchemyAsyncRepository - ([2fd99a5](https://github.com/gazorby/strawchemy/commit/2fd99a59f2269f61dd9a334b67dd3343a13182b2)) - [@gazorby](https://github.com/gazorby)
#### ⚙️ Miscellaneous Tasks
- (**release**) bump to v0.13.3 - ([4b04bb8](https://github.com/gazorby/strawchemy/commit/4b04bb8a28366045ffd764db016c3b65b28c7623)) - [@gazorby](https://github.com/gazorby)

#### 🤝️ Contributors
- [@gazorby](https://github.com/gazorby)

- - -

## [v0.13.2](https://github.com/gazorby/strawchemy/compare/v0.13.1..v0.13.2) - 2025-04-14
#### 🚜 Refactor
- (**pydantic**) remove defer_build=True on base config - ([4457996](https://github.com/gazorby/strawchemy/commit/445799619b6dbc617b65c3b643b592e001991a4c)) - [@gazorby](https://github.com/gazorby)
#### ⚙️ Miscellaneous Tasks
- (**release**) bump to v0.13.2 - ([80021fa](https://github.com/gazorby/strawchemy/commit/80021facb7bcb582a9a997ede45f9f2bc21e0ebe)) - [@gazorby](https://github.com/gazorby)

#### 🤝️ Contributors
- [@gazorby](https://github.com/gazorby)

- - -

## [v0.13.1](https://github.com/gazorby/strawchemy/compare/v0.13.0..v0.13.1) - 2025-04-10
#### 🐛 Bug Fixes
- (**config**) field would not marked as async when it should - ([1b8d74e](https://github.com/gazorby/strawchemy/commit/1b8d74eb1173b33894ef0afff4be83538622b80a)) - [@gazorby](https://github.com/gazorby)
#### 📚 Documentation
- (**readme**) clarify default repository_type value - ([893eeb8](https://github.com/gazorby/strawchemy/commit/893eeb86bacdb61a7762bb0ee6b2b9f0d146c7e8)) - [@gazorby](https://github.com/gazorby)
#### ⚙️ Miscellaneous Tasks
- (**release**) bump to v0.13.1 - ([5bb99a6](https://github.com/gazorby/strawchemy/commit/5bb99a6a07d62cc1df9c0e5875ab6f50c769bb9a)) - [@gazorby](https://github.com/gazorby)

#### 🤝️ Contributors
- [@gazorby](https://github.com/gazorby)

- - -

## [v0.13.0](https://github.com/gazorby/strawchemy/compare/v0.12.2..v0.13.0) - 2025-04-09
#### 🚀 Features
- (**cud**) add filter update mutation - ([c15f60c](https://github.com/gazorby/strawchemy/commit/c15f60c1f7618de8529711e33639b28c8ba6362c)) - [@gazorby](https://github.com/gazorby)
- (**cud**) add delete mutation - ([289d9be](https://github.com/gazorby/strawchemy/commit/289d9bea3bbd38d826578f44607a8978c3b8dffa)) - [@gazorby](https://github.com/gazorby)
- (**cud**) allow settings null on to-one relations - ([1efe0ed](https://github.com/gazorby/strawchemy/commit/1efe0ed9fa118ae95a2ac572d829936195c6880a)) - [@gazorby](https://github.com/gazorby)
#### 🐛 Bug Fixes
- (**cud**) enable add/remove on to-mnay relations; set overwrite previous to-many relations - ([08ee2e7](https://github.com/gazorby/strawchemy/commit/08ee2e79e75161e597d59ca3a1727ca233cce53b)) - [@gazorby](https://github.com/gazorby)
- (**mapping**) exclude foreign keys from inputs - ([17678f2](https://github.com/gazorby/strawchemy/commit/17678f21578675d8f16100208756b9bb934f542c)) - [@gazorby](https://github.com/gazorby)
- (**mapping**) respect nullability when generating input types - ([f87f3b6](https://github.com/gazorby/strawchemy/commit/f87f3b6d6df840540077d079d28bd2d095c57016)) - [@gazorby](https://github.com/gazorby)
- (**schema**) do not allow removing to-many relations if remote fk is not nullable - ([c7203bc](https://github.com/gazorby/strawchemy/commit/c7203bccd4912e2c923515d12bde2097a806dd98)) - [@gazorby](https://github.com/gazorby)
#### 🚜 Refactor
- (**cud**) merge create and update transaction logic - ([769e4ef](https://github.com/gazorby/strawchemy/commit/769e4efa78e9140bab0f0d7d18caba5151d65cff)) - [@gazorby](https://github.com/gazorby)
- (**cud**) implement update repository method - ([1080c25](https://github.com/gazorby/strawchemy/commit/1080c25bf134a7ae509be0194367f7d7dff0dc4e)) - [@gazorby](https://github.com/gazorby)
- (**cud**) implement update input - ([5fd3d9f](https://github.com/gazorby/strawchemy/commit/5fd3d9f91d4dab42419c29eb2b092c8364f165b8)) - [@gazorby](https://github.com/gazorby)
- (**mapper**) remove duplicate assignement - ([f22e1de](https://github.com/gazorby/strawchemy/commit/f22e1deab11a24320f7a17139b83942c98da342b)) - [@gazorby](https://github.com/gazorby)
- (**mapper**) update api - ([a486384](https://github.com/gazorby/strawchemy/commit/a48638470223a426cf02fd9021098b2dd1e4876f)) - [@gazorby](https://github.com/gazorby)
- (**repository**) update code documentation - ([ae39957](https://github.com/gazorby/strawchemy/commit/ae3995739fbb5d60ac11077e00618943eb695b4a)) - [@gazorby](https://github.com/gazorby)
- (**update-input**) make all fields partial, except pks - ([64a6f3e](https://github.com/gazorby/strawchemy/commit/64a6f3e58108e9b7f5e1419b759747f7f01a6a68)) - [@gazorby](https://github.com/gazorby)
- (**utils**) remove unused function - ([68a970b](https://github.com/gazorby/strawchemy/commit/68a970b8a7da0baa4d37ba084dcacd806ad90b2c)) - [@gazorby](https://github.com/gazorby)
#### 📚 Documentation
- (**readme**) add mutation documention - ([5de832a](https://github.com/gazorby/strawchemy/commit/5de832a3d7868f5c544a8c40f6683df9ac045cfd)) - [@gazorby](https://github.com/gazorby)
#### ⚙️ Miscellaneous Tasks
- (**release**) bump to v0.13.0 - ([fd1d725](https://github.com/gazorby/strawchemy/commit/fd1d7257c906f2e2131c079840e33abd3af8d681)) - [@gazorby](https://github.com/gazorby)

#### 🤝️ Contributors
- [@gazorby](https://github.com/gazorby)

- - -

## [v0.12.2](https://github.com/gazorby/strawchemy/compare/v0.12.1..v0.12.2) - 2025-04-03
#### 🐛 Bug Fixes
- (**mapping**) input identifiers not managed by the registry - ([d28a11b](https://github.com/gazorby/strawchemy/commit/d28a11b8fa9b5f33a434644d30a0608c98239d1b)) - [@gazorby](https://github.com/gazorby)
#### ⚙️ Miscellaneous Tasks
- (**release**) bump to v0.12.2 - ([67b8bb1](https://github.com/gazorby/strawchemy/commit/67b8bb1ea1e66090f3c1407e82189a54877709d2)) - [@gazorby](https://github.com/gazorby)

#### 🤝️ Contributors
- [@gazorby](https://github.com/gazorby)

- - -

## [v0.12.1](https://github.com/gazorby/strawchemy/compare/v0.12.0..v0.12.1) - 2025-04-02
#### 🐛 Bug Fixes
- (**query-hook**) relationship loading would fail if triggered by a nested field - ([601086a](https://github.com/gazorby/strawchemy/commit/601086aa3a10b88f7cc24d0518641cc7bce9fdaa)) - [@gazorby](https://github.com/gazorby)
#### ⚙️ Miscellaneous Tasks
- (**release**) bump to v0.12.1 - ([3fba332](https://github.com/gazorby/strawchemy/commit/3fba3320097090572f150446d91c6fbe4b5e0633)) - [@gazorby](https://github.com/gazorby)

#### 🤝️ Contributors
- [@gazorby](https://github.com/gazorby)

- - -

## [v0.12.0](https://github.com/gazorby/strawchemy/compare/v0.11.0..v0.12.0) - 2025-04-01
#### 🚀 Features
- (**cud**) add create mutation - ([b1af031](https://github.com/gazorby/strawchemy/commit/b1af031f64e39ca7e9eef368bedcb6e6c3e5a898)) - [@gazorby](https://github.com/gazorby)
- (**cud**) add create mutation - ([d9ef914](https://github.com/gazorby/strawchemy/commit/d9ef914c60f9396951736c4502f576aa02d16eea)) - [@gazorby](https://github.com/gazorby)
- (**query-hook**) enable relationships loading - ([9100165](https://github.com/gazorby/strawchemy/commit/91001659cfb114df7b3ec6736c36b4b24008a1be)) - [@gazorby](https://github.com/gazorby)
#### 🐛 Bug Fixes
- (**cud**) mixed relations in create - ([7d140ed](https://github.com/gazorby/strawchemy/commit/7d140ed5bb59d829805bc92f5cf3da399fed3a36)) - [@gazorby](https://github.com/gazorby)
- (**mapping**) override type fields would not be retracked - ([98f3375](https://github.com/gazorby/strawchemy/commit/98f33756547fd9a5773e67ae3cdbb6b1d037182a)) - [@gazorby](https://github.com/gazorby)
- (**mapping**) do not enable aggregations on input types - ([24cd763](https://github.com/gazorby/strawchemy/commit/24cd763af01d02d6abcbd174d346f2c938955d51)) - [@gazorby](https://github.com/gazorby)
- (**resolver**) rely on sqlalchemy session type to use choose between sync/async resolver - ([92eabda](https://github.com/gazorby/strawchemy/commit/92eabdaf613e39787bfadb6361b11d11a3149120)) - [@gazorby](https://github.com/gazorby)
#### 🚜 Refactor
- (**doc**) fix typo in license - ([57cf88d](https://github.com/gazorby/strawchemy/commit/57cf88d1545589a13bff87952110a08b2a842d23)) - [@gazorby](https://github.com/gazorby)
- (**dto**) improve dto caching reliability - ([ffa2ab1](https://github.com/gazorby/strawchemy/commit/ffa2ab1dc4d0a18ba98bdd4ae316f6b09731f64e)) - [@gazorby](https://github.com/gazorby)
- (**dx**) add an example app - ([ed3e5d6](https://github.com/gazorby/strawchemy/commit/ed3e5d635f42c7ddcf7b6d2195c2ef1bad434e91)) - [@gazorby](https://github.com/gazorby)
- (**mapping**) add foreign key inputs for relation - ([fda6b60](https://github.com/gazorby/strawchemy/commit/fda6b60e879697d85d62a0c6a311bf5f75ac9ac7)) - [@gazorby](https://github.com/gazorby)
- (**transpiler**) remove unused function - ([1636803](https://github.com/gazorby/strawchemy/commit/1636803ae724753afde977a5e95eb0eaaa8edda8)) - [@gazorby](https://github.com/gazorby)
#### ⚙️ Miscellaneous Tasks
- (**gitignore**) ignore .sqlite files - ([49928b3](https://github.com/gazorby/strawchemy/commit/49928b395f7f57395e9a9f9f59493d8a5b4c94e7)) - [@gazorby](https://github.com/gazorby)
- (**release**) bump to v0.12.0 - ([66ff56b](https://github.com/gazorby/strawchemy/commit/66ff56b8a2fa8dd1948d069333fdeaa57f10d55c)) - [@gazorby](https://github.com/gazorby)
- (**renovate**) enable lock file maintenance - ([5ab6f8e](https://github.com/gazorby/strawchemy/commit/5ab6f8e1dad7da666c9b593b241282814f9240b9)) - [@gazorby](https://github.com/gazorby)

#### 🤝️ Contributors
- [@gazorby](https://github.com/gazorby)

- - -

## [v0.11.0](https://github.com/gazorby/strawchemy/compare/v0.10.0..v0.11.0) - 2025-03-25
#### 🚀 Features
- (**hook**) add QueryHookProtocol - ([afd406a](https://github.com/gazorby/strawchemy/commit/afd406a2463f511cf629e9a71ad218f1e9adbc4b)) - [@gazorby](https://github.com/gazorby)
- (**mapping**) allow setting filter/order_by at the type level - ([c1ead8c](https://github.com/gazorby/strawchemy/commit/c1ead8c89ff765ef299d611073be3d5e03c361fa)) - [@gazorby](https://github.com/gazorby)
#### 🐛 Bug Fixes
- (**hook**) hook would not be correctly applied if triggered by a type - ([0de25a0](https://github.com/gazorby/strawchemy/commit/0de25a058787d5e4d80af558e048a63f6ed71939)) - [@gazorby](https://github.com/gazorby)
- (**mapping**) type annotation override on a list field - ([6f56744](https://github.com/gazorby/strawchemy/commit/6f567441ba708feaa1854223c257de69e29eaf47)) - [@gazorby](https://github.com/gazorby)
- (**order-by**) order by on relation not working properly - ([acf1a8c](https://github.com/gazorby/strawchemy/commit/acf1a8cefd7513eeb2dec9450ae75608c8080a58)) - [@gazorby](https://github.com/gazorby)
#### 🚜 Refactor
- (**hook**) simplify query hook interface - ([5f84532](https://github.com/gazorby/strawchemy/commit/5f84532e630b84c8aa85a4b703bc5b6bf0ed5959)) - [@gazorby](https://github.com/gazorby)
- (**typing**) remove unused type - ([f242ce5](https://github.com/gazorby/strawchemy/commit/f242ce5d1b1a87eaff604bde3e0f20fede939620)) - [@gazorby](https://github.com/gazorby)
#### ⚙️ Miscellaneous Tasks
- (**coverage**) append the coverage session name as file extension - ([7046c63](https://github.com/gazorby/strawchemy/commit/7046c634cfc2ea8a2af7005b2ff9088690196609)) - [@gazorby](https://github.com/gazorby)
- (**coverage**) remove .xml extension in coverage filenames - ([a4c1fda](https://github.com/gazorby/strawchemy/commit/a4c1fda35faf83d9d6cb123245547e133b3652aa)) - [@gazorby](https://github.com/gazorby)
- (**coverage**) let leading dot in coverage data filenames - ([ddf8de9](https://github.com/gazorby/strawchemy/commit/ddf8de9005102f7b1a7ea1cdc52bd16e8f2c6e1e)) - [@gazorby](https://github.com/gazorby)
- (**coverage**) checkout the repository before processing files - ([d2dad3d](https://github.com/gazorby/strawchemy/commit/d2dad3db1619e538c7a40f246116725b023980b6)) - [@gazorby](https://github.com/gazorby)
- (**coverage**) use default coverage data when running tests - ([4773d23](https://github.com/gazorby/strawchemy/commit/4773d234caeb26ef6be64677b85e6968d5e646e9)) - [@gazorby](https://github.com/gazorby)
- (**coverage**) use merge-multiple - ([dfa12d6](https://github.com/gazorby/strawchemy/commit/dfa12d65f6e440927a4d36d81ca2bfe06b0baf9c)) - [@gazorby](https://github.com/gazorby)
- (**coverage**) use coverage combine - ([05b772d](https://github.com/gazorby/strawchemy/commit/05b772d873059391f5026ba9e3ff969818665805)) - [@gazorby](https://github.com/gazorby)
- (**release**) bump to v0.11.0 - ([bd27b8e](https://github.com/gazorby/strawchemy/commit/bd27b8e8a8545557879a7de22f9b5483cd751fb6)) - [@gazorby](https://github.com/gazorby)

#### 🤝️ Contributors
- [@gazorby](https://github.com/gazorby)

- - -

## [v0.10.0](https://github.com/gazorby/strawchemy/compare/v0.9.0..v0.10.0) - 2025-03-21
#### 🐛 Bug Fixes
- ![BREAKING](https://img.shields.io/badge/BREAKING-red) (**query-hooks**) enforce column only attributs in QueryHook.load_columns - ([0cc4bb5](https://github.com/gazorby/strawchemy/commit/0cc4bb5a4b06e64f05bb7ce0fc8a9b23f7bb03f3)) - [@gazorby](https://github.com/gazorby)
#### ⚙️ Miscellaneous Tasks
- (**release**) bump to v0.10.0 - ([03609ab](https://github.com/gazorby/strawchemy/commit/03609ab04e241c33826eae0f91cb3db9d01df64b)) - [@gazorby](https://github.com/gazorby)
- (**release**) bump to v1.0.0 - ([ba914bc](https://github.com/gazorby/strawchemy/commit/ba914bc3a57d67d874a48fb47d604ecf2ed88365)) - [@gazorby](https://github.com/gazorby)

#### 🤝️ Contributors
- [@gazorby](https://github.com/gazorby)

- - -

## [v0.9.0](https://github.com/gazorby/strawchemy/compare/v0.8.0..v0.9.0) - 2025-03-21
#### 🚀 Features
- (**filters**) add insensitive regexp variants - ([27706d5](https://github.com/gazorby/strawchemy/commit/27706d5a9a26f909f2027145992e47d4a264f7f8)) - [@gazorby](https://github.com/gazorby)
- (**filters**) add order filters to string - ([d76c950](https://github.com/gazorby/strawchemy/commit/d76c9509e96cb2300e87bcc87d6aa23ad2215742)) - [@gazorby](https://github.com/gazorby)
- support postgres `Interval` type (mapping and filtering) - ([355994f](https://github.com/gazorby/strawchemy/commit/355994f6747d9b5aa6799708aa0e0063636e8019)) - [@gazorby](https://github.com/gazorby)
#### 🚜 Refactor
- (**graphql**) rename in_, nin_ filters to in, nin - ([d19b061](https://github.com/gazorby/strawchemy/commit/d19b061eb5e9af15affc29aed343adb57a58a39c)) - [@gazorby](https://github.com/gazorby)
#### 📚 Documentation
- (**readme**) update filters section - ([83f43d3](https://github.com/gazorby/strawchemy/commit/83f43d3bc20da1e5d5eeac7f794789e8e18e099a)) - [@gazorby](https://github.com/gazorby)
- (**readme**) add type override documentation - ([5d34539](https://github.com/gazorby/strawchemy/commit/5d34539f5f7078a7935deb47d652de78481adebd)) - [@gazorby](https://github.com/gazorby)
- (**readme**) update filter names - ([8e51154](https://github.com/gazorby/strawchemy/commit/8e51154172f678aeb2ddec39455607b7cfee88df)) - [@gazorby](https://github.com/gazorby)
- (**readme**) clarify supported filters - ([91a52b5](https://github.com/gazorby/strawchemy/commit/91a52b5cfd5218569cde02c54dae831ae843fdf0)) - [@gazorby](https://github.com/gazorby)
#### ⚙️ Miscellaneous Tasks
- (**release**) bump to v0.9.0 - ([36ac3b6](https://github.com/gazorby/strawchemy/commit/36ac3b6dee86a62a7d729619920b72f6046d67d8)) - [@gazorby](https://github.com/gazorby)

#### 🤝️ Contributors
- [@gazorby](https://github.com/gazorby)

- - -

## [v0.8.0](https://github.com/gazorby/strawchemy/compare/v0.6.0..v0.8.0) - 2025-03-20
#### 🚀 Features
- (**geo**) infer shapely types from geoalchemy columns - ([a8ed586](https://github.com/gazorby/strawchemy/commit/a8ed586be7475e24fe042910448cee3aa084ce6e)) - [@gazorby](https://github.com/gazorby)
- (**geo**) infer GeoJSON specific scalars to be inferred from shapely geometries - ([145f495](https://github.com/gazorby/strawchemy/commit/145f495ddfa8e9745e30d71fd2275cbffa3365d9)) - [@gazorby](https://github.com/gazorby)
#### ⚙️ Miscellaneous Tasks
- (**release**) bump to v0.8.0 - ([98c32c0](https://github.com/gazorby/strawchemy/commit/98c32c0bff6773ca87f9580fa4c406bd1738a3ab)) - [@gazorby](https://github.com/gazorby)
- (**release**) bump to v0.7.0 - ([65cb766](https://github.com/gazorby/strawchemy/commit/65cb766047bf80f024650f6be66cc4c2255cf44e)) - [@gazorby](https://github.com/gazorby)

#### 🤝️ Contributors
- [@gazorby](https://github.com/gazorby)

- - -

## [v0.6.0](https://github.com/gazorby/strawchemy/compare/v0.5.3..v0.6.0) - 2025-03-19
#### 🚀 Features
- (**geo**) add GeoJSON scalar variants - ([d197b8d](https://github.com/gazorby/strawchemy/commit/d197b8d5b99cd9102e1c92900c148a024c9d65e5)) - [@gazorby](https://github.com/gazorby)
#### ⚙️ Miscellaneous Tasks
- (**release**) bump to v0.6.0 - ([69d4582](https://github.com/gazorby/strawchemy/commit/69d45829f07ade93d69d8be7958178fde216818e)) - [@gazorby](https://github.com/gazorby)

#### 🤝️ Contributors
- [@gazorby](https://github.com/gazorby)

- - -

## [v0.5.3](https://github.com/gazorby/strawchemy/compare/v0.5.2..v0.5.3) - 2025-03-19
#### 🐛 Bug Fixes
- (**aggregations**) use float for aggregation output of int columns - ([bef9700](https://github.com/gazorby/strawchemy/commit/bef970043c1096fa677bf276c20e0a4618e85bb7)) - [@gazorby](https://github.com/gazorby)
- (**strawberry-type**) model instance passed on types not declaring it - ([06c1c1f](https://github.com/gazorby/strawchemy/commit/06c1c1f7eefaa2c5e1fe2f03f7ef3e854dafe7ea)) - [@gazorby](https://github.com/gazorby)
- (**transpiler**) adding an aggregation column to an existing lateral join would not be properly aliased, leading to a cartesian product on the same table - ([f365120](https://github.com/gazorby/strawchemy/commit/f365120ba9f5c110de9417b725ca32de4ce07d69)) - [@gazorby](https://github.com/gazorby)
- import errors when geo extras is not installed - ([f28f2ea](https://github.com/gazorby/strawchemy/commit/f28f2eaee54b2658cdc294d0cdce6325f54e69c6)) - [@gazorby](https://github.com/gazorby)
#### 🚜 Refactor
- remove the default strawchemy instance - ([b766374](https://github.com/gazorby/strawchemy/commit/b7663745ab49f6415ccc1277421559945f7fcfb0)) - [@gazorby](https://github.com/gazorby)
- remove unused stuff - ([9bd2d1b](https://github.com/gazorby/strawchemy/commit/9bd2d1b0b0738aac5e4dfb4db52a343a72ae363a)) - [@gazorby](https://github.com/gazorby)
#### 📚 Documentation
- (**readme**) make code examples expandable - ([4da85a1](https://github.com/gazorby/strawchemy/commit/4da85a119dcc03a92ce24ad8ebbf4c6791784e6b)) - [@gazorby](https://github.com/gazorby)
- (**readme**) update repository doc - ([d930468](https://github.com/gazorby/strawchemy/commit/d930468ddbe47980ec9cc9de4f8a6524f7b83a88)) - [@gazorby](https://github.com/gazorby)
- update README.md - ([8a53b62](https://github.com/gazorby/strawchemy/commit/8a53b62e8f4cf22709b1ee3292e942774492e052)) - [@gazorby](https://github.com/gazorby)
- update README.md - ([4e5564b](https://github.com/gazorby/strawchemy/commit/4e5564bbc10305cdca8123e5fc059d9ec9fce8a9)) - [@gazorby](https://github.com/gazorby)
#### ⚙️ Miscellaneous Tasks
- (**coverage**) explicitly set source in [tool.coverage.run] as codecov might need it - ([5200d8c](https://github.com/gazorby/strawchemy/commit/5200d8c9e1274daf44cef85707017845930dfda4)) - [@gazorby](https://github.com/gazorby)
- (**deps**) enforce sqlalchemy >= 1.4 - ([6772605](https://github.com/gazorby/strawchemy/commit/677260591bdc3be483b8759526774c5be96570d2)) - [@gazorby](https://github.com/gazorby)
- (**deps**) move shapely to dev dependencies - ([11c393d](https://github.com/gazorby/strawchemy/commit/11c393d056552c9847f62340dbc203dbb4955394)) - [@gazorby](https://github.com/gazorby)
- (**mise**) make the ruff:check depends on _install - ([b863708](https://github.com/gazorby/strawchemy/commit/b863708dbd1a5b59d8f8f1d258306c733721f98b)) - [@gazorby](https://github.com/gazorby)
- (**mise**) upgrade - ([4afd3c8](https://github.com/gazorby/strawchemy/commit/4afd3c86af6f0694a9b1d5b116bbf95ab05ded2f)) - [@gazorby](https://github.com/gazorby)
- (**pyproject**) update classifiers - ([59aa01b](https://github.com/gazorby/strawchemy/commit/59aa01b5b7531a0bf340756de465b9164d0bf9dd)) - [@gazorby](https://github.com/gazorby)
- (**pyproject**) remove multiprocessing from coverage config - ([b8cfe46](https://github.com/gazorby/strawchemy/commit/b8cfe46a0f51f32269ea5a969855235f2f94408c)) - [@gazorby](https://github.com/gazorby)
- (**pyproject**) fix syntax - ([8cd111b](https://github.com/gazorby/strawchemy/commit/8cd111b468caa314d6597e40e5d91a28d435ca9b)) - [@gazorby](https://github.com/gazorby)
- (**release**) bump to v0.5.3 - ([dcb17d7](https://github.com/gazorby/strawchemy/commit/dcb17d7fa9ce83c40c6e3d92e9aa87abcca96dc1)) - [@gazorby](https://github.com/gazorby)

#### 🤝️ Contributors
- [@gazorby](https://github.com/gazorby)

- - -

## [v0.5.2](https://github.com/gazorby/strawchemy/compare/v0.5.1..v0.5.2) - 2025-03-12
#### 🐛 Bug Fixes
- (**pagination**) do not apply offset on the root query when a subquery is present - ([e91da34](https://github.com/gazorby/strawchemy/commit/e91da345507aefb9c8c39a64f39badf4df7c37a7)) - [@gazorby](https://github.com/gazorby)
#### ⚙️ Miscellaneous Tasks
- (**codecov**) fix typo in codecov.yml - ([acfe955](https://github.com/gazorby/strawchemy/commit/acfe9552641eb30c0c51a1e5340088b688df9837)) - [@gazorby](https://github.com/gazorby)
- (**codecov**) merge python version and session name in a single flag - ([0d9f34f](https://github.com/gazorby/strawchemy/commit/0d9f34f8c6b5789305612a0a420f3facfba94924)) - [@gazorby](https://github.com/gazorby)
- (**codecov**) add flags - ([d22a49d](https://github.com/gazorby/strawchemy/commit/d22a49d2954317fac925da6a3d2dc50d7915794c)) - [@gazorby](https://github.com/gazorby)
- (**codecov**) let the action find junit files - ([9848ab2](https://github.com/gazorby/strawchemy/commit/9848ab29986a4e6cd3a78dc5aa46d93570a7c43c)) - [@gazorby](https://github.com/gazorby)
- (**release**) bump to v0.5.2 - ([76d446c](https://github.com/gazorby/strawchemy/commit/76d446c42960e2755733ab70cd0ffc93e5102dc6)) - [@gazorby](https://github.com/gazorby)
- (**test**) set the pytest junit_family to legacy - ([4d5b3d5](https://github.com/gazorby/strawchemy/commit/4d5b3d57bd904ec6897f50335bddef1284de26c8)) - [@gazorby](https://github.com/gazorby)
- add codecov.yml - ([2f77c09](https://github.com/gazorby/strawchemy/commit/2f77c0960116f8f46253c30fdeb6d8d0ed23195e)) - [@gazorby](https://github.com/gazorby)

#### 🤝️ Contributors
- [@gazorby](https://github.com/gazorby)

- - -

## [v0.5.1](https://github.com/gazorby/strawchemy/compare/v0.5.0..v0.5.1) - 2025-03-11
#### 🐛 Bug Fixes
- (**mapping**) field arguments not replaced by override types - ([bf44803](https://github.com/gazorby/strawchemy/commit/bf44803ab5f41502ee24b18cd484ec9f87da4c62)) - [@gazorby](https://github.com/gazorby)
- (**mapping**) dto edge cases - ([fd417a2](https://github.com/gazorby/strawchemy/commit/fd417a21e854dcc9596d3aa8fdb704eebb1e2711)) - [@gazorby](https://github.com/gazorby)
- (**transpiler**) update - ([a786a5f](https://github.com/gazorby/strawchemy/commit/a786a5fa7ada02d5f87eaaa9e82152bbcec6ab23)) - [@gazorby](https://github.com/gazorby)
- (**transpiler**) add id columns in node selection if not present - ([5b06a8d](https://github.com/gazorby/strawchemy/commit/5b06a8d40cf3086fac16e17fb4f9cb85e6cc0bfc)) - [@gazorby](https://github.com/gazorby)
- (**transpiler**) root aggregations not handled when using subquery - ([495420f](https://github.com/gazorby/strawchemy/commit/495420f024308e20e5e03e6d89d73ebf7db52332)) - [@gazorby](https://github.com/gazorby)
- (**transpiler**) properly handle root aggregations - ([bacd111](https://github.com/gazorby/strawchemy/commit/bacd111c553ef8ed8b810d272ff7827f5ff6f26a)) - [@gazorby](https://github.com/gazorby)
- (**transpiler**) remove caching property on resolved tree - ([6b11dcc](https://github.com/gazorby/strawchemy/commit/6b11dccab751a1e390adb6dc612c16c0321756ff)) - [@gazorby](https://github.com/gazorby)
- (**typing**) session_getter - ([af2edaa](https://github.com/gazorby/strawchemy/commit/af2edaa02d50d93879b1137068d60f3e97d08e9b)) - [@gazorby](https://github.com/gazorby)
- update - ([c334738](https://github.com/gazorby/strawchemy/commit/c33473829fa8976f31242828e7294543ef738044)) - [@gazorby](https://github.com/gazorby)
#### 🚜 Refactor
- (**dx**) update .editorconfig - ([89c9ac2](https://github.com/gazorby/strawchemy/commit/89c9ac202218e5d06e3da956ba7b91e7844219fb)) - [@gazorby](https://github.com/gazorby)
- (**transpiler**) minor changes - ([dafa2f5](https://github.com/gazorby/strawchemy/commit/dafa2f5549c1a4f81eaff9cd71bdb57aca24c85b)) - [@gazorby](https://github.com/gazorby)
#### 📚 Documentation
- (**contributing**) add tasks.md reference - ([c75b043](https://github.com/gazorby/strawchemy/commit/c75b043625a0c30f33a358d63d7bd1edc4d22be6)) - [@gazorby](https://github.com/gazorby)
- update CONTRIBUTING.md - ([447e529](https://github.com/gazorby/strawchemy/commit/447e5295c4b6d434669f5aabe5e17825d231f6a9)) - [@gazorby](https://github.com/gazorby)
#### ⚙️ Miscellaneous Tasks
- (**ci**) fix typo - ([0269a3e](https://github.com/gazorby/strawchemy/commit/0269a3ef089086148b95b449380dd128ff988e4c)) - [@gazorby](https://github.com/gazorby)
- (**ci**) fix session param in nox call - ([b273b54](https://github.com/gazorby/strawchemy/commit/b273b54c7a379a5ce9ab10a87faed6f88a7e6d2f)) - [@gazorby](https://github.com/gazorby)
- (**ci**) fix missing arg to test-ci task - ([37aba9c](https://github.com/gazorby/strawchemy/commit/37aba9c6e7f3c3153a1f0c4eb5e5c5a5a477d2e9)) - [@gazorby](https://github.com/gazorby)
- (**ci**) run tests using mise task - ([7902dd9](https://github.com/gazorby/strawchemy/commit/7902dd955cc43ee7b2951d4c4520009385e9c706)) - [@gazorby](https://github.com/gazorby)
- (**ci**) add mise.toml to paths whitelist in skip check job - ([3d23d82](https://github.com/gazorby/strawchemy/commit/3d23d82b21d698d2103817b1d1b89997fa56aa07)) - [@gazorby](https://github.com/gazorby)
- (**ci**) only fail workflow on cancellation/failure of test/lint jobs - ([c67b0d5](https://github.com/gazorby/strawchemy/commit/c67b0d53caa93137791a106b0bb0c2ad08f515ed)) - [@gazorby](https://github.com/gazorby)
- (**lint**) use mise - ([4e03e64](https://github.com/gazorby/strawchemy/commit/4e03e648087c05c7b8424ab3e196714b539ef4e2)) - [@gazorby](https://github.com/gazorby)
- (**mise**) remove actionlint in lint task - ([992aeec](https://github.com/gazorby/strawchemy/commit/992aeec15674324cdbd66ab13a61621105dea1af)) - [@gazorby](https://github.com/gazorby)
- (**mise**) streamline task names - ([dbf4357](https://github.com/gazorby/strawchemy/commit/dbf4357a0b17999e1586e6d88c5629d8ec20ca1b)) - [@gazorby](https://github.com/gazorby)
- (**mise**) add mise.lock - ([135fe82](https://github.com/gazorby/strawchemy/commit/135fe82fe2ac1fb3300a0cc61d9f7fc6e028dc23)) - [@gazorby](https://github.com/gazorby)
- (**mise**) add clean task - ([321ac42](https://github.com/gazorby/strawchemy/commit/321ac4292e8f4b89092d7b1d140494a1e4fa3283)) - [@gazorby](https://github.com/gazorby)
- (**mise**) add a task to run pre-commit checks - ([2b1b787](https://github.com/gazorby/strawchemy/commit/2b1b787e1a438c307d616a966fff1685eaa43ecd)) - [@gazorby](https://github.com/gazorby)
- (**pre-commit**) add a hook to render tasks documentation - ([b067a84](https://github.com/gazorby/strawchemy/commit/b067a846d048ffbbb865740a04f178f58fa9d2e8)) - [@gazorby](https://github.com/gazorby)
- (**pre-commit**) add actionlint hook - ([b75a842](https://github.com/gazorby/strawchemy/commit/b75a842863581c874e18465a3c820f5f1e7453d7)) - [@gazorby](https://github.com/gazorby)
- (**pre-commit**) run pre-commit lint check in mise task - ([6c7b017](https://github.com/gazorby/strawchemy/commit/6c7b0170259d650b426039b4336f25db0f7fb446)) - [@gazorby](https://github.com/gazorby)
- (**release**) bump to v0.5.1 - ([d1b30ca](https://github.com/gazorby/strawchemy/commit/d1b30cae2022e51b74aa91f5742fe1f25049c252)) - [@gazorby](https://github.com/gazorby)
- (**test**) call mise task to generate test matrix - ([43a0308](https://github.com/gazorby/strawchemy/commit/43a0308697661080c2b30758ec40eef178ac9f49)) - [@gazorby](https://github.com/gazorby)

#### 🤝️ Contributors
- [@gazorby](https://github.com/gazorby)

- - -

## [v0.5.0](https://github.com/gazorby/strawchemy/compare/v0.4.0..v0.5.0) - 2025-03-03
#### 🚀 Features
- (**mapping**) add pagination setting on config level - ([5e84f4b](https://github.com/gazorby/strawchemy/commit/5e84f4bca54dbf7eab083dc74a5c37a9171c1818)) - [@gazorby](https://github.com/gazorby)
#### ⚙️ Miscellaneous Tasks
- (**release**) bump to v0.5.0 - ([e15f7c7](https://github.com/gazorby/strawchemy/commit/e15f7c758b3980696cc75e80b5195afaeaf19292)) - [@gazorby](https://github.com/gazorby)

#### 🤝️ Contributors
- [@gazorby](https://github.com/gazorby)

- - -

## [v0.4.0](https://github.com/gazorby/strawchemy/compare/v0.3.0..v0.4.0) - 2025-03-03
#### 🚀 Features
- (**config**) enable custom id field name - ([8f05899](https://github.com/gazorby/strawchemy/commit/8f0589949238a021d8f967149e5a5d14f0a7199a)) - [@gazorby](https://github.com/gazorby)
- (**config**) add default pagination limit setting - ([808670c](https://github.com/gazorby/strawchemy/commit/808670ccdc7540c6830fd3e3ba13e86c6455079a)) - [@gazorby](https://github.com/gazorby)
- (**dto**) add READ_ONLY, WRITE_ONLY and PRIVATE shortcuts - ([5da8660](https://github.com/gazorby/strawchemy/commit/5da86608de2a5336ccfb3a5a9eba85769872dd6a)) - [@gazorby](https://github.com/gazorby)
- (**dto-config**) add method to infer include/exclude from base class - ([0ddb6bd](https://github.com/gazorby/strawchemy/commit/0ddb6bd2f8f7e577d54c4529d242bafb6ad2ba8d)) - [@gazorby](https://github.com/gazorby)
- (**mapping**) enable custom defaults for child pagination - ([ed00372](https://github.com/gazorby/strawchemy/commit/ed00372d49f9b0d8b45fe62802a52e3446fd2352)) - [@gazorby](https://github.com/gazorby)
- add pagination switch and defaults - ([c111cc5](https://github.com/gazorby/strawchemy/commit/c111cc58279229c1f47f73af593945b8f5451723)) - [@gazorby](https://github.com/gazorby)
#### 🐛 Bug Fixes
- (**dto**) partial default value on several places - ([d3d18e8](https://github.com/gazorby/strawchemy/commit/d3d18e85d079e813fdeea29f1d0cf1ecff40fb05)) - [@gazorby](https://github.com/gazorby)
- (**dto-factory**) caching fixes - ([4c1d345](https://github.com/gazorby/strawchemy/commit/4c1d34533eb09aef7ec2a471a7f3c9e969e27c1e)) - [@gazorby](https://github.com/gazorby)
- (**root-aggregations**) set count as optional - ([0bada8b](https://github.com/gazorby/strawchemy/commit/0bada8b7028d236755da78527cf33d4b47c0aa96)) - [@gazorby](https://github.com/gazorby)
- (**root-aggregations**) ensure aggregations are optional - ([a9be792](https://github.com/gazorby/strawchemy/commit/a9be7927ca5cef8c23e0b9e47c659139906f3e67)) - [@gazorby](https://github.com/gazorby)
- (**sqlalchemy-inspector**) mapped classes map not updated - ([6667447](https://github.com/gazorby/strawchemy/commit/66674477a8c222aa40ff38e400149983b72b3026)) - [@gazorby](https://github.com/gazorby)
- (**strawchemy-field**) python name for filter input - ([73cca8b](https://github.com/gazorby/strawchemy/commit/73cca8bba6197a2325a1530bf2363e132b009f6b)) - [@gazorby](https://github.com/gazorby)
- forgot some partial default updates - ([4df92dd](https://github.com/gazorby/strawchemy/commit/4df92dd621ca6cc0b84d9ef3da4271267cc452b3)) - [@gazorby](https://github.com/gazorby)
#### 🚜 Refactor
- (**dto**) streamline arguments of factory decorator method - ([33557b1](https://github.com/gazorby/strawchemy/commit/33557b1abf5a014a8948cc11ce93412c95580be4)) - [@gazorby](https://github.com/gazorby)
- (**dto**) add shortcut utilities - ([a3b3a53](https://github.com/gazorby/strawchemy/commit/a3b3a53ffb201df8dbba250b0440daaed460db79)) - [@gazorby](https://github.com/gazorby)
- (**dto**) expose factory instance in pydantic_sqlalchemy.py - ([d4b1793](https://github.com/gazorby/strawchemy/commit/d4b1793bd71ad7abee3d35619508953e1efc355e)) - [@gazorby](https://github.com/gazorby)
- (**mapping**) child options - ([e2277ab](https://github.com/gazorby/strawchemy/commit/e2277ab742041429181be152ffca9f3f20337cea)) - [@gazorby](https://github.com/gazorby)
- (**pre-commit**) update config - ([a08c121](https://github.com/gazorby/strawchemy/commit/a08c1216fa065bad1959998d5fdfd433e9e37d00)) - [@gazorby](https://github.com/gazorby)
- wip - ([9817a95](https://github.com/gazorby/strawchemy/commit/9817a9574e05cadea46f5bcf1f1ff8d075579758)) - [@gazorby](https://github.com/gazorby)
#### ⚙️ Miscellaneous Tasks
- (**lint**) execute lint sessions on a single default python version - ([60ac239](https://github.com/gazorby/strawchemy/commit/60ac239cb5d59c683f1a03ec240b6a83ba61503f)) - [@gazorby](https://github.com/gazorby)
- (**lint**) add sourcery config - ([0ee4bde](https://github.com/gazorby/strawchemy/commit/0ee4bde598781611c9cae9aa135ce3197bd1e76b)) - [@gazorby](https://github.com/gazorby)
- (**mise**) add auto-bump task - ([545f3c4](https://github.com/gazorby/strawchemy/commit/545f3c434138413b873ec8c3224fc71fcc4d98dc)) - [@gazorby](https://github.com/gazorby)
- (**release**) bump to v0.4.0 - ([ebdbd58](https://github.com/gazorby/strawchemy/commit/ebdbd5877c78642bdaa11786d19eaf30fb41431a)) - [@gazorby](https://github.com/gazorby)
- (**test**) fix array membership test - ([25e5672](https://github.com/gazorby/strawchemy/commit/25e567299d5dfdcda2e9cc97087d4c104fa4e0de)) - [@gazorby](https://github.com/gazorby)
- (**tests**) upload coverage artifacts - ([bc72252](https://github.com/gazorby/strawchemy/commit/bc72252c1453a015f60f70d7facf57fd3fc7c3d6)) - [@gazorby](https://github.com/gazorby)

#### 🤝️ Contributors
- [@gazorby](https://github.com/gazorby)

- - -

## [v0.3.0](https://github.com/gazorby/strawchemy/compare/v0.2.12..v0.3.0) - 2025-02-21
#### 🚀 Features
- (**mapping**) allow strawchemy types to override existing ones - ([c26b495](https://github.com/gazorby/strawchemy/commit/c26b495143049b427311bd76b35af220a159aa1f)) - [@gazorby](https://github.com/gazorby)
#### 📚 Documentation
- update bug_report issue template - ([e213df1](https://github.com/gazorby/strawchemy/commit/e213df15832595a8c8695bb4312ad990c8a6571e)) - [@gazorby](https://github.com/gazorby)
- add SECURITY.md - ([628cd29](https://github.com/gazorby/strawchemy/commit/628cd297e886af7c0e36ef85f3148d771f150633)) - [@gazorby](https://github.com/gazorby)
- add pull request template - ([efcb329](https://github.com/gazorby/strawchemy/commit/efcb329efa66dc89a30fc263e24389515d356e17)) - [@gazorby](https://github.com/gazorby)
- update CONTRIBUTING.md - ([d22f786](https://github.com/gazorby/strawchemy/commit/d22f78617632cf003774b208d019150fd7bf9fd3)) - [@gazorby](https://github.com/gazorby)
#### ⚙️ Miscellaneous Tasks
- (**release**) bump to v0.3.0 - ([6075f54](https://github.com/gazorby/strawchemy/commit/6075f5487462b5fe0595638757a405e758513db5)) - [@gazorby](https://github.com/gazorby)
- add issue/pr templates - ([dc99896](https://github.com/gazorby/strawchemy/commit/dc99896724f1deda7a64768743b6e890c3907d91)) - [@gazorby](https://github.com/gazorby)
- create dependabot.yml - ([14d2026](https://github.com/gazorby/strawchemy/commit/14d20260c12de5a63d8a72404fe113c3e9e3e78b)) - [@gazorby](https://github.com/gazorby)

#### 🤝️ Contributors
- [@gazorby](https://github.com/gazorby)

- - -

## [v0.2.12](https://github.com/gazorby/strawchemy/compare/v0.2.11..v0.2.12) - 2025-02-21
#### ⚙️ Miscellaneous Tasks
- (**release**) bump to v0.2.12 - ([eb32d94](https://github.com/gazorby/strawchemy/commit/eb32d94a6dc85f020a23276a1a963a19a5ccab1a)) - [@gazorby](https://github.com/gazorby)
- create separate environment for cd and publish - ([fbcdf34](https://github.com/gazorby/strawchemy/commit/fbcdf3486fb4643c19153ffac7eb6a600a91f938)) - [@gazorby](https://github.com/gazorby)

#### 🤝️ Contributors
- [@gazorby](https://github.com/gazorby)

- - -

## [v0.2.11](https://github.com/gazorby/strawchemy/compare/v0.2.10..v0.2.11) - 2025-02-21
#### ⚙️ Miscellaneous Tasks
- (**changelog**) fix incorrect release changelog - ([1a8bf11](https://github.com/gazorby/strawchemy/commit/1a8bf11c5bd883749079128be5614fbdd5a1ab32)) - [@gazorby](https://github.com/gazorby)
- (**release**) bump to v0.2.11 - ([4fb6265](https://github.com/gazorby/strawchemy/commit/4fb62651717558632637ff7521fe315d760fffb4)) - [@gazorby](https://github.com/gazorby)
- pass GITHUB_TOKEN to git cliff calls - ([cc21aae](https://github.com/gazorby/strawchemy/commit/cc21aae930467c06e1c2d6e1d21274bb2165e3f5)) - [@gazorby](https://github.com/gazorby)

#### 🤝️ Contributors
- [@gazorby](https://github.com/gazorby)

- - -

## [v0.2.10](https://github.com/gazorby/strawchemy/compare/v0.2.9..v0.2.10) - 2025-02-21
#### ⚙️ Miscellaneous Tasks
- (**release**) bump to v0.2.10 - ([5fb6215](https://github.com/gazorby/strawchemy/commit/5fb621522c20594291a1ff2340e1b170090d21ba)) - [@gazorby](https://github.com/gazorby)
- tweak changelog generation - ([68c6680](https://github.com/gazorby/strawchemy/commit/68c6680fa3db8ffeb52b95680ff3d1e9a6cdcbce)) - [@gazorby](https://github.com/gazorby)

#### 🤝️ Contributors
- [@gazorby](https://github.com/gazorby)

- - -

## [v0.2.9](https://github.com/gazorby/strawchemy/compare/v0.2.8..v0.2.9) - 2025-02-21
#### ⚙️ Miscellaneous Tasks
- (**publish**) add missing `contents: write` permission - ([4f881d7](https://github.com/gazorby/strawchemy/commit/4f881d78a0dfb2574ad244c746f7d7d9255ae12a)) - [@gazorby](https://github.com/gazorby)
- (**release**) bump to v0.2.9 - ([5e8b5c4](https://github.com/gazorby/strawchemy/commit/5e8b5c4aad50332b89f9594d9f772935c81d137a)) - [@gazorby](https://github.com/gazorby)

#### 🤝️ Contributors
- [@gazorby](https://github.com/gazorby)

- - -

## [v0.2.8](https://github.com/gazorby/strawchemy/compare/v0.2.7..v0.2.8) - 2025-02-21
#### ⚙️ Miscellaneous Tasks
- (**cd**) use the pat to create gh release - ([c603955](https://github.com/gazorby/strawchemy/commit/c603955af5446e89c7de42b6f1705b61553f12cf)) - [@gazorby](https://github.com/gazorby)
- (**release**) bump to v0.2.8 - ([97d2413](https://github.com/gazorby/strawchemy/commit/97d24130c168dbd2f05d173066ce27d7c11416e3)) - [@gazorby](https://github.com/gazorby)

#### 🤝️ Contributors
- [@gazorby](https://github.com/gazorby)

- - -

## [v0.2.7](https://github.com/gazorby/strawchemy/compare/v0.2.6..v0.2.7) - 2025-02-21
#### ⚙️ Miscellaneous Tasks
- (**ci**) fix test matrix not generated on tag - ([ae4720d](https://github.com/gazorby/strawchemy/commit/ae4720dd3aa812c1adf067fedb8c26de3286eb11)) - [@gazorby](https://github.com/gazorby)
- (**release**) bump to v0.2.7 - ([be76cf2](https://github.com/gazorby/strawchemy/commit/be76cf262b0bef07a09a0ae0bc299a8f7c8f04de)) - [@gazorby](https://github.com/gazorby)

#### 🤝️ Contributors
- [@gazorby](https://github.com/gazorby)

- - -

## [v0.2.6](https://github.com/gazorby/strawchemy/compare/v0.2.5..v0.2.6) - 2025-02-21
#### ⚙️ Miscellaneous Tasks
- (**ci**) always run ci on tag - ([ffd23ff](https://github.com/gazorby/strawchemy/commit/ffd23fff86ed5d832f590ba5dd64f91202c547c1)) - [@gazorby](https://github.com/gazorby)
- (**release**) bump to v0.2.6 - ([5174967](https://github.com/gazorby/strawchemy/commit/517496725a74985bffcb59f7030a84dec637ea63)) - [@gazorby](https://github.com/gazorby)

#### 🤝️ Contributors
- [@gazorby](https://github.com/gazorby)

- - -

## [v0.2.5](https://github.com/gazorby/strawchemy/compare/v0.2.4..v0.2.5) - 2025-02-21
#### ⚙️ Miscellaneous Tasks
- (**ci**) also run result job if needed step have been skipped - ([474bad3](https://github.com/gazorby/strawchemy/commit/474bad3ba96c8c4d16cec6f0463ea29ba5391406)) - [@gazorby](https://github.com/gazorby)
- (**release**) bump to v0.2.5 - ([0b5cc28](https://github.com/gazorby/strawchemy/commit/0b5cc2855463724269a9365d5a0e88dcb90984da)) - [@gazorby](https://github.com/gazorby)

#### 🤝️ Contributors
- [@gazorby](https://github.com/gazorby)

- - -

## [v0.2.4](https://github.com/gazorby/strawchemy/compare/v0.2.3..v0.2.4) - 2025-02-21
#### ⚙️ Miscellaneous Tasks
- (**ci**) run result job on tag - ([e93941a](https://github.com/gazorby/strawchemy/commit/e93941a47ce4607d6757f072a60aa43095a4bd6e)) - [@gazorby](https://github.com/gazorby)
- (**release**) bump to v0.2.4 - ([d8a4981](https://github.com/gazorby/strawchemy/commit/d8a4981ee1f91a325b6bf669e36232a2e1b6a7dc)) - [@gazorby](https://github.com/gazorby)

#### 🤝️ Contributors
- [@gazorby](https://github.com/gazorby)

- - -

## [v0.2.3](https://github.com/gazorby/strawchemy/compare/v0.2.2..v0.2.3) - 2025-02-21
#### ⚙️ Miscellaneous Tasks
- (**bump**) use personal access toekn to enable ci workflow - ([35f190b](https://github.com/gazorby/strawchemy/commit/35f190b22d113cd9a0d471beea2f62c5bb7f8724)) - [@gazorby](https://github.com/gazorby)
- (**release**) bump to v0.2.3 - ([c98e0cd](https://github.com/gazorby/strawchemy/commit/c98e0cdc9f62b49704c1b29829640bf79c3d5932)) - [@gazorby](https://github.com/gazorby)

#### 🤝️ Contributors
- [@gazorby](https://github.com/gazorby)

- - -

## [v0.2.2](https://github.com/gazorby/strawchemy/compare/v0.2.1..v0.2.2) - 2025-02-21
#### ⚙️ Miscellaneous Tasks
- (**bump**) fix GITHUB_TOKEN env var - ([cc43668](https://github.com/gazorby/strawchemy/commit/cc436682becb95e340026244f377f384177c5c67)) - [@gazorby](https://github.com/gazorby)
- (**bump**) add write permissions - ([6ebae7c](https://github.com/gazorby/strawchemy/commit/6ebae7c0d2f90eafca0a13f985fb83bab31f7b4e)) - [@gazorby](https://github.com/gazorby)
- (**bump**) use kenji-miyake/setup-git-cliff action - ([93c3a9c](https://github.com/gazorby/strawchemy/commit/93c3a9c48449a2077deffdb1b9668de3fdde96f4)) - [@gazorby](https://github.com/gazorby)
- (**bump**) fix --bumped-version flag - ([edfe14e](https://github.com/gazorby/strawchemy/commit/edfe14e378cf858b23545e4e6378c554bddc9541)) - [@gazorby](https://github.com/gazorby)
- (**bump**) add missing --bump-version flag - ([842e831](https://github.com/gazorby/strawchemy/commit/842e831cc99d7653069804d5233488d855ae5306)) - [@gazorby](https://github.com/gazorby)
- (**bump**) fix auto bump - ([7251e12](https://github.com/gazorby/strawchemy/commit/7251e12c1ce42724a314556586a41d00baf35f86)) - [@gazorby](https://github.com/gazorby)
- (**release**) bump to v0.2.2 - ([a8ee5b6](https://github.com/gazorby/strawchemy/commit/a8ee5b62bd3c144e2ea865dede6b85647207bede)) - [@gazorby](https://github.com/gazorby)
- pretty workflow names - ([5b467ab](https://github.com/gazorby/strawchemy/commit/5b467abf9ae38577b9cf8196f25716e0098d0ed7)) - [@gazorby](https://github.com/gazorby)
- add bump and publish workflows - ([e8ab0c8](https://github.com/gazorby/strawchemy/commit/e8ab0c817107f44b499b09e079f95f742c7e0797)) - [@gazorby](https://github.com/gazorby)

#### 🤝️ Contributors
- [@gazorby](https://github.com/gazorby)

- - -

## [v0.2.1](https://github.com/gazorby/strawchemy/compare/v0.2.0..v0.2.1) - 2025-02-20
#### ⚙️ Miscellaneous Tasks
- (**release**) bump to v0.2.1 - ([5e59c22](https://github.com/gazorby/strawchemy/commit/5e59c221011c1f0414b29024a0e60471076225a7)) - [@gazorby](https://github.com/gazorby)
- add publish workflow; auto commit CHANGELOG.md when generating changelog - ([6fdd13b](https://github.com/gazorby/strawchemy/commit/6fdd13b2c8b191116814de9e8036ceba4b1b8477)) - [@gazorby](https://github.com/gazorby)
- add codeql workflow - ([758dcc0](https://github.com/gazorby/strawchemy/commit/758dcc081a2efa8ddba6e30769ff1a1b85d28c3e)) - [@gazorby](https://github.com/gazorby)

#### 🤝️ Contributors
- [@gazorby](https://github.com/gazorby)

- - -

## [v0.2.0](https://github.com/gazorby/strawchemy/compare/v0.1.0..v0.2.0) - 2025-02-20
#### 📚 Documentation
- (**readme**) add badges - ([f1b92a5](https://github.com/gazorby/strawchemy/commit/f1b92a54197caa205eef84614824eaf93c91e4a6)) - [@gazorby](https://github.com/gazorby)
- move CONTRIBUTING.md to the correct place - ([ad6bbd1](https://github.com/gazorby/strawchemy/commit/ad6bbd19b9b88cc606d7b18e1d60ff1b24890adc)) - [@gazorby](https://github.com/gazorby)
#### ⚙️ Miscellaneous Tasks
- (**release**) bump to v0.2.0 - ([2bcb70a](https://github.com/gazorby/strawchemy/commit/2bcb70a8178821fa7bf4047f07e2104e83804b6a)) - [@gazorby](https://github.com/gazorby)
- (**test**) set COLUMNS env var - ([46b70af](https://github.com/gazorby/strawchemy/commit/46b70afb21ba898c8524ac3f2a09bb632ca990f2)) - [@gazorby](https://github.com/gazorby)
- (**test**) fix result job - ([a12c11d](https://github.com/gazorby/strawchemy/commit/a12c11d44651d69e4f087d2c28616cc4719fa672)) - [@gazorby](https://github.com/gazorby)
- (**test**) remove unneeded step - ([ce18a5a](https://github.com/gazorby/strawchemy/commit/ce18a5a815b249b8d20dd5c196d2338248aec6a7)) - [@gazorby](https://github.com/gazorby)
- (**test**) add unit test workflow - ([f560d04](https://github.com/gazorby/strawchemy/commit/f560d0426b67bc328a3cd6bcb73a3b144e8457ce)) - [@gazorby](https://github.com/gazorby)
- (**uv**) commit uv.lock - ([f7df4f8](https://github.com/gazorby/strawchemy/commit/f7df4f82059f5b5ddf74a08ec73c622ae103198f)) - [@gazorby](https://github.com/gazorby)
- add changelog generation workflow - ([b018a78](https://github.com/gazorby/strawchemy/commit/b018a782e8449d25e26440c17e934cc2df7b2440)) - [@gazorby](https://github.com/gazorby)

#### 🤝️ Contributors
- [@gazorby](https://github.com/gazorby)

- - -

## [v0.1.0](https://github.com/gazorby/strawchemy/compare/3a01dc2b31db02507400257e1996fb0c83b177ce..v0.1.0) - 2025-02-19
#### 🚀 Features
- initial commit - ([3a01dc2](https://github.com/gazorby/strawchemy/commit/3a01dc2b31db02507400257e1996fb0c83b177ce)) - [@gazorby](https://github.com/gazorby)
#### ⚙️ Miscellaneous Tasks
- (**release**) bump to v0.1.0 - ([d72c22a](https://github.com/gazorby/strawchemy/commit/d72c22a88aacb41e1ddafd8004b024629a348430)) - [@gazorby](https://github.com/gazorby)

#### 🤝️ Contributors
- [@gazorby](https://github.com/gazorby)
