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

/* GPSMCPMMS config-editor frontend, the stock design (spec sections
 * 4.4 - 4.9).
 *
 * This file is one way of drawing the editor, and only that. What a value is
 * and how a module is saved is core.js's business, which the page loads
 * first; a deployment that wants the editor to look and behave differently
 * puts an app.js of its own into ui_dir, which is then served in place of
 * this file -- and likewise app.css and app.html -- and keeps core.js. */
"use strict";

if (typeof reloadData !== "function") {
    // A page from before the split, kept because a deployment had changed
    // it: it loads this file and nothing else.
    document.getElementById("app").textContent =
        "This page is out of date: it must load /core.js before /app.js.";
    throw new Error("core.js is not loaded");
}

/* What this design keeps about the page it drew. It lives in S beside the
   data, because that is where every function in here already looks. */
Object.assign(S, {
    langPanel: null,         // null | "new" | "edit"
    langForm: {},            // what the open panel has been told so far
    open: {},                // dump path -> group expanded?
    listsA: {},              // dump path -> {sel}
    listsB: {},              // dump path -> {pos, draft, changed}
    message: null,           // {text, cls} on screen now; see msg()
});
// The position and the draft of every list editor were about values that
// have just been replaced.
onReload(() => { S.listsB = {}; S.listsA = {}; });

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

/* A message is kept in S and not only in its box, because renderAll() builds
   the page from nothing -- the box included -- and a render follows a message
   more often than not: the options of a dynamic enum and a fetched hint both
   arrive after the page is drawn, and draw it again when they do. Kept in the
   box alone, "Saved" lasted until the panel just saved had its options back,
   and on the service cards, which ask for theirs on every save, that was no
   time at all. So every render draws the message anew, and only msg() and
   its timer decide how long it lives: six seconds for news, until the next
   message for an error. */
let msgTimer = null;
function msg(text, cls = "info") {
    S.message = {text, cls};
    showMessage();
    clearTimeout(msgTimer);
    if (cls !== "error")
        msgTimer = setTimeout(() => { S.message = null; showMessage(); }, 6000);
}

/* Into whichever box the page has now: the one that stood there when the
   message was given may have been thrown away by a render since. */
function showMessage() {
    const box = document.getElementById("messages");
    if (!box) return;
    box.innerHTML = "";
    if (S.message)
        box.append(el("div", {class: `msg ${S.message.cls}`}, S.message.text));
}
// what core.js has to say goes the same way as what this file says
onNotify(msg);

/* ---------- hints (spec 4.9.5) ---------- */
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

/* ---------- single input fields ---------- */
function buildInput(node, cur, commit, commitQuiet, ctx, enumArg) {
    // returns an element whose 'change' leads to commit(newModelValue)
    //
    // What the field is -- its kind, its options, what it shows, whether it
    // may be written -- is fieldSpec()'s answer, and what a typed value is
    // worth is readField()'s. This function only chooses the element and
    // wires the two up.
    const spec = fieldSpec(node, cur, ctx, enumArg);
    const fail = (input) => {
        input.classList.add("invalid");
        msg(xl("Invalid input"), "error");
        setTimeout(() => input.focus(), 0);   // keep the focus (spec 4.5)
    };
    const ok = (input, v) => { input.classList.remove("invalid"); commit(v); };
    const read = (input) => {
        const got = readField(spec, input.value);
        if (got.invalid) fail(input); else ok(input, got.value);
    };
    const off = spec.fixed ? "" : null;
    const held = spec.fixed || spec.backend ? "" : null;

    switch (spec.kind) {
    case "boolean":
        return el("input", {type: "checkbox", disabled: off,
            // touching the box always answers it, so the third state goes away
            onchange: (e) => { e.target.indeterminate = false;
                               commit(e.target.checked); }});
    case "enum": {
        if (spec.pending)
            return el("select", {disabled: ""}, el("option", {}, "…"));
        if (spec.error)
            return el("select", {disabled: "", class: "invalid"},
                      el("option", {}, xl(spec.error)));
        // a proposal taken is a value the draft now holds; see proposedOption()
        if (spec.proposal !== undefined) commitQuiet(spec.proposal);
        const sel = el("select", {disabled: held,
                class: spec.orphaned ? "invalid" : null,
                title: spec.orphaned ? spec.cur : null,
                onchange: (e) => commit(e.target.value || null)},
            // The empty entry is blank, and says nothing: a field nobody
            // has filled in shows it, and a word there would read like a
            // value. It carried "clear" inside a list for a while, when
            // emptying the field was how a member was removed -- removing
            // is a button of its own now, and the entry is back to meaning
            // "nothing chosen".
            el("option", {value: ""}, ""),
            spec.orphaned
                ? el("option", {value: spec.cur}, xl("Value not known"))
                : null,
            ...spec.options.map(o => {
                const {text, hint} = optionWording(o);
                return el("option", {value: o.value, title: hint},
                          hint ? `${text} (${hint})` : text);
            }));
        sel.value = spec.cur === null || spec.cur === undefined ? "" : spec.cur;
        return sel;
    }
    case "color":
        return el("input", {type: "color", value: spec.hex, disabled: held,
            onchange: (e) => commit(colorOfHex(e.target.value))});
    case "number": {
        const input = el("input", {type: "number", step: spec.step,
            value: spec.shown, placeholder: spec.placeholder,
            disabled: off, readonly: spec.backend ? "" : null});
        input.addEventListener("change", () => read(input));
        return input;
    }
    default: {
        const input = el("input", {
            type: spec.secret ? "password" : "text",
            value: spec.shown, placeholder: spec.placeholder,
            disabled: off, readonly: spec.backend ? "" : null});
        input.addEventListener("keydown",
            (e) => { if (e.key === "Enter" || e.keyCode === 13) input.blur(); });
        input.addEventListener("change", () => read(input));
        return input;
    }
    }
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
        let data = null;
        try {
            data = await captureValue(node.path);
        } finally {
            thaw();
            btn.disabled = false;
        }
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
    // "Test" unless the declaration says otherwise. A button that records a
    // name is not testing anything, and the word on it should say what
    // pressing it does.
    const btn = el("button", {class: "small"},
                   xl(node.ui.test_button || "Test"));
    btn.addEventListener("click", async () => {
        const t = await runTest(node.path, currentValue());
        // Three outcomes, not two: a test routine that returns "false" comes
        // back with status 200, and "Successful: false" contradicted itself.
        // A "true" says no more than that the routine ran without error --
        // whether the right ring tone sounded is decided by whoever listened.
        const clean = t.clean;
        const outcome = !t.started
            ? xl("The test could not be started.")
            : (t.clean
                ? xl("The test routine ran without errors.")
                : xl("The test routine could not carry out the test."));
        // The technical reason goes underneath rather than behind a colon:
        // the sentence ends in a full stop, and "... carry the test out.: 500"
        // reads like a typo. It is not translated -- what the server hands
        // back is written in no language of this house.
        const detail = !t.started
            ? el("p", {class: "detail"}, t.error)
            : null;
        await modal([node.ui.test_func_msg ? xl(node.ui.test_func_msg) : "",
                     el("p", {class: "outcome " + (clean ? "ok" : "error")},
                        outcome),
                     detail],
                    {alert: true});
    });
    return btn;
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
    // a proposal the draft takes is written like a value, without a render
    const proposal = likelyValue(node, cur, relKeys, ctx);
    if (proposal !== undefined) {
        cur = proposal;
        setIn(container, relKeys, cur);
        ctx.markDirtyQuiet();
    }
    const commit = (v) => {
        setIn(container, relKeys, v);
        ctx.markDirty();
        ctx.rerender();
        // a verdict that refuses the value marks the field on the next render
        if (PROBE_TYPES.has(cons.type)) probeValue(node, v, ctx.rerender);
    };
    // Withdrawing during a render: no second render, or this goes round in
    // circles -- the same caution as with likely_val above.
    const commitQuiet = (v) => {
        setIn(container, relKeys, v);
        ctx.markDirtyQuiet();
    };
    const enumArg = enumArgOf(cons, container, relKeys);
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

    const row = el("div", {class: "field-row", "data-path": node.path},
        el("label", {}, xl(node.ui.label || node.path.split(".").pop())),
        node.ui.tooltip ? el("span",
            {class: "help", title: xl(node.ui.tooltip)}, "?") : null,
        input,
        repeats ? el("span", {class: "field-note"},
                     xl("Value already taken"))
                : refused ? el("span", {class: "field-note"}, refused) : null);
    // Nothing beside a locked field either: capturing a card, uploading a
    // file and probing all write where the field may not be written.
    const locked = S.readOnly || !!ctx.locked;
    if (node.configurability === 2 && node.ui.acquire_button && !locked)
        row.append(acquireButton(node, input, commit));
    if (PROBE_TYPES.has(cons.type) && !locked)
        row.append(probeButton(node, () => getIn(container, relKeys),
                               ctx.rerender));
    if (cons.type === "file" && !locked)
        row.append(uploadButton(node, ctx, commit));
    // A list of options that can change while somebody is looking at it
    // (spec 4.9.1): the same button a hint has, for the same reason -- what
    // is shown is a statement about the present. Not for a session that may
    // not write: asking again may set the device to work.
    if (cons.refreshable && typeof cons.one_of === "string" && !locked)
        row.append(el("button", {class: "hint-refresh", type: "button",
            title: xl("Refresh"),
            onclick: () => { fetchEnumOptions(node.path, ctx.rerender,
                                              enumArg, true);
                             ctx.rerender(); }},
            "↻"));
    if (node.ui.test_func && !locked)
        row.append(testButton(node, () => getIn(container, relKeys)));

    return withHint(node, ctx, row);
}

/* A hint belongs above the thing it is about, close enough that nobody has to
   work out which one that is; the wrapper is what ties the two together.

   Above a group rather than inside it, deliberately. A collapsed group is not
   rendered at all, so a hint in its body would be gone exactly when somebody
   has not opened it -- and the state of a ring of LEDs is the kind of thing
   you want to read without opening anything. */
function withHint(node, ctx, body) {
    const hint = hintFor(node, ctx);
    return hint ? el("div", {class: "field-block"}, hint, body) : body;
}

function collapsible(pathKey, labelText, tooltip, renderBody, extraClass,
                     headerExtra) {
    const isOpen = !!S.open[pathKey];
    const group = el("div", {class: `group ${extraClass || ""}`,
                             "data-path": pathKey});
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
        return withHint(node, ctx, collapsible(node.path,
            xl(node.ui.label || relKeys[relKeys.length - 1]),
            node.ui.tooltip ? xl(node.ui.tooltip) : null,
            () => renderDictBody(node, container, relKeys, ctx),
            null, groupTestButton(node, container, relKeys)));
    }
    if (node.item_template) {
        const simple = !node.item_template.children;
        // Nested lists take the two tones in turn. A list inside a record of
        // another list is the place where it stops being obvious which
        // "Apply" applies to what: the inner buttons sit inside the outer
        // record, and both sets look the same. Alternating says which floor
        // you are on -- and because each tone is set on the body it applies
        // to, everything inside it picks up its colours by inheritance.
        const depth = ctx.listDepth || 0;
        const listCtx = Object.assign({}, ctx, {listDepth: depth + 1});
        const tone = "tone-" + (depth % 2 + 1);
        return withHint(node, ctx, collapsible(node.path,
            xl(node.ui.label || relKeys[relKeys.length - 1]),
            node.ui.tooltip ? xl(node.ui.tooltip) : null,
            () => simple ? renderListA(node, container, relKeys, listCtx, tone)
                         : renderListB(node, container, relKeys, listCtx, tone),
            null, groupTestButton(node, container, relKeys)));
    }
    return fieldRow(node, container, relKeys, ctx);
}

/* ---------- list editor, Case A: simple members (spec 4.6.2 A) ---------- */
function renderListA(node, container, relKeys, ctx, tone) {
    const list = getIn(container, relKeys) || [];
    const cons = node.constraints, tpl = node.item_template;
    const fixed = S.readOnly || node.configurability === 0 || !!ctx.locked;
    const st = S.listsA[node.path] ||
               (S.listsA[node.path] = {sel: list.length, drafts: {}});
    if (!st.drafts) st.drafts = {};
    const body = el("div", {class: "group-body list-a " + (tone || "tone-1")});

    // The row behind the last one is where a new member goes, and it is the
    // one selected when the group opens -- for a list of simple values, and
    // only there: a record navigator opens on the first record, because a
    // record is read before it is added to.
    //
    // Where nothing can be added there is no such row, and the selection
    // falls back on the last member there is.
    const growable = !fixed && list.length < cons.max_size;
    const last = growable ? list.length : Math.max(list.length - 1, 0);
    if (!(st.sel >= 0) || st.sel > last) st.sel = last;

    const rerenderList = () => ctx.rerender();
    const select = (i) => { st.sel = i; rerenderList(); };
    const stored = (i) => (i < list.length ? list[i] : null);
    const shown = (i) => (i in st.drafts ? st.drafts[i] : stored(i));
    const cellText = (v) => (v === null || v === undefined || v === "")
        ? "\u00a0" : memberLabel(tpl, v);

    // ---- the table, so that the row being edited can be corrected in place
    const rows = [];
    let selectedRow = null, selectedCell = null;
    for (let i = 0; i <= last; i++) {
        const td = el("td", {}, cellText(shown(i)));
        const tr = el("tr", {class: (i === st.sel ? "selected" : "") +
                                    (i in st.drafts ? " pending" : "")}, td);
        tr.addEventListener("click", () => { if (!fixed) select(i); });
        rows.push(tr);
        if (i === st.sel) { selectedRow = tr; selectedCell = td; }
    }
    const wrap = el("div", {class: "table-wrap"}, el("table", {},
        el("tbody", {}, ...rows)));

    // ---- the member's own field
    // Not a text box: the spec says "an input field for the value of a list
    // element" (4.6.2 A.2) -- one field, not one *text* field, and a member
    // that is an enum wants the enum's list. Typed by hand it was the
    // identifier that had to be typed: a chain member is stored as a
    // telephone number, so choosing a contact meant knowing their number by
    // heart and spelling it the way the store spells it.
    //
    // configurability travels from the list: a list nobody may change must
    // not hand out a field they can. Only that case travels, though. A
    // member that is captured rather than typed carries a 2 of its own, and
    // taking the list's 1 instead turned it into a text box -- a telegram to
    // be typed off a log, which is the very thing the capture button is
    // there to spare.
    const tplNode = Object.assign({}, tpl, {
        configurability: node.configurability === 0 ? 0 : tpl.configurability,
    });
    // A list of simple values holds no duplicates (spec 4.9.2), so what is
    // already in it has no business in the list of choices. The selected
    // member itself stays on offer -- the field has to be able to show what
    // it is editing.
    const memberCtx = Object.assign({}, ctx, {
        usedEnumValues: new Set(list.filter((v, i) => i !== st.sel)),
    });
    // What the member's options are computed for: the field the template
    // names, seen from the member's own place -- one step further in than
    // the list itself, which is what the index stands for here. A member has
    // no siblings, so what it names lies outside its list ("^chain_id").
    let valInput = null, asBuilt = null;

    // What is typed is a draft and nothing more until Apply: the table shows
    // it, the data does not hold it, and it survives a move to another row.
    // Before this, the first keystroke that reached the field was already a
    // member of the list -- the next empty row appeared underneath, Apply had
    // nothing left to do, and a mistake could only be removed, not corrected.
    //
    // A draft exists only where it is a value and a different one: emptying
    // the field is how a row goes back to what it holds, and on the empty row
    // it is how what was typed is dropped.
    //
    // Noted without a re-render, deliberately. A click on Apply blurs the
    // field first; a field whose change rebuilt the panel would take the
    // button out from under the pointer, and the click would land on a new
    // element and never be a click at all.
    const noteDraft = (v) => {
        if (v === "" || v === undefined) v = null;
        if (v === null || v === stored(st.sel)) delete st.drafts[st.sel];
        else st.drafts[st.sel] = v;
        if (selectedCell) selectedCell.textContent = cellText(shown(st.sel));
        if (selectedRow)
            selectedRow.classList.toggle("pending", st.sel in st.drafts);
        settle();
    };

    const applyDraft = () => {
        // A pending edit first, through the field's own change handler: that
        // is where the value is read in the member's own type and validated,
        // so Apply and leaving the field stay the same act.
        valInput.dispatchEvent(new Event("change"));
        const v = shown(st.sel);
        if (v === null || v === undefined || v === "") return;
        const twin = list.indexOf(v);
        if (twin >= 0 && twin !== st.sel) {
            // Already a member. Typing one is how a member is looked up, so
            // the selection goes there rather than an error going up.
            delete st.drafts[st.sel];
            select(twin);
            return;
        }
        const atEnd = st.sel >= list.length;
        if (atEnd && list.length >= cons.max_size) {
            msg(xl("List is full"), "error");
            return;
        }
        if (atEnd) list.push(v); else list[st.sel] = v;
        delete st.drafts[st.sel];
        setIn(container, relKeys, list);
        ctx.markDirty();
        // A member confirmed at the end brings the next empty row at once,
        // and the selection goes there: that is how five members are entered
        // with nothing but the field and Apply.
        if (atEnd) st.sel = list.length;
        rerenderList();
    };

    const removeRow = () => {
        if (st.sel >= list.length) {
            delete st.drafts[st.sel];       // the empty row: drop the draft
            rerenderList();
            return;
        }
        list.splice(st.sel, 1);
        // The drafts of the rows below move up with them; the one on the row
        // that goes, goes with it.
        const moved = {};
        for (const key of Object.keys(st.drafts)) {
            const i = Number(key);
            if (i === st.sel) continue;
            moved[i > st.sel ? i - 1 : i] = st.drafts[key];
        }
        st.drafts = moved;
        setIn(container, relKeys, list);
        ctx.markDirty();
        rerenderList();
    };

    const applyBtn = el("button", {class: "lead", disabled: "",
                                   onclick: applyDraft}, xl("Apply"));
    const removeBtn = el("button", {disabled: "", onclick: removeRow},
                         xl("Remove"));
    // Apply is on where the selected row carries something unconfirmed --
    // recorded as a draft, or still standing in the field unblurred, because
    // a button that is off takes no click and the blur would never happen.
    // Remove is on for every row there is, and on the empty row only once
    // something has been typed into it: there is nothing else to remove.
    const settle = () => {
        const live = valInput && ("value" in valInput ||
                                  valInput.type === "checkbox")
            ? (valInput.type === "checkbox" ? valInput.checked
                                            : valInput.value)
            : null;
        const touched = (st.sel in st.drafts) ||
                        (live !== null && live !== "" && live !== asBuilt);
        applyBtn.disabled = fixed || !touched;
        removeBtn.disabled = fixed ||
            !(st.sel < list.length || touched);
    };

    valInput = buildInput(tplNode, shown(st.sel), noteDraft, noteDraft,
                          memberCtx,
                          enumArgOf(tpl.constraints, container,
                                    relKeys.concat([0])));
    asBuilt = ("value" in valInput || valInput.type === "checkbox")
        ? (valInput.type === "checkbox" ? valInput.checked : valInput.value)
        : null;
    valInput.addEventListener("input", settle);
    settle();

    const posField = el("input", {class: "pos-field", type: "text",
        value: st.sel + 1, disabled: fixed ? "" : null});
    posField.addEventListener("change", () => {
        const n = parseInt(posField.value, 10);
        select(Number.isInteger(n) && n >= 1 && n <= last + 1 ? n - 1 : last);
    });

    // Three rows are shown and the rest are scrolled to (default.css) -- and
    // the selected one is brought into view, because the one selected by
    // default is the last: on a list of ten it would otherwise sit below the
    // fold, and the field beside the table would be editing something
    // nobody can see. Measured after the layout rather than reckoned from
    // the stylesheet: what a row is high is what the reader's language and
    // font make it.
    // On a timer and not in an animation frame: a window that is not being
    // painted -- another one in front of it, the tab in the background --
    // runs no frame callbacks at all, and the scrolling would then be the
    // one thing that works everywhere except where somebody is looking.
    setTimeout(() => {
        if (!wrap.isConnected || !wrap.clientHeight) return;
        const trs = wrap.querySelectorAll("tr");
        const tr = trs[st.sel];
        if (!tr) return;
        const top = tr.offsetTop - trs[0].offsetTop, high = tr.offsetHeight;
        if (top < wrap.scrollTop) wrap.scrollTop = top;
        else if (top + high > wrap.scrollTop + wrap.clientHeight)
            wrap.scrollTop = top + high - wrap.clientHeight;
    }, 0);

    // A value hardware produces is captured here as it is at a field
    // (spec 4.9.3): the template may carry backend_provided, and then the
    // member's own field gets the button. Without it, a list of values that
    // can only be captured had to be a list of one-field records -- that
    // being the only way to a field that has a button -- and the reader got
    // a record navigator for what is one column of telegrams.
    //
    // The captured value takes the road a typed one takes: it becomes this
    // row's draft, the table shows it, and Apply puts it in the list. What
    // the capture asks on is the template's own path, the same path a
    // record's field asks on -- which is what the module's '*' matches.
    const editLine = el("div", {class: "edit-line"}, posField, valInput);
    if (!fixed && tplNode.configurability === 2 && tpl.ui.acquire_button)
        editLine.append(acquireButton(tplNode, valInput, noteDraft));
    body.append(editLine, wrap,
                el("div", {class: "apply-line"}, removeBtn, applyBtn));
    return body;
}

/* ---------- list editor, Case B: record members (spec 4.6.2 B) ---------- */
function renderListB(node, container, relKeys, ctx, tone) {
    const list = getIn(container, relKeys) || [];
    const tpl = node.item_template, cons = node.constraints;
    // A fixed list locks its length and composition -- no adding, no removing
    // -- but its members' inner leaves stay editable unless they lock
    // themselves (spec 2.1, key 4). Applying an edited record must therefore
    // stay possible; only the structural actions are barred.
    const structureFixed = S.readOnly || node.configurability === 0 ||
                           !!ctx.locked;
    let st = S.listsB[node.path];
    if (!st || st.pos > list.length + 1) {
        // Opened on the first record. The empty slot behind the last one is
        // reached with "New", which is the button that says what it is for;
        // a navigator that opens there shows an empty form for a list that
        // may be full of records, and the records are what somebody came to
        // look at. (A list of simple values does open on its empty row --
        // there the table shows everything at once, so the row where
        // something new goes is the only thing the field could usefully be
        // editing.)
        st = S.listsB[node.path] = {pos: 1, draft: null, changed: false};
    }
    if (st.draft === null) {
        // The record being edited has just become a different one -- a move,
        // a New, an Undo, a Remove. Every list editor nested inside it is
        // still holding the previous record's position and draft: those
        // states are kept under the node's path, and a list inside an item
        // template has one path for all the records of the enclosing list.
        //
        // Left standing, a fresh contact opened with the previous contact's
        // availabilities on screen -- and saved without them, because nobody
        // pressed Apply on a window that already looked right. What was shown
        // was neither what was stored nor what was meant.
        for (const store of [S.listsA, S.listsB])
            for (const key of Object.keys(store))
                if (key.startsWith(node.path + ".")) delete store[key];
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

    // A record that carries its own protection (spec 4.4 knows only the
    // declared sort), seen by a session without the password: it is shown --
    // a chain has to be able to name the contact it calls -- and nothing in
    // it can be touched. Read off the stored record and not off the draft,
    // or clearing the checkbox would unlock the record it protects.
    const memberLocked = memberIsLocked(cons, list, st.pos - 1);

    // standalone unique keys constrain the enum options of other rows
    const standaloneKeys = standaloneKeysOf(cons);
    const recCtx = Object.assign({}, ctx, {
        locked: ctx.locked || memberLocked,
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
        let childCtx = standaloneKeys.includes(key)
            ? Object.assign({}, recCtx,
                {usedEnumValues: usedEnumValuesIn(list, st.pos - 1, key)})
            : recCtx;
        // The flag itself is the one field a session without the password
        // may never write, in any record: setting it is what protection is,
        // and a contact somebody adds in an ordinary session is an ordinary
        // contact.
        if (key === cons.protected_by && !S.admin)
            childCtx = Object.assign({}, childCtx, {locked: true});
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
    const repeatsKey = memberRepeatsKey(cons, list, st.pos - 1, st.draft,
                                        recCtx);

    // ...and it has to be known by something: see memberLacksKey().
    const missingKey = memberLacksKey(cons, st.draft);

    // ...and the same rule again at the button, not only at the navigator: a
    // position typed straight into the field must not find a way in either.
    // Not the module's blue. That blue means "save this module", and a
    // button inside a list applies a record -- the two must not look alike.
    // The weight is what keeps it the first among the four.
    const apply = el("button", {class: "lead",
        disabled: S.readOnly || memberLocked || !st.changed || repeatsKey
                      || missingKey
                      || (structureFixed && st.pos > list.length)
                          ? "" : null,
        title: missingKey ? xl("Every key of this entry must be filled in")
                          : null},
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
        disabled: structureFixed || memberLocked || st.pos > list.length
                      ? "" : null},
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

    return el("div", {class: "group-body list-b " + (tone || "tone-1")},
        el("div", {class: "layout"}, recordBody, nav),
        el("div", {class: "action-block"}, neu, remove, undo, apply));
}

/* ---------- modules and save (spec 4.5) ---------- */
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
    const obstacle = saveObstacle(mid);
    if (obstacle) {
        msg(obstacle, "error");
        return;
    }
    if (!await confirmUnsetBooleans(mid)) return;
    const done = await submitModule(mid);
    if (done.outcome === "files") return;       // said already, see notify()
    if (done.outcome === "ended") {
        await modal(xl("The editing session has ended."), {alert: true});
        location.reload();
        return;
    }
    if (done.outcome === "failed") {
        msg(`${xl("Apply failed")}: ${done.detail}`, "error");
        return;
    }
    renderAll();
    if (done.outcome === "rejected") {
        msg(`${xl("Apply failed")}: ${xl("Rejected")}: ` +
            done.rejected.join(", "), "error");
    } else {
        msg(xl("Saved"), "ok");
    }
}

/* Kept identical to the sentence config.py registers as a key: the editor
   looks it up, and a rewording on one side alone would show the English. */
const DORMANT_HINT =
    "This module has given up its parameters because it does not need " +
    "them any more. The button brings them back for this session.";

/* A module that has retired keeps its heading, so it stays where the reader
   last saw it and its absence does not read as a fault. Nothing opens, so
   nothing offers to: no arrow, no click, and the CSS takes the pointer away.
   What stands under it is the reason and the way back. */
function dormantModule(mid) {
    // Collapsible like every other module, and closed like every other
    // module: it is one of the panels, and a block that behaves differently
    // reads as a different kind of thing.
    return collapsible(mid, xl(S.dormant[mid]), null,
        () => el("div", {class: "group-body dormant-body"},
            el("div", {class: "hint"}, xl(DORMANT_HINT)),
            el("button", {class: "small", onclick: () => reviveModule(mid)},
                xl("Bring them back"))),
        "module");
}

async function reviveModule(mid) {
    if (!await wakeModule(mid)) {
        msg(`${xl("Apply failed")}: ${xl("No answer from the device.")}`,
            "error");
        return;
    }
    renderAll();
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
    const taken = await takeOverWith(passwd);
    if (taken !== "ok") {
        msg(taken === "refused" ? xl("Incorrect password")
                                : xl("No answer from the device."), "error");
        return;
    }
    renderAll();
    msg(xl("Session taken over"), "ok");
}

/* The one finding that comes with something to press. Kept identical to the
   string config.py reports, because that is what it is matched against. */
const FACTORY_PASSWD_FINDING =
    "The device is still using the factory default password";

async function changePassword() {
    const neu = await modal(xl("New password"), {input: {type: "password"}});
    if (neu === null || neu === "") return;
    if (!await setPassword(neu)) {
        msg(xl("Apply failed"), "error");
        return;
    }
    // The session stays. It used to end here, and the button was called
    // "Exit admin mode" for it -- but ending a session is what the button
    // marked "End session" is for, and being thrown out for having set a
    // password is a strange reward. Setting a value does not touch the
    // session, so reloading the data is enough: the finding goes, and
    // whoever set the password is still an administrator.
    renderAll();
    msg(xl("Saved"), "ok");
}

/* The document's own language and direction, which default.html cannot know:
   it is served before anybody has chosen one, and it used to claim German
   for every reader. `lang` matters beyond looks -- it is what a screen reader
   picks a voice by, and what a browser hyphenates by. */
function applyTextDirection() {
    document.documentElement.lang = S.lang || S.sourceLang;
    document.documentElement.dir = RTL_LANGS.has(S.lang) ? "rtl" : "ltr";
    document.title = editorTitle();
}

async function switchLanguage(lang) {
    await useLanguage(lang);
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

async function downloadTemplate(target, refs) {
    if (!isLangCode(target))
        return msg(xl("Invalid input"), "error");
    const got = await fetchTemplate(target, refs);
    if (got.error !== undefined)
        return msg(`${xl("Apply failed")}: ${got.error}`, "error");
    triggerDownload(got.blob, `${target}.csv`);
    msg(`${xl("Download CSV")}: ${target}.csv`, "ok");
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
    if (!isLangCode(target))
        return msg(xl("Invalid input"), "error");
    const sent = await sendTranslation(file, target, name);
    if (sent.error !== undefined)
        return msg(`${xl("Invalid file")}: ${sent.error}`, "error");
    triggerDownload(sent.report, `${target}.report.csv`);
    renderAll();
    msg(`${xl("Translation processed")}: ` +
        `${sent.translated} / ${sent.total} ${xl("translated")}`, "ok");
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

   The numbers come with loadLangList(), and the device withholds them from
   everybody else. The source language is left out of both the count and the
   list: it has no dictionary and is complete by construction, so naming it
   would only invite the question why it never moves. */
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
/* One banner per module, and inside it one line per finding. Two banners
   for one module would read as two modules; two findings run together on
   one line read as one muddled thought. Where two findings could be said
   as a single sentence a module says them as one -- what arrives here as
   two really is two, and a line of its own is the honest separator.

   Sorted by module id, the same order the panels below are in: a device
   chooses that order by prefixing its ids, and a banner that ignored it
   would send the reader down the page in the wrong direction.

   A box of their own rather than straight into the page, because they are the
   one part of it that changes without anybody having done anything -- see
   watchStanding() -- and redrawing the whole page for a new finding would
   take the field out from under whoever is typing into it. */
function drawFindings() {
    const box = document.getElementById("findings");
    if (!box) return;
    box.innerHTML = "";
    for (const mid of Object.keys(S.moduleStatus).sort())
        box.append(el("div", {class: "banner"},
            ...S.moduleStatus[mid].map(m => el("div",
                {class: "finding " + m.level},
                xl(m.text),
                m.text === FACTORY_PASSWD_FINDING && S.admin
                    ? el("button", {class: "small", onclick: changePassword},
                         xl("Change password"))
                    : null,
                m.path
                    ? el("button", {class: "small",
                                    onclick: () => showPath(m.path)},
                         xl("Show"))
                    : null))));
}

/* Takes the reader to what a finding is about: every group on the way down
   is opened, and the deepest thing the page then has for that path is brought
   into view. That may be less than the path names -- a member of a list is
   not a place of its own on this page, and the list it belongs to is as near
   as it gets. */
function showPath(path) {
    const parts = path.split(".");
    const prefixes = parts.map((_, i) => parts.slice(0, i + 1).join("."));
    for (const prefix of prefixes) S.open[prefix] = true;
    renderAll();
    for (const prefix of prefixes.reverse()) {
        const target = [...document.querySelectorAll("[data-path]")]
            .find(e => e.getAttribute("data-path") === prefix);
        if (target) {
            target.scrollIntoView({block: "center"});
            break;
        }
    }
}

/* Looks again every ten seconds while the page is being looked at. What a
   module has found may have gone since the page was drawn, or only just
   turned up, and a finding that was dealt with an hour ago is worse than
   none. A page nobody sees asks nothing.

   The one thing said aloud is the end of this page's own session: taken
   over, or run out. Until now that was learned at the next Save, with
   whatever had been typed in the meantime. Said once -- the way back is a
   reload, and repeating it would not bring that any nearer. */
const STANDING_EVERY = 10000;
let sessionLossSaid = false;
function watchStanding() {
    setInterval(async () => {
        if (document.hidden) return;
        const wasMine = !S.readOnly && S.session === "valid";
        if (!await refreshStatus()) return;
        drawFindings();
        if (wasMine && S.session !== "valid" && !sessionLossSaid) {
            sessionLossSaid = true;
            msg(xl("The editing session has ended."), "error");
        }
    }, STANDING_EVERY);
}

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
            await endSession();
            location.reload();
        }}, xl("End session")));
    app.append(general);
    if (S.admin && S.langPanel) app.append(renderLangPanel(S.langPanel));
    app.append(el("div", {id: "messages"}));
    showMessage();              // a message outlives the box it was shown in

    if (S.readOnly)
        app.append(el("div", {class: "banner readonly"},
            xl("Read-only mode: another session is active"),
            el("button", {class: "small", onclick: () => location.reload()},
               xl("Reload")),
            el("button", {class: "small", onclick: takeOverSession},
               xl("Take over session")),
            lockFreeHint()));
    app.append(el("div", {id: "findings"}));
    drawFindings();

    // sorted by module id, which is how a device controls the order of the
    // groups on screen -- prefix the ids and you have chosen the sequence
    const ids = Array.from(new Set(Object.keys(S.cvv)
                                   .concat(Object.keys(S.dormant)))).sort();
    for (const mid of ids) {
        // A dormant module has no cvv entry at all -- its tree node went with
        // its parameters -- so it is drawn from the heading alone.
        if (S.dormant[mid]) { app.append(dormantModule(mid)); continue; }
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

async function boot() {
    try {
        await loadLangList();
        await loadLang();
        await reloadData();
        applyTextDirection();
        renderAll();
        watchStanding();
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
