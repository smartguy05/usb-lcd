# Notes

- Claude status-line JSON exposes only `five_hour` and `seven_day`; Fable needs the undocumented OAuth usage endpoint and must degrade gracefully.
- The OAuth endpoint is aggressively rate-limited. Fetch off the render path, cache normalized values, and honor backoff.
- Recent Claude hook summaries complete in roughly 0.5-0.8 seconds, but the current two-second limit has failed during slower starts; hook CLI imports currently pull in the entire daemon stack.
- Doctor must read Claude/Codex JSON explicitly as UTF-8; Windows' default cp1252 decoder fails on valid Unicode settings content.
- Preserve the last known Fable window when a successful OAuth response omits that bucket; upstream response shapes may change independently of authentication.
- The OAuth endpoint also returns `five_hour` and `seven_day`; ignoring those
  leaves the LCD stale whenever Claude's status-line callback is quiet.
