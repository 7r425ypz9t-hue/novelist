"""Style fingerprint consent (AT18) and the experimental NLQI rubric."""

SAMPLE = ("كان البحر يتنفس ببطء، وكانت المدينة تنام على صوته. " * 40).strip()


def test_AT18_protected_sample_without_permission_is_refused(writer):
    p = writer.project()
    for basis in ("third_party", "unknown"):
        r = writer.post(f"/v1/projects/{p['id']}/style-profiles",
                        json={"name": "x", "samples": [SAMPLE], "rights_basis": basis, "declaration": True})
        assert r.status_code == 422 and r.json()["type"] == "/problems/unlicensed-sample"
    r = writer.post(f"/v1/projects/{p['id']}/style-profiles",
                    json={"name": "x", "samples": [SAMPLE], "rights_basis": "own_work", "declaration": True,
                          "imitate_author": "مؤلف حي مشهور"})
    assert r.status_code == 422 and r.json()["type"] == "/problems/imitation-refused"
    assert writer.get(f"/v1/projects/{p['id']}/style-profiles").json()["items"] == []


def test_owned_samples_build_erasable_profile_without_storing_text(writer):
    p = writer.project()
    r = writer.post(f"/v1/projects/{p['id']}/style-profiles",
                    json={"name": "صوتي", "samples": [SAMPLE, SAMPLE + " ثم صمت."], "rights_basis": "own_work",
                          "declaration": True})
    assert r.status_code == 201
    prof = r.json()
    assert prof["features"]["mean_sentence_words"] > 0 and "البحر" not in str(prof["features"])
    assert writer.delete(f"/v1/projects/{p['id']}/style-profiles/{prof['id']}").status_code == 204
    assert writer.get(f"/v1/projects/{p['id']}/style-profiles").json()["items"] == []


def test_nlqi_is_weighted_human_rubric_with_disagreement(make_writer):
    owner, reader = make_writer("o"), make_writer("r")
    p = owner.project()
    owner.post(f"/v1/projects/{p['id']}/members", json={"email": reader.email, "role": "reader"})
    assert owner.put(f"/v1/projects/{p['id']}/nlqi/weights", json={"weights": {"plot": 50}}).status_code == 400
    owner.post(f"/v1/projects/{p['id']}/nlqi/assessments", json={"scores": {"plot": 8, "style": 6}, "notes": {"plot": "حبكة محكمة"}})
    reader.post(f"/v1/projects/{p['id']}/nlqi/assessments", json={"scores": {"plot": 4, "style": 6}})
    n = owner.get(f"/v1/projects/{p['id']}/nlqi").json()
    plot = next(d for d in n["dimensions"] if d["key"] == "plot")
    assert plot["mean"] == 6 and plot["spread"] == 2 and plot["raters"] == 2
    assert n["assessments"][0]["index"] == 70.0  # (15*8 + 15*6)/30 → 70% of covered weight
    assert "تجريبي" in n["disclaimer"] and "ليس نتيجة علمية" in n["disclaimer"]
