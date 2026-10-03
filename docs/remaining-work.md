# What is still outstanding

Audited against NEXA.md's owned-file lists (§18, §21.2–§26.2). Everything not
listed here exists and is tested.

The point of this page is to separate three very different kinds of "not done":
work nobody has written, work that needs hardware or a human, and work that is
deliberately deferred.

## Not uploaded: Member 6 (desktop UI)

The only work package still missing in full.

| Expected by §26.2 / §18 | What it is |
|---|---|
| `src/nexa/ui/` | application shell, dashboard, meeting, review, schedule, employees, preview, audit and settings screens |
| `src/nexa/i18n/` | Arabic/English UI strings and RTL layout switching |
| `src/nexa/themes/` | light and dark themes |
| `apps/nexa_desktop.py` | `Nexa.exe` entry point |
| `resources/translations/`, `resources/icons/`, `resources/themes/` | UI assets |
| `tests/e2e/` | end-to-end screen tests |
| `scripts/build_windows.py` | PyInstaller build for both executables |
| `docs/demo-script.md` | the demo walkthrough; needs the UI to exist |

Nothing has been stubbed out for them. An empty package created by the wrong
member is a merge conflict waiting to happen, and §19 rule 7 puts each directory
behind one owner. Everything Member 6 needs to call already exists and is
tested — see the public interfaces in the README.

## Needs hardware or a human, not code

These cannot be finished by writing software, so they are not "missing files":

* **Real Windows audio capture** (§22.1). `src/nexa/audio/` is complete and unit
  tested, but WASAPI loopback, device enumeration and a 60–90 minute recording
  have never run against real hardware. Member 2 flagged this themselves.
* **The ASR benchmark dataset** (§22.5, `tests/audio/`). The plan requires real
  recordings in Arabic, English, mixed, noisy and long categories, spoken by the
  team. `scripts/prepare_dataset.py` and `docs/recording_prompts.json` are the
  tooling for producing it; the audio itself has to be recorded.
* **A real ASR run.** `scripts/download_models.py --asr whisper-medium` fetches
  the weights; no model has been downloaded, so transcription accuracy is
  unmeasured and §15.1's model choice is still open.
* **A real LLM run.** Same for `--llm`. Member 3's extractor currently runs
  against a mock runtime, so extraction precision is unmeasured against the
  §39.2 fixtures with a real model.
* **The Gmail account and OAuth client** (§24.4, team/admin setup). The code is
  complete and the flow is tested against a faked `InstalledAppFlow`; only the
  live round trip to accounts.google.com is unverified.
  `python scripts/setup_gmail.py status` says exactly what is missing, and
  [email.md](email.md) has the 10-minute setup.
* **PyInstaller packaging** (§26.2). Neither executable has been built.

## Deliberately deferred

* **`resources/extraction_prompts/`** (§23.2). Member 3's system prompt and
  few-shot library live in `intelligence/prompts.py` instead of as resource
  files. Moving them out is worth doing for the same reason the email templates
  are resources — prompt wording can then be corrected without a code change,
  and `PROMPT_VERSION` already exists to track it — but the golden-file suite
  pins the current prompt, so the move needs their sign-off rather than mine.
* **`tests/integration/member2/` and `tests/integration/member3/`** (§22.2,
  §23.2). Both members' suites are unit-only. The seams they would have covered
  are tested from the other side instead:
  `tests/integration/test_transcript_to_actions.py` covers transcript →
  actions, and `tests/integration/test_cross_member.py` covers the rest. Real
  per-member integration tests still want real audio and a real model.
* **Early-event smart reminders** beyond the implemented rule set (§33's
  "early event protection") have one policy; §33 hints at more tuning once the
  team sees real meeting times.

## Fixed along the way

Recorded so nobody re-reports them:

* The Member 1 + Member 3 merge had emptied `tests/conftest.py`, so **0 of 366
  tests could run**. See the repair commit.
* Three silent bugs in Member 3's date layer and a mock runtime that ignored its
  input — [date-rules.md](date-rules.md).
* Five broken joins when Member 5 landed, including a private copy of the frozen
  contracts — [integration.md](integration.md).
* `ExtractionService` (§23.2, §23.3) did not exist, so a `Transcript` could not
  become action candidates at all.
* `DuplicateService.merge` (§23.3) did not exist, so the Review screen's
  `[ Merge ]` button had nothing to call.
* English deadlines resolved **backwards** — "by Friday" on a Thursday came back
  as the previous Friday — and `next Monday` resolved to nothing.
* `scripts/download_models.py` (§18) did not exist, so there was no documented
  way to obtain any model.

## How to check this page is still true

```bash
python -m pytest                      # the whole suite, offline
python scripts/download_models.py --list
python scripts/setup_gmail.py status
python apps/nexa_worker.py --status
```

The structural audit behind this page is a short script over NEXA.md's owned-file
lists; re-run it after any merge.
