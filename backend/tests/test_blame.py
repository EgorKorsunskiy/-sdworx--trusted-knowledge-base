from app.services.blame import VersionSnap, compute_blame, contributor_stats
from app.services.diff import split_fragments, split_fragments_ex


def S(n, body, editor):
    return VersionSnap(n, body, editor)


def test_single_version():
    lines = compute_blame([S(1, "One. Two.\nThree.", 5)])
    assert [l.text for l in lines] == ["One.", "Two.", "Three."]
    assert all(l.contributor_ids == (5,) and l.introduced_in == 1 and l.last_edited_in == 1 for l in lines)


def test_added_fragment_attributed_to_editor():
    lines = compute_blame([S(1, "One.", 1), S(2, "One. Two.", 2)])
    assert lines[0].contributor_ids == (1,)
    assert lines[1].contributor_ids == (2,)
    assert (lines[1].introduced_in, lines[1].last_edited_in) == (2, 2)


def test_edited_fragment_keeps_previous_contributors():
    lines = compute_blame([S(1, "The cat sat.", 1), S(2, "The cat slept.", 2)])
    assert len(lines) == 1
    assert lines[0].contributor_ids == (1, 2)
    assert (lines[0].introduced_in, lines[0].last_edited_in) == (1, 2)


def test_removed_fragment_dropped():
    lines = compute_blame([S(1, "One. Two. Three.", 1), S(2, "One. Three.", 2)])
    assert [l.text for l in lines] == ["One.", "Three."]
    assert all(l.contributor_ids == (1,) for l in lines)
    stats = contributor_stats(lines)
    assert [s["user_id"] for s in stats] == [1]


def test_duplicate_identical_fragments():
    lines = compute_blame([S(1, "Same. Same.", 1), S(2, "Same. Same. Same.", 2)])
    assert [l.text for l in lines] == ["Same."] * 3
    owners = [l.contributor_ids for l in lines]
    assert owners.count((1,)) == 2 and owners.count((2,)) == 1


def test_back_and_forth_dedupes_in_order():
    lines = compute_blame(
        [S(1, "Alpha beta.", 1), S(2, "Alpha gamma.", 2), S(3, "Alpha delta.", 1)]
    )
    assert lines[0].contributor_ids == (1, 2)
    assert (lines[0].introduced_in, lines[0].last_edited_in) == (1, 3)


def test_empty_body():
    assert compute_blame([S(1, "", 1)]) == []
    assert compute_blame([S(1, "One.", 1), S(2, "", 2)]) == []
    assert contributor_stats([]) == []


def test_title_only_change_adds_no_contributor():
    lines = compute_blame([S(1, "One. Two.", 1), S(2, "One. Two.", 2)])
    assert all(l.contributor_ids == (1,) and l.last_edited_in == 1 for l in lines)


def test_every_fragment_has_contributor_in_long_scenario():
    bodies = [
        "A one. A two. A three.",
        "A one. A two changed. A three.\nNew line.",
        "A one.\nNew line. Extra.",
        "Totally different. Extra.",
        "Totally different now. Extra. A one.",
        "",
        "Back again.",
    ]
    snaps = [S(i + 1, b, (i % 3) + 1) for i, b in enumerate(bodies)]
    for k in range(1, len(snaps) + 1):
        lines = compute_blame(snaps[:k])
        assert [l.text for l in lines] == split_fragments(snaps[k - 1].body)
        assert all(len(l.contributor_ids) >= 1 for l in lines)


def test_split_fragments_ex_round_trip():
    for body in ["One.\r\nTwo.", "One.\n\nTwo three. Four!", "A.  B?   C\nD", "Just one"]:
        frags = split_fragments_ex(body)
        assert "".join(s + t for s, t in frags) == body.replace("\r\n", "\n")
        assert [t for _, t in frags] == split_fragments(body)
    assert split_fragments_ex("One.\n\nTwo.") == [("", "One."), ("\n\n", "Two.")]
    assert split_fragments_ex("A. B") == [("", "A."), (" ", "B")]
    assert split_fragments_ex(None) == []


def test_contributor_stats_ordering_and_counts():
    snaps = [S(1, "One. Two.", 2), S(2, "One. Two. Three. Four.", 1), S(3, "One. Two. Three. Four. Five.", 3)]
    stats = contributor_stats(compute_blame(snaps))
    by = {s["user_id"]: s for s in stats}
    assert by[2]["fragment_count"] == 2 and by[2]["fragment_indexes"] == [0, 1]
    assert by[1]["fragment_count"] == 2 and by[1]["fragment_indexes"] == [2, 3]
    assert by[3]["fragment_count"] == 1 and by[3]["first_version"] == 3
    # tie on count: smaller first_version first
    assert [s["user_id"] for s in stats] == [2, 1, 3]
