# Backlog

## Triage (revisit after Day 6)
- ~~**Grounding false positive at sentence boundaries.**~~ Fixed 2026-10-20 (see devlog): a trailing period ends a run, except after abbreviations (U.S.) and place titles (Mt.).
- **Grounding checks facts, not relevance.** A replay summary's actions included "Stay hydrated" and "Have a cooling plan if smoke impacts your area", which don't follow from a red flag or wind alert. Consider limiting actions to the alert's INSTRUCTION text plus the runbook.
- **Replay strict mode rejects useful text.** Nova often writes days or times into replay output ("Friday", "8 PM"; on 2026-10-20 after the boundary fix, its only violations were `friday` and `weekend`); strict mode rejects it as designed. Consider telling the model about the appended until-time with an example, or one retry with the violations quoted back.
- **Timeline wording for prod.** `explain_incident` timelines read "CodeDeploy issued Deployment" / "CloudWatch issued checkout-service latency". Use per-source verbs ("deployment v4→v5 finished", "alarm went into ALARM").
- **Spoken overview repeats the caution.** Live 2026-10-20: the replay overview read "…Be extremely cautious with anything that can spark. In effect until 12:07 AM Friday. Use extreme caution with anything that can spark a wildfire." The AI summary already says it, and the overview then adds the top action. Consider skipping the top action when the summary already covers it.
- **Model availability.** Claude Haiku 4.5 now works (the use-case form went through); Haiku 5.5 is still not enabled for the account (FL-008).
