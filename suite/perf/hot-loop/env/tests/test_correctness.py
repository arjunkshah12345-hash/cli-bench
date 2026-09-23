from matrix_ops import count_pairs_within


def test_empty():
    assert count_pairs_within([], 1.0) == 0


def test_single():
    assert count_pairs_within([(0, 0)], 1.0) == 0


def test_two_points():
    assert count_pairs_within([(0, 0), (1, 1)], 1.5) == 1
    assert count_pairs_within([(0, 0), (3, 4)], 4.9) == 0
    assert count_pairs_within([(0, 0), (3, 4)], 5.0) == 1


def test_exact_boundary_counts():
    # distance exactly r is included (<= r)
    assert count_pairs_within([(0, 0), (1.0, 0.0)], 1.0) == 1


def test_zero_radius_only_coincident():
    pts = [(0, 0), (0, 0), (1, 0)]
    assert count_pairs_within(pts, 0.0) == 1  # only the coincident pair


def test_duplicates_count():
    pts = [(1, 1)] * 4
    # all pairs within r=0: C(4,2) = 6
    assert count_pairs_within(pts, 0.0) == 6


def test_square():
    pts = [(0, 0), (1, 0), (0, 1), (1, 1)]
    assert count_pairs_within(pts, 1.0) == 4  # 4 edges, diagonal is sqrt(2) > 1
    assert count_pairs_within(pts, 1.5) == 6  # all pairs


def test_negative_coords():
    pts = [(-1, -1), (-1.5, -1.5), (2, 2)]
    assert count_pairs_within(pts, 1.0) == 1
    assert count_pairs_within(pts, 5.0) == 3


def test_float_r():
    pts = [(0.0, 0.0), (0.5, 0.5)]
    assert count_pairs_within(pts, 0.7071067811865476) == 1
