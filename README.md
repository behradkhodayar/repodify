<p align="center">
  <img alt="Repodify" src="web/public/RepodifyGithub.png" width="100%">
</p>

# Repodify

**Turn a stretch of a podcast into one shorter, tailored digest episode.**

Search for ur desired podcast name or Paste its link, pick the episodes u want,
& Repodify creates a single chronological episode u can stream or download. It
runs **on ur own machine**, or w/ **ur own API keys (BYOK)** — ur choice at
every step.

<p>
  <img alt="Python 3.13" src="https://img.shields.io/badge/python-3.13-3776AB?logo=python&logoColor=white">
  <img alt="FastAPI" src="https://img.shields.io/badge/API-FastAPI-009688?logo=fastapi&logoColor=white">
  <img alt="LangGraph" src="https://img.shields.io/badge/pipeline-LangGraph-1C3C3C">
  <img alt="React 19" src="https://img.shields.io/badge/web-React%2019-61DAFB?logo=react&logoColor=black">
  <img alt="Ruff" src="https://img.shields.io/badge/lint-ruff-D7FF64?logo=ruff&logoColor=black">
  <a href="LICENSE"><img alt="License: MIT" src="https://img.shields.io/badge/license-MIT-blue"></a>
  <a href="https://peerpush.com/p/repodify"><img alt="Launching on PeerPush" src="https://peerpush.com/p/repodify/badge.png"></a>
</p>

> **Why this exists.** Suppose it's 2026, u're new to ML, & u want to learn
> the *history* of the field by listening to the podcasts that covered it as it
> happened — dozens of hours across dozens of episodes. Repodify condenses that
> archive into one coherent listen that walks the story start to finish.
> Summarizing is only the first use case: the same pipeline can translate,
> augment, or otherwise re-voice a run of episodes into exactly the episode u
> want. Always on **ur** hardware, or w/ **ur** keys.

---

## Try it

```bash
./launch          # or: make run
```

That's it. `./launch` syncs deps, starts Redis, & runs the API, the worker,
& the web app together.

- **GPU on this machine** → real local backends, no cloud required.
- **No GPU** → a short BYOK wizard so u can plug in ur own keys.
- **No GPU & no keys** → `./launch --fake` still walks the whole flow on CPU.

| Flag | Effect |
|---|---|
| _(none)_ | Auto-detect GPU → real local, else BYOK wizard |
| `--fake` | Keyless CPU run — no models, no network |
| `--real` | Force real mode even if GPU detection is inconclusive |
| `--postgres` | Also start Postgres |

When it's up (busy ports are remapped automatically):

```
  Built app     http://localhost:8000/app/
```

u need [uv](https://docs.astral.sh/uv/), Python 3.13, Node 20+, & Docker or
Podman (for Redis). Real runs also need ffmpeg & a CUDA GPU.

Press **Ctrl-C** to stop the app. `make stop` halts the containers.

---

## License

Repodify is released under the [MIT License](LICENSE). © 2026 Behrad Khodayar.

[Architecture](docs/architecture.md) · [Contributing](CONTRIBUTING.md)
