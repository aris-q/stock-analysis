# Two-Version Git Workflow (Prod + Dev, Separate Folders)

A reusable setup for keeping a stable "prod" version and an experimental "dev"
version of a project without branch-switching accidents. Works for any repo,
especially ones where the app writes its own data files into the project
folder (databases, JSON caches, logs) — that's exactly the situation that
makes switching branches *in place* dangerous: git has to reconcile those
data files on every checkout, and it's easy to end up on the wrong branch
without noticing.

**The core idea:** one GitHub repo, two branches (`main` and `dev`), but
**two separate folders on your machine** — one pinned to each branch. You
never `git checkout` between them; you `cd` between them instead.

```
C:\Code_Git\<project>          →  branch: main   (stable, what you actually run)
C:\Code_Git\<project>-dev      →  branch: dev    (experiments, safe to break)
```

---

## 1. One-time setup

Replace `<repo-url>` and `<project>` with your own.

```bash
cd C:\Code_Git
git clone <repo-url> <project>-dev
cd <project>-dev
git checkout -b dev
git push -u origin dev
```

If the push is rejected with a 403 / permission error, your machine has
cached the wrong GitHub login. Fix it one of two ways:
- Push once from **GitHub Desktop** instead (it uses its own stored login), or
- Clear the cached credential: Windows **Credential Manager** → Windows
  Credentials → remove the `git:https://github.com` entry → run the push
  again and log in as the right account.

**Recreate anything the clone doesn't bring over** (these are normally
gitignored on purpose — secrets and local environments don't belong in git):
```bash
# .env — copy your API keys / secrets from the prod folder, don't commit them
# venv — make your own local virtual environment
python -m venv venv
venv\Scripts\pip install -r requirements.txt
```

From now on:
- Work on experiments in `<project>-dev`, always on the `dev` branch.
- Run the real thing from `<project>` on `main`.
- Never `git checkout main` inside the dev folder or vice versa — that
  defeats the whole point. Each folder stays on its one branch permanently.

---

## 2. Daily dev loop

```bash
cd C:\Code_Git\<project>-dev
git pull origin dev              # get anything you pushed from elsewhere
# ...make changes...
git add <specific files>          # avoid `git add -A` — see the data-file warning below
git commit -m "describe the change"
git push origin dev
```

---

## 3. Publishing dev → prod

### Step A — before merging, check what's actually in the diff
```bash
git diff main..dev --stat
```
Look for anything that is **runtime data, not code** (databases, generated
JSON, logs, caches). If your app writes to files inside the repo folder
while running, a dev-session's test data can accidentally get committed —
you do NOT want that overwriting prod's real data on merge. If you see
data files in the diff that shouldn't move to prod, unstage/revert just
those files on the dev side before merging:
```bash
git checkout main -- path/to/that/data/file.json
git commit -m "keep prod data file out of this merge"
```

### Step B — merge (pick one)

**Option 1 — quick, no review (fine for a solo project, low-risk changes):**
```bash
cd C:\Code_Git\<project>-dev
git checkout main
git pull origin main
git merge dev
git push origin main
```

**Option 2 — via Pull Request (recommended once changes matter):**
```bash
cd C:\Code_Git\<project>-dev
git push origin dev
gh pr create --base main --head dev --title "..." --body "..."
```
Review the diff on GitHub (or hand it to an assistant/colleague), click
**Merge**, then continue to Step C.

### Step C — update the prod folder
```bash
cd C:\Code_Git\<project>
git pull origin main
```
Restart the app so it picks up the new code.

---

## 4. Snapshots you never intend to touch again → use a tag, not a branch

If you just want a frozen point you can return to (not something you'll
keep developing), don't leave a branch alive for it — tag the commit
instead. Tags don't show up as something a GUI tool can accidentally check
out into, and they cost nothing to keep around.

```bash
git tag v1-stable <commit-hash>
git push origin v1-stable
```

To resurrect a tagged snapshot later into a working copy:
```bash
git checkout -b recovery-branch v1-stable
```

---

## 5. Quick reference — command cheat sheet

| Task | Command |
|---|---|
| Clone repo into a second folder | `git clone <url> <folder>` |
| Create + switch to a new branch | `git checkout -b <branch>` |
| Push a new branch, set upstream | `git push -u origin <branch>` |
| See what a merge would bring in | `git diff main..dev --stat` |
| Merge dev into main | `git checkout main && git merge dev` |
| Push a PR instead of merging locally | `gh pr create --base main --head dev` |
| Tag a snapshot | `git tag <name> <commit>` |
| List all branches (local + remote) | `git branch -a` |
| Check which branch you're on | `git status -sb` |
| Fix a rejected push (wrong cached login) | Push once via GitHub Desktop, or clear the credential in Windows Credential Manager |

---

## 6. The one habit that prevents most git accidents

**Before every commit, glance at the file list.** `git status` (or your
GUI's changed-files panel) should match what you think you just changed —
if you touched three Python files and the list shows twelve JSON data
files and no Python, stop and look before committing. This single glance
is what would have caught most git mishaps before they happened.
