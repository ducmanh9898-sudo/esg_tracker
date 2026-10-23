"""Small text normalization shared by retrieval and provenance checks."""
import re
import unicodedata


def normalized_label(value):
    text = unicodedata.normalize("NFD", value.lower().replace("\u0111", "d"))
    text = "".join(char for char in text if not unicodedata.combining(char))
    return " ".join(re.findall(r"[a-z0-9]+", text))
