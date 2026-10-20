# Backlog

## Triage (revisit after Day 6)
- **Grounding false positive at sentence boundaries.** The capitalized-phrase regex in `triage/grounding.py` treats a trailing period as part of a word, so a run continues past the end of a sentence: "…Los Angeles and Ventura Counties. Winds…" yields the place candidate "Ventura Counties Winds" (also "Ventura Counties Use"). Seen live on 2026-10-20 for both Nova Lite and Claude Haiku 4.5 on replays, so triage fell back to the template. Fix: end a run at a period followed by whitespace (keep abbreviations like "U.S." working), and add those live outputs as tests.
- **Grounding checks facts, not relevance.** A replay summary's actions included "Stay hydrated" and "Have a cooling plan if smoke impacts your area", which don't follow from a red flag or wind alert. Consider limiting actions to the alert's INSTRUCTION text plus the runbook.
- **Replay strict mode rejects useful text.** Nova often writes days or times into replay output ("Friday", "8 PM"); strict mode rejects it as designed. Consider telling the model about the appended until-time with an example, or one retry with the violations quoted back.
- **Timeline wording for prod.** `explain_incident` timelines read "CodeDeploy issued Deployment" / "CloudWatch issued checkout-service latency". Use per-source verbs ("deployment v4→v5 finished", "alarm went into ALARM").
- **Model availability.** Claude Haiku 4.5 now works (the use-case form went through); Haiku 5.5 is still not enabled for the account (FL-008).
