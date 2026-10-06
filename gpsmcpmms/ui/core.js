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

/* GPSMCPMMS config-editor core: everything about the editor that is not
 * a matter of design.
 *
 * What a value is, whether it is valid, which fields are on screen and which
 * an unmet rule has switched off, what the device says about a host or a
 * path, how a module is saved -- none of that changes when the editor is
 * drawn differently, and all of it is in here. What is not in here is a
 * single element: this file never touches the document.
 *
 * It belongs to the library and is served from the package itself, at
 * /core.js, never from ui_dir. A deployment that brings its own app.html,
 * app.css and app.js therefore still gets every correction made in here
 * with the next upgrade, and cannot fall behind the device it talks to.
 *
 * A design loads this file first and then builds on what it declares. It
 * never speaks to the device itself: every request there is goes out from
 * here.
 *
 *   state      S
 *   small      xl, deepCopy, getIn, setIn, api, authHeaders
 *   values     composeValue, scaleOut, scaleIn, inRange, validValue,
 *              hexOfColor, colorOfHex
 *   structure  enumArgOf, relevanceHolds, visibleChildren, hasVisibleContent,
 *              memberLabel, resolveWithPaths, takenElsewhere,
 *              pathMatchesPattern, usedEnumValuesIn, checkModuleLists,
 *              collectUnsetBooleans
 *   members    standaloneKeysOf, memberIsLocked, memberRepeatsKey,
 *              memberLacksKey
 *   device     fetchEnumOptions, fetchHint, pendingFilesFor,
 *              flushPendingFiles, PROBE_TYPES, probeValue, captureValue,
 *              runTest, wakeModule, loadLangList, loadLang, reloadData,
 *              refreshStatus
 *   findings   allFindings, findingsUnder, worstLevel, FINDING_RANK
 *   saving     saveObstacle, unsetBooleans, submitModule
 *   session    takeOverWith, setPassword, endSession
 *   languages  useLanguage, langName, isLangCode, fetchTemplate,
 *              sendTranslation, targetFromFileName, RTL_LANGS
 *   wording    editorTitle
 *   told       onNotify, onReload
 *
 * The editing token lives ONLY in this runtime memory (spec 4.8). */
"use strict";

const S = {
    token: null, readOnly: false, admin: false, factory: false,
    // what each module last said about itself, keyed by module id: a list
    // of findings, each {text, level, path} -- see allFindings()
    moduleStatus: {},
    // what each module is doing at this moment, keyed by module id, as far
    // as it says; and whose the editing session is: "valid" for this page's
    // own, "other", or "none". Both age -- see refreshStatus().
    state: {},
    session: null,
    dormant: {},             // module id -> label, admin only
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
    coverage: null,          // {total, done:{lang:n}}; admins only
    orphans: null,           // lang -> keys nothing registers; admins only
    edit: {},                // moduleId -> working value (deep copy)
    dirty: {},               // moduleId -> bool
    adopted: {},             // moduleId -> Set of likely_val fields filled in
    enums: {},               // dump path -> {values}|{error}|{pending}
    hints: {},               // dump path -> {text, at}|{error}|{pending}
    pendingFiles: {},        // dump path -> [{name, file}] chosen, not yet sent
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

function authHeaders() {
    const h = {"X-GPSMCPMMS-Api": "1"};
    if (S.token) h["X-GPSMCPMMS-Token"] = S.token;
    return h;
}

/* ---------- what a design is told ----------
   Two things happen in here that a design has to hear about, and neither can
   be a return value: a failure met halfway through a conversation with the
   device, and the moment the tree on screen stops being the tree there is.

   notify() carries the first. What is said is already in the reader's
   language; `cls` is "info", "ok" or "error". Where and how long it shows is
   the design's business -- a bar above the form, a toast, a line beside the
   field -- so nothing in this file draws it.

   The second is for whatever a design keeps about the tree it drew: which row
   of a list is selected, which record is half edited. reloadData() replaces
   every value those were about, and they have to go with them. */
let notifier = null;
const reloadListeners = [];
function onNotify(fn) { notifier = fn; }
function notify(text, cls = "info") { if (notifier) notifier(text, cls); }
function onReload(fn) { reloadListeners.push(fn); }

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

/* 'values_for' names the field whose draft value the provider is given, and
   `ownKeys` is the path of the field doing the naming. A plain name is a
   sibling in the same record; each leading '^' steps one level further out,
   which is how a list member reaches past its own list -- the members of a
   help chain are offered the contacts of that chain's category, and the
   category stands beside the list, not in it.

   Unset means null, not "no argument": the provider is meant to be able to
   tell the two apart. Out of reach -- more '^' than there is path, which
   happens inside a record the navigator renders on its own -- is null too;
   there is nothing truthful to send. */
function enumArgOf(cons, container, ownKeys) {
    const spec = cons && cons.one_of_for;
    if (spec === undefined) return undefined;
    const name = spec.replace(/^\^+/, "");
    const cut = ownKeys.length - 1 - (spec.length - name.length);
    if (cut < 0) return null;
    return getIn(container, ownKeys.slice(0, cut).concat(name)) ?? null;
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

function hexOfColor(v) {
    if (!Array.isArray(v)) return "#000000";
    return "#" + v.map(x => (x || 0).toString(16).padStart(2, "0")).join("");
}
function colorOfHex(h) {
    return [1, 3, 5].map(i => parseInt(h.slice(i, i + 2), 16));
}

/* ---------- dynamic enums (spec 4.9.1) ---------- */
/* `arg` is the current value of the sibling a 'values_for' declaration named,
   or undefined where none was declared. It is remembered beside the options,
   because that is what says whether they are still the answer to the question
   being asked -- and without it every render would ask again, and every
   answer would render again. */
async function fetchEnumOptions(path, rerender, arg, refresh) {
    S.enums[path] = {pending: true, arg};
    let url = `/api/config/enum-options?path=${encodeURIComponent(path)}`;
    if (arg !== undefined)
        url += `&arg=${encodeURIComponent(JSON.stringify(arg))}`;
    // Only the button says this. Drawing the field asks what the device
    // knows; the button asks it to look again, and looking may cost
    // something nobody ordered by opening a group.
    if (refresh) url += "&refresh=1";
    const r = await api(url);
    S.enums[path] = (r.data && r.data.values) ? {values: r.data.values, arg}
                  : {error: (r.data && r.data.error) || xl("No answer from the device."),
                     arg};
    // xl() on a string the device sent: the library's own failure messages are
    // registered keys, and a text the hosting application invented falls
    // through to itself. Rendering it raw left the library's own German --
    // and later English -- standing in a Turkish editor.
    if (S.enums[path].error) notify(xl(S.enums[path].error), "error");
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

/* ---------- uploading into a 'file' parameter ---------- */
/* Choosing a file does not transfer it. It joins the options and gets
   selected, and nothing leaves the browser until the module is saved -- so a
   file parameter behaves like every other field, where nothing is committed
   until Save and Undo really does undo. Sending it at once also wrote
   to the device on the strength of a click that the user might never confirm. */
function pendingFilesFor(path) {
    return S.pendingFiles[path] || (S.pendingFiles[path] = []);
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
                // xl() for the reason fetchEnumOptions gives: every refusal
                // of a file is a key, and shown raw it read in English -- or
                // "Abgelehnt", in German -- whatever language was chosen
                notify(`${xl("Invalid file")}: ${name}: ${xl(err)}`, "error");
                return false;
            }
        }
        delete S.pendingFiles[path];
        delete S.enums[path];      // the options must be asked for again
    }
    return true;
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
        return notify(`${xl("Check failed")}: ` +
                   `${d.error || xl("No answer from the device.")}`,
                   "error");
    const [text, level] = verdict(d);
    const refused = level === "error";
    const changed = refused !== !!S.probeBad[node.path];
    if (refused) S.probeBad[node.path] = text;
    else delete S.probeBad[node.path];
    notify(text, level);
    // without the re-render the marking would never appear; the message
    // survives it (see msg)
    if (changed && rerender) rerender();
}

/* Which children of a dict actually make it onto the screen: the hidden ones
   and those an unmet relevance rule switches off never do. A protected subtree
   is not even in the dump outside admin mode, so the same walk answers "is
   there anything here at all" -- see hasVisibleContent -- and "which lists
   must Save hold to their minimum" -- see checkModuleLists. */
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

/* What a member reads as in the table. What is stored is the value; for an
   enum that is an identifier, and a column of identifiers tells nobody which
   contact stands in which place. The options may not have arrived yet -- the
   field beside the table is what asks for them -- and until they do the raw
   value is still better than a blank. */
function memberLabel(tpl, v) {
    const cons = tpl.constraints || {};
    if (cons.one_of === undefined) return String(v);
    if (Array.isArray(cons.one_of)) {
        const hit = cons.one_of.find(o => o.value === v);
        return hit ? (hit.verbatim ? hit.label : xl(hit.label)) : String(v);
    }
    const values = (S.enums[tpl.path] || {}).values;
    const o = values && values[v];
    if (!o) return String(v);
    return o.verbatim ? (o.label || String(v)) : xl(o.label || String(v));
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

function usedEnumValuesIn(list, exceptIdx, prop) {
    const used = new Set();
    list.forEach((rec, i) => {
        if (i !== exceptIdx && rec && rec[prop] !== null &&
                rec[prop] !== undefined)
            used.add(rec[prop]);
    });
    return used;
}

/* ---------- what holds for a member of a list of records ----------
   Asked of a draft before it is applied, wherever and however a design lets
   a record be edited: `idx` is the member's place in `list`, or the list's
   length for one that is not in it yet. */

/* standalone unique keys constrain the enum options of other rows */
function standaloneKeysOf(cons) {
    return (cons.keys || []).filter(g => g.length === 1).map(g => g[0]);
}

/* A record that carries its own protection (spec 4.4 knows only the declared
   sort), seen by a session without the password: it is shown -- a chain has
   to be able to name the contact it calls -- and nothing in it can be
   touched. Read off the stored record and not off the draft, or clearing the
   checkbox would unlock the record it protects. */
function memberIsLocked(cons, list, idx) {
    return !S.admin && !!cons.protected_by && idx < list.length &&
           !!(list[idx] || {})[cons.protected_by];
}

/* As long as the draft repeats a member that already exists, applying it
   would only hand the backend something it is going to drop again. `ctx`
   carries where the record sits (memberKeys) and the distinct_values rules
   owned further up (distinctScopes). */
function memberRepeatsKey(cons, list, idx, draft, ctx) {
    const standalone = standaloneKeysOf(cons);
    return Object.keys(draft || {}).some((key) => {
        const value = draft[key];
        if (value === null || value === undefined || value === "") return false;
        return (standalone.includes(key) &&
                usedEnumValuesIn(list, idx, key).has(value)) ||
               takenElsewhere(ctx, ctx.memberKeys.concat([key])).has(value);
    });
}

/* A member is known by its keys, and one that is not known by anything has
   no business in the list: it would take a place, count towards the list's
   size, and read as a finished row while whoever loads it later has to guess
   what it was meant to be. The backend refuses it too -- stopping it here
   saves the round trip and, more to the point, says so while the field that
   is empty is still on screen.

   Only the keys. Everything else in the member may stay open; nothing says
   the whole record has to be settled in one sitting. */
function memberLacksKey(cons, draft) {
    return (cons.keys || []).some(group => group.some(key => {
        const value = (draft || {})[key];
        return value === null || value === undefined || value === "";
    }));
}

/* ---------- what a save is held to (spec 4.5) ---------- */
/* Structural validation before saving: list minimum sizes, at every depth.

   A list inside a list member -- the contacts of one help chain, say -- used
   to be passed over: the walk stopped at a list's own length and never looked
   into its members, so a member whose own list was too short went to the
   device without a word. The device takes it, because partial values are
   valid there; the minimum is enforced here or nowhere.

   `trail` says which member is meant: the label of every list on the way
   down, with the position of the member taken -- the number its position
   field shows, so it can be typed straight in.

   Only what is on screen is held to its minimum: the walk takes the children
   visibleChildren() lets through, judged by the value of the dict they sit
   in -- inside a list member, by that member. A list that is hidden, or that
   an unmet relevance rule has switched off, can be neither seen nor filled,
   and a refusal naming it left nothing to do but give up the whole module.
   The device agrees about the second kind: a subtree whose relevance does
   not hold counts as ready there. */
function checkModuleLists(node, value, focusErr, trail = []) {
    if (node.item_template) {
        const list = value || [];
        const label = `"${xl(node.ui.label || node.path)}"`;
        if (list.length < node.constraints.min_size) {
            focusErr(`${xl("Too few entries in")} ` +
                     trail.concat([label]).join(" › "));
            return false;
        }
        return list.every((member, i) => checkModuleLists(
            node.item_template, member, focusErr,
            trail.concat([`${label} ${i + 1}`])));
    }
    for (const [key, child] of visibleChildren(node, value, [])) {
        if (!checkModuleLists(child, value ? value[key] : null, focusErr,
                              trail))
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

/* ---------- saving a module ----------
   The three steps of a save, apart, because what stands between them is a
   design's to say: how a refusal is shown, how the reader is asked about the
   booleans nobody answered, what the page does once the device has spoken.

   saveObstacle() names what stops a save before anything is sent, or returns
   null. unsetBooleans() lists the answers still owed; a design asks, and
   writes `false` into S.edit for those it was allowed to. submitModule() then
   sends files and values and reports how it went:

     "files"     an upload was refused; notify() has already said which
     "ended"     the device no longer honours this session's token
     "failed"    the device answered with an error; `detail` carries it
     "rejected"  stored, except for the paths in `rejected`
     "saved"     stored as sent

   After the last two the tree has been loaded afresh. */
function saveObstacle(mid) {
    let failure = null;
    if (!checkModuleLists(S.cvv[mid], S.edit[mid], (m) => failure = m))
        return failure;
    // What the device rejected does not go to the device. Here rather than
    // while typing: there it is only marked, so the typo stays visible and
    // correctable -- it is not taken away.
    const refused = Object.keys(S.probeBad)
                          .filter(p => p === mid || p.startsWith(mid + "."));
    if (refused.length)
        return `${xl("Apply failed")}: ` +
            refused.map(p => `${p.split(".").pop()} (${S.probeBad[p]})`)
                   .join(", ");
    return null;
}

function unsetBooleans(mid) {
    const found = [];
    collectUnsetBooleans(S.cvv[mid], S.edit, [mid], found);
    return found;
}

async function submitModule(mid) {
    // the files first: a value naming a file the device does not have is
    // worse than not saving at all, so a refused upload abandons the save
    if (!await flushPendingFiles(mid)) return {outcome: "files"};
    const r = await api("/api/config/update",
        {json: {module: mid, value: S.edit[mid]}});
    // 401 is the device answering and refusing the token. The session has
    // ended -- taken over, or timed out -- and the reason is in the device's
    // log. There is no way back but a fresh session, and the password with
    // it: what makes somebody an administrator is the password, and it is
    // nowhere kept to be offered again.
    if (r.status === 401) return {outcome: "ended"};
    if (r.status !== 200)
        return {outcome: "failed",
                detail: (r.data && r.data.error) || r.status};
    if (r.data.module_status) S.moduleStatus = r.data.module_status;
    if (r.data.dormant) S.dormant = r.data.dormant;
    const rejected = r.data.rejected;
    await reloadData();
    return {outcome: rejected.length > 0 ? "rejected" : "saved", rejected};
}

/* ---------- findings ----------
   What the modules have to report, for a design to put wherever it puts such
   things: all above the form, each beside what it is about, a count at the
   door of the place to go to.

   `text` is a key and wants xl(). `level` is "error", "warning" or "info" --
   FINDING_RANK puts them in that order. `path` is where the finding points,
   and null where the module named no place; such a finding is about its
   module as a whole, which is how findingsUnder() files it.

   The order within a module is the module's own and is kept: it said the
   first thing first. */
const FINDING_RANK = {error: 0, warning: 1, info: 2};

function allFindings() {
    const out = [];
    for (const mid of Object.keys(S.moduleStatus).sort())
        for (const f of S.moduleStatus[mid])
            out.push({module: mid, text: f.text, level: f.level,
                      path: f.path || null});
    return out;
}

/* Those about `path` or anything below it. A module's id is a path too. */
function findingsUnder(path) {
    return allFindings().filter((f) => {
        const at = f.path || f.module;
        return at === path || at.startsWith(path + ".");
    });
}

/* The most serious level among `findings`, or null for none. */
function worstLevel(findings) {
    let worst = null;
    for (const f of findings)
        if (worst === null || FINDING_RANK[f.level] < FINDING_RANK[worst])
            worst = f.level;
    return worst;
}

/* ---------- how things stand right now ----------
   What the modules are doing, what they have found and whose the session is
   are all true only for a while, and nothing tells the page when they stop
   being so. A design that wants to stay true asks again from time to time --
   how often, and whether at all while nobody is looking, is its to decide.

   Asking costs the device nothing it would mind and, deliberately, changes
   nothing there: no session is opened by it and none is kept alive, so a
   page left open overnight does not hold the write lock by having watched.

   Returns true where something is different from what S held, false where
   nothing is, and null where the device did not answer -- in which case S is
   left as it was, because "no answer" is not "nothing to report". */
async function refreshStatus() {
    let r = null;
    try { r = await api("/api/status"); } catch (e) { return null; }
    if (r.status !== 200 || !r.data) return null;
    const now = {moduleStatus: r.data.module_status || {},
                 state: r.data.state || {},
                 session: r.data.session};
    const was = JSON.stringify({moduleStatus: S.moduleStatus, state: S.state,
                                session: S.session});
    Object.assign(S, now);
    if (typeof r.data.lock_free_in === "number")
        S.lockFreeIn = r.data.lock_free_in;
    return JSON.stringify(now) !== was;
}

/* ---------- asking the device to do something ----------
   Each of these is one request, and each says how it went in words a design
   can act on without knowing what the device answered with. */

/* value capture for backend_provided params (spec 4.9.3). Only one capture
   may ever be outstanding -- a single backend event would otherwise land in
   whichever field happened to ask first -- so a design keeps everything else
   still until this returns. What comes back is the device's own answer:
   {value}, {timeout: true} or {error}; null where there was none. */
async function captureValue(path) {
    try {
        const r = await api(
            `/api/value/capture?path=${encodeURIComponent(path)}`);
        return r.data;
    } catch (e) {
        return null;        // device unreachable
    }
}

/* Three outcomes, not two: a test routine that returns "false" comes back
   with status 200, and "Successful: false" contradicted itself. `clean` says
   no more than that the routine ran without error -- whether the right ring
   tone sounded is decided by whoever listened. `error` is what the device
   handed back where the test never started, and is written in no language of
   this house. */
async function runTest(path, value) {
    const r = await api("/api/config/test", {json: {path, value}});
    const started = r.status === 200;
    return {started, clean: started && !!r.data.result,
            error: started ? null : ((r.data && r.data.error) || r.status)};
}

/* A module that has given its parameters up is asked to register them again.
   Registering parameters ends the editing session, so the device issues a
   new token in the same breath; without taking it the next request would
   arrive unauthorized, having done nothing wrong. */
async function wakeModule(mid) {
    const r = await api("/api/config/revive", {json: {module: mid}});
    if (r.status !== 200) return false;
    if (r.data && r.data.token) S.token = r.data.token;
    await reloadData();
    return true;
}

/* ---------- the session ----------
   An editor whose window was closed without ending its session keeps the
   write lock for the rest of the idle timeout. The admin password takes the
   lock back (spec 4.8): "ok", "refused" for a wrong password, "silent" where
   the device did not answer. The password is not carried into the new
   session; protected parameters still need reloadData(passwd). */
async function takeOverWith(passwd) {
    const r = await api("/api/session/takeover", {json: {passwd}});
    if (r.status !== 200 || !r.data || !r.data.token)
        return r.status === 403 ? "refused" : "silent";
    S.token = r.data.token;
    await reloadData();
    return "ok";
}

/* Setting a value does not touch the session, so whoever set the password is
   still an administrator afterwards; the tree is loaded again because the
   finding about the factory password goes with it. */
async function setPassword(neu) {
    const r = await api("/api/config/update",
        {json: {module: "config", value: {ui_passwd: neu}}});
    if (r.status !== 200 || r.data.rejected.length) return false;
    await reloadData();
    return true;
}

async function endSession() {
    await api("/api/end_session", {json: {}});
}

/* ---------- languages ---------- */
async function useLanguage(lang) {
    S.lang = lang;
    localStorage.setItem("gpsmcpmms_lang", lang);
    await loadLang();
}

function isLangCode(code) { return /^[a-z]{2,3}$/.test(code); }

/* Translations are managed by a CSV round-trip (spec 4.5): a template goes
   out, is filled offline, and comes back; the device answers with a report.
   Both ends hand over a file -- {blob}, {report, translated, total} -- or
   {error}, and what becomes of the file is the design's to decide. */
async function fetchTemplate(target, refs) {
    const url = `/api/lang/template?lang=${target}` +
                `&refs=${encodeURIComponent(refs.join(","))}`;
    const resp = await fetch(url, {headers: authHeaders()});
    if (!resp.ok) {
        let err = resp.status;
        try { err = (await resp.json()).error || err; } catch (e) { /**/ }
        return {error: err};
    }
    return {blob: await resp.blob()};
}

async function sendTranslation(file, target, name) {
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
        return {error: err};
    }
    const sent = {report: await resp.blob(),
                  translated: resp.headers.get("X-GPSMCPMMS-Translated"),
                  total: resp.headers.get("X-GPSMCPMMS-Total")};
    if (S.lang === target) await loadLang();
    await loadLangList();
    return sent;
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

function targetFromFileName(file) {
    const stem = file.name.replace(/\.csv$/i, "");
    return /^[a-z]{2,3}$/.test(stem) ? stem.toLowerCase() : null;
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
    S.moduleStatus = r.data.module_status || {};
    S.state = r.data.state || {};
    S.session = r.data.read_only ? "other" : "valid";
    S.dormant = r.data.dormant || {};
    S.protectedOmitted = r.data.protected_omitted;
    S.cvv = r.data.cvv;
    S.edit = {};
    S.dirty = {};
    for (const fn of reloadListeners) fn();
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
