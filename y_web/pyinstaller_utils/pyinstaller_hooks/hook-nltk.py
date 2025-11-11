"""
PyInstaller hook for NLTK optimization.

This hook minimizes NLTK's footprint by only including the VADER sentiment lexicon
instead of the entire NLTK corpus, which can be over 100MB.
"""

from PyInstaller.utils.hooks import collect_data_files

# Only collect VADER lexicon data
# This reduces NLTK data from ~100MB to ~1MB
datas = []

# Try to collect only the VADER lexicon
try:
    vader_data = collect_data_files("nltk", subdir="sentiment/vader_lexicon")
    if vader_data:
        datas = vader_data
        print("✓ Collected VADER lexicon only")
except Exception as e:
    print(f"⚠ Warning collecting VADER lexicon: {e}")
    # Fallback: don't collect any NLTK data, it will be handled in spec file
    pass

# Exclude NLTK modules we don't need
excludedimports = [
    "nltk.tokenize.stanford",
    "nltk.translate",
    "nltk.parse",
    "nltk.tag.stanford",
    "nltk.stem.snowball",
    "nltk.corpus",  # Exclude corpus readers we don't use
]
