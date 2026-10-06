"""
YouTube comment triage — Streamlit UI.

Streamlit re-runs this entire script on every interaction. That matters here
because a run costs real money, so the rules are:
  - classification happens ONLY inside the button branch
  - results live in st.session_state, so filtering never re-fetches
  - _analyse_cached memoises by video id, so re-analysing a video is free

Run:  streamlit run streamlit_app.py
"""

import streamlit as st

import core

st.set_page_config(page_title="YouTube Comment Triage", page_icon="💬", layout="wide")

st.markdown(
    """
    <style>
      .block-container { padding-top: 3rem; }
      div[data-testid="stTextInput"] input { text-align: center; }
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_data(show_spinner=False, ttl=3600)
def _analyse_cached(vid: str, url: str) -> dict:
    """Keyed on the video id, so pasting the same video twice costs nothing.

    `vid` is the real cache key; `url` is only passed through to the validator.
    ttl matches nothing in particular — it just stops the cache growing forever.
    """
    bar = st.progress(0.0, text="Starting…")
    try:
        return core.analyse(url, lambda f, msg: bar.progress(min(f, 1.0), text=msg))
    finally:
        bar.empty()


def landing() -> None:
    st.markdown("<h1 style='text-align:center'>YouTube Comment Triage</h1>", unsafe_allow_html=True)
    st.markdown(
        "<p style='text-align:center;opacity:.7'>"
        "Paste a video URL. Every comment is sorted by type, sentiment and how much "
        "it deserves a reply — so the ones worth answering float to the top.<br>"
        f"<small>Up to {core.MAX_COMMENTS} comments per run. Nothing is stored.</small></p>",
        unsafe_allow_html=True,
    )


def results(data: dict) -> None:
    df = data["df"]
    worth = int((df["reply_worthy"] >= core.ANSWER_AT).sum())

    a, b, c, d = st.columns(4)
    a.metric("Comments", len(df))
    b.metric("Worth replying to", worth)
    c.metric("This run", f"₹{data['cost']:.2f}")
    d.metric("Per 1,000", f"₹{data['cost'] / len(df) * 1000:.2f}")

    if data["failed"]:
        st.caption(f"{data['failed']} classification calls failed and were dropped.")

    found = sorted(df["type"].unique())
    left, right = st.columns([1, 3])
    bucket = left.radio("Priority", ["All", "Answer these", "Maybe", "Ignore"], horizontal=False)
    types = right.multiselect("Type", found, default=found)

    view = core.apply_filters(df, types, bucket)
    st.caption(f"Showing {len(view)} of {len(df)}")

    st.dataframe(
        view,
        hide_index=True,
        use_container_width=True,
        height=560,
        column_order=core.COLUMNS,
        column_config={
            "reply_worthy": st.column_config.ProgressColumn(
                "reply-worthy", min_value=0.0, max_value=1.0, format="%.2f",
                width="medium",
                help="max(is a question, merits a response) x (1 - hostile/spam). "
                     "A ranking key, not a verdict.",
            ),
            "type": st.column_config.TextColumn("type", width="small"),
            "sentiment": st.column_config.TextColumn("sentiment", width="small"),
            "difficulty": st.column_config.TextColumn(
                "difficulty", width="small",
                help="How hard the question is to answer. '—' means it did not read as a question.",
            ),
            "comment": st.column_config.TextColumn("comment", width="large"),
            "likes": st.column_config.NumberColumn("likes", width="small"),
            "sure?": st.column_config.NumberColumn(
                "sure?", format="%.2f", width="small",
                help="Confidence in the TYPE label only. Low means Jev was torn "
                     "between two types — treat those rows with suspicion.",
            ),
        },
    )
    st.caption("Click a cell to read a long comment in full.")


landing()

mid = st.columns([1, 2, 1])[1]
with mid:
    url = st.text_input(
        "YouTube URL", placeholder="https://www.youtube.com/watch?v=…",
        label_visibility="collapsed",
    )
    go = st.button("Analyse", type="primary", use_container_width=True)

# The ONLY place that spends money. Filters below re-run the script but never
# reach this branch, so they cost nothing.
if go:
    try:
        vid = core.video_id(url or "")
        if not vid:
            raise core.Fail("That doesn't look like a YouTube video URL.")
        st.session_state["data"] = _analyse_cached(vid, url)
    except core.Fail as e:
        st.session_state.pop("data", None)      # reset rather than leave stale results
        st.error(str(e))
    except Exception as e:                      # noqa: BLE001 - surface, don't traceback
        st.session_state.pop("data", None)
        st.error(f"Something went wrong: {e}")

if "data" in st.session_state:
    st.divider()
    results(st.session_state["data"])
