import pytest

from app.embeddings import cosine_similarity_01


def test_cosine_similarity_01_identical_vectors_is_one():
    assert cosine_similarity_01([1.0, 2.0, 3.0], [1.0, 2.0, 3.0]) == pytest.approx(1.0)


def test_cosine_similarity_01_orthogonal_vectors_is_half():
    assert cosine_similarity_01([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.5)


def test_cosine_similarity_01_opposite_vectors_is_zero():
    assert cosine_similarity_01([1.0, 0.0], [-1.0, 0.0]) == pytest.approx(0.0)


def test_cosine_similarity_01_rejects_mismatched_dimensions():
    with pytest.raises(ValueError):
        cosine_similarity_01([1.0, 0.0], [1.0, 0.0, 0.0])


def test_cosine_similarity_01_handles_zero_vector_without_crashing():
    # A zero-norm embedding shouldn't ever happen (encoder L2-normalizes), but the
    # function must not divide by zero if it somehow does.
    assert cosine_similarity_01([0.0, 0.0], [1.0, 0.0]) == pytest.approx(0.5)
