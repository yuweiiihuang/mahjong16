# Table V2 Layout Contract

The V2 table uses a fixed `1600 x 1000` scene. Visual scaling belongs in
`TableViewport`; tile positions stay in scene coordinates.

## Zones

- Hand zones own concealed hand and drawn tiles.
- Discard zones own river tiles only.
- Meld-flower zones own exposed melds and flowers.
- Center console is a forbidden overlap target for discard tiles.

Zone ownership is encoded in `src/components/table-v2/layout.ts` through
`collectLayoutBoxes()` and `findLayoutViolations()`.

## Pass Criteria

- Stress anchor `anchor-v2-stress` must report zero layout violations.
- Each rendered tile must stay inside its owner zone.
- River tiles must not overlap the center console.
- River display is capped at 24 visible discards per seat: 6 columns x 4 rows.
  Older discards should move to history/log views instead of shrinking table
  readability.
- Discard growth must use fixed slots and must not move hand, meld, flower, or
  console zones.
- E2E captures must include `*-layout-report.json`; non-empty `violations`
  means the run failed even if screenshots were produced.

## Recommended Gate

```bash
cd ui/web
npm run test -- src/components/table-v2/layout.test.ts src/components/table-v2/TableV2.test.tsx
UI_E2E_ANCHOR=anchor-v2-stress UI_E2E_LAYOUT=v2 npm run test:e2e:ui
```
