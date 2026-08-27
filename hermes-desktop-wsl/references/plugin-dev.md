# Desktop Plugin Development

## SDK surface (only these import)
```js
import { atom, cn, host, haptic, usePluginI18n, useValue } from '@hermes/plugin-sdk'
import { jsx, jsxs } from 'react/jsx-runtime'
```
- `host.state.*` — readonly atoms (`activeSessionId`, `cwd`, `gateway`, `model`, `profile`, `viewport`).
- `host.request(method, params)` — gateway JSON-RPC.
- `host.navigate(path)` — open an in-app route (e.g. `/artifacts`).
- `host.notify({ kind, message })`.
- `ctx.register({ id, area, order?, render?, data? })` — panes, statusBar.right/left, PALETTE_AREA, etc.
- `ctx.i18n.register({ en: {...}, ja: {...} })` — plugin-local strings.
- `ctx.storage.get/set/remove` — namespaced persistence.
- State: `atom(initial)` + `useValue(atom)` (NOT React useState — the file is not compiled).

## Pane registration
```js
ctx.register({
  id: 'pane', area: 'panes', title: 'Preview',
  data: { placement: 'right', width: '420px' },
  render: () => jsx(MyPane, {})
})
```

## Artifacts caveat (verified in source)
Artifacts are stored in `apps/desktop/src/store/artifacts.ts` `$artifactRegistry` nanostore,
populated from the rendered transcript. There is NO gateway RPC and NO dashboard endpoint that
exposes them, so a plugin cannot read the registry from outside the app's JS context. To surface
generated artifacts, call `host.navigate('/artifacts')` — the native page already renders HTML/SVG/
code in a sandboxed right-rail. Do NOT re-implement the sandbox renderer inside a plugin.

## Verification
```bash
node --check ~/.hermes/desktop-plugins/<id>/plugin.js     # syntax
# launch app, then:
grep -riE "<id>.*fail|failed to load.*<id>" ~/.hermes/logs/   # SDK logs ONLY on failure
```
The headless `hermes serve` backend logs "web UI disabled — use `hermes dashboard`" — BENIGN.
The desktop app IS the UI; that 404 is expected, not a crash.

## Pitfalls
- JSX syntax will NOT parse — use `jsx('div', { children: ... })`.
- Never hardcode colors; use theme vars (`var(--ui-text-secondary)`, `var(--ui-accent)`).
- `hermes config set hooks.outbound "[...]"` coerces nested lists to strings — edit config.yaml directly or via yaml round-trip.
