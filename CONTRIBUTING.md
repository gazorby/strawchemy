# Contribution guide

## ⚙️ Setting up the environment

This project uses [mise](https://mise.jdx.dev/) to manage tasks used for building and testing.

1. Install mise

   - Install mise globally

     See [here](https://mise.jdx.dev/installing-mise.html)

   - Installing mise locally

     If you don't want to install mise globally, you can perform a local install using the provided bootstrap script.

     1. Run `./tools/mise` to download and install mise in the `.mise` folder
     2. (optional) [Activate mise in your shell](https://mise.jdx.dev/installing-mise.html#shells)

2. Run `mise run install` to install all dependencies and pre-commit hooks
3. See [tasks](https://github.com/gazorby/strawchemy/blob/main/tasks.md) documentation for more details

## 🤝 Code contributions

1. [Fork](https://github.com/gazorby/strawchemy/fork) the [strawchemy repository](https://github.com/gazorby/strawchemy)
2. Clone your fork locally with git
3. Set up the environment
4. Make your changes
5. Run `mise run lint` to run linters and formatters. This step is optional and will be executed automatically by git before you make a commit, but you may want to run it manually in order to apply fixes automatically by git before you make a commit, but you may want to run it manually in order to apply fixes
6. Commit your changes to git
7. Push the changes to your fork
8. Open a pull request. Give the pull request a descriptive title indicating what it changes. If it has a corresponding open issue, the issue number should be included in the title as well. For example a pull request that fixes issue `bug: Increased stack size making it impossible to find needle #100` could be titled `fix(#100): Make needles easier to find by applying fire to`

💡 Tip

Pull requests and commits all need to follow the Conventional Commit format

## Creating a new release

### Using the GitHub workflow

1. Run the [bump workflow](https://github.com/gazorby/strawchemy/actions/workflows/bump.yaml) to bump the version and create a tag.

   Note: You can use the `auto` input when running the action to let `git-cliff` figure out the next version number. You can also choose one of `major`, `minor` or `patch`.

2. Go to [Actions](https://github.com/gazorby/strawchemy/actions) and approve the release workflow

   Check that the release and then the publish workflows run successfully

### Using the mise task

1. Run `mise run auto-bump` to automatically bump the version
2. Push your changes
