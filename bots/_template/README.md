# A bot

One directory = one bot = one dsh agent preset. Copied by the face's **New bot** form
(`face/src/bots.ts` `createBot`); never hand-copy it — the id has to satisfy dsh's grammar
`[a-z0-9][a-z0-9-]*` and the composition has to carry the soul.

| File | Owner | What |
|---|---|---|
| `agent.cordis.yml` | the face (GENERATED) | the composition dsh mounts: the `kairos-bot` plugin (persona + tool mask) and this bot's skill root |
| `preset.yml` | the operator, via the form | `name`, `description` — what the roster shows |
| `SOUL.md` | the operator, via the form or the bot page | the persona SOURCE. The face copies it into the composition; a hand edit reaches nothing until the face saves it again |
| `skills/` | the operator | this bot's stance pack, a dsh skill root: `skills/<skill>/SKILL.md` with `name` + `description` frontmatter |
| `journal/` | the bot, from its home | the only directory the bot may write |

Rules: no `{{` anywhere in `SOUL.md` (the system prompt is a strict template with no escape);
the mask in `agent.cordis.yml` is visibility, not authority — the sandbox and Gate 2 are the
fences, and neither is containment.
Kairos never edits anything under `bots/` (AGENTS.md).
