# Recording script — Expanso log triage with Cribl decision model

**This is the script for the take.** David's walkthrough, edited: eight beats,
in the order the board tells the story. `RUNBOOK.md` has the clicks; this has
the words. The board is `http://127.0.0.1:8890`, localhost only.

Backend: Cribl's open-weight `cribl-decision-1.0` (4B LoRA on Qwen3.5-4B-Base served
locally on `:8100` via `shared/cribl-decision-server.py`, compatible with the
`/v1/systemone` API). No metered cloud API, no external leak.

**Branding:** Expanso in masthead and on the edge; decision node named factually in text: Cribl cribl-decision-1.0 (local 4B · Apache-2.0). No co-branding or partnership claim.

## Three things changed from the raw draft, and why

1. **The "10,000 per second" figure is out.** Nothing here measured it and this
   demo runs at about 40 lines a second, so on camera it would be a number the
   screen contradicts. The line now says Cribl's local model is fast enough to sit
   in the pipeline on-machine, which the board shows.
2. **"90%" becomes the number on the screen.** Real runs measured 86% and 89%.
   Read the fork label aloud instead of quoting a round figure from memory.
3. **"Non-deterministic 10%" becomes "what a rule can't settle".** The data is
   not random; it is vague, or only means something in context. That is also the
   better pitch for telemetry decision models.

Added: one concrete example (beat 6). An INFO line that needs attention is the
most persuasive ten seconds available, and the local decision model catches it.

## The walkthrough

### 1. The problem · act one, nothing deployed

**Screen.** Source on the left, squares flowing straight into the raw bucket.
Point at the card bottom right: "N of the last 30 lines are the same 3 messages".

> So, what we have here is a standard logging setup. Every line your systems
> write gets shipped, exactly as written, to a raw endpoint so you can analyze
> it later. And that works. But look at what's actually in there. It's the same
> few messages, over and over. You pay to move all of it, you pay to store all
> of it, you pay to query all of it, and you don't learn anything until it has
> already landed in your backend. That costs money, and it costs you time on
> the day something is actually wrong.

### 2. Why Expanso first · still act one

> So the first thing we're going to do is put an Expanso Edge pipeline in front
> of it. This part is completely deterministic. It runs right where the logs are
> produced, on the server itself or on a gateway next to it, and it can filter,
> shape and count even very high-volume log data before anything moves. That
> saves you money. More importantly, your data arrives structured and contextualized.

### 3. Show it, deploy it · act two

**Do.** Click **Pipeline YAML**, pick `pipeline-logging.yaml`. Then the Expanso
Cloud console: deploy it as job `log-triage`. Back to **Live flow**.

> Let me show you what that pipeline is. It's one file. Shape the record,
> fingerprint it, count how often we've seen it. I'll go over to Expanso Cloud
> and deploy it.

*(8-15 s of deploy. Say nothing. It gets cut to 2-3 s.)*

> And there it is, running. Every record is now structured and counted, and for
> now it all goes to the archive. Same logs, a lot more context to be smart with.

### 4. Why Cribl decision models · act two still running

> But there's a lot you can't settle with a rule. Sometimes the input is just
> vague. Sometimes a line only matters because of what happened in the last ten
> minutes. Writing a rule for every one of those is a losing game. That's where
> Cribl's open-weight `cribl-decision-1.0` model comes in. You hand it a
> record and a few questions, and you get structured answers back on-machine.

### 5. Flip the switch · act three

**Do.** Point at the four question chips, then flip the **decision switch**.

> So in the same pipeline, we add a Cribl decision step. Most of this traffic is routine,
> and Expanso knows that immediately, no model needed. Whatever it can't settle,
> it hands to Cribl, along with the recurrence history it has already counted. Normally you
> would never put a model in the hot path of your logs. Cribl's 4B decision model is
> fast enough that you can run it right here. I'm going to flip this switch, and now
> the model is part of the pipeline.
> You can see the split right here. *[read the fork label]* never touch the
> model. The rest go to Cribl.

### 6. What comes back · the example

**Do.** Let the buckets fill for a few seconds. Then click **INFO: health check
500**, wait ~10 s, click **NOTIFY**. Esc to close.

> When the answers come back, Expanso routes on them. Page the on-call. Notify
> the team that owns it. Send it to a person if the model isn't sure. Archive the
> rest. And that happens out at the edge, so you're not waiting for data to
> reach your backend before something gets triggered.
>
> Here's my favorite example. I'm injecting a health check that returns a 500,
> but it's logged as INFO. Route on severity alone and that goes straight to the
> archive, and nobody ever sees it. Cribl flagged it, and it went to the owning
> team. Same log level as all the noise. Completely different meaning.

It is a live model's judgment, not a fixture. If it lands in REVIEW, say "The model
wasn't sure, so a person looks at it" in place of the last three sentences. If
it lands in ARCHIVE, skip the example; the beat stands without it.

### 7. When the model goes away · the outage

**Do.** Click **Break the link to model**. Let the held count build 10-15 s. Click
**Restore the link**. **Never hold past ~40 s**: after 15 attempts a record stops
waiting and goes to REVIEW, which is correct but a different story.

> One more thing. Machine learning is great, but network calls and services fail.
> Model endpoints get overloaded. From the pipeline's side those
> are all the same thing: no answer. So let me break it. The model is now refusing
> every request. Look at what Expanso does. It doesn't guess, it doesn't drop
> anything, and it doesn't stall. Routine traffic keeps flowing, and everything
> that needs the model is held right here on edge (--kept). *[read the held count]*
> Now I restore it, and everything that was waiting goes through, gets a real answer,
> and lands where it belongs.

### 8. Close

> So that's the whole thing. One pipeline. Rules handle the routine bulk for
> almost nothing. Cribl handles the judgment calls, live on-machine. And Expanso
> makes sure nothing gets lost in between. You spend less, you find out sooner,
> and adding local intelligence was one more step in a pipeline you already had.

## Rules while talking

- Say "Cribl reported" or "Cribl flagged". Never "Cribl is N% accurate": these are
  observed judgments on synthetic events.
- No dollar figure. "Costs money" is fine; a price needs a stated rate per call
  and per GB, and the board states neither.
- Read numbers off the screen. Do not quote one from memory.
- The outage is simulated and the board says so. The failed calls, the hold and
  the release are real.
- Pipeline YAML tab: "this is the source file", not "this is what Cloud is
  running". The board does not read the deployed spec back.

## What the board claims, and what backs it

| Claim on screen | Backed by |
|---|---|
| "N% skipped the model · no call made" | `bypassed / (bypassed + judged + unanswered)`, completed receipts of this run only. |
| Bypass matches only configured exact messages | exact match on level INFO + service + raw message. |
| "Severity-only baseline: X" | computed in the pipeline on the identical input: ERROR→page, WARN→notify, INFO→archive |
| Destinations | local JSONL demo files under `data/`, labelled as such on screen. |
| Events | synthetic, labelled on screen |
