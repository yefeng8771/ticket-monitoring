# Public UI Release & Alignment Process

This is the fixed cadence for every UI/design wave and every public release. It exists so README, screenshots, Release notes, package assets and commit history always tell one story.

## 1. Canonical copy (single source of truth)

The opening blockquote of `README.md` / `README_EN.md` is the original introduction and must not be re-positioned or extended:

```markdown
> 自托管的多渠道机票价格监控：五平台明细采集 → 钉钉图文推送 → 达标四层强提醒。
> 国内航线与国际航线（五洲目的地）同一套采集-判定-推送链路。
> 数据留在本机，配置全在网页，开源免费。
```

```markdown
> Self-hosted multi-channel flight price monitoring: 5-platform fare collection →
> rich DingTalk group reports → 4-layer urgent alerts when your target price hits.
> Domestic and international routes (destinations across five continents) run
> through the same collection → judging → push pipeline.
> Your data stays on your machine. Everything is configured in the browser. Free & open source.
```

Rules:
- No hard-coded `Version` badge. The Release badge is the single version pointer: use `github/v/release?display_name=release` so it follows the Release name (the constant `v1.0` tag is not a version).
- No internal round jargon (`r348`, “production probe”, etc.) in public copy.
- CN/EN section order, screenshot order, feature counts and claims stay in parity.
- The Release body starts with the canonical one-paragraph intro; version, gate counts, source SHA and SHA256 follow it. Do not rewrite the intro per release.
- Feature facts must match the shipped build: 5 monitor tabs, 4 config partitions, `SHA256SUMS.txt`, actual platform count/sizes.

## 2. Every UI wave (fixed rhythm)

1. **Deep-check GitHub**: `git fetch origin --prune`; read `origin/main`, latest Release name/body/assets, README/EN and screenshots. Record the remote SHA/version and compare with local. Never design against stale visuals.
2. **Five concurrent audits**: config cards/settings rails, filter/table workbench, overlays (modals/popovers/savebar/toasts), global text clipping/overflow, buttons/actions/touch. Each audit must return viewport, selector, rects and file:line.
3. **Implement** the P0/P1 findings; do not add new decorative scope. Keep one canonical action per job and one page identity.
4. **Add a gate for every fixed defect**, at the viewport where it was found (390/671/768/1024/1280/1360/1512/1920). A fix without a gate is not done.
5. **Bake docs**: regenerate `docs/screenshots`, rebuild `docs/site/index.html`, update README/EN feature counts and alt text, and add `docs/release-notes-v<version>.md`.
6. **Verify pixels**: Playwright light/dark at the affected widths, zero pageerror, no horizontal overflow, no text/button intersections. Compare the rendered page against the screenshot/initial intro standard.
7. **Commit explicitly**: one release commit per version — code, tests, screenshots, README/EN counts, version bump and `docs/release-notes-v<version>.md` together. No follow-up `docs:` count/wording commits; squash those into the release commit before pushing. Do not commit partial parallel-session work. Do not rewrite unrelated history.

## 3. Public release cadence

1. **Freeze** parallel writers; confirm `webui.py`, backend and tests are the same coherent state. Do not build from a moving worktree.
2. **Integrate** the complete watch/feature backend, tests and pins. Run:
   - `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest tests/ -q`
   - `python docs/uitest.py`
   - only then bump the version in `main.py`, its version gate and `docs/release-notes-v<version>.md`.
3. **Commit** the single release commit and push `main` fast-forward. Keep the public history at one commit per version: fixups/counts/docs found after the commit are squashed into it before push, not appended as new commits. Never force-push unrelated history; a repo-hygiene rewrite must be an explicit operation with a backup branch and a tree-equality check (see §5).
4. **Trigger** `.github/workflows/release-build.yml` (`workflow_dispatch`) on the exact pushed SHA. Reject artifacts whose run `head_sha` differs.
5. **Verify** four zips: package root layout, no config/data/logs/user_data/ghtoken, packaged executable `--version` equals the release version, and SHA256 values.
6. **One upload per release** under the existing `v1.0` constant tag: the four zips plus one `SHA256SUMS.txt`. Replace the previous set only after the new set is verified; never leave intermediate folders or duplicate per-file sha files in `dist_package/`.
7. **Update Release** name/body from the canonical intro + current version/counts/source SHA/SHA256. Keep the tag name constant, but **move `v1.0` to the exact verified SHA last** (after assets/body) and verify `main.py` at the tag carries the current version — the Release page's "Source code" link resolves through the tag, not HEAD.
8. **Run** `python docs/release_align_check.py` until PASS; it now asserts tag target version, CI green on HEAD, screenshot tracking, zero-byte assets and the live 8765 version. Then verify README badge, Release name/body/assets, screenshots and live 8765 all show the same version.

## 4. Definition of done

- README/EN canonical intro unchanged; no stale version/count/jargon.
- All referenced screenshots exist, are tracked, non-zero, current, width-capped on mobile, and match the shipped UI.
- Release name/body/assets/source SHA are version-consistent; four platform packages verified.
- `v1.0` tag target carries the current version; CI is green on the exact source SHA.
- pytest + uitest green with zero pageerror; the exact pushed SHA produced the assets.
- Local live console and GitHub public page show the same current design.
- History has exactly one commit per published version; `dist_package/` holds exactly one current release set.

## 5. Artifact & history hygiene

- `dist_package/` is a delivery surface, not a workshop: keep only `ticket-monitoring-win64.zip`, `ticket-monitoring-linux-x64.zip`, `ticket-monitoring-macos-arm64.zip`, `ticket-monitoring-macos-x64.zip` and `SHA256SUMS.txt`. Delete `_check*`, `_ci`, `release_*`, `_r*_dist`, `_rel_*` and ad-hoc `.sha256` files as soon as they are superseded.
- Release notes live in `docs/` and are tracked; `.gitignore`'s root-only `/RELEASE-*.md` rule must never swallow `docs/release-notes-*.md`.
- One commit per version. If repeated `docs:`/`release:` follow-ups already exist, compress them explicitly: create a backup branch, rebase only the recent release train, assert `git diff <old> <new>` is empty, re-point `main` and `v1.0`, then rebuild assets from the new SHA. Record the operation in the release notes.
- One GitHub Release, one Pages deployment, one asset set per version. Do not upload intermediate builds or re-bake identical screenshots just to create a new commit.
