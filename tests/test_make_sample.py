import pandas as pd
import pytest

import make_sample as ms


def small_communes():
    """Tiny hand-made table: 3 small, 3 medium, 2 large communes."""
    return pd.DataFrame({
        "qid": [f"Q{i}" for i in range(8)],
        "insee": ["01049", "2A004", "2B033", "77186", "97105", "97411", "75056", "13055"],
        "name": list("ABCDEFGH"),
        "pop": [100, 499, 500, 1999, 2000, 50000, 49999, 2_000_000],
        "lat": [0.0] * 8,
        "lon": [0.0] * 8,
    })


def test_add_department_all_cases():
    out = ms.add_department(small_communes())
    assert out["departement"].tolist() == ["01", "2A", "2B", "77", "971", "974", "75", "13"]


def test_add_department_does_not_modify_input():
    df = small_communes()
    ms.add_department(df)
    assert "departement" not in df.columns


def test_add_size_class_bounds():
    out = ms.add_size_class(small_communes(), ms.SIZE_BINS, ms.SIZE_LABELS)
    assert out["taille"].astype(str).tolist() == [
        "<500", "<500", "500-1999", "500-1999",
        "2000-9999", ">=50000", "10000-49999", ">=50000",
    ]


def test_count_strata_sums_to_total():
    out = ms.add_size_class(small_communes(), ms.SIZE_BINS, ms.SIZE_LABELS)
    assert ms.count_strata(out)["communes"].sum() == len(out)


def test_draw_stratified_respects_quota_and_small_strata():
    df = ms.add_size_class(small_communes(), ms.SIZE_BINS, ms.SIZE_LABELS)
    sample = ms.draw_stratified(df, {"<500": 1, ">=50000": 5}, seed=1)
    counts = sample["taille"].value_counts()
    assert counts["<500"] == 1
    assert counts[">=50000"] == 2          # stratum smaller than quota: take all


def test_draw_stratified_is_reproducible():
    df = ms.add_size_class(small_communes(), ms.SIZE_BINS, ms.SIZE_LABELS)
    a = ms.draw_stratified(df, {"<500": 1}, seed=7)
    b = ms.draw_stratified(df, {"<500": 1}, seed=7)
    assert a["insee"].tolist() == b["insee"].tolist()


def test_forced_commune_is_included_and_size_unchanged():
    df = ms.add_size_class(small_communes(), ms.SIZE_BINS, ms.SIZE_LABELS)
    sample = ms.draw_stratified(df, {">=50000": 1}, seed=3)
    forced = [c for c in ["97411", "75056"] if c not in set(sample["insee"])][0]
    out = ms.add_forced_communes(sample, df, [forced], seed=3)
    assert forced in set(out["insee"])
    assert len(out) == len(sample)
    assert out["insee"].is_unique


def test_forced_unknown_code_raises():
    df = ms.add_size_class(small_communes(), ms.SIZE_BINS, ms.SIZE_LABELS)
    with pytest.raises(ValueError):
        ms.add_forced_communes(df.head(1), df, ["99999"], seed=1)


def test_save_sample_sorted_and_insee_stays_text(tmp_path):
    df = ms.add_department(small_communes())
    df = ms.add_size_class(df, ms.SIZE_BINS, ms.SIZE_LABELS)
    path = tmp_path / "s.csv"
    ms.save_sample(df, str(path))
    back = pd.read_csv(path, dtype={"insee": str})
    assert back["insee"].tolist() == sorted(back["insee"].tolist())
    assert "01049" in back["insee"].tolist()