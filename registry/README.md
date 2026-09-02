# Registry

Pointers to skills, plugins and tooling built outside this repo.

**Pointer by default, vendor only what you depend on.** An entry here is a note
that something exists and what we currently think of it — not an endorsement and
not an installation.

## Trust tiers

| Tier | Meaning |
|---|---|
| `official` | Published by Anthropic. Still read it before enabling hooks. |
| `vetted` | Someone here read the source and recorded the date in `last_reviewed`. |
| `unvetted` | Listed because it is widely used or worth knowing about. **Nobody here has read it.** |

`unvetted` is not a soft warning. Skills change how the agent behaves and hooks
execute shell commands on your machine without a permission prompt, so
installing an unread bundle is running unread code with your credentials. The
large multi-hundred-skill collections are the clearest case: they are a
supply-chain decision presented as a convenience.

## Adding an entry

One YAML file per entry, validated against `../schema/registry.schema.json`.
Required: `id`, `name`, `source`, `trust`, `category`, `what_it_does`.
`last_reviewed` is required when `trust: vetted`.

Add the entry *before* installing (ECC-0040).
