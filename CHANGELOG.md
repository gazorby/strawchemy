# Changelog

All notable changes to this project will be documented in this file.

## [0.15.3](https://github.com/gazorby/strawchemy/compare/v0.15.2..v0.15.3) - 2025-04-29

### ⚙️ Miscellaneous Tasks

- *(release)* Bump to v0.15.3 - ([6c6207e](https://github.com/gazorby/strawchemy/commit/6c6207eb52f31b9f762d2bc8928d5184be757ffc))
- Fix python 3.13 - ([2b4cf16](https://github.com/gazorby/strawchemy/commit/2b4cf169e317cf4d5d1362fa1e07b3acc4f31ace))
## [0.15.2](https://github.com/gazorby/strawchemy/compare/v0.15.1..v0.15.2) - 2025-04-29

### ⚙️ Miscellaneous Tasks

- *(publish)* Enable uv cache - ([c1d60ec](https://github.com/gazorby/strawchemy/commit/c1d60ec9f792c4eb0fd60e99050eb35745337a11))
- *(release)* Bump to v0.15.2 - ([fe3695b](https://github.com/gazorby/strawchemy/commit/fe3695bc24740aff435457e4eddd651a7f3e39d1))
## [0.15.1](https://github.com/gazorby/strawchemy/compare/v0.15.0..v0.15.1) - 2025-04-28

### ⚙️ Miscellaneous Tasks

- *(publish)* Use python 3.13 - ([1c8754a](https://github.com/gazorby/strawchemy/commit/1c8754a689c05228092a0b70126df086e8e7f943))
- *(release)* Bump to v0.15.1 - ([c536774](https://github.com/gazorby/strawchemy/commit/c536774cc96d9fc98f485d16c8cbf9edea5267e3))
## [0.15.0](https://github.com/gazorby/strawchemy/compare/v0.14.2..v0.15.0) - 2025-04-28

### 🚀 Features

- *(input)* Track relationship changes - ([feee547](https://github.com/gazorby/strawchemy/commit/feee5478028556cbc419041b9bfa12dd9712dd0e))

### ⚙️ Miscellaneous Tasks

- *(release)* Bump to v0.15.0 - ([aeb1ed3](https://github.com/gazorby/strawchemy/commit/aeb1ed33a6e67803e42f7f85236211cf2edcaafe))
## [0.14.2](https://github.com/gazorby/strawchemy/compare/v0.14.1..v0.14.2) - 2025-04-24

### 🐛 Bug Fixes

- *(mutation-input)* Override would not be applied in certain cases - ([a70791f](https://github.com/gazorby/strawchemy/commit/a70791f09c5bdff38baf14e36943c726d7297407))
- *(mutation-input)* Override would not be applied in certain cases - ([bbe75a8](https://github.com/gazorby/strawchemy/commit/bbe75a8165d38f21ae9ff4c5195513534f804373))

### 🚜 Refactor

- Update _StrawberryQueryNode method names - ([783855d](https://github.com/gazorby/strawchemy/commit/783855d2add7a155db0ed5c58fd57edc79f7292d))

### 🧪 Testing

- *(pytest-plugin)* Improve coverage - ([15b2a86](https://github.com/gazorby/strawchemy/commit/15b2a861b43cfdd7f55b4470506c26aafed7625b))
- *(unit)* Remove test_pydantic_to_mapped_override test case - ([36b1131](https://github.com/gazorby/strawchemy/commit/36b11318e799e921f377147537de5f9c0b341136))
- *(unit)* Remove test_pydantic_to_mapped_override test case - ([7e1f79c](https://github.com/gazorby/strawchemy/commit/7e1f79c7f2745822a4c0b59bdc6617c9d3e4137a))

### ⚙️ Miscellaneous Tasks

- *(release)* Bump to v0.14.2 - ([d5c6038](https://github.com/gazorby/strawchemy/commit/d5c6038bac18959f5ad0d1e5998bddfa410b044b))
- Run tests in renovate/dependabot branches - ([17b761f](https://github.com/gazorby/strawchemy/commit/17b761f95af77cf209a803b3e7c95e51b89bafe9))
- Run tests in renovate/dependabot branches - ([9e137f5](https://github.com/gazorby/strawchemy/commit/9e137f5e334241b66164fa49edcfaca440acb82a))

## New Contributors ❤️

* @dependabot[bot] made their first contribution## [0.14.1](https://github.com/gazorby/strawchemy/compare/v0.14.0..v0.14.1) - 2025-04-24

### 🐛 Bug Fixes

- *(dto)* Override params passed to .to_mapped() would not apply if they were excluded in dto - ([eb39a92](https://github.com/gazorby/strawchemy/commit/eb39a929249e6a758989cc9539aa7888238e542d))

### 🚜 Refactor

- *(strawchemy-repository)* Update `root_type` param to `type` - ([4354c51](https://github.com/gazorby/strawchemy/commit/4354c510c216f42a88bf6b4649aecedcbd17ddfc))

### ⚙️ Miscellaneous Tasks

- *(release)* Bump to v0.14.1 - ([cf2c732](https://github.com/gazorby/strawchemy/commit/cf2c73266a3e004f3122098b0e15bfeb1493ff60))
- *(renovate)* Extend config:semverAllMonthly config - ([063b476](https://github.com/gazorby/strawchemy/commit/063b476c46c1019526cf5f2d0e28f39288069afb))
## [0.14.0](https://github.com/gazorby/strawchemy/compare/v0.13.7..v0.14.0) - 2025-04-24

### 🚀 Features

- *(mutation)* Expose Input to strawchemy repository - ([fe1d1f5](https://github.com/gazorby/strawchemy/commit/fe1d1f5752e1745d4632ab0f9885f378d6f0636a))
- *(schema)* Add pydantic input validation - ([580bbef](https://github.com/gazorby/strawchemy/commit/580bbefd610468f8aba47f20198e8331130d1753))

### 🐛 Bug Fixes

- *(validation)* Handle nested models - ([1fa7e14](https://github.com/gazorby/strawchemy/commit/1fa7e14b60e7e7de52ae91645036611cbffe1f0b))

### 🚜 Refactor

- *(factory)* Remove type/input decorators on _StrawberryFactory - ([de5a75d](https://github.com/gazorby/strawchemy/commit/de5a75d7c3c923b18ec37fae6b65a1f5cd67701b))
- *(repository)* Move common logic in a base class for sync/async strawchemy repositories - ([4b31d3a](https://github.com/gazorby/strawchemy/commit/4b31d3ab5c8ebf9f9f185f5fc49fdbdcb2ba444c))
- *(validation)* Update mapper api - ([299fb0a](https://github.com/gazorby/strawchemy/commit/299fb0a32f870482db0aef32260dccffaf677d65))
- Wip - ([a3b6aef](https://github.com/gazorby/strawchemy/commit/a3b6aef4ea15d7bc355c8c62f4fea756e796279e))

### 📚 Documentation

- *(readme)* Update - ([2ade51e](https://github.com/gazorby/strawchemy/commit/2ade51eb1645c79198af327ec3cc25e678e2eba5))
- *(readme)* Add a section for input validation - ([fea65c5](https://github.com/gazorby/strawchemy/commit/fea65c5fda2afebf0663e50a76c52e83f7c487de))

### 🧪 Testing

- *(mutation)* Add missing snapshots - ([6cdbbca](https://github.com/gazorby/strawchemy/commit/6cdbbcacc5b9125c70ab21fc35a78819be54d458))
- *(validation)* Add test cases for validation in custom resolvers - ([e4db99a](https://github.com/gazorby/strawchemy/commit/e4db99a1dd6f10c7bd97448264873db1369902d2))

### ⚙️ Miscellaneous Tasks

- *(release)* Bump to v0.14.0 - ([ada7bcb](https://github.com/gazorby/strawchemy/commit/ada7bcb5a5e778599f878bc1619d3e015f1e480d))
## [0.13.7](https://github.com/gazorby/strawchemy/compare/v0.13.6..v0.13.7) - 2025-04-15

### 🐛 Bug Fixes

- *(dto)* Incorrect forward ref name set in the tracking graph when building recursive dtos - ([ac20b7b](https://github.com/gazorby/strawchemy/commit/ac20b7b1f2e745e7e41ed5ec40ee66ba2d31ec7e))

### ⚙️ Miscellaneous Tasks

- *(release)* Bump to v0.13.7 - ([70619a5](https://github.com/gazorby/strawchemy/commit/70619a5b92ad1e837e4bd04fb535537e8acc984b))
## [0.13.6](https://github.com/gazorby/strawchemy/compare/v0.13.5..v0.13.6) - 2025-04-15

### 🚜 Refactor

- *(mapper)* More factory reuse - ([1c00afc](https://github.com/gazorby/strawchemy/commit/1c00afce6f1795b11a4e3c30b47560fbaa1f3f70))

### ⚙️ Miscellaneous Tasks

- *(release)* Bump to v0.13.6 - ([ac39d47](https://github.com/gazorby/strawchemy/commit/ac39d47bf85a5134c93d1b4fb13f83ee3ae88c8d))
## [0.13.5](https://github.com/gazorby/strawchemy/compare/v0.13.4..v0.13.5) - 2025-04-15

### 🐛 Bug Fixes

- *(dto)* Reuse order_by factory to generate orderBy args - ([3640dc0](https://github.com/gazorby/strawchemy/commit/3640dc0c509c9a530d0b1b844aa5cd3fe162b581))

### ⚙️ Miscellaneous Tasks

- *(release)* Bump to v0.13.5 - ([a379b35](https://github.com/gazorby/strawchemy/commit/a379b35ebf13832a6c2c341fa98950cadbf27d4b))
## [0.13.4](https://github.com/gazorby/strawchemy/compare/v0.13.3..v0.13.4) - 2025-04-15

### 🐛 Bug Fixes

- *(dto)* Not all unresolved dto would be tracked - ([cb384c4](https://github.com/gazorby/strawchemy/commit/cb384c48995cfeca6bb922dad9a7389cbdeeb23e))

### ⚙️ Miscellaneous Tasks

- *(release)* Bump to v0.13.4 - ([3f4da43](https://github.com/gazorby/strawchemy/commit/3f4da43678ac34732bb97b5b28edd2e1ed45577f))
## [0.13.3](https://github.com/gazorby/strawchemy/compare/v0.13.2..v0.13.3) - 2025-04-15

### 🐛 Bug Fixes

- *(dto)* Track unresolved forward refs - ([57d8bf1](https://github.com/gazorby/strawchemy/commit/57d8bf11d7f44aff91f2ede42ca0d02d1699cb32))
- *(testapp)* Explictly set StrawchemyAsyncRepository - ([2fd99a5](https://github.com/gazorby/strawchemy/commit/2fd99a59f2269f61dd9a334b67dd3343a13182b2))

### 🧪 Testing

- *(order-by)* Remove flaky test - ([6aa09e1](https://github.com/gazorby/strawchemy/commit/6aa09e1a8949e8d4246cfabc30e0294d4ef5fa6b))

### ⚙️ Miscellaneous Tasks

- *(release)* Bump to v0.13.3 - ([4b04bb8](https://github.com/gazorby/strawchemy/commit/4b04bb8a28366045ffd764db016c3b65b28c7623))
## [0.13.2](https://github.com/gazorby/strawchemy/compare/v0.13.1..v0.13.2) - 2025-04-14

### 🚜 Refactor

- *(pydantic)* Remove defer_build=True on base config - ([4457996](https://github.com/gazorby/strawchemy/commit/445799619b6dbc617b65c3b643b592e001991a4c))

### ⚙️ Miscellaneous Tasks

- *(release)* Bump to v0.13.2 - ([80021fa](https://github.com/gazorby/strawchemy/commit/80021facb7bcb582a9a997ede45f9f2bc21e0ebe))
## [0.13.1](https://github.com/gazorby/strawchemy/compare/v0.13.0..v0.13.1) - 2025-04-10

### 🐛 Bug Fixes

- *(config)* Field would not marked as async when it should - ([1b8d74e](https://github.com/gazorby/strawchemy/commit/1b8d74eb1173b33894ef0afff4be83538622b80a))

### 📚 Documentation

- *(readme)* Clarify default repository_type value - ([893eeb8](https://github.com/gazorby/strawchemy/commit/893eeb86bacdb61a7762bb0ee6b2b9f0d146c7e8))

### ⚙️ Miscellaneous Tasks

- *(release)* Bump to v0.13.1 - ([5bb99a6](https://github.com/gazorby/strawchemy/commit/5bb99a6a07d62cc1df9c0e5875ab6f50c769bb9a))
## [0.13.0](https://github.com/gazorby/strawchemy/compare/v0.12.2..v0.13.0) - 2025-04-09

### 🚀 Features

- *(cud)* Allow settings null on to-one relations - ([1efe0ed](https://github.com/gazorby/strawchemy/commit/1efe0ed9fa118ae95a2ac572d829936195c6880a))
- *(cud)* Add delete mutation - ([289d9be](https://github.com/gazorby/strawchemy/commit/289d9bea3bbd38d826578f44607a8978c3b8dffa))
- *(cud)* Add filter update mutation - ([c15f60c](https://github.com/gazorby/strawchemy/commit/c15f60c1f7618de8529711e33639b28c8ba6362c))

### 🐛 Bug Fixes

- *(cud)* Enable add/remove on to-mnay relations; set overwrite previous to-many relations - ([08ee2e7](https://github.com/gazorby/strawchemy/commit/08ee2e79e75161e597d59ca3a1727ca233cce53b))
- *(mapping)* Respect nullability when generating input types - ([f87f3b6](https://github.com/gazorby/strawchemy/commit/f87f3b6d6df840540077d079d28bd2d095c57016))
- *(mapping)* Exclude foreign keys from inputs - ([17678f2](https://github.com/gazorby/strawchemy/commit/17678f21578675d8f16100208756b9bb934f542c))
- *(schema)* Do not allow removing to-many relations if remote fk is not nullable - ([c7203bc](https://github.com/gazorby/strawchemy/commit/c7203bccd4912e2c923515d12bde2097a806dd98))

### 🚜 Refactor

- *(cud)* Implement update input - ([5fd3d9f](https://github.com/gazorby/strawchemy/commit/5fd3d9f91d4dab42419c29eb2b092c8364f165b8))
- *(cud)* Implement update repository method - ([1080c25](https://github.com/gazorby/strawchemy/commit/1080c25bf134a7ae509be0194367f7d7dff0dc4e))
- *(cud)* Merge create and update transaction logic - ([769e4ef](https://github.com/gazorby/strawchemy/commit/769e4efa78e9140bab0f0d7d18caba5151d65cff))
- *(mapper)* Update api - ([a486384](https://github.com/gazorby/strawchemy/commit/a48638470223a426cf02fd9021098b2dd1e4876f))
- *(mapper)* Remove duplicate assignement - ([f22e1de](https://github.com/gazorby/strawchemy/commit/f22e1deab11a24320f7a17139b83942c98da342b))
- *(repository)* Update code documentation - ([ae39957](https://github.com/gazorby/strawchemy/commit/ae3995739fbb5d60ac11077e00618943eb695b4a))
- *(update-input)* Make all fields partial, except pks - ([64a6f3e](https://github.com/gazorby/strawchemy/commit/64a6f3e58108e9b7f5e1419b759747f7f01a6a68))
- *(utils)* Remove unused function - ([68a970b](https://github.com/gazorby/strawchemy/commit/68a970b8a7da0baa4d37ba084dcacd806ad90b2c))

### 📚 Documentation

- *(readme)* Add mutation documention - ([5de832a](https://github.com/gazorby/strawchemy/commit/5de832a3d7868f5c544a8c40f6683df9ac045cfd))

### 🧪 Testing

- *(cud)* Add update test cases - ([06814aa](https://github.com/gazorby/strawchemy/commit/06814aa0b9020910a65e74ad9cf6bd8c2041ff48))
- *(cud)* Update query snapshots - ([d2ba852](https://github.com/gazorby/strawchemy/commit/d2ba852fb8e93e3cf68fb5484f3b53f23a899361))
- *(cud)* Add test cases for invalid relation inputs - ([1535b75](https://github.com/gazorby/strawchemy/commit/1535b751225b60d7cb4e0220b64d56df7fc27e56))
- *(cud)* Add test cases for delete mutation - ([3bd3fb3](https://github.com/gazorby/strawchemy/commit/3bd3fb3746d3998bc8d58609f117958b39200eda))
- *(integration)* Update query snapshots - ([6a11b24](https://github.com/gazorby/strawchemy/commit/6a11b24a4f16f31d9b6a09851acb1ff01e3b5bdc))
- *(integration)* Add create mutation test cases - ([a84d5b1](https://github.com/gazorby/strawchemy/commit/a84d5b166b3b78fd0f9dee54c54f5e11e7305a64))
- *(integration)* Better sql snapshot formatting - ([4238c2f](https://github.com/gazorby/strawchemy/commit/4238c2f97b7d173aa14764f3deec75837d28460b))
- *(unit)* Add test cases for invalid inputs - ([502be53](https://github.com/gazorby/strawchemy/commit/502be5365cabf61e46aa37b5843e53da65e6aad9))
- *(unit)* Remove default dto_config test case - ([dc06ca9](https://github.com/gazorby/strawchemy/commit/dc06ca9f173a16baaa2100b4e568930698e03dd0))

### ⚙️ Miscellaneous Tasks

- *(release)* Bump to v0.13.0 - ([fd1d725](https://github.com/gazorby/strawchemy/commit/fd1d7257c906f2e2131c079840e33abd3af8d681))
## [0.12.2](https://github.com/gazorby/strawchemy/compare/v0.12.1..v0.12.2) - 2025-04-03

### 🐛 Bug Fixes

- *(mapping)* Input identifiers not managed by the registry - ([d28a11b](https://github.com/gazorby/strawchemy/commit/d28a11b8fa9b5f33a434644d30a0608c98239d1b))

### ⚙️ Miscellaneous Tasks

- *(release)* Bump to v0.12.2 - ([67b8bb1](https://github.com/gazorby/strawchemy/commit/67b8bb1ea1e66090f3c1407e82189a54877709d2))
## [0.12.1](https://github.com/gazorby/strawchemy/compare/v0.12.0..v0.12.1) - 2025-04-02

### 🐛 Bug Fixes

- *(query-hook)* Relationship loading would fail if triggered by a nested field - ([601086a](https://github.com/gazorby/strawchemy/commit/601086aa3a10b88f7cc24d0518641cc7bce9fdaa))

### ⚙️ Miscellaneous Tasks

- *(release)* Bump to v0.12.1 - ([3fba332](https://github.com/gazorby/strawchemy/commit/3fba3320097090572f150446d91c6fbe4b5e0633))
## [0.12.0](https://github.com/gazorby/strawchemy/compare/v0.11.0..v0.12.0) - 2025-04-01

### 🚀 Features

- *(cud)* Add create mutation - ([d9ef914](https://github.com/gazorby/strawchemy/commit/d9ef914c60f9396951736c4502f576aa02d16eea))
- *(cud)* Add create mutation - ([b1af031](https://github.com/gazorby/strawchemy/commit/b1af031f64e39ca7e9eef368bedcb6e6c3e5a898))
- *(query-hook)* Enable relationships loading - ([9100165](https://github.com/gazorby/strawchemy/commit/91001659cfb114df7b3ec6736c36b4b24008a1be))

### 🐛 Bug Fixes

- *(cud)* Mixed relations in create - ([7d140ed](https://github.com/gazorby/strawchemy/commit/7d140ed5bb59d829805bc92f5cf3da399fed3a36))
- *(mapping)* Do not enable aggregations on input types - ([24cd763](https://github.com/gazorby/strawchemy/commit/24cd763af01d02d6abcbd174d346f2c938955d51))
- *(mapping)* Override type fields would not be retracked - ([98f3375](https://github.com/gazorby/strawchemy/commit/98f33756547fd9a5773e67ae3cdbb6b1d037182a))
- *(resolver)* Rely on sqlalchemy session type to use choose between sync/async resolver - ([92eabda](https://github.com/gazorby/strawchemy/commit/92eabdaf613e39787bfadb6361b11d11a3149120))

### 💼 Other

- *(doc)* Fix typo in license - ([57cf88d](https://github.com/gazorby/strawchemy/commit/57cf88d1545589a13bff87952110a08b2a842d23))

### 🚜 Refactor

- *(dto)* Improve dto caching reliability - ([ffa2ab1](https://github.com/gazorby/strawchemy/commit/ffa2ab1dc4d0a18ba98bdd4ae316f6b09731f64e))
- *(dx)* Add an example app - ([ed3e5d6](https://github.com/gazorby/strawchemy/commit/ed3e5d635f42c7ddcf7b6d2195c2ef1bad434e91))
- *(mapping)* Add foreign key inputs for relation - ([fda6b60](https://github.com/gazorby/strawchemy/commit/fda6b60e879697d85d62a0c6a311bf5f75ac9ac7))
- *(transpiler)* Remove unused function - ([1636803](https://github.com/gazorby/strawchemy/commit/1636803ae724753afde977a5e95eb0eaaa8edda8))

### 🧪 Testing

- *(mutations)* Update snapshot assertions - ([ea9ea0a](https://github.com/gazorby/strawchemy/commit/ea9ea0a2c7dae79b895c64763c89fef9f21eb78d))
- *(unit)* Add unit test case for distinct enum - ([2d01e1e](https://github.com/gazorby/strawchemy/commit/2d01e1e422ce989c80deb185b54cad4e4c18b680))
- *(unit)* Remove old test - ([5603edd](https://github.com/gazorby/strawchemy/commit/5603edd9ddc591335073f3b43d3bf44a3bcd75e6))
- *(unit)* Add test case for wrong relationship configuration in query hook - ([ece4d32](https://github.com/gazorby/strawchemy/commit/ece4d32ae1b02c25f4fcacac34ef7306c26ab718))

### ⚙️ Miscellaneous Tasks

- *(gitignore)* Ignore .sqlite files - ([49928b3](https://github.com/gazorby/strawchemy/commit/49928b395f7f57395e9a9f9f59493d8a5b4c94e7))
- *(release)* Bump to v0.12.0 - ([66ff56b](https://github.com/gazorby/strawchemy/commit/66ff56b8a2fa8dd1948d069333fdeaa57f10d55c))
- *(renovate)* Enable lock file maintenance - ([5ab6f8e](https://github.com/gazorby/strawchemy/commit/5ab6f8e1dad7da666c9b593b241282814f9240b9))

## New Contributors ❤️

* @renovate[bot] made their first contribution## [0.11.0](https://github.com/gazorby/strawchemy/compare/v0.10.0..v0.11.0) - 2025-03-25

### 🚀 Features

- *(hook)* Add QueryHookProtocol - ([afd406a](https://github.com/gazorby/strawchemy/commit/afd406a2463f511cf629e9a71ad218f1e9adbc4b))
- *(mapping)* Allow setting filter/order_by at the type level - ([c1ead8c](https://github.com/gazorby/strawchemy/commit/c1ead8c89ff765ef299d611073be3d5e03c361fa))

### 🐛 Bug Fixes

- *(hook)* Hook would not be correctly applied if triggered by a type - ([0de25a0](https://github.com/gazorby/strawchemy/commit/0de25a058787d5e4d80af558e048a63f6ed71939))
- *(mapping)* Type annotation override on a list field - ([6f56744](https://github.com/gazorby/strawchemy/commit/6f567441ba708feaa1854223c257de69e29eaf47))
- *(order-by)* Order by on relation not working properly - ([acf1a8c](https://github.com/gazorby/strawchemy/commit/acf1a8cefd7513eeb2dec9450ae75608c8080a58))

### 🚜 Refactor

- *(hook)* Simplify query hook interface - ([5f84532](https://github.com/gazorby/strawchemy/commit/5f84532e630b84c8aa85a4b703bc5b6bf0ed5959))
- *(typing)* Remove unused type - ([f242ce5](https://github.com/gazorby/strawchemy/commit/f242ce5d1b1a87eaff604bde3e0f20fede939620))

### 🧪 Testing

- *(integration)* Add test case for distinctOn - ([2ed11c1](https://github.com/gazorby/strawchemy/commit/2ed11c145f7d730e12af794da16db10b67dd7d97))

### ⚙️ Miscellaneous Tasks

- *(coverage)* Use coverage combine - ([05b772d](https://github.com/gazorby/strawchemy/commit/05b772d873059391f5026ba9e3ff969818665805))
- *(coverage)* Use merge-multiple - ([dfa12d6](https://github.com/gazorby/strawchemy/commit/dfa12d65f6e440927a4d36d81ca2bfe06b0baf9c))
- *(coverage)* Use default coverage data when running tests - ([4773d23](https://github.com/gazorby/strawchemy/commit/4773d234caeb26ef6be64677b85e6968d5e646e9))
- *(coverage)* Checkout the repository before processing files - ([d2dad3d](https://github.com/gazorby/strawchemy/commit/d2dad3db1619e538c7a40f246116725b023980b6))
- *(coverage)* Let leading dot in coverage data filenames - ([ddf8de9](https://github.com/gazorby/strawchemy/commit/ddf8de9005102f7b1a7ea1cdc52bd16e8f2c6e1e))
- *(coverage)* Remove .xml extension in coverage filenames - ([a4c1fda](https://github.com/gazorby/strawchemy/commit/a4c1fda35faf83d9d6cb123245547e133b3652aa))
- *(coverage)* Append the coverage session name as file extension - ([7046c63](https://github.com/gazorby/strawchemy/commit/7046c634cfc2ea8a2af7005b2ff9088690196609))
- *(release)* Bump to v0.11.0 - ([bd27b8e](https://github.com/gazorby/strawchemy/commit/bd27b8e8a8545557879a7de22f9b5483cd751fb6))
## [0.10.0](https://github.com/gazorby/strawchemy/compare/v0.9.0..v0.10.0) - 2025-03-21

### 🐛 Bug Fixes

- *(query-hooks)* [**breaking**] Enforce column only attributs in QueryHook.load_columns - ([0cc4bb5](https://github.com/gazorby/strawchemy/commit/0cc4bb5a4b06e64f05bb7ce0fc8a9b23f7bb03f3))

### 🧪 Testing

- *(integration)* Test empty query hooks - ([9df6df9](https://github.com/gazorby/strawchemy/commit/9df6df97f67c701bd60a5ca60b6aad31539c592f))
- *(integration)* Update snapshot - ([8b4aef5](https://github.com/gazorby/strawchemy/commit/8b4aef551cb4ff5f2d8c6649241789b608303960))

### ⚙️ Miscellaneous Tasks

- *(release)* Bump to v1.0.0 - ([ba914bc](https://github.com/gazorby/strawchemy/commit/ba914bc3a57d67d874a48fb47d604ecf2ed88365))
- *(release)* Bump to v0.10.0 - ([03609ab](https://github.com/gazorby/strawchemy/commit/03609ab04e241c33826eae0f91cb3db9d01df64b))
## [0.9.0](https://github.com/gazorby/strawchemy/compare/v0.8.0..v0.9.0) - 2025-03-21

### 🚀 Features

- *(filters)* Add order filters to string - ([d76c950](https://github.com/gazorby/strawchemy/commit/d76c9509e96cb2300e87bcc87d6aa23ad2215742))
- *(filters)* Add insensitive regexp variants - ([27706d5](https://github.com/gazorby/strawchemy/commit/27706d5a9a26f909f2027145992e47d4a264f7f8))
- Support postgres `Interval` type (mapping and filtering) - ([355994f](https://github.com/gazorby/strawchemy/commit/355994f6747d9b5aa6799708aa0e0063636e8019))

### 📚 Documentation

- *(readme)* Clarify supported filters - ([91a52b5](https://github.com/gazorby/strawchemy/commit/91a52b5cfd5218569cde02c54dae831ae843fdf0))
- *(readme)* Update filter names - ([8e51154](https://github.com/gazorby/strawchemy/commit/8e51154172f678aeb2ddec39455607b7cfee88df))
- *(readme)* Add type override documentation - ([5d34539](https://github.com/gazorby/strawchemy/commit/5d34539f5f7078a7935deb47d652de78481adebd))
- *(readme)* Update filters section - ([83f43d3](https://github.com/gazorby/strawchemy/commit/83f43d3bc20da1e5d5eeac7f794789e8e18e099a))

### ⚙️ Miscellaneous Tasks

- *(release)* Bump to v0.9.0 - ([36ac3b6](https://github.com/gazorby/strawchemy/commit/36ac3b6dee86a62a7d729619920b72f6046d67d8))
## [0.8.0](https://github.com/gazorby/strawchemy/compare/v0.6.0..v0.8.0) - 2025-03-20

### 🚀 Features

- *(geo)* Infer GeoJSON specific scalars to be inferred from shapely geometries - ([145f495](https://github.com/gazorby/strawchemy/commit/145f495ddfa8e9745e30d71fd2275cbffa3365d9))
- *(geo)* Infer shapely types from geoalchemy columns - ([a8ed586](https://github.com/gazorby/strawchemy/commit/a8ed586be7475e24fe042910448cee3aa084ce6e))

### ⚙️ Miscellaneous Tasks

- *(release)* Bump to v0.7.0 - ([65cb766](https://github.com/gazorby/strawchemy/commit/65cb766047bf80f024650f6be66cc4c2255cf44e))
- *(release)* Bump to v0.8.0 - ([98c32c0](https://github.com/gazorby/strawchemy/commit/98c32c0bff6773ca87f9580fa4c406bd1738a3ab))
## [0.6.0](https://github.com/gazorby/strawchemy/compare/v0.5.3..v0.6.0) - 2025-03-19

### 🚀 Features

- *(geo)* Add GeoJSON scalar variants - ([d197b8d](https://github.com/gazorby/strawchemy/commit/d197b8d5b99cd9102e1c92900c148a024c9d65e5))

### 🧪 Testing

- *(geo)* Conditionally skip tests when geoalchemy2 is not installed - ([3ecc576](https://github.com/gazorby/strawchemy/commit/3ecc576e7f3b30a9a460dc0b6f3c31422e4f87e8))

### ⚙️ Miscellaneous Tasks

- *(release)* Bump to v0.6.0 - ([69d4582](https://github.com/gazorby/strawchemy/commit/69d45829f07ade93d69d8be7958178fde216818e))
## [0.5.3](https://github.com/gazorby/strawchemy/compare/v0.5.2..v0.5.3) - 2025-03-19

### 🐛 Bug Fixes

- *(aggregations)* Use float for aggregation output of int columns - ([bef9700](https://github.com/gazorby/strawchemy/commit/bef970043c1096fa677bf276c20e0a4618e85bb7))
- *(strawberry-type)* Model instance passed on types not declaring it - ([06c1c1f](https://github.com/gazorby/strawchemy/commit/06c1c1f7eefaa2c5e1fe2f03f7ef3e854dafe7ea))
- *(transpiler)* Adding an aggregation column to an existing lateral join would not be properly aliased, leading to a cartesian product on the same table - ([f365120](https://github.com/gazorby/strawchemy/commit/f365120ba9f5c110de9417b725ca32de4ce07d69))
- Import errors when geo extras is not installed - ([f28f2ea](https://github.com/gazorby/strawchemy/commit/f28f2eaee54b2658cdc294d0cdce6325f54e69c6))

### 🚜 Refactor

- Remove unused stuff - ([9bd2d1b](https://github.com/gazorby/strawchemy/commit/9bd2d1b0b0738aac5e4dfb4db52a343a72ae363a))
- Remove the default strawchemy instance - ([b766374](https://github.com/gazorby/strawchemy/commit/b7663745ab49f6415ccc1277421559945f7fcfb0))

### 📚 Documentation

- *(readme)* Update repository doc - ([d930468](https://github.com/gazorby/strawchemy/commit/d930468ddbe47980ec9cc9de4f8a6524f7b83a88))
- *(readme)* Make code examples expandable - ([4da85a1](https://github.com/gazorby/strawchemy/commit/4da85a119dcc03a92ce24ad8ebbf4c6791784e6b))
- Update README.md - ([4e5564b](https://github.com/gazorby/strawchemy/commit/4e5564bbc10305cdca8123e5fc059d9ec9fce8a9))
- Update README.md - ([8a53b62](https://github.com/gazorby/strawchemy/commit/8a53b62e8f4cf22709b1ee3292e942774492e052))

### 🧪 Testing

- *(integration)* Add filters tests - ([875fc90](https://github.com/gazorby/strawchemy/commit/875fc90e2f0b5c25c4aca13c55ac069cb16de17c))
- *(integration)* Add geo filter tests - ([9a03a29](https://github.com/gazorby/strawchemy/commit/9a03a29e3a2d8a0a2711b215eeba61084dabfea1))
- *(integration)* Add aggregation tests - ([b5ee7d2](https://github.com/gazorby/strawchemy/commit/b5ee7d2885f174eb564dcdfd67133d0d945238a3))
- *(integration)* Add aggregation filter tests - ([150cb3d](https://github.com/gazorby/strawchemy/commit/150cb3dc5ca6a6cfe6ab5a12c9981a44ebe09f32))
- *(integration)* Add order by test cases - ([4eb84d7](https://github.com/gazorby/strawchemy/commit/4eb84d7803b1e12119a4b4d94daff9dc5a7163f3))
- *(integration)* Add filtered statement test case - ([9f1f648](https://github.com/gazorby/strawchemy/commit/9f1f648c195c58196fd94b082eae5cfb33389539))
- *(integration)* Assert aggregation values in test_statistical_aggregation - ([43e04ed](https://github.com/gazorby/strawchemy/commit/43e04edce34700424dd51329d51369f0d1c19ba6))
- *(integration)* Add custom resolver test case - ([5882dd0](https://github.com/gazorby/strawchemy/commit/5882dd0e57553c120d01adcf0e23cc6279998a95))
- *(integration)* Add test case for get_one_or_none repo method - ([ca953dd](https://github.com/gazorby/strawchemy/commit/ca953ddbb9a18f93d794d0caf0f10d77081af9be))
- *(integration)* Add case to test querying __typename do not fails - ([12e6272](https://github.com/gazorby/strawchemy/commit/12e627224fd5ee0bea9cb761489e7e89b1485813))
- *(integration)* Add query optimizations test cases - ([58be932](https://github.com/gazorby/strawchemy/commit/58be932b6abd3a42290ed1276e9ff16b67b81022))
- *(integration)* Update query optimizations test cases - ([06d9499](https://github.com/gazorby/strawchemy/commit/06d9499f12e75e9a9c8f91b768b7eeca5022cbf0))
- *(integration)* Add query hooks test cases - ([7d7a653](https://github.com/gazorby/strawchemy/commit/7d7a653a5817f0c07c4d39158cf58dfa6d4fe1b9))
- *(integration)* Add root aggregation and paginated test cases - ([20f3ef0](https://github.com/gazorby/strawchemy/commit/20f3ef0d4744debb7db4dff27bedc557c18e3684))
- *(local)* Use nox for specific test tasks - ([29d3984](https://github.com/gazorby/strawchemy/commit/29d3984d12f1ac595643799b9d140d8d6757c509))
- *(unit)* Add aggregation filters and root aggregation schemas - ([40c4c74](https://github.com/gazorby/strawchemy/commit/40c4c740d6ab295a70f61d597b365ac6629fcd79))
- *(unit)* Add various dto test cases - ([2b2647e](https://github.com/gazorby/strawchemy/commit/2b2647ee381c732f77d5dc6173c0e27dea34955c))
- First batch - ([60033ad](https://github.com/gazorby/strawchemy/commit/60033ad5ed309a8e2c79e538844c6cd1e8521324))

### ⚙️ Miscellaneous Tasks

- *(coverage)* Explicitly set source in [tool.coverage.run] as codecov might need it - ([5200d8c](https://github.com/gazorby/strawchemy/commit/5200d8c9e1274daf44cef85707017845930dfda4))
- *(mise)* Upgrade - ([4afd3c8](https://github.com/gazorby/strawchemy/commit/4afd3c86af6f0694a9b1d5b116bbf95ab05ded2f))
- *(mise)* Make the ruff:check depends on _install - ([b863708](https://github.com/gazorby/strawchemy/commit/b863708dbd1a5b59d8f8f1d258306c733721f98b))
- *(pyproject)* Fix syntax - ([8cd111b](https://github.com/gazorby/strawchemy/commit/8cd111b468caa314d6597e40e5d91a28d435ca9b))
- *(pyproject)* Remove multiprocessing from coverage config - ([b8cfe46](https://github.com/gazorby/strawchemy/commit/b8cfe46a0f51f32269ea5a969855235f2f94408c))
- *(pyproject)* Update classifiers - ([59aa01b](https://github.com/gazorby/strawchemy/commit/59aa01b5b7531a0bf340756de465b9164d0bf9dd))
- *(release)* Bump to v0.5.3 - ([dcb17d7](https://github.com/gazorby/strawchemy/commit/dcb17d7fa9ce83c40c6e3d92e9aa87abcca96dc1))
## [0.5.2](https://github.com/gazorby/strawchemy/compare/v0.5.1..v0.5.2) - 2025-03-12

### 🐛 Bug Fixes

- *(pagination)* Do not apply offset on the root query when a subquery is present - ([e91da34](https://github.com/gazorby/strawchemy/commit/e91da345507aefb9c8c39a64f39badf4df7c37a7))

### 🧪 Testing

- *(integration)* Add test case asserting only queried fields are are present in SELECT - ([5f46c42](https://github.com/gazorby/strawchemy/commit/5f46c420960633dd008d100f701736cb5dfbd0a0))
- *(unit)* Add mapping test case for enum - ([b27dbb6](https://github.com/gazorby/strawchemy/commit/b27dbb64070793cc5d6d051b1e0ccba625a0d1ac))

### ⚙️ Miscellaneous Tasks

- *(codecov)* Let the action find junit files - ([9848ab2](https://github.com/gazorby/strawchemy/commit/9848ab29986a4e6cd3a78dc5aa46d93570a7c43c))
- *(codecov)* Add flags - ([d22a49d](https://github.com/gazorby/strawchemy/commit/d22a49d2954317fac925da6a3d2dc50d7915794c))
- *(codecov)* Merge python version and session name in a single flag - ([0d9f34f](https://github.com/gazorby/strawchemy/commit/0d9f34f8c6b5789305612a0a420f3facfba94924))
- *(codecov)* Fix typo in codecov.yml - ([acfe955](https://github.com/gazorby/strawchemy/commit/acfe9552641eb30c0c51a1e5340088b688df9837))
- *(release)* Bump to v0.5.2 - ([76d446c](https://github.com/gazorby/strawchemy/commit/76d446c42960e2755733ab70cd0ffc93e5102dc6))
- *(test)* Set the pytest junit_family to legacy - ([4d5b3d5](https://github.com/gazorby/strawchemy/commit/4d5b3d57bd904ec6897f50335bddef1284de26c8))
- Add codecov.yml - ([2f77c09](https://github.com/gazorby/strawchemy/commit/2f77c0960116f8f46253c30fdeb6d8d0ed23195e))
## [0.5.1](https://github.com/gazorby/strawchemy/compare/v0.5.0..v0.5.1) - 2025-03-11

### 🐛 Bug Fixes

- *(mapping)* Dto edge cases - ([fd417a2](https://github.com/gazorby/strawchemy/commit/fd417a21e854dcc9596d3aa8fdb704eebb1e2711))
- *(mapping)* Field arguments not replaced by override types - ([bf44803](https://github.com/gazorby/strawchemy/commit/bf44803ab5f41502ee24b18cd484ec9f87da4c62))
- *(transpiler)* Remove caching property on resolved tree - ([6b11dcc](https://github.com/gazorby/strawchemy/commit/6b11dccab751a1e390adb6dc612c16c0321756ff))
- *(transpiler)* Properly handle root aggregations - ([bacd111](https://github.com/gazorby/strawchemy/commit/bacd111c553ef8ed8b810d272ff7827f5ff6f26a))
- *(transpiler)* Root aggregations not handled when using subquery - ([495420f](https://github.com/gazorby/strawchemy/commit/495420f024308e20e5e03e6d89d73ebf7db52332))
- *(transpiler)* Add id columns in node selection if not present - ([5b06a8d](https://github.com/gazorby/strawchemy/commit/5b06a8d40cf3086fac16e17fb4f9cb85e6cc0bfc))
- *(transpiler)* Update - ([a786a5f](https://github.com/gazorby/strawchemy/commit/a786a5fa7ada02d5f87eaaa9e82152bbcec6ab23))
- *(typing)* Session_getter - ([af2edaa](https://github.com/gazorby/strawchemy/commit/af2edaa02d50d93879b1137068d60f3e97d08e9b))
- Update - ([c334738](https://github.com/gazorby/strawchemy/commit/c33473829fa8976f31242828e7294543ef738044))

### 🚜 Refactor

- *(dx)* Update .editorconfig - ([89c9ac2](https://github.com/gazorby/strawchemy/commit/89c9ac202218e5d06e3da956ba7b91e7844219fb))
- *(transpiler)* Minor changes - ([dafa2f5](https://github.com/gazorby/strawchemy/commit/dafa2f5549c1a4f81eaff9cd71bdb57aca24c85b))

### 📚 Documentation

- *(contributing)* Add tasks.md reference - ([c75b043](https://github.com/gazorby/strawchemy/commit/c75b043625a0c30f33a358d63d7bd1edc4d22be6))
- Update CONTRIBUTING.md - ([447e529](https://github.com/gazorby/strawchemy/commit/447e5295c4b6d434669f5aabe5e17825d231f6a9))

### 🧪 Testing

- *(integration)* Initial work - ([cc644b5](https://github.com/gazorby/strawchemy/commit/cc644b5edbfb79d745820d9b91d1bf7972db390c))
- *(integration)* Add relation tests - ([7b9de00](https://github.com/gazorby/strawchemy/commit/7b9de002b52e6c976c0d0fe6048e9086afd42efb))
- *(snapshot)* Use a custom pytest marker for snapshot-based tests - ([7bf8ff6](https://github.com/gazorby/strawchemy/commit/7bf8ff666a26002aaf548017d0ddd8b76c71edb6))
- *(unit)* Move unit schemas in unit folder - ([4f83c4a](https://github.com/gazorby/strawchemy/commit/4f83c4a1e8012122164771da5fae4475c174c7ad))

### ⚙️ Miscellaneous Tasks

- *(ci)* Only fail workflow on cancellation/failure of test/lint jobs - ([c67b0d5](https://github.com/gazorby/strawchemy/commit/c67b0d53caa93137791a106b0bb0c2ad08f515ed))
- *(ci)* Add mise.toml to paths whitelist in skip check job - ([3d23d82](https://github.com/gazorby/strawchemy/commit/3d23d82b21d698d2103817b1d1b89997fa56aa07))
- *(ci)* Run tests using mise task - ([7902dd9](https://github.com/gazorby/strawchemy/commit/7902dd955cc43ee7b2951d4c4520009385e9c706))
- *(ci)* Fix missing arg to test-ci task - ([37aba9c](https://github.com/gazorby/strawchemy/commit/37aba9c6e7f3c3153a1f0c4eb5e5c5a5a477d2e9))
- *(ci)* Fix session param in nox call - ([b273b54](https://github.com/gazorby/strawchemy/commit/b273b54c7a379a5ce9ab10a87faed6f88a7e6d2f))
- *(ci)* Fix typo - ([0269a3e](https://github.com/gazorby/strawchemy/commit/0269a3ef089086148b95b449380dd128ff988e4c))
- *(lint)* Use mise - ([4e03e64](https://github.com/gazorby/strawchemy/commit/4e03e648087c05c7b8424ab3e196714b539ef4e2))
- *(mise)* Add a task to run pre-commit checks - ([2b1b787](https://github.com/gazorby/strawchemy/commit/2b1b787e1a438c307d616a966fff1685eaa43ecd))
- *(mise)* Add clean task - ([321ac42](https://github.com/gazorby/strawchemy/commit/321ac4292e8f4b89092d7b1d140494a1e4fa3283))
- *(mise)* Add mise.lock - ([135fe82](https://github.com/gazorby/strawchemy/commit/135fe82fe2ac1fb3300a0cc61d9f7fc6e028dc23))
- *(mise)* Streamline task names - ([dbf4357](https://github.com/gazorby/strawchemy/commit/dbf4357a0b17999e1586e6d88c5629d8ec20ca1b))
- *(mise)* Remove actionlint in lint task - ([992aeec](https://github.com/gazorby/strawchemy/commit/992aeec15674324cdbd66ab13a61621105dea1af))
- *(pre-commit)* Run pre-commit lint check in mise task - ([6c7b017](https://github.com/gazorby/strawchemy/commit/6c7b0170259d650b426039b4336f25db0f7fb446))
- *(pre-commit)* Add actionlint hook - ([b75a842](https://github.com/gazorby/strawchemy/commit/b75a842863581c874e18465a3c820f5f1e7453d7))
- *(pre-commit)* Add a hook to render tasks documentation - ([b067a84](https://github.com/gazorby/strawchemy/commit/b067a846d048ffbbb865740a04f178f58fa9d2e8))
- *(release)* Bump to v0.5.1 - ([d1b30ca](https://github.com/gazorby/strawchemy/commit/d1b30cae2022e51b74aa91f5742fe1f25049c252))
- *(test)* Call mise task to generate test matrix - ([43a0308](https://github.com/gazorby/strawchemy/commit/43a0308697661080c2b30758ec40eef178ac9f49))
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
