# Roadmap

- [ ] **Speaker name extraction** — identify the real host/guest names from the
  podcast (audio + episode metadata) and label the digest cast with them, instead
  of the diarization ids (`SPEAKER_00`).
- [ ] **Human-readable job names** — name each job after its brief/prompt instead
  of the current hash-digest id.
- [ ] **Bullet-proof retry on limit hit (BYOK)** — resilient retry/back-off when a
  hosted provider returns a rate-limit or quota error, so a long job survives it.
- [ ] **Translation** — render the digest in the user's language of choice.
- [ ] **Search in podcast contents** — search ingested transcripts so users can
  find and listen to topics of their choice, not only a pre-picked episode range.
- [ ] **Telegram bot** — a TG bot front-end to request a digest and receive the
  finished episode.
