# Installing MemoryLake into QwenWork (instructions for the agent)

You are an agent running inside QwenWork, and the user asked you to install
the MemoryLake plugin from this repository. Follow these steps exactly. They
install the plugin as published: do not use the plugin-creator skill, and do
not rewrite, restructure, or "improve" any file of the plugin -- its hooks
depend on the files staying as they are.

Supported: QwenWork on macOS and Linux (the plugin's hooks are bash scripts).

## 1. Download the repository

Use your shell tool. Download into a fresh temporary directory:

```bash
work=$(mktemp -d)
git clone --depth 1 https://github.com/memorylake-ai/memorylake-harness.git "$work/memorylake-harness" \
  || { curl -fsSL https://codeload.github.com/memorylake-ai/memorylake-harness/tar.gz/refs/heads/main \
         | tar -xz -C "$work" && mv "$work/memorylake-harness-main" "$work/memorylake-harness"; }
ls "$work/memorylake-harness/qwenwork-plugin/.qoder-plugin/plugin.json"
```

If both the clone and the tarball fail, GitHub is not reachable from this
network. Tell the user so, and stop.

The plugin is the `qwenwork-plugin` directory, **not** the repository root:
the root holds plugins for other apps and has no `plugin.json` of its own.

## 2. Install it

QwenWork loads every plugin directory under `~/.qwenworkcn/plugins-custom/`
when a conversation starts (a directory counts as a plugin when it has
`.qoder-plugin/plugin.json`). Installing is copying the plugin there, under
the folder name `memorylake`. Use your shell tool:

```bash
src="$work/memorylake-harness/qwenwork-plugin"
dest="$HOME/.qwenworkcn/plugins-custom/memorylake"
mkdir -p "$HOME/.qwenworkcn/plugins-custom"
rm -rf "$dest.new" && cp -R "$src" "$dest.new"
# An existing copy is an earlier MemoryLake version: this is an upgrade.
[ -d "$dest" ] && mv "$dest" "$work/memorylake-previous"
mv "$dest.new" "$dest"
ls "$dest/.qoder-plugin/plugin.json" "$dest/hooks/hooks.json" "$dest/bin/ml-recall"
```

If the directory already existed, tell the user you upgraded MemoryLake.

Do not install through `mcp__qw-builtin__qw_action`: QwenWork 1.2.1's
connector has no plugin-install action (the key
`qwenwork.settings.plugins.install_from_path` that some skill documents
mention is rejected there), and the copy above is exactly what such an
install does.

If the copy fails (for example the session runs in a sandbox that cannot
write to the home directory), package the plugin instead and hand it over
for a manual import:

```bash
cd "$work/memorylake-harness" && zip -qr "$HOME/Downloads/memorylake-qwenwork.zip" qwenwork-plugin
```

Tell the user to import `~/Downloads/memorylake-qwenwork.zip` from
QwenWork's plugin settings (install from a local file), then continue with
step 4 once they confirm.

## 3. Clean up

The download is no longer needed:

```bash
rm -rf "$work"
```

## 4. Set up MemoryLake

The plugin needs the `memorylake` CLI, a login, and a config file. Check
whether this machine already has them (another MemoryLake plugin may have set
it up):

```bash
{ command -v memorylake || ls ~/.memorylake/bin/memorylake ~/.local/bin/memorylake; } 2>/dev/null
ls ~/.memorylake/harness/config.md 2>/dev/null
```

If both exist, setup is already done; say so. Otherwise run the setup now:
read `~/.qwenworkcn/plugins-custom/memorylake/skills/memorylake-init/SKILL.md`
and follow it. (This conversation started before the plugin existed, so its
skills are not in your skill list; read the file directly.)

## 5. Tell the user

- MemoryLake is installed (or upgraded), and which setup steps were needed.
- **Start a new conversation** to use it: QwenWork loads plugins when a
  conversation starts, so this one runs without MemoryLake.
- From then on, every message reminds you to search MemoryLake first, and --
  if conversation sync is on -- every turn is saved to MemoryLake.
- If anything misbehaves, ask you to run the MemoryLake status check (the
  memorylake-status skill).
