# Output quality review

Branch: `review/output-quality`, based on `main` at `cbc13f7` (this repository has no `master`). Changes are not merged or pushed.

## Review checkpoints

1. Contracts: optional source/cleaned-image provenance and explicit quality findings.
2. Cleanup: source analysis cache, flat-surface reconstruction, masked photographic repair, bounded failure handling and saved intermediate results.
3. Typography and layouts: real font measurements, consistent line height, balanced templates and composition checks.
4. Studio: live option cards, Original / Clean background / Final comparison, actionable quality details and clear editing/export controls.
5. Validation and presentation: representative image benchmark, real-provider/browser checks, before/after examples and measured timings.

Each checkpoint is committed separately. Review with `git log main..review/output-quality --oneline` and `git diff main...review/output-quality`. Returning to `main` restores the accepted code baseline; runtime designs are separate from Git.

The acceptance standard is a visibly clean background, editable text that fits, an intact library logo, and a useful final export. Tests support that standard; they do not establish photographic perfection. Review findings remain visible when automated checks cannot establish a clean result.
