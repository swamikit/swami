# Parser change

Parser stays deterministic and stdlib-only (ADR-0004). IR is semantic-rich (ADR-0007).

## What changed
- Summary:
- Files touched (`tool/src/parser/*.py`):

## Patch types now supported
- [ ] Newly decoded patch(es):
- [ ] Newly decoded port(s) / default values:
- [ ] Placed-vs-library separation still holds (root field 14 = library, not document)

## Tests
- [ ] Unit tests added under `tool/tests/`
- [ ] Touch oracle still parses to ~25 placed nodes / ~44 edges
- [ ] Golden IR diff reviewed (semantic names preserved)

## Related
- **ADR:** docs/decisions/ADR-XXXX-
- **`NEEDS-VERIFY.md` entries unblocked:**
