import re


def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").replace("\u00a0", " ")).strip()


def sentence_split(text: str) -> list[str]:
    text = clean_text(text)
    if not text:
        return []
    try:
        import spacy
        nlp = spacy.blank("vi")
        nlp.add_pipe("sentencizer")
        return [sent.text.strip() for sent in nlp(text).sents if sent.text.strip()]
    except Exception:
        return [part.strip() for part in re.split(r"(?<=[.!?])\s+", text) if part.strip()]

