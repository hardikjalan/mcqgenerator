# components/

Where a component lives is decided by **who uses it**, not by what it renders.

| Folder | Contains | Rule |
|--------|----------|------|
| `ui/` | Style-only primitives — inputs, labels, buttons | No Supabase calls, no role awareness, no business logic |
| `shared/` | Composites used by **more than one** role — dashboard header, logo, sign-out button, quiz question renderer | May read the session, must never branch on `role` |
| `faculty/` | Faculty-only — upload zone, assessment builder steps | Never imported from `app/dashboard/student` |
| `student/` | Student-only — quiz player, timer, results view | Never imported from `app/dashboard/faculty` |

**Promotion path:** a component starts in its role folder. The moment a second
role needs it, move it to `shared/` (or `ui/` if it has no logic) rather than
importing across role folders — a cross-role import is the signal that the file
is in the wrong place.

Types go in `@/types`, runtime constants and helpers in `@/lib` — not in a
`types.ts` inside a role folder, or the other role ends up importing from it.
