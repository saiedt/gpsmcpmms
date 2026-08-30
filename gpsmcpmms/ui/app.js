/*
 * Copyright 2026 saiedt
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

/* GPSMCPMMS config-editor frontend (spec sections 4.4 - 4.9).
 * The editing token lives ONLY in this runtime memory (spec 4.8). */
"use strict";

const S = {
    token: null, readOnly: false, admin: false, factory: false,
    lockFreeIn: null,        // seconds until the foreign session lapses
    protectedOmitted: false,
    cvv: {},                 // parsed /api/cvv_data dump
    xl: {},                  // active translation dictionary
    // What somebody chose last, failing that the language of their browser,
    // failing that the one the source keys are written in. A fixed "de" stood
    // here while the keys were German; today that would name a language
    // nobody told the device about -- and for a German visitor it falls out
    // anyway. Whether a dictionary exists for it is loadLangList()'s verdict.
    lang: localStorage.getItem("gpsmcpmms_lang") ||
          (navigator.language || "").split("-")[0] || "en",
    // Until /api/lang/info answers, assume only the source language exists:
    // it is the one language that is always there, being every key's own
    // wording. The server names it in `source` -- never guess it here again.
    sourceLang: "en",
    languages: ["en"],
    // Whether the hosting application named the languages it permits. It
    // decides the shape of the "new language" row, so assume it does until
    // /api/lang/info says otherwise: shutting the fields on a deployment that
    // turns out to be open is a moment's confusion, opening them on one that
    // is bounded invites a code the device will refuse.
    bounded: true,
    appTitle: "",            // what the hosting application calls itself
    langNames: {},           // code -> name; the app's list, or endonyms
    langPanel: null,         // null | "new" | "edit"
    langForm: {},            // what the open panel has been told so far
    coverage: null,          // {total, done:{lang:n}}; admins only
    orphans: null,           // lang -> keys nothing registers; admins only
    edit: {},                // moduleId -> working value (deep copy)
    dirty: {},               // moduleId -> bool
    adopted: {},             // moduleId -> Set of likely_val fields filled in
    open: {},                // dump path -> group expanded?
    enums: {},               // dump path -> {values}|{error}|{pending}
    hints: {},               // dump path -> {text, at}|{error}|{pending}
    pendingFiles: {},        // dump path -> [{name, file}] chosen, not yet sent
    listsA: {},              // dump path -> {sel}
    listsB: {},              // dump path -> {pos, draft, changed}
    probeBad: {},            // dump path -> the device refused this value
};

function xl(key) { return S.xl[key] || key; }
function deepCopy(v) { return v === undefined ? v : JSON.parse(JSON.stringify(v)); }
function getIn(obj, keys) {
    let cur = obj;
    for (const k of keys) {
        if (cur === null || cur === undefined) return undefined;
        cur = cur[k];
    }
    return cur;
}
function setIn(obj, keys, val) {
    let cur = obj;
    for (const k of keys.slice(0, -1)) cur = cur[k];
    cur[keys[keys.length - 1]] = val;
}

/* ---------- API ---------- */
async function api(path, opts = {}) {
    const headers = Object.assign(
        {"X-GPSMCPMMS-Api": "1"}, opts.headers || {});
    if (S.token) headers["X-GPSMCPMMS-Token"] = S.token;
    if (opts.json !== undefined) {
        headers["Content-Type"] = "application/json";
        opts.body = JSON.stringify(opts.json);
        opts.method = opts.method || "POST";
    }
    const resp = await fetch(path, Object.assign({}, opts, {headers}));
    let data = null;
    try { data = await resp.json(); } catch (e) { /* non-json */ }
    return {status: resp.status, data};
}

/* ---------- tiny DOM + modal helpers ---------- */
function el(tag, attrs, ...children) {
    const node = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
        if (k === "class") node.className = v;
        else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
        else if (v !== null && v !== undefined) node.setAttribute(k, v);
    }
    for (const c of children) {
        if (c === null || c === undefined) continue;
        node.append(c.nodeType ? c : document.createTextNode(c));
    }
    return node;
}

function modal(text, options = {}) {
    // options: {input: {type, value, placeholder}, select: [..], alert: bool}
    return new Promise((resolve) => {
        const root = document.getElementById("modal-root");
        const close = (result) => { root.innerHTML = ""; resolve(result); };
        let input = null, select = null;
        if (options.input) {
            input = el("input", {
                type: options.input.type || "text",
                value: options.input.value || "",
                placeholder: options.input.placeholder || ""});
        }
        if (options.select) {
            select = el("select", {},
                ...options.select.map(o => el("option", {value: o}, o)));
        }
        const buttons = [el("button", {
            class: "primary",
            onclick: () => close(input ? input.value :
                                 select ? select.value : true)
        }, xl("OK"))];
        if (!options.alert) {
            buttons.push(el("button", {onclick: () => close(null)},
                            xl("Cancel")));
        }
        // An array becomes one paragraph per entry. A newline would not do:
        // the text lands in a single <p>, where the browser folds it away.
        // An entry that is already an element is taken as it comes, which is
        // how a caller gives one paragraph a colour of its own.
        const box = el("div", {class: "modal"},
            ...(Array.isArray(text)
                    ? text.filter(Boolean).map(
                          t => t instanceof Node ? t : el("p", {}, t))
                    : [el("p", {}, text)]),
            input, select,
            el("div", {class: "buttons"}, ...buttons));
        root.append(el("div", {class: "overlay"}, box));
        if (input) { input.focus(); input.addEventListener("keydown",
            (e) => { if (e.key === "Enter" || e.keyCode === 13)
                         close(input.value); }); }
    });
}

/* Freezes the whole editor behind a button-less overlay while a backend
   operation is pending, and returns the function that thaws it again. Callers
   must thaw in a `finally`, so a failure can never leave the editor stuck. */
function freeze(text) {
    const overlay = el("div", {class: "overlay"},
        el("div", {class: "modal busy"}, el("p", {}, text)));
    document.getElementById("modal-root").append(overlay);
    return () => overlay.remove();
}

let msgTimer = null;
function msg(text, cls = "info") {
    const box = document.getElementById("messages");
    if (!box) return;
    box.innerHTML = "";
    box.append(el("div", {class: `msg ${cls}`}, text));
    clearTimeout(msgTimer);
    if (cls !== "error") msgTimer = setTimeout(() => box.innerHTML = "", 6000);
}

/* ---------- values, scaling, validation ---------- */
function composeValue(node) {
    if (node.children) {
        const value = {};
        for (const [k, c] of Object.entries(node.children))
            value[k] = composeValue(c);
        return value;
    }
    return deepCopy(node.value === undefined ? null : node.value);
}

function scaleOut(ui, v) {   // model -> display
    if (v === null || v === undefined || !ui.scale_op) return v;
    const f = parseFloat(ui.scale_factor);
    const r = ui.scale_op === "*" ? v * f : v / f;
    return +r.toPrecision(12);
}
function scaleIn(ui, cons, d) {   // display -> model
    if (d === null || !ui.scale_op) return d;
    const f = parseFloat(ui.scale_factor);
    let r = ui.scale_op === "*" ? d / f : d * f;
    if (cons.ranged_int || cons.type === "int") r = Math.round(r);
    return +r.toPrecision(12);
}

function inRange(v, range) {
    return ((range[0] === null || v >= range[0]) &&
            (range[1] === null || v <= range[1]));
}

function validValue(cons, v) {   // v in model space; null = unset -> valid
    if (v === null || v === undefined) return true;
    if (Array.isArray(cons.one_of))
        return cons.one_of.some(o => o.value === v);
    if (typeof cons.one_of === "string") return typeof v === "string";
    if (cons.patterned_string !== undefined)
        return typeof v === "string" &&
               new RegExp(`^(?:${cons.patterned_string})$`).test(v);
    if (cons.ranged_int) return Number.isInteger(v) && inRange(v, cons.ranged_int);
    if (cons.ranged_float)
        return typeof v === "number" && inRange(v, cons.ranged_float);
    switch (cons.type) {
        case "boolean": return typeof v === "boolean";
        case "color": return Array.isArray(v) && v.length === 3;
        case "int": return Number.isInteger(v);
        case "float": return typeof v === "number";
        case "path": case "pingable": case "url":
            return typeof v === "string" && v !== "" && !/[\s]/.test(v);
        default: return typeof v === "string";   // string, password
    }
}

function relevanceHolds(rule, dictValue) {
    const l = dictValue ? dictValue[rule.child_key] : undefined;
    const r = rule.value;
    switch (rule.op) {
        case "==": return l === r;
        case "!=": return l !== r;
        case "~=": return typeof l === "string" && typeof r === "string" &&
                          new RegExp(r).test(l);
    }
    if (l === null || l === undefined) return false;
    switch (rule.op) {
        case "<": return l < r;
        case ">": return l > r;
        case "<=": return l <= r;
        case ">=": return l >= r;
    }
    return false;
}

/* ---------- dynamic enums (spec 4.9.1) ---------- */
/* `arg` is the current value of the sibling a 'values_for' declaration named,
   or undefined where none was declared. It is remembered beside the options,
   because that is what says whether they are still the answer to the question
   being asked -- and without it every render would ask again, and every
   answer would render again. */
async function fetchEnumOptions(path, rerender, arg) {
    S.enums[path] = {pending: true, arg};
    let url = `/api/config/enum-options?path=${encodeURIComponent(path)}`;
    if (arg !== undefined)
        url += `&arg=${encodeURIComponent(JSON.stringify(arg))}`;
    const r = await api(url);
    S.enums[path] = (r.data && r.data.values) ? {values: r.data.values, arg}
                  : {error: (r.data && r.data.error) || xl("No answer from the device."),
                     arg};
    // xl() on a string the device sent: the library's own failure messages are
    // registered keys, and a text the hosting application invented falls
    // through to itself. Rendering it raw left the library's own German --
    // and later English -- standing in a Turkish editor.
    if (S.enums[path].error) msg(xl(S.enums[path].error), "error");
    rerender();
}

/* ---------- hints (spec 4.9.5) ----------
   A tooltip explains and is timeless. A hint asserts something about the
   present, so it is fetched rather than declared, and shown with the moment it
   was established -- an assertion nobody dated goes on claiming it long after
   it stopped being so. */
async function fetchHint(path, rerender) {
    S.hints[path] = {pending: true};
    const r = await api(`/api/config/hint?path=${encodeURIComponent(path)}` +
                        `&lang=${encodeURIComponent(S.lang || S.sourceLang)}`);
    S.hints[path] = (r.data && typeof r.data.text === "string")
                  ? {text: r.data.text, at: r.data.at}
                  : {error: (r.data && r.data.error) ||
                            xl("No answer from the device.")};
    rerender();
}

function hintFor(node, ctx) {
    const hint = node.ui && node.ui.hint;
    if (!hint) return null;
    if (hint !== true)                       // declared text: nothing to ask
        return el("div", {class: "hint"}, xl(hint));

    const state = S.hints[node.path];
    if (!state) {
        fetchHint(node.path, ctx.rerender);
        return el("div", {class: "hint"}, "…");
    }
    if (state.pending) return el("div", {class: "hint"}, "…");
    if (state.error)
        return el("div", {class: "hint invalid"}, xl(state.error));
    return el("div", {class: "hint"},
        el("span", {class: "hint-text"}, state.text),
        el("span", {class: "hint-meta"}, `${xl("As of")} ${state.at}`),
        el("button", {class: "hint-refresh", type: "button",
                      title: xl("Refresh"),
                      onclick: () => fetchHint(node.path, ctx.rerender)},
           "↻"));
}

/* ---------- uploading into a 'file' parameter ---------- */
/* Choosing a file does not transfer it. It joins the options and gets
   selected, and nothing leaves the browser until the module is saved -- so a
   file parameter behaves like every other field, where nothing is committed
   until Save and Undo really does undo. Sending it at once also wrote
   to the device on the strength of a click that the user might never confirm. */
function pendingFilesFor(path) {
    return S.pendingFiles[path] || (S.pendingFiles[path] = []);
}

function uploadButton(node, ctx, commit) {
    const pattern = (node.constraints || {}).patterned_string;
    const picker = el("input", {type: "file", multiple: "",
                                style: "display:none",
        onchange: (e) => {
            const files = Array.from(e.target.files || []);
            e.target.value = "";              // so the same file can be re-sent
            if (!files.length) return;
            const queue = pendingFilesFor(node.path), refused = [];
            let selected = null;
            for (const file of files) {
                const name = file.name;
                // checked here as well as on the device: the answer must come
                // while the file picker is still fresh in mind, not at save
                if (name !== name.replace(/^.*[\\/]/, "") || name.includes("..")
                        || (pattern && !new RegExp(`^(?:${pattern})$`).test(name))) {
                    refused.push(name);
                    continue;
                }
                const at = queue.findIndex(p => p.name === name);
                if (at >= 0) queue.splice(at, 1);
                queue.push({name, file});
                selected = name;
            }
            if (refused.length)
                msg(`${xl("File type not allowed")}: ${refused.join(", ")}`,
                    "error");
            if (selected !== null) commit(selected);
            else ctx.rerender();
        }});
    return el("span", {class: "file-upload"}, picker,
        el("button", {class: "btn", type: "button",
                      onclick: () => picker.click()},
           xl("Choose file")));
}

/* Sends what the file fields of a module are holding, just before its values
   go. Returns false when something was refused, and then the save is abandoned
   rather than saving a value naming a file that never arrived. */
async function flushPendingFiles(mid) {
    const paths = Object.keys(S.pendingFiles)
        .filter(p => p === mid || p.startsWith(mid + "."));
    for (const path of paths) {
        for (const {name, file} of S.pendingFiles[path]) {
            const fd = new FormData();
            fd.append("path", path);
            fd.append("file", file);
            if (S.token) fd.append("token", S.token);
            const resp = await fetch("/api/config/file",
                {method: "POST", headers: authHeaders(), body: fd});
            if (!resp.ok) {
                let err = resp.status;
                try { err = (await resp.json()).error || err; } catch (e) {/**/}
                msg(`${xl("Invalid file")}: ${name}: ${err}`, "error");
                return false;
            }
        }
        delete S.pendingFiles[path];
        delete S.enums[path];      // the options must be asked for again
    }
    return true;
}

/* ---------- single input fields ---------- */
function hexOfColor(v) {
    if (!Array.isArray(v)) return "#000000";
    return "#" + v.map(x => (x || 0).toString(16).padStart(2, "0")).join("");
}
function colorOfHex(h) {
    return [1, 3, 5].map(i => parseInt(h.slice(i, i + 2), 16));
}

function buildInput(node, cur, commit, commitQuiet, ctx, enumArg) {
    // returns an element whose 'change' leads to commit(newModelValue)
    const cons = node.constraints || {}, ui = node.ui || {};
    const fixed = S.readOnly || node.configurability === 0;
    const backend = node.configurability === 2;
    const fail = (input) => {
        input.classList.add("invalid");
        msg(xl("Invalid input"), "error");
        setTimeout(() => input.focus(), 0);   // keep the focus (spec 4.5)
    };
    const ok = (input, v) => { input.classList.remove("invalid"); commit(v); };

    if (cons.type === "boolean") {
        return el("input", {type: "checkbox", disabled: fixed ? "" : null,
            // touching the box always answers it, so the third state goes away
            onchange: (e) => { e.target.indeterminate = false;
                               commit(e.target.checked); }},
            );
    }
    if (cons.one_of !== undefined) {
        let options = Array.isArray(cons.one_of) ? cons.one_of : null;
        if (options === null) {           // dynamic enum
            const state = S.enums[node.path];
            // Ask again as soon as the field the options are computed from
            // has become another one -- in the draft, long before saving:
            // the voices of a language nobody has applied yet.
            if (!state || state.arg !== enumArg) {
                fetchEnumOptions(node.path, ctx.rerender, enumArg);
                return el("select", {disabled: ""}, el("option", {}, "…"));
            }
            if (state.pending)
                return el("select", {disabled: ""}, el("option", {}, "…"));
            if (state.error)
                return el("select", {disabled: "", class: "invalid"},
                          el("option", {}, xl(state.error)));
            options = Object.entries(state.values).map(([value, o]) =>
                ({value, label: (o && o.label) || value,
                  tooltip: o && o.tooltip,
                  // a name the service made up is not translated -- and so
                  // stands in no dictionary either
                  verbatim: !!(o && o.verbatim)}));
        }
        // a file waiting to be sent is already choosable, though the device
        // has never heard of it -- that is the whole point of choosing before
        // saving
        if (cons.type === "file")
            for (const {name} of (S.pendingFiles[node.path] || []))
                if (!options.some(o => o.value === name))
                    options.push({value: name, label: name});
        // A dynamic enum's options are settled only at runtime, which is why
        // the core could never check the stored value against them ("defer
        // the exact check" in cvv_tree). Once the provider stops offering it
        // -- a German voice, say, after the announcement language moved to
        // Turkish -- it is no longer a choice but a leftover. The field
        // already *looked* empty, because no <option> matched it; here that
        // becomes true, so saving really is rid of it and the device's state
        // agrees with what is on screen. Dynamic enums only: a static one the
        // core checks at load time, discarding whatever no longer fits the
        // declaration.
        if (Array.isArray(cons.one_of) === false && !fixed && !backend &&
                cur !== null && cur !== undefined && cur !== "" &&
                !options.some(o => o.value === cur)) {
            commitQuiet(null);
            cur = null;
        }
        if (ctx.usedEnumValues)           // uniqueness filter (spec 4.9.2)
            options = options.filter(o => o.value === cur ||
                                          !ctx.usedEnumValues.has(o.value));
        // An option's tooltip goes into the visible text, not only into the
        // title. A title on an <option> is honoured by hardly any browser --
        // Firefox shows it, Chrome and Edge do not -- and a hint nobody sees
        // is the same as no hint. It cost somebody an afternoon of listening
        // to voices they did not want, because the one thing that told male
        // from female was in that title.
        //
        // The two halves are translated differently on purpose: a verbatim
        // label is an identifier and stays as it is, while the tooltip beside
        // it is prose. So "de-DE-Wavenet-H (weiblich)" -- the name untouched,
        // the hint in the reader's language.
        const sel = el("select", {disabled: fixed || backend ? "" : null,
                onchange: (e) => commit(e.target.value || null)},
            el("option", {value: ""}, ""),
            ...options.map(o => {
                const text = o.verbatim ? o.label : xl(o.label);
                const hint = o.tooltip ? xl(o.tooltip) : null;
                return el("option", {value: o.value, title: hint},
                          hint ? `${text} (${hint})` : text);
            }));
        sel.value = cur === null || cur === undefined ? "" : cur;
        return sel;
    }
    if (cons.type === "color") {
        return el("input", {type: "color", value: hexOfColor(cur),
            disabled: fixed || backend ? "" : null,
            onchange: (e) => commit(colorOfHex(e.target.value))});
    }
    const numeric = cons.ranged_int || cons.ranged_float ||
                    cons.type === "int" || cons.type === "float";
    if (numeric) {
        const isInt = !!cons.ranged_int || cons.type === "int";
        const input = el("input", {type: "number",
            step: isInt && !ui.scale_op ? "1" : "any",
            value: cur === null || cur === undefined ? "" : scaleOut(ui, cur),
            placeholder: ui.placeholder || "",
            disabled: fixed ? "" : null, readonly: backend ? "" : null});
        input.addEventListener("change", () => {
            if (input.value.trim() === "") return ok(input, null);
            const d = parseFloat(input.value);
            if (Number.isNaN(d)) return fail(input);
            let v = scaleIn(ui, cons, d);
            if (isInt && !ui.scale_op) {
                if (!Number.isInteger(d)) return fail(input);
                v = Math.round(v);
            }
            if (!isInt && Number.isInteger(v)) v = v + 0.0;
            if (!validValue(cons, isInt ? v : parseFloat(v)))
                return fail(input);
            ok(input, v);
        });
        return input;
    }
    const input = el("input", {
        type: cons.type === "password" ? "password" : "text",
        value: cur === null || cur === undefined ? "" : cur,
        placeholder: ui.placeholder || "",
        disabled: fixed ? "" : null, readonly: backend ? "" : null});
    input.addEventListener("keydown",
        (e) => { if (e.key === "Enter" || e.keyCode === 13) input.blur(); });
    input.addEventListener("change", () => {
        const v = input.value === "" ? null : input.value;
        if (!validValue(cons, v)) return fail(input);
        ok(input, v);
    });
    return input;
}

/* value capture for backend_provided params (spec 4.9.3) */
function acquireButton(node, input, commit) {
    const btn = el("button", {class: "small"}, xl(node.ui.acquire_button));
    btn.addEventListener("click", async () => {
        btn.disabled = true;
        // The editor freezes until the capture succeeds or fails: only one
        // capture may ever be outstanding, otherwise a single backend event
        // would land in whichever field happened to ask first while the other
        // keeps waiting (see handle_value_event, spec 4.9.3).
        const thaw = freeze(xl("Reading value..."));
        let r = null;
        try {
            r = await api(
                `/api/value/capture?path=${encodeURIComponent(node.path)}`);
        } catch (e) {
            r = null;       // device unreachable; reported below
        } finally {
            thaw();
            btn.disabled = false;
        }
        const data = r && r.data;
        if (data && data.value !== null && data.value !== undefined) {
            input.value = data.value;
            commit(data.value);
            msg(xl("Value applied"), "ok");
        } else if (data && data.timeout) {
            msg(xl("Timeout"), "error");
        } else {
            // the device answers refusals with the DECL_LANG key, so that the
            // session's own language decides how they read
            msg(data && data.error ? xl(data.error)
                                   : xl("No answer from the device."),
                "error");
        }
    });
    return btn;
}

function testButton(node, currentValue) {
    const btn = el("button", {class: "small"}, xl("Test"));
    btn.addEventListener("click", async () => {
        const r = await api("/api/config/test",
            {json: {path: node.path, value: currentValue()}});
        // Three outcomes, not two: a test routine that returns "false" comes
        // back with status 200, and "Successful: false" contradicted itself.
        // A "true" says no more than that the routine ran without error --
        // whether the right ring tone sounded is decided by whoever listened.
        const clean = (r.status === 200) && !!r.data.result;
        const outcome = (r.status !== 200)
            ? xl("The test could not be started.")
            : (r.data.result
                ? xl("The test routine ran without errors.")
                : xl("The test routine could not carry out the test."));
        // The technical reason goes underneath rather than behind a colon:
        // the sentence ends in a full stop, and "... carry the test out.: 500"
        // reads like a typo. It is not translated -- what the server hands
        // back is written in no language of this house.
        const detail = (r.status !== 200)
            ? el("p", {class: "detail"}, (r.data && r.data.error) || r.status)
            : null;
        await modal([node.ui.test_func_msg ? xl(node.ui.test_func_msg) : "",
                     el("p", {class: "outcome " + (clean ? "ok" : "error")},
                        outcome),
                     detail],
                    {alert: true});
    });
    return btn;
}

/* A 'pingable' host and a 'path' are the two values the editor can verify by
   itself, so that a wrong entry shows up while it is being made and not only
   when the device later fails to use it. Both checks belong to the backend: the
   file system is the device's, and what matters about a host is whether the
   *device* reaches it -- the browser may well sit on the other interface. The
   verdicts stay three-way rather than yes/no, because "not there" has very
   different meanings (a typo, or a box that is merely switched off). */
const PROBE_TYPES = new Set(["path", "pingable"]);
const PROBE_VERDICT = {
    reachable:  (d) => [`${xl("Reachable")}: ${d.address}`, "ok"],
    silent:     (d) => [`${d.address}: ${xl("no response to ping")}`, "info"],
    unresolvable: () => [xl("Name cannot be resolved"), "error"],
    file:       () => [xl("File exists"), "ok"],
    directory:  () => [xl("Folder exists"), "ok"],
    creatable:  () => [xl("Does not exist yet, can be created"), "info"],
    missing:    () => [xl("Path does not exist"), "error"],
};

/* Two of the seven verdicts can be nothing but a typo: a name that resolves to
   nothing, and a path whose parent folder does not exist either. Those mark the
   field, exactly as a value the browser itself rejects is marked, and Speichern
   refuses the module until it is dealt with -- a value the device has already
   said it cannot use has no business being stored.

   Marked, not withdrawn: what somebody typed stays on screen to be corrected,
   which is what fail() does for the checks that run in the browser. The
   difference is only in the timing -- those refuse before the value is
   committed, this answer arrives afterwards.

   The other two failures leave no mark at all. A host that resolves but stays
   silent is a speakerphone switched off while somebody configures it, and an
   absent path whose parent exists is a log file written on first use; refusing
   either would make the editor unusable exactly when it is needed. */
async function probeValue(node, value, rerender) {
    if (typeof value !== "string" || value.trim() === "") {
        delete S.probeBad[node.path];
        return;
    }
    const r = await api("/api/config/probe",
                        {json: {path: node.path, value: value}});
    const d = r.data || {};
    const verdict = PROBE_VERDICT[d.outcome];
    if (r.status !== 200 || !verdict)
        return msg(`${xl("Check failed")}: ` +
                   `${d.error || xl("No answer from the device.")}`,
                   "error");
    const [text, level] = verdict(d);
    const refused = level === "error";
    const changed = refused !== !!S.probeBad[node.path];
    if (refused) S.probeBad[node.path] = text;
    else delete S.probeBad[node.path];
    msg(text, level);
    // report first, then re-render: the re-render must not overtake the
    // message, and without it the marking would never appear
    if (changed && rerender) rerender();
}

function probeButton(node, currentValue, rerender) {
    const btn = el("button", {class: "small"}, xl("Check"));
    btn.addEventListener("click", async () => {
        btn.disabled = true;
        // The same verdict has the same consequence, whether it arrives at
        // the press of a button or by itself: it marks the field. A button
        // that only reports, beside a field that remembers none of it, would
        // leave two truths about one value.
        try { await probeValue(node, currentValue(), rerender); }
        finally { btn.disabled = false; }
    });
    return btn;
}

/* ---------- rows, groups, dict bodies (spec 4.6 / 4.6.1) ---------- */
function fieldRow(node, container, relKeys, ctx) {
    let cur = getIn(container, relKeys);
    const cons = node.constraints || {};
    // A likely_val is a proposal, not a decision: the backend never adopts it
    // -- an unset parameter keeps config_ready() false, which is the whole
    // difference to a default_val -- but the editor fills it in, so that the
    // admin only has to confirm it by saving, or type something else over it.
    // Adopting once per draft keeps emptying the field possible; re-filling it
    // on every render would not.
    const proposal = node.ui.likely_val;
    const adoptKey = relKeys.join(".");
    if (proposal !== undefined && (cur === null || cur === undefined) &&
            node.configurability === 1 && !S.readOnly &&
            !ctx.adopted.has(adoptKey)) {
        ctx.adopted.add(adoptKey);
        cur = proposal;
        setIn(container, relKeys, cur);
        ctx.markDirtyQuiet();
    }
    const commit = (v) => {
        setIn(container, relKeys, v);
        ctx.markDirty();
        ctx.rerender();
        // the answer arrives long after the re-render, so the message survives;
        // a verdict that refuses the value marks the field on the next one
        if (PROBE_TYPES.has(cons.type)) probeValue(node, v, ctx.rerender);
    };
    // Withdrawing during a render: no second render, or this goes round in
    // circles -- the same caution as with likely_val above.
    const commitQuiet = (v) => {
        setIn(container, relKeys, v);
        ctx.markDirtyQuiet();
    };
    // 'values_for' names a sibling field; its draft value is the provider's
    // argument. Unset means null, not "no argument" -- the provider is meant
    // to be able to tell the two apart.
    const forKey = cons.one_of_for;
    const enumArg = forKey === undefined ? undefined
        : (getIn(container, relKeys.slice(0, -1).concat(forKey)) ?? null);
    const input = buildInput(node, cur, commit, commitQuiet, ctx, enumArg);
    if (input.type === "checkbox") {
        input.checked = !!cur;
        // A boolean that was never answered is neither yes nor no. Without the
        // third state it would look exactly like "no", and the parameter would
        // silently keep config_ready() false with nothing on screen to show it.
        input.indeterminate = (cur === null || cur === undefined);
    }
    // A property that identifies a list member (list_keys, spec 4.9.2) may not
    // repeat. For an enum the taken options are simply never offered, but a
    // value that is typed -- or captured from hardware, as an rfid is -- has
    // nothing standing in its way. The backend drops such a member, and by
    // then the entry has silently vanished; flagged here, the collision is
    // visible while it is still being made.
    // ...and the same question one or more levels up, for a rule owned by a
    // container rather than by the list this field sits in. A record being
    // edited carries its position, so it is not mistaken for a stranger.
    const absKeys = (ctx.memberKeys || []).concat(relKeys);
    const filled = cur !== null && cur !== undefined && cur !== "";
    const repeats = !!(filled && (
        (ctx.usedEnumValues && ctx.usedEnumValues.has(cur)) ||
        takenElsewhere(ctx, absKeys).has(cur)));
    // Rejected by the device: the same marking as for input the browser
    // rejects itself -- except that here the verdict comes from where the
    // value will later be needed.
    const refused = S.probeBad[node.path];
    if ((repeats || refused) && input.classList) input.classList.add("invalid");

    const row = el("div", {class: "field-row"},
        el("label", {}, xl(node.ui.label || node.path.split(".").pop())),
        node.ui.tooltip ? el("span",
            {class: "help", title: xl(node.ui.tooltip)}, "?") : null,
        input,
        repeats ? el("span", {class: "field-note"},
                     xl("Value already taken"))
                : refused ? el("span", {class: "field-note"}, refused) : null);
    if (node.configurability === 2 && node.ui.acquire_button && !S.readOnly)
        row.append(acquireButton(node, input, commit));
    if (PROBE_TYPES.has(cons.type) && !S.readOnly)
        row.append(probeButton(node, () => getIn(container, relKeys),
                               ctx.rerender));
    if (cons.type === "file" && !S.readOnly)
        row.append(uploadButton(node, ctx, commit));
    if (node.ui.test_func && !S.readOnly)
        row.append(testButton(node, () => getIn(container, relKeys)));

    // A hint belongs above its field, close enough that nobody has to work out
    // which one it is about; the wrapper is what ties the two together.
    const hint = hintFor(node, ctx);
    return hint ? el("div", {class: "field-block"}, hint, row) : row;
}

function collapsible(pathKey, labelText, tooltip, renderBody, extraClass,
                     headerExtra) {
    const isOpen = !!S.open[pathKey];
    const group = el("div", {class: `group ${extraClass || ""}`});
    const header = el("div", {class: "group-header"},
        el("span", {class: "arrow"}, isOpen ? "▼" : "▶"),
        el("span", {}, labelText),
        tooltip ? el("span", {class: "help", title: tooltip}, "?") : null,
        headerExtra || null);
    header.addEventListener("click", () => {
        S.open[pathKey] = !S.open[pathKey];
        renderAll();
    });
    group.append(header);
    if (isOpen) group.append(renderBody());
    return group;
}

/* Which children of a dict actually make it onto the screen: the hidden ones
   and those an unmet relevance rule switches off never do. A protected subtree
   is not even in the dump outside admin mode, so the same walk answers "is
   there anything here at all" -- see hasVisibleContent. */
function visibleChildren(node, container, relKeys) {
    const dictValue = getIn(container, relKeys);
    return Object.entries(node.children || {}).filter(([key, child]) => {
        if (child.ui && child.ui.hidden) return false;
        const rule = node.relevance && node.relevance[key];
        return !(rule && !relevanceHolds(rule, dictValue));
    });
}

/* An empty group is a heading that promises something and delivers nothing.
   That happens for real outside admin mode, where a module whose parameters
   are all protected arrives with no children at all. */
function hasVisibleContent(node, container, relKeys) {
    if (!node.children) return true;      // a leaf or a list editor is content
    return visibleChildren(node, container, relKeys).some(
        ([key, child]) => hasVisibleContent(child, container,
                                            relKeys.concat([key])));
}

function renderDictBody(node, container, relKeys, ctx) {
    const body = el("div", {class: "group-body"});
    for (const [key, child] of visibleChildren(node, container, relKeys)) {
        if (!hasVisibleContent(child, container, relKeys.concat([key])))
            continue;
        body.append(renderNode(child, container, relKeys.concat([key]), ctx));
    }
    return body;
}

/* A test_func may sit on a whole group rather than on a single field -- a SIP
   access whose credentials are only meaningful together, or a set of LED
   settings to be shown as one. Its button then belongs in the group header,
   and must not fold the group away when clicked. */
function groupTestButton(node, container, relKeys) {
    if (!node.ui.test_func || S.readOnly) return null;
    const btn = testButton(node, () => getIn(container, relKeys));
    btn.addEventListener("click", (e) => e.stopPropagation());
    return btn;
}

function renderNode(node, container, relKeys, ctx) {
    if (node.children) {
        // A group carrying distinct_values notes itself on the way down, so
        // that a leaf far below -- possibly inside a list -- can ask it
        // whether a value is already spoken for. The leaf checks its own
        // scope first and only then consults its ancestors, which is the
        // only way a rule owned by a container ever reaches its members.
        if (node.constraints && node.constraints.distinct_values) {
            ctx = Object.assign({}, ctx, {
                distinctScopes: (ctx.distinctScopes || []).concat([{
                    groups: node.constraints.distinct_values,
                    container, relKeys,
                }]),
            });
        }
        return collapsible(node.path,
            xl(node.ui.label || relKeys[relKeys.length - 1]),
            node.ui.tooltip ? xl(node.ui.tooltip) : null,
            () => renderDictBody(node, container, relKeys, ctx),
            null, groupTestButton(node, container, relKeys));
    }
    if (node.item_template) {
        const simple = !node.item_template.children;
        return collapsible(node.path,
            xl(node.ui.label || relKeys[relKeys.length - 1]),
            node.ui.tooltip ? xl(node.ui.tooltip) : null,
            () => simple ? renderListA(node, container, relKeys, ctx)
                         : renderListB(node, container, relKeys, ctx),
            null, groupTestButton(node, container, relKeys));
    }
    return fieldRow(node, container, relKeys, ctx);
}

/* ---------- list editor, Case A: simple members (spec 4.6.2 A) ---------- */
function renderListA(node, container, relKeys, ctx) {
    const list = getIn(container, relKeys) || [];
    const st = S.listsA[node.path] || (S.listsA[node.path] = {sel: null});
    if (st.sel !== null && st.sel >= list.length) st.sel = null;
    const cons = node.constraints, tpl = node.item_template;
    const fixed = S.readOnly || node.configurability === 0;
    const body = el("div", {class: "group-body list-a"});

    const rerenderList = () => ctx.rerender();
    const select = (i) => { st.sel = i; rerenderList(); };

    const posField = el("input", {class: "pos-field", type: "text",
        value: st.sel === null ? list.length + 1 : st.sel + 1,
        disabled: fixed ? "" : null});
    posField.addEventListener("change", () => {
        const n = parseInt(posField.value, 10);
        select(Number.isInteger(n) && n >= 1 && n <= list.length ? n - 1
                                                                 : null);
    });

    const commitVal = async (raw) => {
        const v = raw === "" ? null : raw;
        if (v === null) {                                    // A.6, removal
            if (st.sel !== null &&
                    await modal(xl("Really remove this entry?")) !== null) {
                list.splice(st.sel, 1);
                st.sel = null;
                ctx.markDirty();
            }
            rerenderList();
            return;
        }
        if (!validValue(tpl.constraints, v)) {
            msg(xl("Invalid input"), "error");
            return;
        }
        const existing = list.indexOf(v);
        if (existing >= 0) { select(existing); return; }     // search select
        if (st.sel !== null) {
            list[st.sel] = v;                                // replace
        } else {
            if (list.length >= cons.max_size) {
                msg(xl("List is full"), "error");
                return;
            }
            list.push(v);
            st.sel = null;
        }
        setIn(container, relKeys, list);
        ctx.markDirty();
        rerenderList();
    };

    const valInput = el("input", {type: "text",
        value: st.sel === null ? "" : list[st.sel],
        disabled: fixed ? "" : null});
    valInput.addEventListener("keydown",
        (e) => { if (e.key === "Enter" || e.keyCode === 13)
                     valInput.blur(); });
    valInput.addEventListener("change", () => commitVal(valInput.value));

    const rows = list.map((v, i) => {
        const tr = el("tr", {class: st.sel === i ? "selected" : ""},
                      el("td", {}, String(v)));
        tr.addEventListener("click", () => { if (!fixed) select(i); });
        return tr;
    });
    body.append(
        el("div", {class: "edit-line"}, posField, valInput),
        el("div", {class: "table-wrap"}, el("table", {},
            el("tbody", {}, ...rows))),
        el("div", {class: "apply-line"},
            el("button", {disabled: fixed ? "" : null,
                onclick: () => commitVal(valInput.value)}, xl("Apply"))));
    return body;
}

/* ---------- distinct_values across a group of paths (spec 4.9.7) ----------
   The rule belongs to a container, so no single field can answer it alone.
   A leaf therefore asks each enclosing scope in turn: resolve the group's
   patterns against that scope's working value, and see whether anybody else
   already holds what is about to be entered. Without this the editor sends a
   value the device is bound to refuse -- or worse, one it silently drops. */
/* Every place a pattern reaches, with the route taken to get there: knowing
   the route is what lets a leaf recognise which of the hits is itself. */
function resolveWithPaths(value, parts, prefix) {
    prefix = prefix || [];
    if (!parts.length) return [{path: prefix, value}];
    const [head, ...rest] = parts;
    if (head === "*") {
        return Array.isArray(value)
            ? value.flatMap((v, i) => resolveWithPaths(v, rest,
                                                       prefix.concat([i])))
            : [];
    }
    if (!value || typeof value !== "object") return [];
    return resolveWithPaths(value[head], rest, prefix.concat([head]));
}

/* What the other participants already hold. `absKeys` is where this leaf sits
   relative to the module -- for a record being edited that includes its
   position in the list, which is how it avoids colliding with the copy of
   itself still sitting there. */
function takenElsewhere(ctx, absKeys) {
    const taken = new Set();
    for (const scope of ctx.distinctScopes || []) {
        const own = absKeys.slice(scope.relKeys.length).join(".");
        if (!own) continue;
        const base = getIn(scope.container, scope.relKeys);
        for (const group of scope.groups) {
            if (!group.some(p => pathMatchesPattern(p, own))) continue;
            for (const pattern of group)
                for (const hit of resolveWithPaths(base, pattern.split("."))) {
                    if (hit.path.join(".") === own) continue;      // myself
                    if (hit.value !== null && hit.value !== undefined &&
                            hit.value !== "")
                        taken.add(hit.value);
                }
        }
    }
    return taken;
}

function pathMatchesPattern(pattern, path) {
    const p = pattern.split("."), q = path.split(".");
    return p.length === q.length &&
           p.every((e, i) => e === "*" || e === q[i]);
}

/* ---------- list editor, Case B: record members (spec 4.6.2 B) ---------- */
function usedEnumValuesIn(list, exceptIdx, prop) {
    const used = new Set();
    list.forEach((rec, i) => {
        if (i !== exceptIdx && rec && rec[prop] !== null &&
                rec[prop] !== undefined)
            used.add(rec[prop]);
    });
    return used;
}

function renderListB(node, container, relKeys, ctx) {
    const list = getIn(container, relKeys) || [];
    const tpl = node.item_template, cons = node.constraints;
    // A fixed list locks its length and composition -- no adding, no removing
    // -- but its members' inner leaves stay editable unless they lock
    // themselves (spec 2.1, key 4). Applying an edited record must therefore
    // stay possible; only the structural actions are barred.
    const structureFixed = S.readOnly || node.configurability === 0;
    let st = S.listsB[node.path];
    if (!st || st.pos > list.length + 1) {
        st = S.listsB[node.path] = {pos: 1, draft: null, changed: false};
    }
    if (st.draft === null) {
        st.draft = st.pos <= list.length ? deepCopy(list[st.pos - 1])
                                         : composeValue(tpl);
        st.changed = false;
        st.adopted = new Set();   // every fresh draft may take the proposals
    }
    // On a fixed list the empty new-record slot is not a place anybody can
    // go: its length is locked, so position list.length + 1 does not exist.
    // Disabling "New" was not enough -- the navigator still walked into that
    // slot, and Apply there appended an entry the device then refused at
    // save time, which is a late and puzzling way to learn that a list
    // cannot grow.
    const lastPos = structureFixed ? Math.max(list.length, 1)
                                   : list.length + 1;
    const goTo = (pos) => {                       // B.3 / B.4: discard edits
        st.pos = (pos >= 1 && pos <= lastPos) ? pos : lastPos;
        st.draft = null;
        ctx.rerender();
    };

    // standalone unique keys constrain the enum options of other rows
    const standaloneKeys = (cons.keys || [])
        .filter(g => g.length === 1).map(g => g[0]);
    const recCtx = Object.assign({}, ctx, {
        // where this record sits, so a field inside it can be located within
        // a rule owned further up -- and can tell itself apart from the copy
        // of itself already in the list
        memberKeys: (ctx.memberKeys || []).concat(relKeys, [st.pos - 1]),
        adopted: st.adopted,
        markDirty: () => {
            st.changed = true;
            ctx.rerender();
        },
        markDirtyQuiet: () => { st.changed = true; },
    });

    const recordBody = el("div", {class: "record-block"});
    for (const [key, child] of visibleChildren(tpl, st.draft, [])) {
        if (!hasVisibleContent(child, st.draft, [key])) continue;
        const childCtx = standaloneKeys.includes(key)
            ? Object.assign({}, recCtx,
                {usedEnumValues: usedEnumValuesIn(list, st.pos - 1, key)})
            : recCtx;
        recordBody.append(renderNode(child, st.draft, [key], childCtx));
    }

    const posField = el("input", {class: "pos-field", type: "text",
        value: st.pos});
    posField.addEventListener("change", () => {
        const n = parseInt(posField.value, 10);
        goTo(Number.isInteger(n) ? n : lastPos);
    });
    const nav = el("div", {class: "nav-block"},
        el("button", {onclick: () =>
            goTo(st.pos > 1 ? st.pos - 1 : lastPos)}, "▲"),
        posField,
        el("button", {onclick: () =>
            goTo(st.pos < lastPos ? st.pos + 1 : 1)}, "▼"));

    // The same rule one level up: as long as the draft repeats a member that
    // already exists, applying it would only hand the backend something it is
    // going to drop again.
    const repeatsKey = Object.keys(st.draft || {}).some((key) => {
        const value = st.draft[key];
        if (value === null || value === undefined || value === "") return false;
        return (standaloneKeys.includes(key) &&
                usedEnumValuesIn(list, st.pos - 1, key).has(value)) ||
               takenElsewhere(recCtx, recCtx.memberKeys.concat([key]))
                   .has(value);
    });

    // ...and the same rule again at the button, not only at the navigator: a
    // position typed straight into the field must not find a way in either.
    const apply = el("button", {class: "primary",
        disabled: S.readOnly || !st.changed || repeatsKey
                      || (structureFixed && st.pos > list.length)
                          ? "" : null},
        xl("Apply"));
    apply.addEventListener("click", () => {
        if (st.pos <= list.length) {
            list[st.pos - 1] = deepCopy(st.draft);
        } else {
            if (list.length >= cons.max_size)
                return msg(xl("List is full"), "error");
            list.push(deepCopy(st.draft));
        }
        setIn(container, relKeys, list);
        st.changed = false;
        ctx.markDirty();
        ctx.rerender();
    });
    const remove = el("button", {
        disabled: structureFixed || st.pos > list.length ? "" : null},
        xl("Remove"));
    remove.addEventListener("click", () => {
        list.splice(st.pos - 1, 1);
        setIn(container, relKeys, list);
        ctx.markDirty();
        goTo(st.pos);                                   // B.6 leave event
    });
    const undo = el("button",
        {disabled: !st.changed ? "" : null}, xl("Undo"));
    undo.addEventListener("click", () => { st.draft = null; ctx.rerender(); });

    // "Neu" jumps to the empty new-record slot (position list_size+1) to add
    // an entry; disabled when the list is fixed or already full
    const isNew = st.pos > list.length;
    const neu = el("button", {
        disabled: structureFixed || list.length >= cons.max_size || isNew
                      ? "" : null,
        onclick: () => goTo(list.length + 1)}, xl("New"));

    return el("div", {class: "group-body list-b"},
        el("div", {class: "layout"}, recordBody, nav),
        el("div", {class: "action-block"}, neu, remove, undo, apply));
}

/* ---------- modules and save (spec 4.5) ---------- */
function checkModuleLists(node, value, focusErr) {
    // structural validation before saving: list minimum sizes
    if (node.item_template) {
        const list = value || [];
        if (list.length < node.constraints.min_size) {
            focusErr(`${xl("Too few entries in")} ` +
                     `"${xl(node.ui.label || node.path)}"`);
            return false;
        }
        return true;
    }
    for (const [key, child] of Object.entries(node.children || {})) {
        if (!checkModuleLists(child, value ? value[key] : null, focusErr))
            return false;
    }
    return true;
}

/* Booleans that were never answered: an unticked box is indistinguishable from
   an unanswered one, so they are collected and confirmed once before saving
   rather than quietly leaving the module incomplete. Hidden and currently
   irrelevant fields are skipped, exactly as the renderer skips them. */
function collectUnsetBooleans(node, container, relKeys, found) {
    const value = getIn(container, relKeys);
    if (!node.children) {
        const cons = node.constraints || {};
        if (cons.type === "boolean" && (value === null || value === undefined))
            found.push({keys: relKeys,
                        label: xl(node.ui.label || relKeys[relKeys.length - 1])});
        return;
    }
    for (const [key, child] of Object.entries(node.children)) {
        if (child.ui && child.ui.hidden) continue;
        const rule = node.relevance && node.relevance[key];
        if (rule && !relevanceHolds(rule, value)) continue;
        collectUnsetBooleans(child, container, relKeys.concat([key]), found);
    }
}

async function confirmUnsetBooleans(mid) {
    const found = [];
    collectUnsetBooleans(S.cvv[mid], S.edit, [mid], found);
    if (!found.length) return true;
    const answered = await modal(
        xl("These options were never set; apply them as “no”/“disabled”?") +
        " " + found.map(f => f.label).join(", "));
    if (!answered) return false;
    for (const f of found) setIn(S.edit, f.keys, false);
    return true;
}

async function saveModule(mid) {
    let failure = null;
    if (!checkModuleLists(S.cvv[mid], S.edit[mid],
                          (m) => failure = m)) {
        msg(failure, "error");
        return;
    }
    // What the device rejected does not go to the device. Here rather than
    // while typing: there it is only marked, so the typo stays visible and
    // correctable -- it is not taken away.
    const refused = Object.keys(S.probeBad)
                          .filter(p => p === mid || p.startsWith(mid + "."));
    if (refused.length) {
        msg(`${xl("Apply failed")}: ` +
            refused.map(p => `${p.split(".").pop()} (${S.probeBad[p]})`)
                   .join(", "), "error");
        return;
    }
    if (!await confirmUnsetBooleans(mid)) return;
    // the files first: a value naming a file the device does not have is
    // worse than not saving at all, so a refused upload abandons the save
    if (!await flushPendingFiles(mid)) return;
    const r = await api("/api/config/update",
        {json: {module: mid, value: S.edit[mid]}});
    if (r.status === 401) {
        await modal(xl("No answer from the device."), {alert: true});
        location.reload();
        return;
    }
    if (r.status !== 200) {
        msg(`${xl("Apply failed")}: ` +
            ((r.data && r.data.error) || r.status), "error");
        return;
    }
    const rejected = r.data.rejected;
    await reloadData();
    renderAll();
    if (rejected.length > 0) {
        msg(`${xl("Apply failed")}: ${xl("Rejected")}: ` +
            rejected.join(", "), "error");
    } else {
        msg(xl("Saved"), "ok");
    }
}

function renderModule(mid) {
    const node = S.cvv[mid];
    const ctx = {
        module: mid,
        markDirty: () => { S.dirty[mid] = true; },
        // adopting a likely_val happens *during* a render and must therefore
        // not ask for another one (see fieldRow)
        markDirtyQuiet: () => { S.dirty[mid] = true; },
        adopted: S.adopted[mid] || (S.adopted[mid] = new Set()),
        rerender: () => renderAll(),
    };
    return collapsible(mid, xl(node.ui.label || mid),
        node.ui.tooltip ? xl(node.ui.tooltip) : null,
        () => {
            const body = renderDictBody(node, S.edit, [mid], ctx);
            if (!S.readOnly) {
                body.append(el("div", {class: "save-row"},
                    el("button", {class: "primary",
                        disabled: S.dirty[mid] ? null : "",
                        onclick: () => saveModule(mid)}, xl("Save"))));
            }
            return body;
        }, "module");
}

/* ---------- level 0: general features (spec 4.4, 4.5, 4.8, C) ---------- */
async function unlockProtected() {
    const passwd = await modal(xl("Password"),
                               {input: {type: "password"}});
    if (passwd === null) return;
    await reloadData(passwd);
    if (S.wrongPasswd) msg(xl("Incorrect password"), "error");
    renderAll();
}

/* An editor whose window was closed without ending its session keeps the write
   lock for the rest of the idle timeout, and reloading cannot recover it -- a
   reload throws away this tab's token, which is what made it read-only in the
   first place. The admin password takes the lock back (spec 4.8). It is not
   carried into the new session: protected parameters still need the separate,
   deliberate unlock. */
async function takeOverSession() {
    const passwd = await modal(xl("Password"),
                               {input: {type: "password"}});
    if (passwd === null) return;
    const r = await api("/api/session/takeover", {json: {passwd}});
    if (r.status !== 200 || !r.data || !r.data.token) {
        msg(r.status === 403 ? xl("Incorrect password")
                             : xl("No answer from the device."), "error");
        return;
    }
    S.token = r.data.token;
    await reloadData();
    renderAll();
    msg(xl("Session taken over"), "ok");   // after the re-render, or it is lost
}

async function exitAdminMode() {
    if (S.factory) {
        const neu = await modal(xl("New password"),
                                {input: {type: "password"}});
        if (neu === null || neu === "") return;
        const r = await api("/api/config/update",
            {json: {module: "config", value: {ui_passwd: neu}}});
        if (r.status !== 200 || r.data.rejected.length) {
            msg(xl("Apply failed"), "error");
            return;
        }
    }
    await api("/api/end_session", {json: {}});
    location.reload();
}

const RTL_LANGS = new Set(["fa", "ar", "he", "ur", "ps", "sd"]);
/* What the editor is called, in the reading language and with the hosting
   application's name in it -- or without, for an application that gave none.
   The name is inserted rather than looked up: it is a proper noun, and where
   it belongs in the sentence is the translation's business, not a prefix. */
function editorTitle() {
    return S.appTitle
        ? xl("{app} Configuration Editor").replace("{app}", S.appTitle)
        : xl("Configuration Editor");
}

/* The document's own language and direction, which index.html cannot know:
   it is served before anybody has chosen one, and it used to claim German
   for every reader. `lang` matters beyond looks -- it is what a screen reader
   picks a voice by, and what a browser hyphenates by. */
function applyTextDirection() {
    document.documentElement.lang = S.lang || S.sourceLang;
    document.documentElement.dir = RTL_LANGS.has(S.lang) ? "rtl" : "ltr";
    document.title = editorTitle();
}

async function switchLanguage(lang) {
    S.lang = lang;
    localStorage.setItem("gpsmcpmms_lang", lang);
    await loadLang();
    applyTextDirection();
    renderAll();
}

/* Translations are managed by a CSV round-trip (spec 4.5): download a
 * template (DECL_LANG source + chosen reference columns + the target column),
 * fill it offline -- a human or an AI assistant -- and upload it again; the
 * backend answers with a report file. The slow work happens off-session, so
 * nothing can be lost to a token timeout. */
function triggerDownload(blob, name) {
    const a = el("a", {href: URL.createObjectURL(blob), download: name});
    document.body.append(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 2000);
}

function authHeaders() {
    const h = {"X-GPSMCPMMS-Api": "1"};
    if (S.token) h["X-GPSMCPMMS-Token"] = S.token;
    return h;
}

async function downloadTemplate(target, refs) {
    if (!/^[a-z]{2,3}$/.test(target))
        return msg(xl("Invalid input"), "error");
    const url = `/api/lang/template?lang=${target}` +
                `&refs=${encodeURIComponent(refs.join(","))}`;
    const resp = await fetch(url, {headers: authHeaders()});
    if (!resp.ok) {
        let err = resp.status;
        try { err = (await resp.json()).error || err; } catch (e) { /**/ }
        return msg(`${xl("Apply failed")}: ${err}`, "error");
    }
    triggerDownload(await resp.blob(), `${target}.csv`);
    msg(`${xl("Download CSV")}: ${target}.csv`, "ok");
}

function targetFromFileName(file) {
    const stem = file.name.replace(/\.csv$/i, "");
    return /^[a-z]{2,3}$/.test(stem) ? stem.toLowerCase() : null;
}

async function uploadTranslation(file, code, name) {
    // The panel knows which language this is -- the target was chosen or
    // typed before the template was even downloaded. Guessing it from the
    // file name is only the fallback for a file that arrived another way.
    let target = (code || "").trim().toLowerCase() || targetFromFileName(file);
    if (!target) {
        target = await modal(xl("Language code"), {input: {}});
        if (target === null) return;
        target = target.trim().toLowerCase();
    }
    if (!/^[a-z]{2,3}$/.test(target))
        return msg(xl("Invalid input"), "error");
    const fd = new FormData();
    fd.append("file", file);
    fd.append("lang", target);
    if (S.token) fd.append("token", S.token);
    // a language nobody can name would show up in every dropdown as a code
    if (name) fd.append("name", name);

    const resp = await fetch("/api/lang/upload",
        {method: "POST", headers: authHeaders(), body: fd});
    if (!resp.ok) {
        let err = resp.status;
        try { err = (await resp.json()).error || err; } catch (e) { /**/ }
        return msg(`${xl("Invalid file")}: ${err}`, "error");
    }
    const translated = resp.headers.get("X-GPSMCPMMS-Translated");
    const total = resp.headers.get("X-GPSMCPMMS-Total");
    triggerDownload(await resp.blob(), `${target}.report.csv`);
    if (S.lang === target) await loadLang();
    await loadLangList();
    renderAll();
    // message after the re-render, so renderAll() does not wipe it
    msg(`${xl("Translation processed")}: ` +
        `${translated} / ${total} ${xl("translated")}`, "ok");
}

/* ---------- managing translations ----------
   Two panels rather than one, because "manage" never said which of the two
   things you were about to do and the controls looked the same either way.
   They differ in exactly one row: the row that answers "which language am I
   working on".

   Note what the target selector is *not*: it is not the language selector in
   the row above. That one decides what language you read the editor in, and
   conflating the two would mean improving the Turkish translation only while
   reading the whole editor in Turkish -- which is precisely backwards for the
   normal case, somebody polishing a language they do not speak. */
/* How the translations stand, as the panel's opening line.

   It lives in here and nowhere else, for the reason that decides its
   visibility: a reader who may not upload a dictionary can do nothing with
   the answer. This panel is the one place only an admin ever sees, so putting
   the report here needs no rule about who may look -- the place is the rule.

   The numbers come from /api/lang/info, which withholds them from everybody
   else. The source language is left out of both the count and the list: it has
   no dictionary and is complete by construction, so naming it would only
   invite the question why it never moves. */
function langStatusNodes() {
    const cov = S.coverage;
    if (!cov || !cov.total || !cov.done) return [];
    const langs = Object.keys(cov.done).filter(l => l !== S.sourceLang);
    const byName = (a, b) => langName(a).localeCompare(langName(b));
    const short = langs.filter(l => cov.done[l] < cov.total).sort(byName)
                       .map(l => `${langName(l)} (${cov.done[l]}/${cov.total})`);
    const out = [el("span", {}, short.length
        ? xl("{n} translations; still incomplete: {langs}.")
              .replace("{n}", langs.length).replace("{langs}", short.join(", "))
        : xl("All {n} translations are complete.")
              .replace("{n}", langs.length))];

    // Orphans were computed and sent for a long time without anybody rendering
    // them. They belong in the same sentence-place: an entry nothing uses any
    // more is offered to a translator as work, and only an admin can clear it.
    const stale = Object.keys(S.orphans || {})
        .filter(l => (S.orphans[l] || []).length).sort(byName)
        .map(l => `${langName(l)} (${S.orphans[l].length})`);
    if (stale.length)
        out.push(el("span", {class: "hint-inline"},
            xl("Entries nothing uses any more: {langs}.")
                .replace("{langs}", stale.join(", "))));

    // Asking again, inside the last sentence rather than beside it. As a
    // sibling in the row it was a flex item of its own, and a report long
    // enough to fill the line pushed it onto the next one, where it stood
    // alone under the text like a stray. Inside the span it wraps with the
    // words it belongs to.
    out[out.length - 1].append(
        el("button", {class: "small lang-refresh", type: "button",
                      title: xl("Reload"), "aria-label": xl("Reload"),
                      onclick: async () => { await loadLangList();
                                             renderAll(); }},
           "↻"));
    return out;
}

function renderLangPanel(mode) {
    // everything except the source language: translating it into itself is
    // the one row nobody can fill in
    const active = S.languages.filter(l => l !== S.sourceLang);
    const st = S.langForm || (S.langForm = {});

    // The way out, in the corner. Until now the panel could only be closed by
    // pressing the button that had opened it, and nothing said so.
    //
    // A cross rather than a word, because it sits in the corner rather than in
    // a sentence -- and the word is what it carries as its label, so a reader
    // who cannot make out the glyph is still told what it does.
    const closeX = el("button", {class: "panel-close", type: "button",
                                 title: xl("Close"), "aria-label": xl("Close"),
                                 onclick: () => { S.langPanel = null;
                                                  renderAll(); }},
                      "×");

    // row 0 -- how the translations stand, with a way to ask again.
    //
    // The asking is not decoration. It would be, if an upload were the only
    // thing that moved these numbers -- an upload refreshes them by itself.
    // But translate() notes a key on the way past, every time, and
    // note_xlation_keys() is open to the application at any moment: a string
    // first spoken or first shown while this panel stands open raises the
    // total, and every language's standing drops with it, silently. Nothing
    // downstream is harmed, because a template is always cut from the key set
    // as it is at that second -- but the line would be reporting a past.
    //
    // Left out entirely where there is nothing to report, so that an empty
    // line never pushes the panel open by itself.
    const status = langStatusNodes();
    const row0 = status.length ? el("div", {class: "lang-panel-row"}, ...status)
                               : null;

    // row 1 -- the only row that differs between the two panels
    let row1, targetOf;
    if (mode === "edit") {
        const sel = el("select", {onchange: () => { st.target = sel.value;
                                                    renderAll(); }},
            ...active.map(l => el("option", {value: l}, langName(l))));
        if (active.includes(st.target)) sel.value = st.target;
        else st.target = active[0];
        targetOf = () => sel.value;
        row1 = el("div", {class: "lang-panel-row"},
            el("span", {}, xl("Editing") + ":"), sel);
    } else {
        // Two shapes, and the application chooses which by shipping
        // languages.json or not. With a list, the picker holds every language
        // there is to add and the two fields only show what was picked --
        // typing a code the list does not name would be a request the device
        // is bound to refuse. Without one, there is nothing to pick from and
        // the fields are the way in.
        const unused = S.bounded
            ? Object.keys(S.langNames || {})
                  .filter(c => !S.languages.includes(c))
                  .sort((a, b) => langName(a).localeCompare(langName(b)))
            : [];
        const code = el("input", {type: "text", class: "lang-code",
                                  placeholder: xl("Language code"),
                                  readonly: S.bounded ? "" : null,
                                  value: st.newCode || ""});
        const name = el("input", {type: "text", class: "lang-name",
                                  placeholder: xl("Language name"),
                                  readonly: S.bounded ? "" : null,
                                  value: st.newName || ""});
        const pick = el("select", {disabled: S.bounded ? null : "",
                                   onchange: (e) => {
            const c = e.target.value;
            if (!c) return;
            st.newCode = code.value = c;
            st.newName = name.value = langName(c);
        }}, el("option", {value: ""}, "—"),
           ...unused.map(c => el("option", {value: c}, langName(c))));
        if (!S.bounded) {
            const typed = (field, key) => field.addEventListener("input",
                () => { st[key] = field.value; });
            typed(code, "newCode");
            typed(name, "newName");
        }
        targetOf = () => (code.value || "").trim().toLowerCase();

        row1 = el("div", {class: "lang-panel-row"},
            el("span", {}, xl("New language") + ":"), pick, code, name);
    }

    // row 2 -- context languages: everything active except the source
    // language, and except the one being worked on
    const boxes = active.map(l => {
        const cb = el("input", {type: "checkbox", value: l});
        return {l, cb,
                label: el("label", {class: "ref-box"}, cb, " " + langName(l))};
    });
    const limit = () => {
        const chosen = boxes.filter(b => b.cb.checked).length;
        boxes.forEach(b => {
            const isTarget = b.l === targetOf();
            b.cb.disabled = isTarget || (!b.cb.checked && chosen >= 3);
            b.label.style.display = isTarget ? "none" : "";
        });
    };
    boxes.forEach(b => b.cb.addEventListener("change", limit));
    const row2 = boxes.length ? el("div", {class: "lang-panel-row wrap"},
        el("span", {}, xl("Translating the source keys, with up to 3 "
                          + "languages as further context (please choose):")),
        ...boxes.map(b => b.label)) : null;

    // row 3 -- the sequence, spelled out. Three steps that always ran in this
    // order but never said so.
    const picker = el("input", {type: "file", accept: ".csv",
                                style: "display:none"});
    const choose = el("button", {class: "small", type: "button",
        onclick: () => picker.click()}, xl("Select completed CSV"));
    picker.addEventListener("change", () => {
        // the label becomes the file name: otherwise nothing on screen says
        // what the third button is about to send
        choose.textContent = picker.files.length ? picker.files[0].name
                                                 : xl("Select completed CSV");
    });
    const row3 = el("div", {class: "lang-panel-row"},
        el("span", {}, xl("Translation file: start by")),
        el("button", {class: "small primary", type: "button", onclick: () =>
            downloadTemplate(targetOf(),
                boxes.filter(b => b.cb.checked && b.l !== targetOf())
                     .map(b => b.l))}, xl("Download CSV")),
        el("span", {}, xl("then")), picker, choose,
        el("span", {}, xl("finally")),
        el("button", {class: "small", type: "button", onclick: () => {
            if (!picker.files.length) return;
            uploadTranslation(picker.files[0],
                              mode === "new" ? targetOf() : null,
                              mode === "new" ? (st.newName || "").trim() : null);
        }}, xl("Upload the selected CSV")));

    const panel = el("div", {class: "lang-panel"},
                     closeX, row0, row1, row2, row3);
    limit();
    return panel;
}

/* ---------- top level rendering ---------- */
function renderAll() {
    const app = document.getElementById("app");
    app.innerHTML = "";
    app.append(
        el("h1", {class: "title"}, editorTitle()),
        el("hr", {class: "title-rule"}));

    const general = el("div", {class: "general-row"});
    if (S.protectedOmitted && !S.readOnly)
        general.append(el("button", {onclick: unlockProtected},
                          xl("Show protected parameters")));
    const langSel = el("select", {onchange: (e) =>
                                      switchLanguage(e.target.value)},
        ...S.languages.map(l => el("option", {value: l}, langName(l))));
    langSel.value = S.languages.includes(S.lang) ? S.lang : S.sourceLang;
    general.append(el("span", {}, xl("Language") + ":"), langSel);
    if (S.admin) {
        const toggle = async (mode) => {
            S.langPanel = S.langPanel === mode ? null : mode;
            S.langForm = {};              // a fresh panel starts empty
            // Asked for again on the way in, for two reasons: the standing of
            // the translations is only sent to an admin, so the answer fetched
            // at start-up carries none of it -- and a report about how things
            // stand should be true at the moment somebody looks, not at the
            // moment the page was loaded.
            if (S.langPanel) await loadLangList();
            renderAll();
        };
        // adding comes first: it is the rarer and the more consequential of
        // the two, and putting it second invites reaching for it by mistake
        //
        // Both are switches, and they say so twice: 'toggled' draws them
        // pressed rather than accented -- the accent on this same panel means
        // "do this", on "Download CSV" -- and aria-pressed says the same to a
        // reader who cannot see either.
        const switchAttrs = (mode) => ({
            class: "small" + (S.langPanel === mode ? " toggled" : ""),
            "aria-pressed": S.langPanel === mode ? "true" : "false",
        });
        general.append(
            el("button", {...switchAttrs("new"),
                          onclick: () => toggle("new")},
               xl("Add new translation")),
            el("button", {...switchAttrs("edit"),
                          disabled: S.languages.length < 2 ? "" : null,
                          title: S.languages.length < 2
                                     ? xl("No translation exists yet")
                                     : null,
                          onclick: () => toggle("edit")},
               xl("Edit existing translation")));
    }
    general.append(el("span", {class: "spacer"}));
    if (!S.readOnly)
        general.append(el("button", {onclick: async () => {
            await api("/api/end_session", {json: {}});
            location.reload();
        }}, xl("End session")));
    app.append(general);
    if (S.admin && S.langPanel) app.append(renderLangPanel(S.langPanel));
    app.append(el("div", {id: "messages"}));

    if (S.readOnly)
        app.append(el("div", {class: "banner readonly"},
            xl("Read-only mode: another session is active"),
            el("button", {class: "small", onclick: () => location.reload()},
               xl("Reload")),
            el("button", {class: "small", onclick: takeOverSession},
               xl("Take over session")),
            lockFreeHint()));
    if (S.factory)
        app.append(el("div", {class: "banner"},
            xl("The device is still using the factory default password"),
            S.admin ? el("button", {class: "small", onclick: exitAdminMode},
                         xl("Exit admin mode")) : null));

    // sorted by module id, which is how a device controls the order of the
    // groups on screen -- prefix the ids and you have chosen the sequence
    for (const mid of Object.keys(S.cvv).sort()) {
        if (!hasVisibleContent(S.cvv[mid], S.edit, [mid])) continue;
        app.append(renderModule(mid));
    }
}

/* When the lock falls by itself -- read off the browser's clock. The device
   sends a duration rather than a time: it may have no RTC and start on the
   value fake-hwclock left behind, so its own idea of the time can be off while
   the clock of the machine in front of it is right. That also disposes of
   every assumption about time zones. */
function lockFreeHint() {
    if (typeof S.lockFreeIn !== "number") return null;
    const at = new Date(Date.now() + S.lockFreeIn * 1000);
    const hhmm = String(at.getHours()).padStart(2, "0") + ":" +
                 String(at.getMinutes()).padStart(2, "0");
    return el("span", {class: "hint-inline"},
              xl("Alternatively, without an admin password: renewed access "
                 + "after {time}.").replace("{time}", hhmm));
}

/* ---------- data loading ---------- */
async function loadLang() {
    const r = await api(`/api/schema/${S.lang}`);
    S.xl = r.data || {};
}

async function loadLangList() {
    const r = await api("/api/lang/info");
    if (r.data && r.data.languages) S.languages = r.data.languages;
    if (r.data && r.data.source) S.sourceLang = r.data.source;
    if (r.data && typeof r.data.bounded === "boolean")
        S.bounded = r.data.bounded;
    if (r.data && typeof r.data.app_title === "string")
        S.appTitle = r.data.app_title;
    if (r.data && r.data.options) S.langNames = r.data.options;
    // Both are admin-only at the source and simply absent for anybody else,
    // which is what keeps the panel's report out of reach without a rule here.
    S.coverage = (r.data && r.data.coverage) || null;
    S.orphans = (r.data && r.data.orphans) || null;
    // The browser may name a language no dictionary here covers. What would
    // show then are the keys themselves -- readable, but the dropdown would
    // stand on something that does not appear in it.
    if (S.languages.length && !S.languages.includes(S.lang))
        S.lang = S.languages.includes(S.sourceLang) ? S.sourceLang
                                                    : S.languages[0];
}

/* What a language is called. A code is a last resort and a sign that somebody
   added a language without saying what it is: "ps" in a dropdown tells a
   deployer nothing, and a translator choosing their working language even
   less. */
function langName(code) {
    return (S.langNames && S.langNames[code]) || code;
}

async function reloadData(passwd) {
    let url = "/api/cvv_data";
    const params = [];
    if (passwd !== undefined) params.push(`passwd=${encodeURIComponent(passwd)}`);
    if (params.length) url += "?" + params.join("&");
    const r = await api(url);
    if (!r.data) throw new Error("no data");
    S.token = r.data.token || S.token;
    S.readOnly = r.data.read_only;
    S.lockFreeIn = r.data.lock_free_in;
    S.admin = r.data.admin;
    S.wrongPasswd = r.data.wrong_passwd;
    S.factory = r.data.factory_default_passwd;
    S.protectedOmitted = r.data.protected_omitted;
    S.cvv = r.data.cvv;
    S.edit = {};
    S.dirty = {};
    S.listsB = {};
    S.listsA = {};
    // The rejections belong to the draft values just discarded: what stands
    // in the form now came from the device and is valid there.
    S.probeBad = {};
    // A dynamic enum's options are computed by the device out of its own
    // state, and that state has just become another one. The voice list
    // hangs on the stored announcement language: without this line it went
    // on showing the previous language's voices after a save, and only a
    // page reload put it right. Only fields that are actually on screen get
    // asked about -- a collapsed section costs nothing.
    S.enums = {};
    // S.adopted deliberately survives: saving re-loads the tree, and a
    // proposal the admin has cleared on purpose must not come back -- which
    // would also leave Speichern lit, inviting them to adopt it by accident.
    // A real fresh start comes with a page load, which resets S as a whole.
    for (const [mid, node] of Object.entries(S.cvv))
        S.edit[mid] = composeValue(node);
}

async function boot() {
    try {
        await loadLangList();
        await loadLang();
        await reloadData();
        applyTextDirection();
        renderAll();
    } catch (e) {
        document.getElementById("app").innerHTML = "";
        document.getElementById("app").append(
            el("div", {class: "banner"},
               xl("No answer from the device."),
               el("button", {class: "small",
                   onclick: () => location.reload()}, xl("Reload"))));
    }
}

boot();
