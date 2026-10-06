# YouTube Comment Triage

Paste a YouTube URL. Every comment in the section is classified on four axes and
ranked so the ones actually worth a reply float to the top.

| Axis | Primitive | Output |
|---|---|---|
| Type | Choice, 13 labels | question, praise, criticism, correction, spam_scam, … |
| Reply-worthiness | 3 × Noul | 0–1 score, combined in code |
| Sentiment | Score, 5 levels | hostile → enthusiastic |
| Question difficulty | Score, 5 levels | trivial → unanswerable |

Classification runs on [Jev](https://docs.typesafe.ai) (`jev-1.13`), TypeSafe's
System One model — a structured-decision API that returns typed values rather
than prose, so there is no JSON parsing or output validation layer.

## Run it

```bash
python -m venv .venv && . .venv/bin/activate   # Windows: .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp .env.example .env                           # then fill in both keys
streamlit run streamlit_app.py
```

`.env` needs:

```
TYPESAFE_API_KEY=...     # console.typesafe.ai/keys
YOUTUBE_API_KEY=...      # Google Cloud Console, enable YouTube Data API v3
```

`smoke_test.py` makes one minimal call (~₹0.01) to confirm the endpoint and key
before you run the full app.

## Deploy

Streamlit Community Cloud — free, no card, public apps only:

1. Push this repo to GitHub (public).
2. share.streamlit.io → **New app** → pick the repo, main file `streamlit_app.py`.
3. **Advanced settings → Secrets**, paste:
   ```toml
   TYPESAFE_API_KEY = "..."
   YOUTUBE_API_KEY = "..."
   ```
4. Deploy.

Keys go in Streamlit's secrets store, never the repo — `.gitignore` excludes
both `.env` and `.streamlit/secrets.toml`.

## Layout

| File | Why it's separate |
|---|---|
| `questions.py` | The six question definitions. Edit label wording here only. |
| `core.py` | Fetch, classify, score, rate-limit. No UI framework — swapping Streamlit for anything else touches nothing in here. |
| `streamlit_app.py` | UI only. |

## Design notes

**One request per comment, not batched.** Batching inputs is the reflex when a
bill scales with item count, and here it is wrong. The question block is ~1,170
tokens and a comment averages ~30, so the questions are ~94% of every request
and amortising comments across one call saves 2.7%. The variant that *would* pay
(numbering comments in one state and referencing them by index) leans on
list-indexing, which the vendor documents as unreliable. Measured cost:
**₹5.02 per 1,000 comments**.

**Nothing is stored.** No database, no retention job, no deletion endpoint.
That is a compliance decision as much as a simplicity one: YouTube's Developer
Policies cap storage of comment data at 30 days (§III.E.4.d) and require deletion
within 7 days on request (§III.E.4.g). Holding comments only for the lifetime of
one request means neither obligation can be violated. Author names, channel IDs
and avatars are never read — they are personal data and are not needed to
classify text.

**Reply-worthiness is three Nouls, not one Choice.** It is a ranking key, so a
continuous probability is the right shape; `confidence` on a Choice measures how
peaked the distribution is, not how much a reply is deserved.

**Difficulty is gated in code, not by an N/A option.** Score requires *ordered*
levels, so a non-ordinal "not applicable" at index 0 would corrupt the
probability-weighted mean — a 50/50 split between N/A and "very hard" would
return ≈1.0, i.e. "easy". Comments that don't read as questions show `—`.

**Ordering is `time`, not `relevance`.** YouTube re-ranks relevance between
calls, so the same URL returned a different sample and different counts on every
run.

## Known limitations

- **Fine-grained type labels are the weakest axis.** The independent benchmark of
  Jev ([arXiv 2609.37647](https://arxiv.org/abs/2609.37647)) reports 96%+ on
  binary sentiment but **58.5% on 6-way emotion**, and names fine-grained labels
  and rubric judgments as weak spots — which is exactly the 13-way taxonomy and
  the difficulty rubric. Treat `type` as a triage aid, not ground truth. The
  `sure?` column surfaces where the model was torn.
- **Thresholds are untuned.** `ANSWER_AT` / `MAYBE_AT` are placeholders. The same
  benchmark found Jev's binary probabilities rank well but sit poorly against
  0.5; tuning took one dataset's micro-F1 from 0.50 to 0.75.
- **English-primary.** Non-English and code-mixed comments (Hinglish is common in
  YouTube comment sections) are classified with lower accuracy.
- **Abuse protection is one layer, not two.** Streamlit Community Cloud exposes
  no reliable client IP, so there is no per-IP limit — only a process-wide daily
  cap, which resets if the app restarts. A spend cap on the API key is the real
  backstop and the only one that cannot be bypassed.
- **200 comments per run**, newest first — not a full-video analysis.
