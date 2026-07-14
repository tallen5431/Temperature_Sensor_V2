# Release / installer readiness checklist

The one-click installer pipeline ([`.github/workflows/release.yml`](../.github/workflows/release.yml))
is wired up and the Linux build is verified end-to-end. Before you rely on it to
distribute the hub, work through the items below. They're ordered by what matters
most.

## Status today

| Piece | State |
| --- | --- |
| Linux `.tar.gz` bundle | **Verified** — built, launched, served the dashboard, accepted an ingest, and created its data in the per-user dir (`~/.local/share/Setpoint`). |
| Windows `.exe` installer (Inno Setup) | **Authored, not yet run.** Builds on the `windows-latest` runner; not executed on a real Windows machine. |
| macOS `.dmg` (`.app` bundle) | **Authored, not yet run.** Builds on the `macos-latest` runner; not executed on a real Mac. |
| Code signing / notarization | **Off** until the cert secrets are set (see `RELEASE_SIGNING.md`). Installers build **unsigned** meanwhile. |

## 1. Do a build dry-run (do this first)

Confirm all three installers build green on the runners. Push a throwaway tag,
watch **Actions → release**, then delete it:

```bash
git tag v0.0.0-test && git push origin v0.0.0-test
# … watch the three jobs go green …
# clean up the test tag and the release it created:
git push --delete origin v0.0.0-test
# then delete the "v0.0.0-test" release from the repo's Releases page
```

> Note: this dry-run could **not** be run from the Claude Code sandbox — that
> environment only allows pushing the working branch, not tags, and the GitHub
> app token can't dispatch workflows. Run it from your own checkout.

## 2. Test the installers on real machines

CI proves the installers **build**, not that they **install and run** on Windows
and macOS. On a real machine for each OS, download the artifact from the dry-run
release and verify:

- [ ] Installs without an admin password (per-user install).
- [ ] Launches from the Start menu / Applications and the dashboard opens in the
      browser at <http://localhost:8088>.
- [ ] A reading ingests and shows up; **Load demo data** works.
- [ ] Data lands in the per-user directory (`%LOCALAPPDATA%\Setpoint` /
      `~/Library/Application Support/Setpoint`), and survives a relaunch.
- [ ] Uninstall works (Windows: Apps; macOS: drag to Trash).

## 3. Turn on code signing (removes the scary OS prompts)

Unsigned installers work but show a one-time "unverified app" warning
(documented in `INSTALL.md`). To remove it, buy certificates and set the GitHub
secrets — full instructions in [`RELEASE_SIGNING.md`](RELEASE_SIGNING.md):

- [ ] **Windows Authenticode cert** (OV ≈ $200/yr, or **EV** ≈ $300–400/yr).
      EV is worth it: an OV cert still triggers SmartScreen "unknown publisher"
      until the cert earns download **reputation**; EV bypasses that from day one.
- [ ] **Apple Developer account** ($99/yr) → a **Developer ID Application**
      certificate **and** an App Store Connect API key for **notarization**.
      Without notarization macOS still warns; with it, the app opens cleanly.

The next tagged release after the secrets are set is automatically signed — no
code change needed.

## 4. Polish (nice-to-have, not blocking)

- [ ] **App icons.** The exe, the macOS `.app`, and the installer currently use
      no custom icon (`packaging/temperature_hub.spec` has `icon=None`; the `.iss`
      has no `SetupIconFile`). Add `packaging/icon.ico` (Windows) and
      `packaging/icon.icns` (macOS), then set `icon=` in the spec's `EXE(...)` and
      `BUNDLE(...)`, and `SetupIconFile=..\icon.ico` in `setpoint.iss`.
- [ ] **Installer EULA.** The Windows installer shows `LICENSE`. If you want
      click-through acceptance of the end-user terms instead, point
      `LicenseFile` in `setpoint.iss` at `..\..\docs\EULA.md` (convert to
      `.txt`/`.rtf` — Inno wants plain text or RTF).
- [ ] **Version stamping.** The release version comes from the git tag; keep it
      in step with `core/version.py` `HUB_VERSION` so the About/Diagnostics
      version matches the installer filename.
- [ ] **Auto-update.** There is no in-app updater; users re-download a newer
      installer (their data is preserved). Fine for now — revisit if you ship
      often.

## 5. First real release

Once 1–3 are done:

```bash
git tag v2.4.0 && git push origin v2.4.0
```

The workflow builds, signs, notarizes, and publishes the three installers to a
GitHub Release. Point the product listing and `README` at that Releases page.
