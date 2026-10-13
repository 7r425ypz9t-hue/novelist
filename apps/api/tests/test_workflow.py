"""«مسار الرواية»: stage states follow live data; the next step follows editorial priority and the user's role."""

LONG = ("كان نادر يقف عند الميناء كل مساء يعدّ السفن العائدة واحدةً واحدة، ثم يعود إلى بيته صامتاً. " * 60).strip()


def _wf(w, pid):
    r = w.get(f"/v1/projects/{pid}/workflow")
    assert r.status_code == 200, r.text
    body = r.json()
    return body, {s["key"]: s for s in body["stages"]}


def test_path_moves_with_the_novel_and_recommends_one_next_step(writer):
    p = writer.project("رواية المسار")
    pid = p["id"]
    body, st = _wf(writer, pid)
    assert body["next"]["key"] == "foundation" and st["writing"]["state"] == "todo"
    assert body["next"]["action"]["to"] == f"/p/{pid}/settings" and body["next"]["why"]

    assert writer.patch(f"/v1/projects/{pid}", json={"logline": "صبيّ يتعلّم الانتظار", "word_goal": 600}).status_code == 200
    ch = writer.node(pid, "chapter", "الأول")
    assert writer.write(ch["document_id"], "بداية قصيرة.").status_code == 200
    body, st = _wf(writer, pid)
    assert st["foundation"]["state"] == "done"
    assert body["next"]["key"] == "bible"                      # no characters yet

    assert writer.post(f"/v1/projects/{pid}/characters", json={"canonical_name": "نادر"}).status_code == 201
    body, st = _wf(writer, pid)
    assert body["next"]["key"] == "writing" and st["analysis"]["state"] == "todo"   # too short to analyse

    assert writer.write(ch["document_id"], LONG).status_code == 200
    body, st = _wf(writer, pid)
    assert st["analysis"]["state"] == "active" and body["next"]["key"] == "analysis"

    run = writer.run(pid, "A00", confirm_high_risk=True).json()
    assert run["status"] in ("succeeded", "partial"), run
    body, st = _wf(writer, pid)
    assert st["analysis"]["state"] == "done"
    if st["decisions"]["state"] == "active":
        assert body["next"]["key"] in ("continuity", "decisions")
    assert body["total"] == 8 and 0 < body["done"] <= 8

    # editing after the check makes it stale again
    assert writer.write(ch["document_id"], LONG + " وانتهى المساء.").status_code == 200
    assert _wf(writer, pid)[1]["analysis"]["state"] == "active"


def test_actions_respect_the_role_and_strangers_get_404(writer, make_writer):
    p = writer.project("رواية الأدوار")
    reader = make_writer("reader")
    writer.post(f"/v1/projects/{p['id']}/members", json={"email": reader.email, "role": "reader"})
    body, st = _wf(reader, p["id"])
    assert st["writing"]["action"] is None and st["foundation"]["action"] is None   # nothing a reader cannot do
    assert body["next"] is None or body["next"]["action"] is not None
    assert make_writer("stranger").get(f"/v1/projects/{p['id']}/workflow").status_code == 404


def test_a_check_already_run_is_tracked_even_on_a_short_draft(writer):
    p = writer.project("قصة قصيرة")
    ch = writer.node(p["id"], "chapter", "الوحيد")
    assert writer.write(ch["document_id"], "سطران فقط.").status_code == 200
    assert _wf(writer, p["id"])[1]["analysis"]["state"] == "todo"
    assert writer.run(p["id"], "A00", confirm_high_risk=True).json()["status"] in ("succeeded", "partial")
    assert _wf(writer, p["id"])[1]["analysis"]["state"] == "done"
    assert writer.write(ch["document_id"], "سطران فقط، وثالث.").status_code == 200
    assert _wf(writer, p["id"])[1]["analysis"]["state"] == "active"
