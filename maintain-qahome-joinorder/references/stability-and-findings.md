# Join Order Stability & Findings

Characterization from multi-run experiments (4 builds × 3 runs, all FULLSCAN, on func45). Use this when asked "is the test stable", "how many runs", "why did plans change", or when interpreting `INVALID_QUERY_PLAN`.

## Statistics determinism is the foundation
- `cubrid optimizedb` gathers **sampled** stats → large-table cardinality estimates jitter run-to-run for identical data (e.g. `cast_info` est. 36,087,825 vs 36,073,830). On cost-boundary queries this **flips the chosen plan within the same build** (~5 flip-floppers: 19d/20b/29b/8a/9d under sampling).
- `UPDATE STATISTICS … WITH FULLSCAN` gives **exact, identical** cardinalities across runs → **113/113 physical-plan stability** within a build. This is why the writer uses FULLSCAN. (A `NULL`/changed plan within one build almost always means non-FULLSCAN stats, not an engine change.)
- Sampled-vs-FULLSCAN is itself a huge plan difference (~48/113 queries change plan between the two stats methods) — **never compare a sampled run against a FULLSCAN run** for plan-diff; it's methodology contamination, not an engine change.

## Timing stability (within-build, FULLSCAN, func45)
- **Build-level total: ~2–3% CV** (highly reproducible) — this is what makes build-vs-build comparison trustworthy.
- Per-query: **median ~1.6% CV; ~55% of queries < 2%, ~74% < 5%**, but a ~13% tail > 10% CV.
- The noisy tail is a **fixed, query-specific set, consistent across builds**, and it is **execution-time / buffer-cache I/O sensitivity**, NOT plan instability or random per-run noise. Genuinely noisy (abs. variance that matters): **23a/23b (CV up to 42%), 6d/6f, 7c, 8d, 15d, 13d** (also 12b/13b/13c moderate). Trivially "noisy" (tiny abs.): 1b/1c/1d, 7a, 13a (sub-100 ms). The noisy set shares the SAME plan/operators as stable queries — they are just the longer, scan-heavier ones whose working set isn't fully kept resident by one warmup.
- Run-position effect: the first reuse run is only ~2–3% slower (marginal cold buffer). Median-of-N absorbs the "one slow run of three" pattern, which is why the build total stays 2–3%.

## Single-run sufficiency
- One run/build is fine for **build-level central performance** and for catching **large** regressions, but a single run's per-query value carries the full run-to-run noise → a single-run ±5% per-query verdict mis-flags the noisy tail.
- For reliable per-query comparison, prefer **per-query medians across runs**; ~6–9 runs pins the build aggregate tightly. The production single-shot benchmark (no warmup, 1 run, compare-vs-fixed-CSV) is coarser than cptp (warmup + median).
- The per-query timeout cap is a runaway safety net, not a regression gate — regression magnitude comes from recorded times + the viewer's ±5% classification.

## Real finding: 2248→2251 optimizer regression
On a clean all-FULLSCAN matrix (2245→2248→2251→2255), with **statistics identical across builds** (so any plan change is purely the engine):
- 2245→2248: **0** real plan changes; **2248→2251: 28** real plan changes; 2251→2255: 0.
- Nature: join *order* unchanged; the **2251 optimizer chooses different secondary indexes** on the large fact tables (`movie_info`, `movie_companies`, `movie_keyword`) — an index access-path costing change.
- Impact: net **+17.7%** on the 28 queries — severe regressions in the **22 and 28 query families** (sub-second → multi-second; e.g. 22d 0.45 s→9.2 s, 14b 0.058 s→1.47 s) partly offset by gains (15c −86%, 12a −65%, 23 family). A genuine performance regression worth a JIRA, narrowable to the exact commit with an intermediate build.

## Interpreting `INVALID_QUERY_PLAN`
- Real only when comparing **same stats method** (FULLSCAN-vs-FULLSCAN) against the **pinned baseline reference** (oldest valid run of the baseline build). A high count usually means either sampled-vs-FULLSCAN contamination or the baseline reference is on a different machine/method. A first run with no prior baseline-build reference flags nothing.
- Cross-check a slower/faster verdict against `INVALID_QUERY_PLAN`: a real plan change corroborates a regression; a big timing swing with an unchanged plan is likely the cache/I-O noisy tail.
