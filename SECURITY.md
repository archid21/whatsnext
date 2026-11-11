# Security

## Report a problem

Open a private report: Security tab of this repository, "Report a vulnerability", or email [hello@aivalue.blog](mailto:hello@aivalue.blog?subject=whatsnext) (subject: whatsnext). Do not put exploit details in a public issue. Expect a first reply within 7 days.

## Scope

In scope: a way for whatsnext to write outside the paths in [docs/WHAT-IT-TOUCHES.md](docs/WHAT-IT-TOUCHES.md), run a command you did not pass, read a file outside the repository and the session folders it names, or leak session content.

Out of scope: `plan done --verify "<command>"` runs the command you give it, by design; and what an agent writes into a plan, progress file or handoff note.

## Design limits

- No network calls, no background process, no model call.
- An absolute or `..` path in `paths.handoff` is ignored.
- Hooks fail silent and exit 0, so a bug cannot block a session.
- Tell your agent not to put secrets in handoff notes or progress files; those files are meant to be committed.
