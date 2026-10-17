<!-- copied from ~/.claude/skills/sprite-pipeline/references/common (ced2f55) on 2026-10-17; ayothaya owns this copy now -->
# Secrets (all routes)

- **Keys only in a gitignored `.env`** (LF line endings; the kit ships `.env.example` with variable names only). Load with `set -a; . ./.env; set +a`; strip `\r` when reading (a CRLF `.env` breaks the auth header). (aroa, from day one)
- **Never print, log or copy a key**; scrub `sk-…` from any error text before printing or logging: an HTTP library once echoed the auth header into an exception. (aroa gen_concepts)
- **No key ever goes to a GPU box.** GPT/image-API calls run on the dev machine; boxes only get the concept PNGs they need. Teardown checks that no `.env`/key is on the box before destroy (kit `tools/fleet/teardown.sh`). (aroa fleet)
- **Webhooks are keys too:** the owner-notification webhook (`DISCORD_WEBHOOK_URL`) is read from `.env` by a local script only (kit `tools/notify/discord.py`); never copy the URL into a box, a log or a doc. (aroa)
- **Pending rotation:** when a key may have leaked (pasted, logged, sent to a box), rotate it and log the rotation as a decision. (aroa: OpenAI key pending rotation)
- **Inspecting a local helper process:** read `/proc/<pid>/cmdline`, and pull only the variable you need from `/proc/<pid>/environ` with an exact `grep '^NAME='`. Never dump or prefix-grep a whole environ: agent runtimes put passwords and tokens in the environment, and a dump puts them into the transcript. (aroa, agent runtimes)
- **Kit hygiene:** before committing a kit or a project repo, grep for secret-looking strings (`sk-`, webhook URLs, `hf_`, `ghp_`, private keys, real host IPs in tests). sprite-kit v1 found one real box IP in a fleet test fixture and replaced it with a documentation address. (sprite-kit v1, 2026-10-13)
