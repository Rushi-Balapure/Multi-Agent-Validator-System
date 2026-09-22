"""Retrieval failures. A corpus hash miss is a hard stop, not an empty index."""


class RetrievalError(RuntimeError):
    """The gatherer or index builder cannot continue."""


class CorpusHashMismatch(RetrievalError):
    """Pinned corpus bytes do not match the file that would be indexed."""
