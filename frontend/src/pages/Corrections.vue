<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { api } from '../api'

const route = useRoute()
const readings = ref([])
const selectedId = ref(null)
const chain = ref(null)
const error = ref('')
const loading = ref(false)

// apply form
const form = ref({ new_kwh: null, new_peak: false, reason: '', note: '' })
const lastRerun = ref(null)

const selectedReading = computed(() => readings.value.find((r) => r.id === selectedId.value))

const load = async () => {
  readings.value = (await api.readings()).items
  if (selectedId.value) await loadChain(selectedId.value)
}

const loadChain = async (id) => {
  selectedId.value = id
  chain.value = await api.chain(id)
  const r = chain.value.reading
  form.value.new_kwh = r.kwh
  form.value.new_peak = !!r.peak
  lastRerun.value = null
}

const flash = (msg) => {
  error.value = msg
  setTimeout(() => (error.value = ''), 4000)
}

const submitCorrection = async () => {
  if (!selectedId.value) return
  loading.value = true
  error.value = ''
  try {
    await api.createCorrection({
      reading_id: selectedId.value,
      new_kwh: Number(form.value.new_kwh),
      new_peak: form.value.new_peak,
      reason: form.value.reason,
      note: form.value.note || null,
    })
    form.value.reason = ''
    form.value.note = ''
    await load()
  } catch (e) {
    flash(parseErr(e))
  } finally {
    loading.value = false
  }
}

const confirm = async (id) => {
  loading.value = true
  error.value = ''
  try {
    await api.confirmCorrection(id)
    await load()
  } catch (e) {
    flash(parseErr(e))
  } finally {
    loading.value = false
  }
}

const rerun = async () => {
  if (!selectedId.value) return
  loading.value = true
  error.value = ''
  try {
    lastRerun.value = await api.rerun(selectedId.value)
    await loadChain(selectedId.value)
  } catch (e) {
    flash(parseErr(e))
  } finally {
    loading.value = false
  }
}

const parseErr = (e) => {
  try {
    const j = JSON.parse(e.message)
    return j.detail || e.message
  } catch {
    return e.message
  }
}

const statusLabel = (s) => (s === 'confirmed' ? '已确认' : s === 'pending' ? '待确认' : s)
const peakLabel = (v) => (v ? '尖峰' : '平段')

onMounted(async () => {
  await load()
  const qid = Number(route.query.reading)
  if (qid && readings.value.some((r) => r.id === qid)) await loadChain(qid)
})
</script>

<template>
  <div class="page corr-page">
    <h1>抄表更正单</h1>
    <p v-if="error" class="err">{{ error }}</p>

    <div class="corr-grid">
      <div class="panel">
        <h3>抄表（当前有效电量）</h3>
        <table>
          <thead>
            <tr><th>#</th><th>户号</th><th>账期</th><th>当前电量</th><th>状态</th><th></th></tr>
          </thead>
          <tbody>
            <tr v-for="r in readings" :key="r.id" :class="{ active: r.id === selectedId }">
              <td>{{ r.id }}</td>
              <td>{{ r.account_id }}</td>
              <td>{{ r.period || '—' }}</td>
              <td>
                <strong>{{ r.kwh }}</strong>
                <span v-if="r.is_corrected" class="muted"> （原始 {{ r.original_kwh }}）</span>
              </td>
              <td>
                <span class="badge pending" v-if="r.has_pending_correction">待确认 #{{ r.pending_correction_id }}</span>
                <span class="badge confirmed" v-else-if="r.is_corrected">已更正 #{{ r.last_correction_id }}</span>
                <span class="muted" v-else>正常</span>
              </td>
              <td><a href="#" @click.prevent="loadChain(r.id)">链条/操作</a></td>
            </tr>
          </tbody>
        </table>
      </div>

      <div v-if="chain && selectedReading" class="panel">
        <h3>
          抄表 #{{ selectedReading.id }} 审计链
          <span class="muted">账期 {{ selectedReading.period || '—' }}</span>
        </h3>

        <div class="kv">
          <div><span class="muted">当前有效电量</span><strong class="hero-num" style="font-size:1.4rem">{{ selectedReading.kwh }}</strong> kWh · {{ peakLabel(selectedReading.peak) }}</div>
          <div v-if="selectedReading.is_corrected"><span class="muted">只读原始快照</span>{{ selectedReading.original_kwh }} kWh · {{ peakLabel(selectedReading.original_peak) }}</div>
        </div>

        <!-- 再测入口：无待确认时可用 -->
        <div class="rerun-row">
          <button :disabled="selectedReading.has_pending_correction || loading" @click="rerun">
            基于当前有效电量再测
          </button>
          <span v-if="selectedReading.has_pending_correction" class="muted">存在待确认更正，确认前不得再测</span>
          <span v-else-if="!selectedReading.is_corrected" class="muted">该抄表尚无已确认更正，可按当前值再测</span>
          <span v-else class="ok">已确认更正，可基于新电量再测（旧运行保留）</span>
        </div>
        <p v-if="lastRerun" class="ok">
          新运行 #{{ lastRerun.run_id }}：{{ lastRerun.kwh }} kWh，合计 ¥{{ lastRerun.total }}
        </p>

        <!-- 发起更正申请 -->
        <div class="sub">
          <h4>发起更正申请</h4>
          <div v-if="selectedReading.has_pending_correction" class="muted">
            该抄表已有待确认更正单 #{{ selectedReading.pending_correction_id }}，请先处理。
          </div>
          <div v-else class="form-grid">
            <label>新电量(kWh)
              <input type="number" min="0" step="1" v-model.number="form.new_kwh" />
            </label>
            <label class="inline"><input type="checkbox" v-model="form.new_peak" /> 尖峰</label>
            <label>更正原因 <input type="text" v-model="form.reason" placeholder="如：估抄改实抄" /></label>
            <label>备注 <input type="text" v-model="form.note" /></label>
            <button :disabled="loading || !form.reason" @click="submitCorrection">提交申请（待确认）</button>
          </div>
        </div>

        <!-- 更正单链 -->
        <div class="sub">
          <h4>更正单（{{ chain.corrections.length }}）</h4>
          <div v-if="!chain.corrections.length" class="muted">暂无更正单。</div>
          <div v-for="c in chain.corrections" :key="c.id" class="corr-card">
            <div class="corr-head">
              <strong>#{{ c.id }}</strong>
              <span class="badge" :class="c.status">{{ statusLabel(c.status) }}</span>
              <span class="muted">{{ c.created_at }}</span>
              <span v-if="c.supersedes_correction_id" class="muted">
                接续 #{{ c.supersedes_correction_id }}
              </span>
              <button
                v-if="c.status === 'pending'"
                :disabled="loading"
                @click="confirm(c.id)"
              >确认</button>
            </div>
            <div class="kv-small">
              <span>{{ c.old_kwh }} → <strong>{{ c.new_kwh }}</strong> kWh</span>
              <span class="muted">{{ peakLabel(c.old_peak) }} → {{ peakLabel(c.new_peak) }}</span>
              <span>原因：{{ c.reason }}</span>
              <span v-if="c.note" class="muted">备注：{{ c.note }}</span>
            </div>
            <ul class="audit">
              <li v-for="a in c.audit" :key="a.id">
                <code>{{ a.created_at }}</code>
                <em>{{ a.event === 'created' ? '发起' : a.event === 'confirmed' ? '确认' : a.event }}</em>
                <span class="muted">{{ a.detail ? JSON.stringify(a.detail) : '' }}</span>
              </li>
            </ul>
          </div>
        </div>

        <!-- 运行历史 -->
        <div class="sub">
          <h4>测算运行（{{ chain.runs.length }}，旧运行不覆盖）</h4>
          <table>
            <thead><tr><th>#</th><th>类型</th><th>输入电量</th><th>结果</th><th>时间</th></tr></thead>
            <tbody>
              <tr v-for="rn in chain.runs" :key="rn.id">
                <td>{{ rn.id }}</td>
                <td>{{ rn.kind }}</td>
                <td>{{ tryKwh(rn.input_json) }}</td>
                <td>{{ tryTotal(rn.result_json) }}</td>
                <td class="muted">{{ rn.created_at }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
function parse(s) { try { return JSON.parse(s) } catch { return {} } }
export default {
  methods: {
    tryKwh: (s) => parse(s).kwh ?? '—',
    tryTotal: (s) => {
      const r = parse(s)
      return r.total != null ? `¥${r.total}` : '—'
    },
  },
}
</script>

<style scoped>
.corr-grid { display: grid; grid-template-columns: minmax(320px, 1fr) minmax(380px, 1.2fr); gap: 1rem; align-items: start; }
tr.active { background: color-mix(in srgb, var(--accent) 12%, transparent); }
.badge { padding: 0.1rem 0.45rem; border-radius: 999px; font-size: 0.78rem; border: 1px solid var(--muted); }
.badge.pending { color: #ffd36b; border-color: #ffd36b; }
.badge.confirmed { color: var(--accent); border-color: var(--accent); }
.kv { display: flex; gap: 2rem; flex-wrap: wrap; margin: 0.5rem 0 1rem; }
.rerun-row { display: flex; align-items: center; gap: 0.75rem; flex-wrap: wrap; margin-bottom: 0.5rem; }
button:disabled { opacity: 0.45; cursor: not-allowed; }
.ok { color: var(--accent); }
.err { color: #ff8b8b; }
.sub { margin-top: 1.1rem; border-top: 1px solid color-mix(in srgb, var(--muted) 30%, transparent); padding-top: 0.8rem; }
.form-grid { display: grid; gap: 0.5rem; }
.form-grid label.inline { display: flex; align-items: center; gap: 0.4rem; }
.corr-card { border: 1px solid color-mix(in srgb, var(--muted) 35%, transparent); border-radius: 10px; padding: 0.6rem 0.8rem; margin-bottom: 0.7rem; }
.corr-head { display: flex; align-items: center; gap: 0.6rem; flex-wrap: wrap; }
.corr-head button { margin-left: auto; }
.kv-small { display: flex; gap: 1rem; flex-wrap: wrap; margin: 0.4rem 0; font-size: 0.92rem; }
.audit { margin: 0.3rem 0 0; padding-left: 1.1rem; }
.audit li { font-size: 0.8rem; margin: 0.15rem 0; }
.audit code { color: var(--muted); margin-right: 0.4rem; }
</style>
