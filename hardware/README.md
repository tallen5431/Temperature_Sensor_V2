# Hardware sources

The board design lives here. Put each revision in its own folder:

```
hardware/
  rev2/          ← the board that is built and bench-verified today
  rev3/          ← when you start it; see ../docs/REV3_NOTES.md
```

## Nothing needs exporting

KiCad's own file formats are plain-text S-expressions, not a binary blob, so the
design files **are** the readable artefact. There is no "export for review" step:
copy the project folder in and commit it.

## What to commit

| File | Why |
|---|---|
| `*.kicad_sch` | **The important one.** Components, values, nets, connections — the whole circuit. |
| `*.kicad_pcb` | Layout: board outline, placement, copper. Needed for anything physical — free area for new parts, pour under `U5`, where an LED lands relative to the enclosure. |
| `*.kicad_pro` | Project settings, so it opens as a project rather than loose files. |
| `*.kicad_sym`, `*.kicad_mod` | Only project-local symbols/footprints you drew yourself. |
| `sym-lib-table`, `fp-lib-table` | So those local libraries actually resolve on another machine. |

## What NOT to commit

Already handled by `.gitignore` at the repo root:

- `*-backups/`, `~*.*`, `*.bak` — KiCad's own autosaves and backup zips
- `*.kicad_prl` — per-user window/view state, pure churn
- `fp-info-cache` — regenerated on open
- `gerbers/`, `*.gbr`, `*.drl`, `*.step`, `*.wrl`, `*.net` — fabrication and 3D
  outputs. All regenerable from the sources, all large, and committing them
  invites the classic failure where the gerbers and the schematic disagree about
  which revision they are.

**One exception worth making:** when you send a board to fab, commit *that exact*
gerber zip once, in a folder named for the order (`rev2/fab/2026-07-jlcpcb.zip`)
and force-add it past the ignore rule. Then "what did I actually have made?" has
an answer that does not depend on remembering settings.

## Getting rev 2 in

From wherever the KiCad project currently lives:

```bash
mkdir -p hardware/rev2
cp -r /path/to/your/kicad/project/* hardware/rev2/
git add hardware/rev2 hardware/README.md .gitignore
git status            # confirm only sources are staged, no *-backups or gerbers
git commit -m "hardware: add rev-2 KiCad sources"
```

## Why this is worth doing beyond code review

The board you are about to certify currently exists in exactly one place: your
disk. The SDoC test report will reference a specific hardware revision, and the
FCC label names you as responsible party for that revision — so "which files were
the certified board?" needs an answer with a commit hash, not a filename with
`_final_v2` in it.
