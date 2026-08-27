/**
 * Preview Pane — NZ1Labs (Hermes v0.20.0 desktop plugin)
 *
 * Hybrid live-preview surface for the Hermes desktop app:
 *   • URL tab    — live iframe preview of a web-design dev server or an
 *                  iOS/Android app preview URL (moveable + collapsible pane).
 *   • Artifacts  — one-click open of the app's native Artifacts page, which
 *                  already renders generated HTML/SVG/code in a sandboxed
 *                  right-rail live preview (the v0.20.0 artifact feature).
 *
 * WHY a navigator, not an inline renderer: artifacts are an in-memory desktop
 * nanostore ($artifactRegistry) with NO gateway RPC — a plugin cannot read the
 * registry from outside the app's JS context. So we navigate to the native
 * /artifacts page (the canonical sandboxed renderer) instead of reimplementing it.
 *
 * Save as:  <hermes home>/desktop-plugins/preview-pane/plugin.js
 * Then:     ⌘K → "Reload desktop plugins"
 *
 * Plain ESM, loaded uncompiled. UI = jsx() calls. Only these imports resolve:
 *   @hermes/plugin-sdk, react, react/jsx-runtime
 */

import { atom, cn, host, haptic, usePluginI18n, useValue } from '@hermes/plugin-sdk'
import { jsx, jsxs } from 'react/jsx-runtime'

const ID = 'preview-pane'

const DEFAULT_URL = 'http://127.0.0.1:8788/'

// Plugin-local reactive state (documented atom/useValue pattern — NOT useState).
const tabAtom = atom('url') // 'url' | 'artifacts'
const urlAtom = atom(DEFAULT_URL)
const draftAtom = atom(DEFAULT_URL)
const collapsedAtom = atom(false)

function Toolbar({ onOpenArtifacts }) {
  const t = usePluginI18n(ID)
  const tab = useValue(tabAtom)
  const collapsed = useValue(collapsedAtom)

  if (collapsed) {
    return jsx('button', {
      className: cn(
        'inline-flex items-center gap-1 px-2 py-1 text-[0.75rem] rounded',
        'text-(--ui-text-tertiary) hover:bg-(--chrome-action-hover) hover:text-foreground'
      ),
      type: 'button',
      onClick: () => collapsedAtom.set(false),
      children: t('expand')
    })
  }

  return jsxs('div', {
    className: 'flex items-center gap-1',
    children: [
      jsx('button', {
        className: cn(
          'rounded px-2 py-1 text-[0.7rem]',
          tab === 'url'
            ? 'bg-(--ui-accent) text-white'
            : 'text-(--ui-text-tertiary) hover:bg-(--chrome-action-hover)'
        ),
        type: 'button',
        onClick: () => tabAtom.set('url'),
        children: t('tabUrl')
      }),
      jsx('button', {
        className: cn(
          'rounded px-2 py-1 text-[0.7rem]',
          tab === 'artifacts'
            ? 'bg-(--ui-accent) text-white'
            : 'text-(--ui-text-tertiary) hover:bg-(--chrome-action-hover)'
        ),
        type: 'button',
        onClick: () => {
          tabAtom.set('artifacts')
          onOpenArtifacts()
        },
        children: t('tabArtifacts')
      }),
      jsx('button', {
        className: cn(
          'ml-auto inline-flex h-7 w-7 items-center justify-center rounded',
          'text-(--ui-text-tertiary) hover:bg-(--chrome-action-hover) hover:text-foreground'
        ),
        type: 'button',
        title: t('collapse'),
        onClick: () => collapsedAtom.set(true),
        children: '–'
      })
    ]
  })
}

function UrlView() {
  const t = usePluginI18n(ID)
  const url = useValue(urlAtom)
  const draft = useValue(draftAtom)
  const cwd = useValue(host.state.cwd)

  const go = () => {
    haptic('tap')
    const next = draft && draft.trim() ? draft.trim() : DEFAULT_URL
    urlAtom.set(next)
    ctx_storage.set('url', next)
    host.notify({ kind: 'info', message: t('navigating', next) })
  }

  return jsxs('div', {
    className: 'flex h-full flex-col gap-2 p-2 text-sm',
    children: [
      jsxs('div', {
        className: 'flex items-center gap-2',
        children: [
          jsx('input', {
            className: cn(
              'flex-1 rounded border border-(--ui-stroke-secondary) bg-transparent px-2 py-1',
              'text-(--ui-text-primary) placeholder:text-(--ui-text-quaternary)'
            ),
            placeholder: t('placeholder'),
            value: draft,
            onChange: e => draftAtom.set(e.target.value)
          }),
          jsx('button', {
            className: cn(
              'rounded bg-(--ui-accent) px-2 py-1 text-[0.75rem] text-white',
              'hover:opacity-90'
            ),
            type: 'button',
            onClick: go,
            children: t('go')
          })
        ]
      }),
      jsx('div', {
        className: 'min-h-0 flex-1 overflow-hidden rounded border border-(--ui-stroke-secondary)',
        children: jsx('iframe', {
          src: url,
          className: 'h-full w-full border-0 bg-white',
          sandbox: 'allow-scripts allow-same-origin allow-forms allow-popups',
          title: t('paneTitle')
        })
      }),
      jsx('div', {
        className: 'text-[0.6875rem] text-(--ui-text-quaternary)',
        children: t('cwd', cwd || '—')
      })
    ]
  })
}

function ArtifactsView() {
  const t = usePluginI18n(ID)
  const sessionId = useValue(host.state.activeSessionId)

  return jsxs('div', {
    className: 'flex h-full flex-col items-center justify-center gap-3 p-4 text-center',
    children: [
      jsx('div', {
        className: 'text-[0.8rem] text-(--ui-text-tertiary)',
        children: t('artifactsHint')
      }),
      jsx('button', {
        className: cn(
          'rounded bg-(--ui-accent) px-3 py-1.5 text-[0.8rem] text-white',
          'hover:opacity-90'
        ),
        type: 'button',
        onClick: () => {
          haptic('tap')
          host.navigate('/artifacts')
          host.notify({ kind: 'info', message: t('opened') })
        },
        children: t('openArtifacts')
      }),
      sessionId
        ? jsx('div', {
            className: 'text-[0.6875rem] text-(--ui-text-quaternary)',
            children: t('session', String(sessionId))
          })
        : null
    ]
  })
}

function PreviewPane() {
  const tab = useValue(tabAtom)
  return jsxs('div', {
    className: 'flex h-full flex-col',
    children: [
      jsx('div', { className: 'border-b border-(--ui-stroke-secondary) p-1', children: jsx(Toolbar, { onOpenArtifacts: () => host.navigate('/artifacts') }) }),
      jsx('div', { className: 'min-h-0 flex-1', children: tab === 'url' ? jsx(UrlView, {}) : jsx(ArtifactsView, {}) })
    ]
  })
}

let ctx_storage = null

export default {
  id: ID,
  name: 'Preview Pane',
  register(ctx) {
    ctx_storage = ctx.storage
    const saved = ctx.storage.get('url')
    if (saved) {
      urlAtom.set(saved)
      draftAtom.set(saved)
    }

    ctx.i18n.register({
      en: {
        paneTitle: 'Preview',
        tabUrl: 'URL',
        tabArtifacts: 'Artifacts',
        placeholder: 'https://… or http://127.0.0.1:PORT/',
        go: 'Go',
        collapse: 'Collapse',
        expand: 'Expand',
        navigating: url => `Preview → ${url}`,
        cwd: cwd => `cwd: ${cwd}`,
        artifactsHint: 'Generated HTML / SVG / code render in the app’s sandboxed Artifacts page.',
        openArtifacts: 'Open Artifacts page',
        opened: 'Artifacts page opened',
        session: id => `session: ${id}`,
        chipTip: 'Preview Pane'
      }
    })

    // Layout pane — draggable to any edge, collapsible like core panes.
    ctx.register({
      id: 'pane',
      area: 'panes',
      title: 'Preview',
      data: { placement: 'right', width: '420px' },
      render: () => jsx(PreviewPane, {})
    })

    // Statusbar chip.
    ctx.register({
      id: 'chip',
      area: 'statusBar.right',
      order: 135,
      render: () => jsx('button', {
        className: cn(
          'inline-flex h-full items-center gap-1 px-1.5 text-[0.6875rem]',
          'text-(--ui-text-tertiary) hover:bg-(--chrome-action-hover) hover:text-foreground'
        ),
        type: 'button',
        title: 'Preview Pane',
        onClick: () => {
          haptic('tap')
          host.navigate('/artifacts')
          host.notify({ kind: 'info', message: 'Preview pane ready' })
        },
        children: ' preview'
      })
    })
  }
}
