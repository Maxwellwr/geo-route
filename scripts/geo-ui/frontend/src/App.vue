<template>
  <div class="app" :class="{ 'nav-open': menuOpen }">
    <div class="nav-backdrop" @click="menuOpen = false"></div>
    <aside class="sidebar">
      <div class="brand">Geo</div>
      <nav class="group-list">
        <button
          v-for="g in groups"
          :key="g.slug"
          type="button"
          class="group-item"
          :class="{ active: g.slug === slug }"
          :disabled="busy"
          @click="selectGroup(g.slug)"
        >
          <span class="group-line">
            <span class="group-title">{{ g.title }}</span>
            <span v-if="g.description" class="group-desc">{{ g.description }}</span>
          </span>
        </button>
      </nav>
      <div class="sidebar-foot">
        <form v-if="creating" class="create-form" @submit.prevent="onCreateGroup">
          <input
            v-model="newTitle"
            type="text"
            placeholder="Название"
            :disabled="busy"
            autofocus
          />
          <input
            v-model="newDesc"
            type="text"
            placeholder="Описание"
            :disabled="busy"
          />
          <div class="create-actions">
            <button type="submit" class="btn btn-primary" :disabled="busy || !newTitle.trim()">
              Создать
            </button>
            <button type="button" class="btn" :disabled="busy" @click="creating = false">
              Отмена
            </button>
          </div>
        </form>
        <button v-else type="button" class="btn btn-add" :disabled="busy" @click="startCreate">
          + Группа
        </button>
      </div>
    </aside>

    <div class="main">
      <div class="mobile-bar">
        <button
          type="button"
          class="menu-btn"
          :aria-expanded="menuOpen ? 'true' : 'false'"
          aria-label="Группы"
          @click="menuOpen = !menuOpen"
        >
          {{ menuOpen ? "×" : "☰" }}
        </button>
        <span class="mobile-bar-title">{{ current ? current.title : "Geo" }}</span>
      </div>
      <header v-if="current" class="header">
        <div v-if="editingHeader" class="header-edit">
          <input
            v-model="headerTitle"
            type="text"
            class="title-input"
            :disabled="busy"
            @keydown.enter.prevent="onSaveHeader"
          />
          <input
            v-model="headerDesc"
            type="text"
            class="desc-input"
            placeholder="Описание"
            :disabled="busy"
            @keydown.enter.prevent="onSaveHeader"
          />
          <div class="header-actions">
            <button type="button" class="btn btn-primary" :disabled="busy" @click="onSaveHeader">
              Сохранить
            </button>
            <button type="button" class="btn" :disabled="busy" @click="editingHeader = false">
              Отмена
            </button>
          </div>
        </div>
        <div v-else class="header-view">
          <div>
            <h1>{{ current.title }}</h1>
            <p v-if="current.description" class="header-desc">{{ current.description }}</p>
          </div>
          <div class="header-actions">
            <button type="button" class="btn" :disabled="busy" @click="startEditHeader">
              Переименовать
            </button>
            <button type="button" class="btn btn-danger" :disabled="busy" @click="onDeleteGroup">
              Удалить
            </button>
          </div>
        </div>
      </header>
      <div v-else class="header header-empty">Выберите группу или создайте новую</div>

      <div class="sections">
        <template v-if="current">
        <section
          v-for="setName in SETS"
          :key="setName"
          class="card"
          :class="'set-' + setName"
        >
          <h2>{{ setLabel(setName) }}</h2>
          <div class="rows">
            <div
              v-for="e in entriesOf(setName)"
              :key="e.id"
              class="row"
              :class="{ collision: collisionFor(e.value) }"
            >
              <div class="row-main">
                <span class="value">{{ e.value }}</span>
                <span v-if="collisionFor(e.value)" class="hint">
                  {{ collisionText(collisionFor(e.value), { slug, set: setName }) }}
                </span>
              </div>
              <div class="row-actions">
                <button
                  v-for="other in otherSets(setName)"
                  :key="other"
                  type="button"
                  class="btn btn-tiny"
                  :disabled="busy"
                  :title="'Перенести в ' + setLabel(other)"
                  @click="onMoveSet(e, other)"
                >
                  → {{ setShort(other) }}
                </button>
                <select
                  v-if="otherGroups().length"
                  class="move-select"
                  :disabled="busy"
                  @change="onMoveGroup(e, $event)"
                >
                  <option value="">в группу…</option>
                  <option v-for="g in otherGroups()" :key="g.slug" :value="g.slug">
                    {{ g.title }}
                  </option>
                </select>
                <button
                  type="button"
                  class="btn btn-tiny btn-danger"
                  :disabled="busy"
                  title="Удалить"
                  @click="onDeleteEntry(e)"
                >
                  ×
                </button>
              </div>
            </div>
            <div
              class="row row-add"
              :class="{ collision: composeDraft(setName) && collisionFor(composeDraft(setName)) }"
            >
              <div class="add-fields">
                <select
                  class="add-kind"
                  :value="draftKinds[setName]"
                  :disabled="busy || !current"
                  @change="onDraftKindChange(setName, $event.target.value)"
                >
                  <option v-for="k in ADD_KINDS" :key="k.id" :value="k.id">{{ k.label }}</option>
                </select>
                <input
                  :list="tagListId(setName)"
                  :value="drafts[setName]"
                  type="text"
                  class="add-input"
                  :placeholder="addPlaceholder(draftKinds[setName])"
                  :disabled="busy || !current"
                  @input="onDraftInput(setName, $event.target.value)"
                  @keydown.enter.prevent="onAdd(setName)"
                />
              </div>
              <datalist :id="'suggest-' + setName">
                <option v-for="s in tagSuggestions[setName]" :key="s" :value="s" />
              </datalist>
              <span
                v-if="composeDraft(setName) && collisionFor(composeDraft(setName))"
                class="hint"
              >
                {{ collisionText(collisionFor(composeDraft(setName))) }}
              </span>
            </div>
          </div>
        </section>
        </template>
      </div>

      <div
        class="log-panel"
        :class="{ 'log-hidden': logMode === 'hidden', 'log-max': logMode === 'max' }"
        :style="logMode === 'normal' ? { height: logHeight + 'px' } : undefined"
      >
        <div
          v-if="logMode === 'normal'"
          class="log-resizer"
          title="Потянуть — высота панели"
          @pointerdown.prevent="onLogDrag"
        />
        <div class="log-bar">
          <span class="log-bar-title">Применение</span>
          <button
            type="button"
            class="log-btn"
            :title="logMode === 'hidden' ? 'Показать лог' : 'Скрыть лог'"
            @click="toggleLogHidden"
          >
            {{ logMode === 'hidden' ? '▴' : '▾' }}
          </button>
          <button
            type="button"
            class="log-btn"
            :title="logMode === 'max' ? 'Свернуть' : 'На весь экран'"
            @click="toggleLogMax"
          >
            {{ logMode === 'max' ? '❐' : '□' }}
          </button>
        </div>
        <div v-show="logMode !== 'hidden'" ref="logEl" class="log-body" aria-label="лог apply">
          <div v-if="!logLines.length" class="log-empty">лог apply</div>
          <div v-for="(line, i) in logLines" :key="i" class="log-line">{{ line }}</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import { computed, nextTick, onMounted, reactive, ref, watch } from "vue";
import {
  addEntry,
  consumeSse,
  createGroup,
  deleteEntry,
  deleteGroup,
  getEntries,
  getGroups,
  getTags,
  patchEntry,
  patchGroup,
} from "./api.js";

/** Сеты UI. Третий сет — добавить сюда, не в вёрстку. */
const SETS = ["blocked-sites", "only-ru"];
const SET_META = {
  "blocked-sites": { label: "VPN / WireGuard", short: "VPN" },
  "only-ru": { label: "прямой RU", short: "RU" },
};
const ADD_KINDS = [
  { id: "domain", label: "domain" },
  { id: "cidr", label: "ip/cidr" },
  { id: "geosite", label: "geosite" },
  { id: "geoip", label: "geoip" },
];
const ADD_PLACEHOLDERS = {
  domain: "example.com",
  cidr: "1.2.3.4 или 10.0.0.0/8",
  geosite: "youtube",
  geoip: "telegram",
};

const CIDR_RE =
  /^((25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)(\/(3[0-2]|[12]?[0-9]))?$/;

function setLabel(id) {
  return (SET_META[id] && SET_META[id].label) || id;
}

function setShort(id) {
  return (SET_META[id] && SET_META[id].short) || id;
}

function norm(input) {
  const v = (input || "").trim();
  if (!v) return "";
  const lower = v.toLowerCase();
  if (lower.startsWith("geosite:") || lower.startsWith("geoip:")) return lower;
  if (CIDR_RE.test(v)) return v;
  return lower;
}

export default {
  name: "App",
  setup() {
    const groups = ref([]);
    const slug = ref("");
    const entries = ref([]);
    const collisions = ref([]);
    const logLines = ref([]);
    const busy = ref(false);
    const menuOpen = ref(false);
    const creating = ref(false);
    const newTitle = ref("");
    const newDesc = ref("");
    const editingHeader = ref(false);
    const headerTitle = ref("");
    const headerDesc = ref("");
    const drafts = reactive(Object.fromEntries(SETS.map((s) => [s, ""])));
    const draftKinds = reactive(Object.fromEntries(SETS.map((s) => [s, "domain"])));
    const tagSuggestions = reactive(Object.fromEntries(SETS.map((s) => [s, []])));
    const suggestTimers = Object.create(null);
    const suggestSeq = Object.fromEntries(SETS.map((s) => [s, 0]));
    const logEl = ref(null);
    const LOG_H_MIN = 72;
    const LOG_H_DEFAULT = 120;
    const LS_H = "geo-ui-log-height";
    const LS_MODE = "geo-ui-log-mode";

    function readLogHeight() {
      const n = Number(localStorage.getItem(LS_H));
      return Number.isFinite(n) && n >= LOG_H_MIN ? n : LOG_H_DEFAULT;
    }

    function readLogMode() {
      const m = localStorage.getItem(LS_MODE);
      return m === "hidden" || m === "max" || m === "normal" ? m : "normal";
    }

    const logHeight = ref(readLogHeight());
    const logMode = ref(readLogMode());

    function persistLog() {
      localStorage.setItem(LS_H, String(logHeight.value));
      localStorage.setItem(LS_MODE, logMode.value);
    }

    function logMaxHeight() {
      return Math.max(LOG_H_MIN, Math.floor(window.innerHeight * 0.9));
    }

    function onLogDrag(ev) {
      if (logMode.value !== "normal") return;
      const startY = ev.clientY;
      const startH = logHeight.value;
      const maxH = logMaxHeight();
      const move = (e) => {
        const next = startH + (startY - e.clientY);
        logHeight.value = Math.min(maxH, Math.max(LOG_H_MIN, next));
      };
      const up = () => {
        window.removeEventListener("pointermove", move);
        window.removeEventListener("pointerup", up);
        persistLog();
      };
      window.addEventListener("pointermove", move);
      window.addEventListener("pointerup", up);
    }

    function toggleLogHidden() {
      logMode.value = logMode.value === "hidden" ? "normal" : "hidden";
      persistLog();
      if (logMode.value !== "hidden") scrollLog();
    }

    function toggleLogMax() {
      logMode.value = logMode.value === "max" ? "normal" : "max";
      persistLog();
      scrollLog();
    }

    const current = computed(
      () => groups.value.find((g) => g.slug === slug.value) || null,
    );

    function groupTitle(s) {
      const g = groups.value.find((x) => x.slug === s);
      return g ? g.title : s;
    }

    function collisionFor(value) {
      const n = norm(value);
      if (!n) return null;
      return collisions.value.find((c) => c.value === n) || null;
    }

    function collisionText(col, skip) {
      if (!col || !col.hits) return "";
      const fmt = (h) => '"' + groupTitle(h[0]) + '", ' + setLabel(h[1]);
      let parts = col.hits
        .filter((h) => {
          if (!skip) return true;
          return !(h[0] === skip.slug && h[1] === skip.set);
        })
        .map(fmt);
      if (!parts.length) parts = col.hits.map(fmt);
      parts = [...new Set(parts)];
      return "уже в " + parts.join("; ");
    }

    function entriesOf(setName) {
      return entries.value.filter((e) => e.set === setName);
    }

    function otherSets(setName) {
      return SETS.filter((s) => s !== setName);
    }

    function otherGroups() {
      return groups.value.filter((g) => g.slug !== slug.value);
    }

    function addPlaceholder(kind) {
      return ADD_PLACEHOLDERS[kind] || "";
    }

    function stripKindPrefix(raw, kind) {
      const v = (raw || "").trim();
      const lower = v.toLowerCase();
      if (kind === "geosite" && lower.startsWith("geosite:")) return v.slice(8).trim();
      if (kind === "geoip" && lower.startsWith("geoip:")) return v.slice(6).trim();
      return v;
    }

    function composeDraft(setName) {
      const kind = draftKinds[setName] || "domain";
      const raw = stripKindPrefix(drafts[setName], kind);
      if (!raw) return "";
      if (kind === "geosite") return "geosite:" + raw.toLowerCase();
      if (kind === "geoip") return "geoip:" + raw.toLowerCase();
      return raw;
    }

    function tagListId(setName) {
      const kind = draftKinds[setName];
      return kind === "geosite" || kind === "geoip" ? "suggest-" + setName : undefined;
    }

    function clearTagSuggestions(setName) {
      if (suggestTimers[setName]) {
        clearTimeout(suggestTimers[setName]);
        suggestTimers[setName] = undefined;
      }
      suggestSeq[setName] += 1;
      tagSuggestions[setName] = [];
    }

    function queueTagSuggestions(setName) {
      clearTagSuggestions(setName);

      const kind = draftKinds[setName];
      if (kind !== "geosite" && kind !== "geoip") return;

      const query = stripKindPrefix(drafts[setName], kind).toLowerCase();
      if (query.length < 2) return;

      const seq = suggestSeq[setName];
      suggestTimers[setName] = setTimeout(async () => {
        suggestTimers[setName] = undefined;
        try {
          const result = await getTags(kind, query, 30);
          if (
            suggestSeq[setName] === seq &&
            draftKinds[setName] === kind &&
            stripKindPrefix(drafts[setName], kind).toLowerCase() === query
          ) {
            tagSuggestions[setName] = result;
          }
        } catch {
          if (suggestSeq[setName] === seq) tagSuggestions[setName] = [];
        }
      }, 250);
    }

    function onDraftInput(setName, value) {
      drafts[setName] = value;
      queueTagSuggestions(setName);
    }

    function onDraftKindChange(setName, kind) {
      draftKinds[setName] = kind;
      queueTagSuggestions(setName);
    }

    async function scrollLog() {
      await nextTick();
      const el = logEl.value;
      if (el) el.scrollTop = el.scrollHeight;
    }

    function pushLog(line) {
      logLines.value.push(line);
      scrollLog();
    }

    async function refreshGroups() {
      const data = await getGroups();
      groups.value = data.groups || [];
      collisions.value = data.collisions || [];
    }

    async function refreshEntries() {
      if (!slug.value) {
        entries.value = [];
        return;
      }
      const data = await getEntries(slug.value);
      entries.value = data.entries || [];
    }

    async function refresh() {
      await refreshGroups();
      if (slug.value && !groups.value.some((g) => g.slug === slug.value)) {
        slug.value = groups.value[0] ? groups.value[0].slug : "";
      }
      await refreshEntries();
    }

    async function selectGroup(s) {
      slug.value = s;
      editingHeader.value = false;
      menuOpen.value = false;
      await refreshEntries();
    }

    async function runMutation(respPromise) {
      if (busy.value) return undefined;
      busy.value = true;
      try {
        const resp = await respPromise;
        const code = await consumeSse(resp, pushLog);
        pushLog("exit " + code);
        await refresh();
        return code;
      } catch (err) {
        pushLog("error: " + (err && err.message ? err.message : String(err)));
        throw err;
      } finally {
        busy.value = false;
      }
    }

    async function onCreateGroup() {
      const title = newTitle.value.trim();
      if (!title || busy.value) return;
      const before = new Set(groups.value.map((g) => g.slug));
      try {
        const code = await runMutation(
          createGroup({ title, description: newDesc.value.trim() }),
        );
        if (code === undefined) return;
        const created = groups.value.find((g) => !before.has(g.slug));
        if (created) await selectGroup(created.slug);
        creating.value = false;
        newTitle.value = "";
        newDesc.value = "";
      } catch {
        /* logged */
      }
    }

    async function onSaveHeader() {
      if (!slug.value || busy.value) return;
      const title = headerTitle.value.trim();
      if (!title) return;
      const body = {};
      if (current.value && title !== current.value.title) body.title = title;
      const desc = headerDesc.value;
      if (current.value && desc !== (current.value.description || "")) {
        body.description = desc;
      }
      if (!Object.keys(body).length) {
        editingHeader.value = false;
        return;
      }
      try {
        await runMutation(patchGroup(slug.value, body));
        editingHeader.value = false;
      } catch {
        /* logged */
      }
    }

    async function onDeleteGroup() {
      if (!slug.value || busy.value) return;
      const title = current.value && current.value.title;
      if (!window.confirm("Удалить группу «" + title + "»?")) return;
      try {
        await runMutation(deleteGroup(slug.value));
        slug.value = groups.value[0] ? groups.value[0].slug : "";
        await refreshEntries();
      } catch {
        /* logged */
      }
    }

    async function onAdd(setName) {
      const value = composeDraft(setName);
      if (!value || !slug.value || busy.value) return;
      try {
        const code = await runMutation(addEntry(slug.value, { set: setName, value }));
        if (code !== undefined) {
          drafts[setName] = "";
          clearTagSuggestions(setName);
        }
      } catch {
        /* keep draft */
      }
    }

    async function onDeleteEntry(entry) {
      if (!slug.value || busy.value) return;
      try {
        await runMutation(deleteEntry(slug.value, entry.id));
      } catch {
        /* logged */
      }
    }

    async function onMoveSet(entry, setName) {
      if (!slug.value || busy.value) return;
      try {
        await runMutation(patchEntry(slug.value, entry.id, { set: setName }));
      } catch {
        /* logged */
      }
    }

    async function onMoveGroup(entry, event) {
      const target = event.target.value;
      event.target.value = "";
      if (!target || !slug.value || busy.value) return;
      try {
        await runMutation(patchEntry(slug.value, entry.id, { group: target }));
      } catch {
        /* logged */
      }
    }

    function startCreate() {
      creating.value = true;
      newTitle.value = "";
      newDesc.value = "";
    }

    function startEditHeader() {
      if (!current.value) return;
      headerTitle.value = current.value.title;
      headerDesc.value = current.value.description || "";
      editingHeader.value = true;
    }

    watch(
      slug,
      () => {
        for (const s of SETS) {
          if (drafts[s] === undefined) drafts[s] = "";
          if (draftKinds[s] === undefined) draftKinds[s] = "domain";
        }
      },
      { immediate: true },
    );

    onMounted(async () => {
      try {
        await refreshGroups();
        if (groups.value.length) await selectGroup(groups.value[0].slug);
      } catch (err) {
        pushLog("error: " + (err && err.message ? err.message : String(err)));
      }
    });

    return {
      SETS,
      ADD_KINDS,
      groups,
      slug,
      entries,
      collisions,
      logLines,
      busy,
      creating,
      menuOpen,
      newTitle,
      newDesc,
      editingHeader,
      headerTitle,
      headerDesc,
      drafts,
      draftKinds,
      tagSuggestions,
      logEl,
      logHeight,
      logMode,
      onLogDrag,
      toggleLogHidden,
      toggleLogMax,
      current,
      setLabel,
      setShort,
      collisionFor,
      collisionText,
      entriesOf,
      otherSets,
      otherGroups,
      addPlaceholder,
      composeDraft,
      tagListId,
      onDraftInput,
      onDraftKindChange,
      selectGroup,
      onCreateGroup,
      onSaveHeader,
      onDeleteGroup,
      onAdd,
      onDeleteEntry,
      onMoveSet,
      onMoveGroup,
      startCreate,
      startEditHeader,
    };
  },
};
</script>
