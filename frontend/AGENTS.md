<!-- BEGIN:nextjs-agent-rules -->
# This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` before writing any code. Heed deprecation notices.
<!-- END:nextjs-agent-rules -->

# House rules

Each of these exists because it was broken once. Keep them and the same bugs
stay fixed.

## Colour, size, spacing

**Every colour and size comes from `app/globals.css`.** No `bg-[#0b0f1a]`, no
`text-slate-600`, no `text-[11px]`. If the value you need isn't a token, add it
to `globals.css` first — that's what keeps the whole product re-skinnable from
one file.

The type scale stops at **12px**. Nothing smaller exists. If text needs to be
smaller than that, the layout is wrong, not the type.

Themes are written once as `light-dark(light, dark)`. The theme switch only
changes `color-scheme` — it never touches colours directly.

**Text must clear 4.5:1 against its background** in both themes. `--text-3` is
the lightest you may go on `--bg`; don't invent something fainter.

## Where files go

Placement is by **who uses it**, not what it renders — see
`components/README.md`. Short version:

| Folder | For |
|---|---|
| `components/ui/` | Style-only primitives. No Supabase, no role awareness |
| `components/shared/` | Used by more than one role |
| `components/faculty/`, `components/student/` | That role only |
| `lib/` | Runtime helpers and constants |
| `types/` | Type-only declarations |

A cross-role import (`app/dashboard/student` reaching into
`components/faculty/`) means the file is in the wrong folder. Move it, don't
import it.

## Configuration

**No addresses in code.** Backend calls go through `apiUrl()` from `lib/env.ts`.
A hardcoded `http://localhost:8000` works right up until you deploy, then
silently points at the user's own machine.

**All environment reads live in `lib/env.ts`.** Don't call `process.env`
anywhere else — three files reading it separately is how they drifted apart.

**New environment variable? Add it to `.env.example` in the same commit.** That
file is force-tracked past the `.env*` ignore rule specifically so it survives.

## Honesty

**Never fake progress or state.** If the length of an operation isn't known,
use the indeterminate `.animate-slide` bar. The upload bar used to tick to 85%
on a timer with no connection to the actual transfer.

**Never fail a user's action over a cosmetic write.** A failed display-name
refresh used to sign people out mid-login. Log it and carry on.

**Report what happened.** Log the real error message. Every failure path in the
OAuth callback once redirected to the same generic text, so none of them could
be told apart.

## Accessibility

- Every interactive element needs a visible focus state. The global
  `:focus-visible` rule handles it — don't add `focus:outline-none` without
  putting something back.
- **Not clickable? Not a link or a button.** Use a `<span>`. A disabled `<a>`
  with `preventDefault` still takes focus and still announces as a link.
- A field hint must be tied to its input. `<Field>` does that for you — pass
  `hint` and don't hand-roll it.
- Dialogs and drawers use the native `<dialog>` element, which gives focus
  trapping and Escape-to-close for free.
- Decorative icons get `aria-hidden`; meaningful ones get a label.
- Respect `prefers-reduced-motion` — the global rule covers it, so don't
  override animations with `!important`.

## Only one user fetch per screen

`AppShell` already loads the signed-in user. Read it with `useUser()` from
`components/shared/UserProvider`. Don't call `supabase.auth.getUser()` in a
page — that's two round trips and two loading states on one screen.

## Before you call it done

```bash
npx tsc --noEmit && npx eslint && npm run build
```

All three must be clean. Lint errors are not warnings to triage later.

**Stop the dev server before running `npm run build`.** They share the `.next`
folder, and a build run against a live `next dev` overwrites its route manifest
part-way through. The symptom is nasty: individual routes start returning 404
while the rest of the app keeps working, so it reads as a code bug when nothing
is wrong. If a route 404s out of nowhere, kill the server, delete `.next`, and
start it again before debugging anything else.

For a quick check while the dev server is up, use `npx tsc --noEmit` and
`npx eslint` — neither touches `.next`.
