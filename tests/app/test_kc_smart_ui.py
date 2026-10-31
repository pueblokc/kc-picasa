"""Smart Search confidence and presentation rules."""

from picasapy.app.kc_smart_ui import result_cards, strong_matches


def test_flat_scores_are_not_presented_as_strong_matches():
    assert not strong_matches([(str(i), 0.265 - i * 0.0002) for i in range(50)])


def test_clear_score_gap_is_a_match():
    assert strong_matches([("winner", 0.33)] + [(str(i), 0.25) for i in range(49)])


def test_weak_absolute_score_is_not_a_match():
    assert not strong_matches([("winner", 0.24)] + [(str(i), 0.1) for i in range(49)])


def test_result_cards_include_reveal_folder(tmp_path):
    photo = tmp_path / "one.jpg"
    card = result_cards([(str(photo), 0.321)])[0]
    assert card["folder"] == str(tmp_path)
    assert card["score"] == 32
