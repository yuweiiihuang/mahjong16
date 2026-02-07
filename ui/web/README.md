# Mahjong Web UI

## Fast Iteration Loop

1. Start local dev server:
   - `npm run dev`
2. Make one small UI change.
3. Re-run repeatable visual smoke capture:
   - `npm run test:e2e:ui`
4. Check generated artifacts under:
   - `ui/web/artifacts/ui-e2e/latest` (from repo root)
   - Current anchor outputs:
     - `anchor-01-self-draw.png`
     - `anchor-01-self-draw.json`

## Merge Gate

- Run full gate before committing:
  - `npm run test:gate`
- This runs:
  - `lint`
  - `unit tests`
  - `build`
  - `repeatable e2e UI screenshots`

## E2E Notes

- The e2e runner is a project-local Playwright script:
  - `ui/web/scripts/run-ui-e2e.mjs` (from repo root)
  - `scripts/run-ui-e2e.mjs` (from `ui/web`)
- Default URL is `http://127.0.0.1:4173` when `UI_E2E_URL` is not set.
- Default anchor is `anchor-01-self-draw` (override with `UI_E2E_ANCHOR`).
- Output folder is reset on every run:
  - `ui/web/artifacts/ui-e2e/latest` (from repo root)
  - `artifacts/ui-e2e/latest` (from `ui/web`)
- If `playwright` is missing, install it in this package:
  - `npm install -D playwright`

---

# React + TypeScript + Vite

This template provides a minimal setup to get React working in Vite with HMR and some ESLint rules.

Currently, two official plugins are available:

- [@vitejs/plugin-react](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react) uses [Babel](https://babeljs.io/) (or [oxc](https://oxc.rs) when used in [rolldown-vite](https://vite.dev/guide/rolldown)) for Fast Refresh
- [@vitejs/plugin-react-swc](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react-swc) uses [SWC](https://swc.rs/) for Fast Refresh

## React Compiler

The React Compiler is not enabled on this template because of its impact on dev & build performances. To add it, see [this documentation](https://react.dev/learn/react-compiler/installation).

## Expanding the ESLint configuration

If you are developing a production application, we recommend updating the configuration to enable type-aware lint rules:

```js
export default defineConfig([
  globalIgnores(['dist']),
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      // Other configs...

      // Remove tseslint.configs.recommended and replace with this
      tseslint.configs.recommendedTypeChecked,
      // Alternatively, use this for stricter rules
      tseslint.configs.strictTypeChecked,
      // Optionally, add this for stylistic rules
      tseslint.configs.stylisticTypeChecked,

      // Other configs...
    ],
    languageOptions: {
      parserOptions: {
        project: ['./tsconfig.node.json', './tsconfig.app.json'],
        tsconfigRootDir: import.meta.dirname,
      },
      // other options...
    },
  },
])
```

You can also install [eslint-plugin-react-x](https://github.com/Rel1cx/eslint-react/tree/main/packages/plugins/eslint-plugin-react-x) and [eslint-plugin-react-dom](https://github.com/Rel1cx/eslint-react/tree/main/packages/plugins/eslint-plugin-react-dom) for React-specific lint rules:

```js
// eslint.config.js
import reactX from 'eslint-plugin-react-x'
import reactDom from 'eslint-plugin-react-dom'

export default defineConfig([
  globalIgnores(['dist']),
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      // Other configs...
      // Enable lint rules for React
      reactX.configs['recommended-typescript'],
      // Enable lint rules for React DOM
      reactDom.configs.recommended,
    ],
    languageOptions: {
      parserOptions: {
        project: ['./tsconfig.node.json', './tsconfig.app.json'],
        tsconfigRootDir: import.meta.dirname,
      },
      // other options...
    },
  },
])
```
