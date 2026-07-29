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
    lang: localStorage.getItem("gpsmcpmms_lang") || "de",
    languages: ["de"],
    edit: {},                // moduleId -> working value (deep copy)
    dirty: {},               // moduleId -> bool
    open: {},                // dump path -> group expanded?
    enums: {},               // dump path -> {values}|{error}|{pending}
    listsA: {},              // dump path -> {sel}
    listsB: {},              // dump path -> {pos, draft, changed}
    langPanelOpen: false,    // translation-management panel toggled open?
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
                            xl("Abbrechen")));
        }
        const box = el("div", {class: "modal"},
            el("p", {}, text), input, select,
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
async function fetchEnumOptions(path, rerender) {
    S.enums[path] = {pending: true};
    const r = await api(`/api/config/enum-options?path=${encodeURIComponent(path)}`);
    S.enums[path] = (r.data && r.data.values) ? {values: r.data.values}
                  : {error: (r.data && r.data.error) || xl("Verbindung zum Gerät verloren")};
    if (S.enums[path].error) msg(S.enums[path].error, "error");
    rerender();
}

/* ---------- single input fields ---------- */
function hexOfColor(v) {
    if (!Array.isArray(v)) return "#000000";
    return "#" + v.map(x => (x || 0).toString(16).padStart(2, "0")).join("");
}
function colorOfHex(h) {
    return [1, 3, 5].map(i => parseInt(h.slice(i, i + 2), 16));
}

function buildInput(node, cur, commit, ctx) {
    // returns an element whose 'change' leads to commit(newModelValue)
    const cons = node.constraints || {}, ui = node.ui || {};
    const fixed = S.readOnly || node.configurability === 0;
    const backend = node.configurability === 2;
    const fail = (input) => {
        input.classList.add("invalid");
        msg(xl("Ungültige Eingabe"), "error");
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
            if (!state) {
                fetchEnumOptions(node.path, ctx.rerender);
                return el("select", {disabled: ""}, el("option", {}, "…"));
            }
            if (state.pending)
                return el("select", {disabled: ""}, el("option", {}, "…"));
            if (state.error)
                return el("select", {disabled: "", class: "invalid"},
                          el("option", {}, state.error));
            options = Object.entries(state.values).map(([value, o]) =>
                ({value, label: (o && o.label) || value,
                  tooltip: o && o.tooltip}));
        }
        if (ctx.usedEnumValues)           // uniqueness filter (spec 4.9.2)
            options = options.filter(o => o.value === cur ||
                                          !ctx.usedEnumValues.has(o.value));
        const sel = el("select", {disabled: fixed || backend ? "" : null,
                onchange: (e) => commit(e.target.value || null)},
            el("option", {value: ""}, ""),
            ...options.map(o => el("option",
                {value: o.value, title: o.tooltip ? xl(o.tooltip) : null},
                xl(o.label))));
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
            placeholder: ui.likely_val !== undefined ?
                             String(scaleOut(ui, ui.likely_val)) :
                             (ui.placeholder || ""),
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
        placeholder: ui.likely_val !== undefined ? String(ui.likely_val)
                                                 : (ui.placeholder || ""),
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
        const thaw = freeze(xl("Wert wird gelesen..."));
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
            msg(xl("Wert übernommen"), "ok");
        } else if (data && data.timeout) {
            msg(xl("Zeitüberschreitung"), "error");
        } else {
            msg((data && data.error) || xl("Verbindung zum Gerät verloren"),
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
        const outcome = (r.status === 200)
            ? `${xl("Erfolgreich")}: ${r.data.result}`
            : `${xl("Fehlgeschlagen")}: ${(r.data && r.data.error) || r.status}`;
        await modal((node.ui.test_func_msg ? xl(node.ui.test_func_msg) + " — "
                                           : "") + outcome, {alert: true});
    });
    return btn;
}

/* ---------- rows, groups, dict bodies (spec 4.6 / 4.6.1) ---------- */
function fieldRow(node, container, relKeys, ctx) {
    const cur = getIn(container, relKeys);
    const commit = (v) => {
        setIn(container, relKeys, v);
        ctx.markDirty();
        ctx.rerender();
    };
    const input = buildInput(node, cur, commit, ctx);
    if (input.type === "checkbox") {
        input.checked = !!cur;
        // A boolean that was never answered is neither yes nor no. Without the
        // third state it would look exactly like "no", and the parameter would
        // silently keep config_ready() false with nothing on screen to show it.
        input.indeterminate = (cur === null || cur === undefined);
    }
    const row = el("div", {class: "field-row"},
        el("label", {}, xl(node.ui.label || node.path.split(".").pop())),
        node.ui.tooltip ? el("span",
            {class: "help", title: xl(node.ui.tooltip)}, "?") : null,
        input);
    if (node.configurability === 2 && node.ui.acquire_button && !S.readOnly)
        row.append(acquireButton(node, input, commit));
    if (node.ui.test_func && !S.readOnly)
        row.append(testButton(node, () => getIn(container, relKeys)));
    return row;
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

function renderDictBody(node, container, relKeys, ctx) {
    const body = el("div", {class: "group-body"});
    const dictValue = getIn(container, relKeys);
    for (const [key, child] of Object.entries(node.children || {})) {
        if (child.ui && child.ui.hidden) continue;
        const rule = node.relevance && node.relevance[key];
        if (rule && !relevanceHolds(rule, dictValue)) continue;
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
                    await modal(xl("Eintrag wirklich entfernen?")) !== null) {
                list.splice(st.sel, 1);
                st.sel = null;
                ctx.markDirty();
            }
            rerenderList();
            return;
        }
        if (!validValue(tpl.constraints, v)) {
            msg(xl("Ungültige Eingabe"), "error");
            return;
        }
        const existing = list.indexOf(v);
        if (existing >= 0) { select(existing); return; }     // search select
        if (st.sel !== null) {
            list[st.sel] = v;                                // replace
        } else {
            if (list.length >= cons.max_size) {
                msg(xl("Liste ist voll"), "error");
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
                onclick: () => commitVal(valInput.value)}, xl("Anwenden"))));
    return body;
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
    const fixed = S.readOnly || node.configurability === 0;
    let st = S.listsB[node.path];
    if (!st || st.pos > list.length + 1) {
        st = S.listsB[node.path] = {pos: 1, draft: null, changed: false};
    }
    if (st.draft === null) {
        st.draft = st.pos <= list.length ? deepCopy(list[st.pos - 1])
                                         : composeValue(tpl);
        st.changed = false;
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
        markDirty: () => {
            st.changed = true;
            ctx.rerender();
        },
    });

    const recordBody = el("div", {class: "record-block"});
    const dictValue = st.draft;
    for (const [key, child] of Object.entries(tpl.children || {})) {
        if (child.ui && child.ui.hidden) continue;
        const rule = tpl.relevance && tpl.relevance[key];
        if (rule && !relevanceHolds(rule, dictValue)) continue;
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

    const apply = el("button", {class: "primary",
        disabled: fixed || !st.changed ? "" : null}, xl("Anwenden"));
    apply.addEventListener("click", () => {
        if (st.pos <= list.length) {
            list[st.pos - 1] = deepCopy(st.draft);
        } else {
            if (list.length >= cons.max_size)
                return msg(xl("Liste ist voll"), "error");
            list.push(deepCopy(st.draft));
        }
        setIn(container, relKeys, list);
        st.changed = false;
        ctx.markDirty();
        ctx.rerender();
    });
    const remove = el("button", {
        disabled: fixed || st.pos > list.length ? "" : null}, xl("Entfernen"));
    remove.addEventListener("click", () => {
        list.splice(st.pos - 1, 1);
        setIn(container, relKeys, list);
        ctx.markDirty();
        goTo(st.pos);                                   // B.6 leave event
    });
    const undo = el("button",
        {disabled: !st.changed ? "" : null}, xl("Rückgängig"));
    undo.addEventListener("click", () => { st.draft = null; ctx.rerender(); });

    // "Neu" jumps to the empty new-record slot (position list_size+1) to add
    // an entry; disabled when the list is fixed or already full
    const isNew = st.pos > list.length;
    const neu = el("button", {
        disabled: fixed || list.length >= cons.max_size || isNew ? "" : null,
        onclick: () => goTo(list.length + 1)}, xl("Neu"));

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
            focusErr(`${xl("Zu wenige Einträge in")} ` +
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
        xl("Diese Optionen wurden nie gesetzt; als \"nein\" übernehmen?") +
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
    if (!await confirmUnsetBooleans(mid)) return;
    const r = await api("/api/config/update",
        {json: {module: mid, value: S.edit[mid]}});
    if (r.status === 401) {
        await modal(xl("Verbindung zum Gerät verloren"), {alert: true});
        location.reload();
        return;
    }
    if (r.status !== 200) {
        msg(`${xl("Übernehmen fehlgeschlagen")}: ` +
            ((r.data && r.data.error) || r.status), "error");
        return;
    }
    const rejected = r.data.rejected;
    await reloadData();
    renderAll();
    if (rejected.length > 0) {
        msg(`${xl("Übernehmen fehlgeschlagen")}: ${xl("Abgelehnt")}: ` +
            rejected.join(", "), "error");
    } else {
        msg(xl("Gespeichert"), "ok");
    }
}

function renderModule(mid) {
    const node = S.cvv[mid];
    const ctx = {
        module: mid,
        markDirty: () => { S.dirty[mid] = true; },
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
                        onclick: () => saveModule(mid)}, xl("Speichern"))));
            }
            return body;
        }, "module");
}

/* ---------- level 0: general features (spec 4.4, 4.5, 4.8, C) ---------- */
async function unlockProtected() {
    const passwd = await modal(xl("Passwort"),
                               {input: {type: "password"}});
    if (passwd === null) return;
    await reloadData(passwd);
    if (S.wrongPasswd) msg(xl("Falsches Passwort"), "error");
    renderAll();
}

async function exitAdminMode() {
    if (S.factory) {
        const neu = await modal(xl("Neues Passwort"),
                                {input: {type: "password"}});
        if (neu === null || neu === "") return;
        const r = await api("/api/config/update",
            {json: {module: "config", value: {ui_passwd: neu}}});
        if (r.status !== 200 || r.data.rejected.length) {
            msg(xl("Übernehmen fehlgeschlagen"), "error");
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
        return msg(xl("Ungültige Eingabe"), "error");
    const url = `/api/lang/template?lang=${target}` +
                `&refs=${encodeURIComponent(refs.join(","))}`;
    const resp = await fetch(url, {headers: authHeaders()});
    if (!resp.ok) {
        let err = resp.status;
        try { err = (await resp.json()).error || err; } catch (e) { /**/ }
        return msg(`${xl("Übernehmen fehlgeschlagen")}: ${err}`, "error");
    }
    triggerDownload(await resp.blob(), `${target}.csv`);
    msg(`${xl("Vorlage herunterladen")}: ${target}.csv`, "ok");
}

function targetFromFileName(file) {
    const stem = file.name.replace(/\.csv$/i, "");
    return /^[a-z]{2,3}$/.test(stem) ? stem.toLowerCase() : null;
}

async function uploadTranslation(file, remove) {
    let target = targetFromFileName(file);
    if (!target) {
        target = await modal(xl("Neuer Sprachcode"), {input: {}});
        if (target === null) return;
        target = target.trim().toLowerCase();
        if (!/^[a-z]{2,3}$/.test(target))
            return msg(xl("Ungültige Eingabe"), "error");
    }
    const fd = new FormData();
    fd.append("file", file);
    fd.append("lang", target);
    if (S.token) fd.append("token", S.token);
    if (remove) fd.append("remove", remove);

    const resp = await fetch("/api/lang/upload",
        {method: "POST", headers: authHeaders(), body: fd});
    if (resp.status === 409) {                 // an 8th language needs room
        const body = await resp.json();
        const pick = await modal(xl("Zu entfernende Sprache wählen"),
                                 {select: body.removable});
        if (pick === null) return;
        return uploadTranslation(file, pick);
    }
    if (!resp.ok) {
        let err = resp.status;
        try { err = (await resp.json()).error || err; } catch (e) { /**/ }
        return msg(`${xl("Ungültige Datei")}: ${err}`, "error");
    }
    const translated = resp.headers.get("X-GPSMCPMMS-Translated");
    const total = resp.headers.get("X-GPSMCPMMS-Total");
    triggerDownload(await resp.blob(), `${target}.report.csv`);
    if (S.lang === target) await loadLang();
    await loadLangList();
    renderAll();
    // message after the re-render, so renderAll() does not wipe it
    msg(`${xl("Übersetzung verarbeitet")}: ` +
        `${translated} / ${total} ${xl("übersetzt")}`, "ok");
}

function renderLangPanel() {
    const others = S.languages.filter(l => l !== "de");
    const targetSel = el("select", {},
        el("option", {value: "__new__"}, xl("Neuer Sprachcode")),
        ...others.map(l => el("option", {value: l}, l)));
    const newCode = el("input", {type: "text", placeholder: "fr",
                                 class: "lang-code"});
    const refBoxes = others.map(l => {
        const cb = el("input", {type: "checkbox", value: l});
        return {l, cb, label: el("label", {class: "ref-box"}, cb, " " + l)};
    });
    const curTarget = () => targetSel.value === "__new__"
        ? newCode.value.trim().toLowerCase() : targetSel.value;
    const refresh = () => {
        newCode.style.display = targetSel.value === "__new__" ? "" : "none";
        const checked = refBoxes.filter(b => b.cb.checked).length;
        refBoxes.forEach(b => {
            b.cb.disabled = (b.l === curTarget()) ||
                            (!b.cb.checked && checked >= 3);
        });
    };
    targetSel.addEventListener("change", refresh);
    newCode.addEventListener("input", refresh);
    refBoxes.forEach(b => b.cb.addEventListener("change", refresh));

    const dl = el("button", {class: "small primary", onclick: () =>
        downloadTemplate(curTarget(),
            refBoxes.filter(b => b.cb.checked && b.l !== curTarget())
                    .map(b => b.l))}, xl("Vorlage herunterladen"));
    const fileInput = el("input", {type: "file", accept: ".csv"});
    const ul = el("button", {class: "small", onclick: () => {
        if (fileInput.files.length) uploadTranslation(fileInput.files[0]);
    }}, xl("Hochladen"));

    const panel = el("div", {class: "lang-panel"},
        el("div", {class: "lang-panel-row"},
            el("span", {}, xl("Zielsprache") + ":"), targetSel, newCode),
        others.length ? el("div", {class: "lang-panel-row"},
            el("span", {}, xl("Referenzsprachen (max. 3)") + ":"),
            ...refBoxes.map(b => b.label)) : null,
        el("div", {class: "lang-panel-row"}, dl,
            el("span", {class: "sep"}, "|"),
            el("span", {}, xl("Übersetzungsdatei hochladen") + ":"),
            fileInput, ul));
    refresh();
    return panel;
}

/* ---------- top level rendering ---------- */
function renderAll() {
    const app = document.getElementById("app");
    app.innerHTML = "";
    app.append(
        el("h1", {class: "title"}, xl("Hub4Help Konfigurationseditor")),
        el("hr", {class: "title-rule"}));

    const general = el("div", {class: "general-row"});
    if (S.protectedOmitted && !S.readOnly)
        general.append(el("button", {onclick: unlockProtected},
                          xl("Geschützte Parameter anzeigen")));
    const langSel = el("select", {onchange: (e) =>
                                      switchLanguage(e.target.value)},
        ...S.languages.map(l => el("option", {value: l}, l)));
    langSel.value = S.languages.includes(S.lang) ? S.lang : "de";
    general.append(el("span", {}, xl("Sprache") + ":"), langSel);
    if (S.admin) {
        general.append(el("button", {class: "small", onclick: () => {
            S.langPanelOpen = !S.langPanelOpen;
            renderAll();
        }}, xl("Übersetzungen verwalten")));
    }
    general.append(el("span", {class: "spacer"}));
    if (!S.readOnly)
        general.append(el("button", {onclick: async () => {
            await api("/api/end_session", {json: {}});
            location.reload();
        }}, xl("Sitzung beenden")));
    app.append(general);
    if (S.admin && S.langPanelOpen) app.append(renderLangPanel());
    app.append(el("div", {id: "messages"}));

    if (S.readOnly)
        app.append(el("div", {class: "banner readonly"},
            xl("Nur-Lese-Modus: Eine andere Sitzung ist aktiv"),
            el("button", {class: "small", onclick: () => location.reload()},
               xl("Erneut laden"))));
    if (S.factory)
        app.append(el("div", {class: "banner"},
            xl("Das Gerät verwendet noch das werksseitige Standardpasswort"),
            S.admin ? el("button", {class: "small", onclick: exitAdminMode},
                         xl("Admin-Modus verlassen")) : null));

    for (const mid of Object.keys(S.cvv).sort())
        app.append(renderModule(mid));
}

/* ---------- data loading ---------- */
async function loadLang() {
    const r = await api(`/api/schema/${S.lang}`);
    S.xl = r.data || {};
}

async function loadLangList() {
    const r = await api("/api/lang/info");
    if (r.data && r.data.languages) S.languages = r.data.languages;
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
               xl("Verbindung zum Gerät verloren"),
               el("button", {class: "small",
                   onclick: () => location.reload()}, xl("Erneut laden"))));
    }
}

boot();
