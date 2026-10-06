"""The six questions sent against each comment. Edit label wording here only."""

COMMENT_TYPE = {
    "question":        {"what": "Asks something and expects an answer.",
                        "not_for": "Rhetorical question making a point -> discussion"},
    "praise":          {"what": "Compliment or appreciation for the video or creator.",
                        "not_for": "Praise plus a question -> question"},
    "criticism":       {"what": "Negative judgement of the video's content, style, or quality.",
                        "not_for": "Personal attack -> abuse"},
    "correction":      {"what": "Claims a specific factual error in the video and states what is right.",
                        "not_for": "Vague disagreement without a correction -> criticism"},
    "discussion":      {"what": "Substantive on-topic commentary or opinion addressed to the community, not asking anything.",
                        "not_for": "Bare praise -> praise"},
    "joke":            {"what": "Humour, meme, pun, copypasta.",
                        "not_for": "Humour whose point is an attack -> abuse"},
    "timestamp":       {"what": "Primarily a timestamp or chapter marker.",
                        "not_for": "Timestamp attached to a question -> question"},
    "content_request": {"what": "Asks for a future video, topic, or feature.",
                        "not_for": "Asking a question about this video -> question"},
    "collab_request":  {"what": "Asks to collaborate, be featured, sponsor, or do business.",
                        "not_for": "Asking the creator to cover a topic -> content_request"},
    "self_promo":      {"what": "Promotes the commenter's own channel, product, or link.",
                        "not_for": "Third-party scam or bot content -> spam_scam"},
    "spam_scam":       {"what": "Bot content, crypto or giveaway scams, impersonation of the creator, mass-posted links.",
                        "not_for": "The commenter promoting their own legitimate channel -> self_promo"},
    "abuse":           {"what": "Attacks a person - the creator, another commenter, or a group. Slurs, harassment, threats.",
                        "not_for": "Harsh but substantive criticism of the content -> criticism"},
    "offtopic":        {"what": "Unrelated to the video and not spam.",
                        "not_for": "Related tangent -> discussion"},
}

QUESTIONS = {
    "comment_type": {
        "type": "choice",
        "instructions": "What kind of comment is this, from the perspective of a creator triaging their comment section?",
        "criteria": COMMENT_TYPE,
    },
    # Three atomic Nouls, combined in code. Each returns a bare 0-1 probability.
    "rw_direct_question": {
        "type": "noul",
        "instructions": "The comment asks the video's creator a question that expects an answer.",
    },
    "rw_merits_response": {
        "type": "noul",
        "instructions": "A creator replying to this comment would add value for the commenter or for other viewers.",
    },
    "rw_is_hostile_or_spam": {
        "type": "noul",
        "instructions": "The comment is abusive, spam, or a scam.",
    },
    # Scores return a continuous value in [0, n-1]. Five levels -> [0.0, 4.0].
    "sentiment": {
        "type": "score",
        "instructions": "What feeling does the comment express?",
        "criteria": [
            "Hostile - expresses anger, contempt, or hatred.",
            "Negative - expresses disappointment, annoyance, or dislike.",
            "Neutral - states something without expressing feeling either way.",
            "Positive - expresses enjoyment, agreement, or appreciation.",
            "Enthusiastic - expresses strong delight, excitement, or devotion.",
        ],
    },
    "q_difficulty": {
        "type": "score",
        "instructions": "If the comment poses a question, how hard is it to answer well?",
        "criteria": [
            "Trivial - answerable in one sentence from the video itself.",
            "Easy - answerable from general knowledge of the topic in a sentence or two.",
            "Moderate - needs a considered explanation or a specific detail the creator knows.",
            "Hard - needs research, testing, or going well beyond the video's scope.",
            "Unanswerable - no definite answer exists, or it is a matter of opinion or prediction.",
        ],
    },
}

SENTIMENT_LABELS = ["hostile", "negative", "neutral", "positive", "enthusiastic"]
DIFFICULTY_LABELS = ["trivial", "easy", "moderate", "hard", "unanswerable"]


def label_from_score(score: float, labels: list[str]) -> str:
    """Score is continuous in [0, len-1]; round to the nearest level for display."""
    return labels[max(0, min(len(labels) - 1, round(score)))]
