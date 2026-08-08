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
    protectedOmitted: false,
    cvv: {},                 // parsed /api/cvv_data dump
    xl: {},                  // active translation dictionary
    // Was jemand zuletzt gewählt hat, sonst die Sprache seines Browsers, sonst
    // die der Quellschlüssel. Fest "de" stand hier, solange die Schlüssel
    // deutsch waren; jetzt wäre das eine Sprache, die dem Gerät niemand gesagt
    // hat -- und für einen deutschen Zugang kommt sie ohnehin heraus. Ob es ein
    // Wörterbuch dafür gibt, entscheidet loadLangList().
    lang: localStorage.getItem("gpsmcpmms_lang") ||
          (navigator.language || "").split("-")[0] || "en",
    languages: ["de"],
    langNames: {},           // code -> name, from ui_dir/languages.json
    maxLanguages: 7,         // how many dictionaries may coexist
    langPanel: null,         // null | "new" | "edit"
    langForm: {},            // what the open panel has been told so far
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
                  : {error: (r.data && r.data.error) || xl("Connection to the device lost"),
                     arg};
    if (S.enums[path].error) msg(S.enums[path].error, "error");
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
                        `&lang=${encodeURIComponent(S.lang || "de")}`);
    S.hints[path] = (r.data && typeof r.data.text === "string")
                  ? {text: r.data.text, at: r.data.at}
                  : {error: (r.data && r.data.error) ||
                            xl("Connection to the device lost")};
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
        return el("div", {class: "hint invalid"}, state.error);
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
   until Save and "Rückgängig" really does undo. Sending it at once also wrote
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
            // Neu fragen, sobald das Feld, für das die Optionen berechnet
            // werden, ein anderes geworden ist -- und zwar im Entwurf, lange
            // vor dem Speichern: die Stimmen einer Sprache, die noch gar
            // nicht übernommen ist.
            if (!state || state.arg !== enumArg) {
                fetchEnumOptions(node.path, ctx.rerender, enumArg);
                return el("select", {disabled: ""}, el("option", {}, "…"));
            }
            if (state.pending)
                return el("select", {disabled: ""}, el("option", {}, "…"));
            if (state.error)
                return el("select", {disabled: "", class: "invalid"},
                          el("option", {}, state.error));
            options = Object.entries(state.values).map(([value, o]) =>
                ({value, label: (o && o.label) || value,
                  tooltip: o && o.tooltip,
                  // ein Name, den der Dienst vergeben hat, wird nicht
                  // übersetzt -- und steht deshalb auch in keinem Wörterbuch
                  verbatim: !!(o && o.verbatim)}));
        }
        // a file waiting to be sent is already choosable, though the device
        // has never heard of it -- that is the whole point of choosing before
        // saving
        if (cons.type === "file")
            for (const {name} of (S.pendingFiles[node.path] || []))
                if (!options.some(o => o.value === name))
                    options.push({value: name, label: name});
        // Die Optionen eines dynamischen Enums stehen erst zur Laufzeit fest,
        // weshalb der Kern den gespeicherten Wert nie gegen sie prüfen konnte
        // ("defer the exact check" in cvv_tree). Bietet der Anbieter ihn nicht
        // mehr an -- eine deutsche Stimme etwa, nachdem die Ansagesprache auf
        // Türkisch gewechselt ist --, dann ist er keine Wahl mehr, sondern ein
        // Rest. Leer *aussehen* tat das Feld ohnehin schon, weil kein <option>
        // dazu passte; hier wird es wahr, damit Speichern ihn wirklich los
        // wird und der Zustand des Geräts dem entspricht, was zu sehen ist.
        // Nur beim dynamischen Enum: ein statisches prüft der Kern bereits
        // beim Laden und verwirft, was nicht mehr zur Deklaration passt.
        if (Array.isArray(cons.one_of) === false && !fixed && !backend &&
                cur !== null && cur !== undefined && cur !== "" &&
                !options.some(o => o.value === cur)) {
            commitQuiet(null);
            cur = null;
        }
        if (ctx.usedEnumValues)           // uniqueness filter (spec 4.9.2)
            options = options.filter(o => o.value === cur ||
                                          !ctx.usedEnumValues.has(o.value));
        const sel = el("select", {disabled: fixed || backend ? "" : null,
                onchange: (e) => commit(e.target.value || null)},
            el("option", {value: ""}, ""),
            ...options.map(o => el("option",
                {value: o.value, title: o.tooltip ? xl(o.tooltip) : null},
                o.verbatim ? o.label : xl(o.label))));
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
            // the device answers refusals with the German key, so that the
            // session's own language decides how they read
            msg(data && data.error ? xl(data.error)
                                   : xl("Connection to the device lost"),
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
        // Drei Ausgänge, nicht zwei: eine Testroutine, die "false" zurückgibt,
        // kommt mit Status 200 zurück, und "Erfolgreich: false" widersprach
        // sich selbst. Und auch ein "true" heißt nur, dass die Routine ohne
        // Fehler durchlief -- ob der richtige Klingelton erklang, entscheidet
        // allein, wer zuhört.
        const clean = (r.status === 200) && !!r.data.result;
        const outcome = (r.status !== 200)
            ? xl("The test could not be started.")
            : (r.data.result
                ? xl("The test routine ran without errors.")
                : xl("The test routine could not carry out the test."));
        // Der technische Grund steht darunter und nicht hinter einem
        // Doppelpunkt: der Satz endet auf einen Punkt, und "... werden.: 500"
        // liest sich wie ein Tippfehler. Übersetzt wird er nicht -- was der
        // Server zurückgibt, steht in keiner Sprache dieses Hauses.
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
                   `${d.error || xl("Connection to the device lost")}`,
                   "error");
    const [text, level] = verdict(d);
    const refused = level === "error";
    const changed = refused !== !!S.probeBad[node.path];
    if (refused) S.probeBad[node.path] = text;
    else delete S.probeBad[node.path];
    msg(text, level);
    // erst melden, dann neu zeichnen: das Neuzeichnen darf die Meldung nicht
    // überholen, und ohne es bliebe die Markierung aus
    if (changed && rerender) rerender();
}

function probeButton(node, currentValue, rerender) {
    const btn = el("button", {class: "small"}, xl("Check"));
    btn.addEventListener("click", async () => {
        btn.disabled = true;
        // Dasselbe Urteil hat dieselbe Folge, ob es auf Knopfdruck kommt oder
        // von selbst: es markiert das Feld. Ein Knopf, der nur berichtet und
        // ein Feld, das sich davon nichts merkt, hinterließe zwei Wahrheiten
        // über denselben Wert.
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
    // Zurücknehmen während des Renderns: kein erneutes Rendern, sonst dreht
    // sich das im Kreis -- dieselbe Vorsicht wie beim likely_val oben.
    const commitQuiet = (v) => {
        setIn(container, relKeys, v);
        ctx.markDirtyQuiet();
    };
    // 'values_for' nennt ein Geschwisterfeld; sein Entwurfswert ist das
    // Argument des Anbieters. Nicht gesetzt heißt null und nicht "kein
    // Argument" -- der Anbieter soll den Unterschied sehen können.
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
    // Vom Gerät zurückgewiesen: dieselbe Markierung wie bei einer Eingabe, die
    // der Browser selbst zurückweist -- nur kommt das Urteil hier von dort, wo
    // der Wert später gebraucht wird.
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
    const goTo = (pos) => {                       // B.3 / B.4: discard edits
        st.pos = (pos >= 1 && pos <= list.length + 1) ? pos : list.length + 1;
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
        goTo(Number.isInteger(n) ? n : list.length + 1);
    });
    const nav = el("div", {class: "nav-block"},
        el("button", {onclick: () =>
            goTo(st.pos > 1 ? st.pos - 1 : list.length + 1)}, "▲"),
        posField,
        el("button", {onclick: () =>
            goTo(st.pos < list.length + 1 ? st.pos + 1 : 1)}, "▼"));

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

    const apply = el("button", {class: "primary",
        disabled: S.readOnly || !st.changed || repeatsKey ? "" : null},
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
    // Was das Gerät zurückgewiesen hat, geht nicht auf das Gerät. Hier und
    // nicht beim Eintippen: dort wird markiert, damit der Tippfehler zu sehen
    // und zu berichtigen ist -- weggenommen wird er nicht.
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
        await modal(xl("Connection to the device lost"), {alert: true});
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
                             : xl("Connection to the device lost"), "error");
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
function applyTextDirection() {
    document.documentElement.dir = RTL_LANGS.has(S.lang) ? "rtl" : "ltr";
}

async function switchLanguage(lang) {
    S.lang = lang;
    localStorage.setItem("gpsmcpmms_lang", lang);
    await loadLang();
    applyTextDirection();
    renderAll();
}

/* Translations are managed by a CSV round-trip (spec 4.5): download a
 * template (German source + chosen reference columns + the target column),
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

async function uploadTranslation(file, remove, code, name) {
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
    if (remove) fd.append("remove", remove);
    // a language nobody can name would show up in every dropdown as a code
    if (name) fd.append("name", name);

    const resp = await fetch("/api/lang/upload",
        {method: "POST", headers: authHeaders(), body: fd});
    if (resp.status === 409) {                 // an 8th language needs room
        const body = await resp.json();
        const pick = await modal(xl("Choose the language to be replaced"),
                                 {select: body.removable});
        if (pick === null) return;
        return uploadTranslation(file, pick);
    }
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
function renderLangPanel(mode) {
    const active = S.languages.filter(l => l !== "de");
    const st = S.langForm || (S.langForm = {});

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
        const unused = Object.keys(S.langNames || {})
            .filter(c => !S.languages.includes(c))
            .sort((a, b) => langName(a).localeCompare(langName(b)));
        const code = el("input", {type: "text", class: "lang-code",
                                  placeholder: xl("Language code"),
                                  value: st.newCode || ""});
        const name = el("input", {type: "text", class: "lang-name",
                                  placeholder: xl("Language name"),
                                  value: st.newName || ""});
        const pick = el("select", {onchange: (e) => {
            const c = e.target.value;
            if (!c) return;
            // the two fields are what actually counts; the dropdown only
            // fills them in, and stays a convenience rather than a gate
            st.newCode = code.value = c;
            st.newName = name.value = langName(c);
        }}, el("option", {value: ""}, "—"),
           ...unused.map(c => el("option", {value: c}, langName(c))));
        const typed = (field, key) => field.addEventListener("input", () => {
            st[key] = field.value;
            pick.value = "";            // hand-typed wins over the list
        });
        typed(code, "newCode");
        typed(name, "newName");
        targetOf = () => (code.value || "").trim().toLowerCase();

        row1 = el("div", {class: "lang-panel-row"},
            el("span", {}, xl("New language") + ":"), pick, code, name);
    }

    // row 1b -- only when every slot is taken. Asked here, before any work,
    // rather than after an upload arrives with the translation already done.
    let row1b = null, replaceOf = () => null;
    if (mode === "new" && S.languages.length >= (S.maxLanguages || 7)) {
        const sel = el("select", {},
            ...active.map(l => el("option", {value: l}, langName(l))));
        replaceOf = () => sel.value;
        row1b = el("div", {class: "lang-panel-row"},
            el("span", {}, xl("To be replaced") + ":"), sel);
    }

    // row 2 -- context languages: everything active except German, and except
    // the one being worked on
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
            uploadTranslation(picker.files[0], replaceOf(),
                              mode === "new" ? targetOf() : null,
                              mode === "new" ? (st.newName || "").trim() : null);
        }}, xl("Upload the selected CSV")));

    const panel = el("div", {class: "lang-panel"}, row1, row1b, row2, row3);
    limit();
    return panel;
}

/* ---------- top level rendering ---------- */
function renderAll() {
    const app = document.getElementById("app");
    app.innerHTML = "";
    app.append(
        el("h1", {class: "title"}, xl("Hub4Help Configuration Editor")),
        el("hr", {class: "title-rule"}));

    const general = el("div", {class: "general-row"});
    if (S.protectedOmitted && !S.readOnly)
        general.append(el("button", {onclick: unlockProtected},
                          xl("Show protected parameters")));
    const langSel = el("select", {onchange: (e) =>
                                      switchLanguage(e.target.value)},
        ...S.languages.map(l => el("option", {value: l}, langName(l))));
    langSel.value = S.languages.includes(S.lang) ? S.lang : "de";
    general.append(el("span", {}, xl("Language") + ":"), langSel);
    if (S.admin) {
        const toggle = (mode) => {
            S.langPanel = S.langPanel === mode ? null : mode;
            S.langForm = {};              // a fresh panel starts empty
            renderAll();
        };
        // adding comes first: it is the rarer and the more consequential of
        // the two, and putting it second invites reaching for it by mistake
        general.append(
            el("button", {class: "small" + (S.langPanel === "new"
                                                ? " primary" : ""),
                          onclick: () => toggle("new")},
               xl("Add new translation")),
            el("button", {class: "small" + (S.langPanel === "edit"
                                                ? " primary" : ""),
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
               xl("Take over session"))));
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

/* ---------- data loading ---------- */
async function loadLang() {
    const r = await api(`/api/schema/${S.lang}`);
    S.xl = r.data || {};
}

async function loadLangList() {
    const r = await api("/api/lang/info");
    if (r.data && r.data.languages) S.languages = r.data.languages;
    if (r.data && r.data.options) S.langNames = r.data.options;
    if (r.data && r.data.max_languages) S.maxLanguages = r.data.max_languages;
    // Der Browser darf eine Sprache nennen, für die es hier kein Wörterbuch
    // gibt. Angezeigt würden dann die Schlüssel selbst -- lesbar, aber die
    // Auswahlliste stünde auf etwas, was nicht darin vorkommt.
    if (S.languages.length && !S.languages.includes(S.lang))
        S.lang = S.languages.includes("en") ? "en" : S.languages[0];
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
    S.admin = r.data.admin;
    S.wrongPasswd = r.data.wrong_passwd;
    S.factory = r.data.factory_default_passwd;
    S.protectedOmitted = r.data.protected_omitted;
    S.cvv = r.data.cvv;
    S.edit = {};
    S.dirty = {};
    S.listsB = {};
    S.listsA = {};
    // Die Zurückweisungen gehören zu den Entwurfswerten, die gerade verworfen
    // wurden: was jetzt im Formular steht, kommt vom Gerät und ist dort gültig.
    S.probeBad = {};
    // Die Optionen eines dynamischen Enums rechnet das Gerät aus seinem
    // eigenen Zustand aus, und der ist gerade ein anderer geworden. Die
    // Stimmenliste hängt an der gespeicherten Ansagesprache: ohne diese Zeile
    // zeigte sie nach dem Speichern weiter die Stimmen der vorigen Sprache,
    // und nur ein Neuladen der Seite brachte sie in Ordnung. Gefragt wird
    // dabei nur nach den Feldern, die auch zu sehen sind -- ein zugeklappter
    // Abschnitt kostet nichts.
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
               xl("Connection to the device lost"),
               el("button", {class: "small",
                   onclick: () => location.reload()}, xl("Reload"))));
    }
}

boot();
