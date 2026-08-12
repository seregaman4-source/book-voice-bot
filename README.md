# Russian Voiceover V2

Reusable pipeline for Russian voiceover of English educational videos.

## Fixed standard

- Source video is preserved without video re-encoding (`-c:v copy`).
- Russian voice: Microsoft `ru-RU-DmitryNeural` by default.
- Translation is prepared contextually before TTS, with course glossary consistency.
- Russian text is adapted to the available source-speech window before aggressive speed-up.
- TTS segments are generated concurrently with retries and cache reuse.
- Every segment is measured after synthesis and may be regenerated at an adjusted rate.
- Segments that still exceed the allowed timing window are flagged `adapt_text` in `manifest.json` rather than silently over-compressed.
- Final mix uses sidechain ducking so the English original fades down under Russian speech and returns smoothly in gaps.
- Final Russian mix is loudness-normalized.
- Final MP4 carries Russian voiceover as default audio and English original as a second audio track. Russian soft subtitles can also be muxed.

## Files

- `job.json` — per-video timed Russian segments and TTS settings.
- `tts_worker.py` — parallel neural TTS, retry, cache, duration measurement, adaptive rate, manifest generation.
- `mix_voiceover.py` — lossless video-stream copy, timed narration placement, dynamic ducking, loudness normalization, dual audio tracks, optional Russian subtitles.
- `glossary_perkins_ru.json` — persistent terminology for Bill Perkins / Composition for the Visual Artist.
- `.github/workflows/tts_v2.yml` — reusable GitHub Actions runner.

## Quality rules

1. Preserve meaning first.
2. Prefer compact natural Russian syntax over high speech-rate compression.
3. Do not translate `value`, `tone`, `shape`, `form`, `mass` mechanically without context.
4. Protect names, artwork titles, institutions and course-specific terminology.
5. Regenerate only problematic segments.
6. Do not deliver final output if any segment is flagged `adapt_text` without review.
