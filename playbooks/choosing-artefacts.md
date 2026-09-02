# Choosing an artefact

Which skills and commands should a project have? Ask the graph:

```bash
python tools/coverage.py --kind skill      # and hook, command, mcp-server, monitor…
python tools/coverage.py --activity ACT-03 # everything debugging needs
```

That answers *which*. This page answers *what kind* — the decision people get
wrong most often, and the one that quietly determines whether a setup works.

---

## The decision table

| What you have | Reach for | Because |
|---|---|---|
| A fact that is always true of this repo | **CLAUDE.md** | Loaded every turn. Budget it (ECC-0002). |
| A procedure the model should follow *when it applies* | **Skill** | Model-invoked. The `description` is the trigger. |
| A procedure a person triggers deliberately | **Command**, or a skill with `disable-model-invocation` | Explicit entry point, no guessing. |
| Something that must happen **every** time | **Hook** | Executed by the harness, not attended to by the model. |
| A bounded job that would pollute the main context | **Subagent** | Its own context window and tool set. |
| Access to an external system | **MCP server** | Check the official marketplace first. |
| Type errors and symbol navigation | **LSP plugin** | Official, 11 languages. Highest single-install leverage (ECC-0033). |
| A log or status to watch in the background | **Monitor** | `monitors/monitors.json`; lines arrive as notifications. |
| Any of the above, shared across repos or people | **Plugin** | Versioned, installable, revocable (ECC-0032). |

## The three mistakes

**Writing a hook as an instruction.** "Always run the formatter after editing"
in CLAUDE.md is a request. It is honoured most of the time — which is the worst
possible failure rate, because it is frequent enough to be trusted and its
misses are never attributed to the mechanism. If it is deterministic, it is a
hook. (ECC-0031)

**Keeping a skill as a pasted prompt.** Once a procedure has been pasted three
times it has become a private, unversioned copy of a shared thing. Two people's
copies diverge within a fortnight and neither knows. (ECC-0030)

**Building what already exists.** Anything crossing a tool boundary — a language
protocol, a vendor API — is maintained by someone else against something that
changes without you. Search `claude-plugins-official` and `claude-community`
before writing. The reverse mistake is rarer but real: installing a general
plugin for something that is genuinely specific to how your team works, then
fighting it.

## Writing a skill that actually fires

A skill is selected on its `description`, so that field is not documentation —
it is the trigger, and it is the whole difference between a skill that fires and
one that sits unused.

- Say **when it applies**, in the words someone would use: *"Use when reviewing
  a PR, checking code quality, or asked to look over a change."* Not *"Reviews
  code."*
- Include the synonyms people actually type. The description is matched against
  intent, not against your naming.
- One job per skill. A skill that does four things fires for none of them
  cleanly.
- Put the detail in the body, not the frontmatter. The description is read to
  decide; the body is read to execute.
- State what **not** to do. Most of the value in a mature skill is the
  guardrails — "propose, then wait", "never write to the user's global
  settings" — because that is the part a capable model would otherwise get
  wrong in a plausible way.

## Where each kind lives

```
.claude/CLAUDE.md              context, loaded every turn
.claude/skills/<name>/SKILL.md model-invoked procedures
.claude/agents/<name>.md       subagents
.claude/settings.json          hooks, permissions — committed
.claude/settings.local.json    personal overrides — gitignored
```

As a plugin, the same components move to the plugin root — `skills/`, `agents/`,
`hooks/hooks.json`, `.mcp.json`, `.lsp.json`, `monitors/` — with only
`plugin.json` inside `.claude-plugin/`. Putting `skills/` inside
`.claude-plugin/` is the most common packaging error and fails silently.

Start standalone in `.claude/`, convert to a plugin when you need to share it.
