# Docling Launcher — standing instructions

A Windows Tkinter front end for `docling convert`, built for **one owner who is not a
programmer**. Read `docs/RESUME_HERE.md` first — it is the current state and what is open.
`docs/KNOWLEDGE.md` holds the measurements and the traps. `TODO.md` is the status board.
The working procedure (commands, checklists) is the `docling-launcher` skill in
`.claude/skills/`.

---

## ⛔ 1 · Talk to the owner in plain words

They asked for this hard-coded: *"You should explain me in short, very simple words…
understandable for a non-technical person. Not in the code."*

- **No code in owner-facing text.** No file names, no function names, no flags, no
  snippets — not even "as extra detail at the end".
- **Lead with the answer**, then at most a line or two of why.
- Say plainly what is fixed, what is not, and what you are unsure of.
- Code comments, commit messages and `docs/` stay as technical as they need to be — the
  next model reads those.

**Red flag:** a paragraph aimed at the owner containing a backtick, a path or a word only
a programmer uses. Rewrite it before sending.

## ⛔ 2 · Build it, drive it, look at it — every time

Writing the code is a third of the job. Nothing is reported as working until:

1. the guards pass (`.venv\Scripts\python.exe -m unittest discover tests`),
2. the **exe is rebuilt** and its self-test run (`DOCLING_LAUNCHER_SELFTEST`), and
3. anything the owner will *see* has been rendered and **looked at** —
   `tools\snap_window.py <folder> light|dark`, then open the picture and read it.

Two of the last three faults were found this way and would not have been found by
reading: an empty strip on the Convert tab, and a self-test that overwrote the owner's
settings. **The exe must be newer than the change** — the build refuses while the
launcher is open, so check, never assume.

## ⛔ 3 · Never steal the screen, never touch the owner's data

- Test windows are **withdrawn**, or shown at 1 % opacity as a non-activating tool window
  (`tools/snap_window.py`). A real window on their screen interrupts their work.
- **Every script that drives the app overrides `APPDATA`.** The owner's
  `settings.json` was clobbered once; a proof run must never write it (`app._selftest`,
  read from the environment at the top of `__init__`).
- Their converted documents are theirs: write a new file beside the old one, never over
  it, and say exactly where it went.
- Never delete a Python installation, a model cache or an output folder without asking.

## ⛔ 4 · Defaults are the owner's call, and every change of one is versioned

Turning an ability on or off for every future conversion is **their decision**, not a
judgement call made while coding. When they make one:

1. change the default in `LauncherSettings`,
2. raise `constants.SETTINGS_VERSION` and add a one-time step in `from_dict` that moves
   an older file and sets `upgrade_note`,
3. the window logs that note at start and saves the file, so it happens once,
4. say it in the tooltip and the "How to use" text in their words, with the cost.

## ⛔ 5 · Measure before you claim, and quote the number

Every ability has a price in seconds and the owner pays it. Before recommending or
rejecting anything, run it on a real document and write the number down in
`docs/KNOWLEDGE.md`. "Should be better now" is not a result; "508 s → 82 s" is.

The same applies to the models' output: a table of numbers read out of a chart is a
**claim**, not data. Check it against the picture before trusting it — the chart model
invents values on engineering charts, which is why it is off by default and every table
it writes carries a warning line.

## ⛔ 6 · A fix is exactly as wide as the fault

Fix the reported case, then look for the same shape elsewhere — and say out loud what the
widest thing the change now does is. Do not widen a rule beyond what the report
justifies, and never remove working behaviour as a side effect.

**Write the guard in the same commit.** 92 guards exist because each of them was once a
fault the owner hit. A behaviour the owner has confirmed and nothing protects is the one
that breaks next week.

## ⛔ 7 · Keep the written record true

Whenever what is true changes, update `TODO.md`, `docs/RESUME_HERE.md` (rewrite the
block — it is a snapshot, not a diary) and `docs/KNOWLEDGE.md` in the **same commit**, and
the project memory. A wrong line is worse than a missing one, because it gets trusted.

Commit messages on this project are full prose: what was found, what was measured, what
was decided and by whom. They are the changelog.

## Conventions

- **Python 3.12 in `.venv`** — Docling's own environment, the one the launcher updates.
  Never install into the system Python.
- The **driver** (`assets/convert_tool.py`) is the single road into Docling. Asset
  scripts run inside `.venv`, import nothing from the launcher package, and ship inside
  the exe.
- Long patches: write a script with the Write tool and run it. The Bash tool mangles long
  heredocs (this has bitten repeatedly).
- The repository is **public**: no personal data, no user paths, no names in it.
