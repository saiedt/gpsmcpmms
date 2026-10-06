"""REST API reachability plus the security contract (spec 4.4 / 4.8)."""

import io

import pytest
from gpsmcpmms import config_mgr

API = {"X-GPSMCPMMS-Api": "1"}


@pytest.fixture
def client(setup_demo_environment):
    """Flask test client against the initialized config_mgr, with a fresh
    (invalidated) exclusive session so each test can obtain its own token."""
    cfg = setup_demo_environment
    # Build the Flask app and register its routes without serving it.
    cfg.start_editor(run_server=False)
    cfg._flask_app.config["TESTING"] = True
    cfg._invalidate_session("test fixture starting from a clean session")
    with cfg._flask_app.test_client() as c:
        yield c


def _fresh_token(client):
    return client.get("/api/cvv_data").get_json()["token"]


def test_cvv_data_ok_and_hides_config_module(client):
    """GET /api/cvv_data is 200 JSON, exposes registered modules, and never
    leaks the internal `config` module (regression for the suppression)."""
    resp = client.get("/api/cvv_data")
    assert resp.status_code == 200
    assert resp.is_json
    cvv = resp.get_json()["cvv"]
    assert "config" not in cvv                       # internal module stays hidden
    assert {"log", "led", "sip", "vtest"} <= set(cvv)


def test_update_requires_csrf_header(client):
    """POST without the X-GPSMCPMMS-Api header is refused (anti-CSRF)."""
    resp = client.post("/api/config/update",
                       json={"module": "vtest", "value": {"n": 3}})
    assert resp.status_code == 403


def test_update_requires_valid_token(client):
    """POST with the header but no/invalid session token is unauthorized."""
    resp = client.post("/api/config/update", headers=API,
                       json={"module": "vtest", "value": {"n": 3}})
    assert resp.status_code == 401
    assert resp.get_json()["error"] == "invalid_token"


def test_valid_update_round_trips(client):
    """A properly authorized update to a non-protected param is applied."""
    token = _fresh_token(client)
    resp = client.post("/api/config/update",
                       headers={**API, "X-GPSMCPMMS-Token": token},
                       json={"module": "vtest", "value": {"n": 9}})
    assert resp.status_code == 200
    assert resp.get_json()["rejected"] == []
    assert config_mgr.query("vtest.n")["vtest.n"] == 9


def test_protected_param_stripped_for_non_admin(client):
    """Without admin, an update to a protected param is stripped, not applied."""
    token = _fresh_token(client)
    resp = client.post("/api/config/update",
                       headers={**API, "X-GPSMCPMMS-Token": token},
                       json={"module": "vtest", "value": {"secret": 42}})
    assert resp.status_code == 200
    assert resp.get_json()["rejected"]                       # secret rejected
    assert config_mgr.query("vtest.secret")["vtest.secret"] == 0   # unchanged


# --------------------------------------------------------------------------
# Bringing a retired module's parameters back (/api/config/revive)
# --------------------------------------------------------------------------

def _admin_token(client):
    """A session that has passed the password, which is what the button needs:
    only an administrator sees a resting module at all."""
    from gpsmcpmms.config import ConfigManager
    resp = client.get("/api/cvv_data?passwd="
                      + ConfigManager.FACTORY_DEFAULT_PASSWD)
    body = resp.get_json()
    assert body["admin"], "the fixture's device is not on the factory password"
    return body["token"]


def test_revive_needs_the_csrf_header(client):
    assert client.post("/api/config/revive",
                       json={"module": "napping"}).status_code == 403


def test_revive_needs_admin(client):
    token = _fresh_token(client)
    resp = client.post("/api/config/revive",
                       headers={**API, "X-GPSMCPMMS-Token": token},
                       json={"module": "napping"})
    assert resp.status_code == 403
    assert resp.get_json()["error"] == "admin_required"


def test_revive_of_a_module_that_is_not_resting_is_a_404(client):
    token = _admin_token(client)
    resp = client.post("/api/config/revive",
                       headers={**API, "X-GPSMCPMMS-Token": token},
                       json={"module": "vtest"})
    assert resp.status_code == 404


def test_revive_calls_the_module_back_and_hands_out_a_new_token(client):
    called = []
    config_mgr.register_params(
        module_id="napping", module_label="Napping",
        param_dict={"n": {"type": "int", "label": "N", "default_val": 1}},
        callback=lambda value: None)

    def wake_up():
        called.append(True)
        config_mgr.register_params(
            module_id="napping", module_label="Napping",
            param_dict={"n": {"type": "int", "label": "N", "default_val": 1}},
            callback=lambda value: None)

    config_mgr.discard_module("napping", revive=wake_up)
    token = _admin_token(client)
    resp = client.post("/api/config/revive",
                       headers={**API, "X-GPSMCPMMS-Token": token},
                       json={"module": "napping"})
    assert resp.status_code == 200
    assert called == [True]
    # Registering ends the editing session, so a new token comes back with the
    # answer; without it the administrator would be sent to the password
    # prompt for having pressed a button.
    assert resp.get_json()["token"]
    assert "napping" not in config_mgr._dormant


def test_a_way_back_that_does_not_register_is_reported_as_a_failure(client):
    config_mgr.register_params(
        module_id="dozing", module_label="Dozing",
        param_dict={"n": {"type": "int", "label": "N", "default_val": 1}},
        callback=lambda value: None)
    config_mgr.discard_module("dozing", revive=lambda: None)
    token = _admin_token(client)
    resp = client.post("/api/config/revive",
                       headers={**API, "X-GPSMCPMMS-Token": token},
                       json={"module": "dozing"})
    # It ran without raising and changed nothing. Calling that a success would
    # send the editor looking for a panel that is not there.
    assert resp.status_code == 500
    assert resp.get_json()["error"] == "revive_failed"


# --------------------------------------------------------------------------
# Who is told what a module found
# --------------------------------------------------------------------------

def test_a_finding_reaches_whoever_is_shown_what_it_is_about(client):
    from gpsmcpmms.config import ConfigManager
    config_mgr.register_params(
        module_id="told", module_label="Told",
        param_dict={"open": {"type": "int", "label": "Open",
                             "default_val": 1},
                    "closed": {"type": "int", "label": "Closed",
                               "protected": True, "default_val": 1}},
        callback=lambda value: [
            {"text": "About the open one.", "path": "told.open"},
            {"text": "About the closed one.", "path": "told.closed"},
            "About nothing in particular."])
    everything = ["About the open one.", "About the closed one.",
                  "About nothing in particular."]

    body = client.get("/api/cvv_data?passwd="
                      + ConfigManager.FACTORY_DEFAULT_PASSWD).get_json()
    assert body["admin"]
    assert body["module_status"]["told"] == everything

    config_mgr._invalidate_session("the same test, now without password")
    body = client.get("/api/cvv_data").get_json()
    assert not body["admin"]
    assert body["module_status"]["told"] == ["About the open one."]

    # The answer to a save is filtered the same way: it is the same banner.
    resp = client.post("/api/config/update",
                       headers={**API, "X-GPSMCPMMS-Token": body["token"]},
                       json={"module": "told", "value": {"open": 2}})
    assert resp.get_json()["module_status"]["told"] == ["About the open one."]

    # A read-only viewer is shown the open parameter, so the finding about it
    # comes along; the lock decides who may change a value, not who may read
    # what is wrong with it.
    body = client.get("/api/cvv_data").get_json()
    assert body["read_only"]
    assert body["module_status"]["told"] == ["About the open one."]


def test_an_update_writes_a_line_naming_the_module(client, caplog):
    # Without it an editing session can only be reconstructed from the
    # timestamps of the checkpoint files, which is guesswork -- and guesswork
    # about what somebody did five minutes ago sounds like an answer.
    token = _fresh_token(client)
    with caplog.at_level("INFO"):
        client.post("/api/config/update",
                    headers={**API, "X-GPSMCPMMS-Token": token},
                    json={"module": "vtest", "value": {"n": 3}})
    assert any("Module 'vtest' updated" in r.message for r in caplog.records)


def test_a_refused_token_writes_a_line_too(client, caplog):
    with caplog.at_level("INFO"):
        client.post("/api/config/update",
                    headers={**API, "X-GPSMCPMMS-Token": "not-the-token"},
                    json={"module": "vtest", "value": {"n": 3}})
    assert any("no longer the current one" in r.message
               for r in caplog.records)


# --------------------------------------------------------------------------
# Uploading into a 'file' parameter (/api/config/file)
# --------------------------------------------------------------------------

def test_a_refused_upload_says_why_in_a_key(client, tmp_path):
    # The editor translates the reason, so the reason has to be a key.
    # "Abgelehnt" stood here after the keys had moved to English, matched
    # none, and every reader was told in German. A fixed value is simply the
    # refusal easiest to provoke: whatever is uploaded, the value is not it.
    from gpsmcpmms.config import ConfigManager
    config_mgr.register_params(
        module_id="tones", module_label="Tones",
        param_dict={"ring": {"type": "file", "label": "Ring tone",
                             "file_dir": str(tmp_path),
                             "bound_to": r".+\.wav",
                             "fixed_val": "bell.wav"}},
        callback=lambda value: None)
    token = _fresh_token(client)
    resp = client.post("/api/config/file",
                       headers={**API, "X-GPSMCPMMS-Token": token},
                       data={"path": "tones.ring",
                             "file": (io.BytesIO(b"RIFF"), "horn.wav")})
    assert resp.status_code == 400
    assert resp.get_json()["error"] in ConfigManager.OWN_UI_KEYS
    # a file the value was refused for does not stay behind (spec 4.9.6)
    assert not (tmp_path / "horn.wav").exists()


# --------------------------------------------------------------------------
# The editor's own files: the library's part, the design's part
# --------------------------------------------------------------------------

def test_the_page_loads_the_core_before_the_design(client):
    # app.js builds on what core.js declares; the other order is a page that
    # stops at its first line.
    page = client.get("/").get_data(as_text=True)
    assert 0 < page.index('src="/core.js"') < page.index('src="/app.js"')


def test_the_core_comes_from_the_package_whatever_ui_dir_holds(client):
    # A deployment that brings its own design keeps the library's half up to
    # date by not having a copy of it: a core.js in ui_dir is never served.
    import os
    cfg = config_mgr
    stray = os.path.join(cfg.ui_dir, "core.js")
    with open(stray, "w", encoding="utf-8") as handle:
        handle.write("// a copy somebody left behind")
    try:
        body = client.get("/core.js").get_data(as_text=True)
    finally:
        os.remove(stray)
    assert "function validValue(" in body
    assert "left behind" not in body


def test_the_core_draws_nothing():
    # The whole point of the split: what is in core.js holds under every
    # design, and it can only do that while it never touches the page.
    import os
    import re
    import gpsmcpmms
    path = os.path.join(os.path.dirname(gpsmcpmms.__file__), "ui", "core.js")
    with open(path, encoding="utf-8") as handle:
        core = handle.read()
    for drawing in (r"document\.\w", r"createElement", r"location\.",
                    r"el\(", r"modal\(", r"msg\(", r"renderAll\("):
        assert not re.search(drawing, core), drawing


def test_the_default_design_speaks_to_the_device_only_through_the_core():
    # A design that issued requests of its own would have to be told about
    # every change to the REST-API; one that does not, cannot fall behind it.
    import os
    import gpsmcpmms
    path = os.path.join(os.path.dirname(gpsmcpmms.__file__), "ui",
                        "default.js")
    with open(path, encoding="utf-8") as handle:
        design = handle.read()
    for own_request in ("/api/", "fetch(", "FormData"):
        assert own_request not in design, own_request


def test_a_design_can_bring_files_of_its_own(client):
    import os
    folder = os.path.join(config_mgr.ui_dir, config_mgr.ASSET_SUBDIR, "fonts")
    os.makedirs(folder, exist_ok=True)
    font = os.path.join(folder, "own.woff2")
    with open(font, "wb") as handle:
        handle.write(b"wOF2")
    try:
        resp = client.get("/assets/fonts/own.woff2")
        assert resp.status_code == 200
        assert resp.get_data() == b"wOF2"
        resp.close()
    finally:
        os.remove(font)
    assert client.get("/assets/fonts/own.woff2").status_code == 404


def test_nothing_beside_the_asset_folder_can_be_fetched_through_it(client):
    # ui_dir also holds the dictionaries and a deployment's own design;
    # the route serves its own folder and does not climb out of it.
    import os
    os.makedirs(os.path.join(config_mgr.ui_dir, config_mgr.ASSET_SUBDIR),
                exist_ok=True)
    beside = os.path.join(config_mgr.ui_dir, "beside.txt")
    with open(beside, "w", encoding="utf-8") as handle:
        handle.write("not an asset")
    try:
        for name in ("../beside.txt", "..%2Fbeside.txt", "../lang/de.json"):
            assert client.get("/assets/" + name).status_code == 404
    finally:
        os.remove(beside)


# --------------------------------------------------------------------------
# The design: the library's by default, the deployment's own in its place
# --------------------------------------------------------------------------

DESIGN_ROUTES = {"html": "/", "css": "/app.css", "js": "/app.js"}


def _own_design(ext, text):
    import os
    path = os.path.join(config_mgr.ui_dir, "app." + ext)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)
    return path


def _served(client, route):
    resp = client.get(route)
    try:
        return resp.status_code, resp.get_data(as_text=True)
    finally:
        resp.close()


def test_without_a_design_of_its_own_a_deployment_gets_the_default(client):
    import os
    for ext in DESIGN_ROUTES:
        assert not os.path.exists(
            os.path.join(config_mgr.ui_dir, "app." + ext)), \
            "nothing is copied into ui_dir any more"
    status, page = _served(client, "/")
    assert status == 200 and 'href="/app.css"' in page
    assert "--accent" in _served(client, "/app.css")[1]
    assert "function renderAll(" in _served(client, "/app.js")[1]


def test_each_part_of_the_design_is_replaced_by_itself(client):
    # app.css alone is the common case: other colours, the stock editor.
    import os
    for ext, route in DESIGN_ROUTES.items():
        before = {r: _served(client, r)[1] for r in DESIGN_ROUTES.values()}
        path = _own_design(ext, "own " + ext)
        try:
            assert _served(client, route) == (200, "own " + ext)
            for other in DESIGN_ROUTES.values():
                if other != route:
                    assert _served(client, other)[1] == before[other]
        finally:
            os.remove(path)
        # taken away again, the default is back without a restart
        assert _served(client, route)[1] == before[route]


def test_the_default_stays_reachable_under_its_own_name(client):
    # What an app.css that begins with '@import "/default.css"' relies on.
    import os
    stock = _served(client, "/app.css")[1]
    path = _own_design("css", '@import "/default.css"; :root { --accent: red }')
    try:
        assert _served(client, "/default.css") == (200, stock)
        assert "function renderAll(" in _served(client, "/default.js")[1]
    finally:
        os.remove(path)


def _stage_like_before(files, record):
    """What a version before this one left in ui_dir."""
    import hashlib
    import json
    import os
    ui = config_mgr.ui_dir
    for name, text in files.items():
        with open(os.path.join(ui, name), "w", encoding="utf-8") as handle:
            handle.write(text)
    if record is not None:
        stamp = {name: hashlib.sha256(text.encode()).hexdigest()
                 for name, text in record.items()}
        with open(os.path.join(ui, ".staged.json"), "w",
                  encoding="utf-8") as handle:
            json.dump(stamp, handle)


def _ui_files():
    import os
    return sorted(name for name in os.listdir(config_mgr.ui_dir)
                  if os.path.isfile(os.path.join(config_mgr.ui_dir, name))
                  and name != "languages.json")


def _clear_ui_files():
    import os
    for name in _ui_files():
        os.remove(os.path.join(config_mgr.ui_dir, name))


def test_copies_nobody_touched_are_cleared_away_with_their_record(client):
    # Left lying, they would count as this deployment's own design and keep
    # serving the frontend of the version that staged them, for good.
    staged = {"index.html": "old page", "style.css": "old css",
              "app.js": "old js"}
    _stage_like_before(staged, staged)
    try:
        config_mgr._retire_staged_assets()
        assert _ui_files() == []
        assert "function renderAll(" in _served(client, "/app.js")[1]
    finally:
        _clear_ui_files()


def test_a_copy_the_deployment_changed_becomes_its_own_design(client):
    staged = {"index.html": "old page", "style.css": "old css",
              "app.js": "old js"}
    _stage_like_before(dict(staged, **{"style.css": "our colours"}), staged)
    try:
        config_mgr._retire_staged_assets()
        assert _ui_files() == ["app.css"]
        assert _served(client, "/app.css") == (200, "our colours")
    finally:
        _clear_ui_files()


def test_a_copy_without_a_record_is_set_aside_not_trusted(client):
    _stage_like_before({"index.html": "whose?", "app.js": "whose?"}, None)
    try:
        config_mgr._retire_staged_assets()
        assert _ui_files() == ["app.js.local", "index.html.local"]
        assert 'href="/app.css"' in _served(client, "/")[1]
    finally:
        _clear_ui_files()


def test_an_own_script_alone_is_nothing_to_clear_away(client):
    # app.js is a name on both sides of the change. Without a record and
    # without the two old names beside it, it is simply a design.
    import os
    path = _own_design("js", "own js")
    try:
        config_mgr._retire_staged_assets()
        assert _ui_files() == ["app.js"]
    finally:
        os.remove(path)
