# Validation

## Fast compile checks

- Run `ant dist` inside `~/cubrid-testtools-internal/qaresult_enhance` for a quick compile pass
- Use this for early feedback only; the real runtime tree is `~/qaresult_en`

## Runtime verification path

1. Deploy into `~/qaresult_en`
2. Restore env-specific files from the chosen `qaresult_en_*` snapshot
3. Run `ant` in `~/qaresult_en`
4. Restart `~/apache-tomcat-8.5.4`
5. Load the affected screen or endpoint

## Targeted regression checklist

- Function or summary changes:
  - summary page loads without falling into the global error page
  - build memo or summary-specific AJAX calls still resolve
- Performance changes:
  - base tables render
  - compare rows keep column alignment
  - memo or verified values persist and reload correctly
- Verify/fail-result changes:
  - filters persist across paging or fragment reload
  - no categories disappear because of global limits
  - show-all or large-result paths still honor safety caps
- Auto-refresh or handler changes:
  - missing file or empty directory cases stop retry loops cleanly
  - log output is informative without tight-loop spam

## Tests and limitations

- `ant junit-test` and `ant junit-report` exist, but many tests are legacy and depend on local runtime or database configuration
- Prefer targeted compile plus manual runtime verification unless the environment is already known-good for JUnit
