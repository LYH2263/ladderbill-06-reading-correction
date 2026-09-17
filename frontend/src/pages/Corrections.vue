<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { getJSON, postJSON } from '../api'

const STATUS_LABEL = { PENDING: '待确认', CONFIRMED: '已确认' }

const route = useRoute()
const accounts = ref([])
const readings = ref([])
const corrections = ref([])
const error = ref('')
const notice = ref('')

// apply form
const accountId = ref(null)
const readingId = ref(null)
const newKwh = ref(0)
const reason = ref('')
const remark = ref('')

// chain view
const chain = ref(null)
// rerun results keyed by correction id
const reruns = ref({})

const accountReadings = computed(() =>
  readings.value.filter((r) => r.account_id === accountId.value),
)
const readingOf = (id) => readings.value.find((r) => r.id === id)
const accountName = (id) => accounts.value.find((a) => a.id === id)?.name ?? `#${id}`
const pendingOf = (rid) =>
  corrections.value.find((c) => c.reading_id === rid && c.status === 'PENDING')

const loadBase = async () => {
  accounts.value = (await getJSON('/api/accounts')).items
  readings.value = (await getJSON('/api/readings')).items
}
const loadCorrections = async () => {
  corrections.value = (await getJSON('/api/corrections')).items
}

const applyQuery = () => {
  const rid = Number(route.query.reading_id)
  if (!rid) return
  const r = readingOf(rid)
  if (!r) return
  accountId.value = r.account_id
  readingId.value = r.id
  newKwh.value = r.kwh
}

onMounted(async () => {
  await loadBase()
  await loadCorrections()
  applyQuery()
})
watch(() => route.query.reading_id, applyQuery)
watch(readingId, (rid) => {
  const r = readingOf(rid)
  if (r) newKwh.value = r.kwh
})

const run = async (fn, okMsg) => {
  error.value = ''
  notice.value = ''
  try {
    await fn()
    if (okMsg) notice.value = okMsg
  } catch (e) {
    error.value = String(e.message || e)
  }
}

const submit = () =>
  run(async () => {
    await postJSON(`/api/readings/${readingId.value}/corrections`, {
      new_kwh: newKwh.value,
      reason: reason.value,
      remark: remark.value || null,
    })
    reason.value = ''
    remark.value = ''
    await loadCorrections()
  }, '更正单已提交，待确认')

const confirm = async (c) =>
  run(async () => {
    await postJSON(`/api/corrections/${c.id}/confirm`)
    // 确认后当前有效电量即时刷新
    await Promise.all([loadBase(), loadCorrections(), chain.value ? openChain(c.reading_id) : null])
  }, `更正单 #${c.id} 已确认，当前有效电量已更新`)

const rerun = async (c) =>
  run(async () => {
    const out = await postJSON(`/api/corrections/${c.id}/rerun`)
    reruns.value = { ...reruns.value, [c.id]: { run_id: out.run.id, total: out.result.total } }
    await loadCorrections()
  }, `已生成新测算运行 #${reruns.value[c.id]?.run_id ?? ''}（历史运行保留）`)

const openChain = async (rid) => {
  chain.value = await getJSON(`/api/readings/${rid}/corrections`)
}
</script>

<template>
  <div class="page">
    <h1>抄表更正</h1>
    <p v-if="error" class="err">{{ error }}</p>
    <p v-if="notice" class="ok-msg">{{ notice }}</p>

    <div class="panel">
      <h3>更正申请</h3>
      <div class="form-row">
        <label>户号
          <select v-model.number="accountId">
            <option :value="null" disabled>选择户号</option>
            <option v-for="a in accounts" :key="a.id" :value="a.id">{{ a.name }}</option>
          </select>
        </label>
        <label>抄表记录
          <select v-model.number="readingId">
            <option :value="null" disabled>选择记录</option>
            <option v-for="r in accountReadings" :key="r.id" :value="r.id">
              #{{ r.id }} · 当前 {{ r.kwh }} kWh{{ r.peak ? ' · 尖峰' : '' }}
            </option>
          </select>
        </label>
        <label>新电量(kWh) <input type="number" v-model.number="newKwh" min="0" step="1" /></label>
        <label>更正原因 <input v-model="reason" placeholder="必填" /></label>
        <label>备注 <input v-model="remark" placeholder="选填" /></label>
        <button :disabled="!readingId || !reason" @click="submit">提交申请</button>
      </div>
      <p v-if="readingId && pendingOf(readingId)" class="warn-msg">
        该记录已有待确认更正单 #{{ pendingOf(readingId).id }}，确认前当前有效电量不变。
      </p>
    </div>

    <div class="panel">
      <h3>更正单</h3>
      <table>
        <thead>
          <tr>
            <th>#</th><th>户号</th><th>抄表</th><th>旧电量 → 新电量</th><th>原因</th>
            <th>状态</th><th>申请时间</th><th>确认时间</th><th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="c in corrections" :key="c.id">
            <td>{{ c.id }}</td>
            <td>{{ accountName(c.account_id) }}</td>
            <td>#{{ c.reading_id }}</td>
            <td>{{ c.old_kwh }} → {{ c.new_kwh }}</td>
            <td>{{ c.reason }}<span v-if="c.remark" class="muted">（{{ c.remark }}）</span></td>
            <td><span class="badge" :class="c.status === 'PENDING' ? 'pending' : 'confirmed'">{{ STATUS_LABEL[c.status] }}</span></td>
            <td class="muted">{{ c.created_at }}</td>
            <td class="muted">{{ c.confirmed_at || '—' }}</td>
            <td class="ops">
              <button v-if="c.status === 'PENDING'" @click="confirm(c)">确认</button>
              <template v-else>
                <button @click="rerun(c)">再测</button>
                <span v-if="reruns[c.id]" class="muted">
                  新运行#{{ reruns[c.id].run_id }} ¥{{ reruns[c.id].total }}
                </span>
                <span v-else-if="c.rerun_id" class="muted">运行#{{ c.rerun_id }}</span>
              </template>
              <a href="javascript:;" @click="openChain(c.reading_id)">链条</a>
            </td>
          </tr>
          <tr v-if="!corrections.length"><td colspan="9" class="muted">暂无更正单</td></tr>
        </tbody>
      </table>
    </div>

    <div v-if="chain" class="panel">
      <h3>更正链条 · 抄表 #{{ chain.reading.id }}</h3>
      <p>
        当前有效电量 <strong class="hero-num" style="font-size:1.4rem">{{ chain.reading.kwh }}</strong> kWh
        <span v-if="chain.reading.original_kwh != null" class="muted">
          · 原始快照 {{ chain.reading.original_kwh }} kWh（只读）
        </span>
        <span v-else class="muted">· 未发生过确认更正</span>
      </p>
      <table>
        <thead>
          <tr><th>#</th><th>旧 → 新</th><th>原因</th><th>状态</th><th>申请</th><th>确认</th><th>再测运行</th></tr>
        </thead>
        <tbody>
          <tr v-for="c in chain.items" :key="c.id">
            <td>{{ c.id }}</td>
            <td>{{ c.old_kwh }} → {{ c.new_kwh }}</td>
            <td>{{ c.reason }}</td>
            <td><span class="badge" :class="c.status === 'PENDING' ? 'pending' : 'confirmed'">{{ STATUS_LABEL[c.status] }}</span></td>
            <td class="muted">{{ c.created_at }}</td>
            <td class="muted">{{ c.confirmed_at || '—' }}</td>
            <td>{{ c.rerun_id ? `#${c.rerun_id}` : '—' }}</td>
          </tr>
          <tr v-if="!chain.items.length"><td colspan="7" class="muted">该记录暂无更正历史</td></tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<style scoped>
.form-row { display: flex; flex-wrap: wrap; gap: 0.9rem; align-items: end; }
.form-row label { display: flex; flex-direction: column; gap: 0.25rem; font-size: 0.85rem; color: var(--muted); }
input[type=number] { width: 7rem; }
select { background: #0d1612; border: 1px solid var(--muted); color: var(--text); padding: 0.35rem 0.5rem; border-radius: 6px; }
.badge { padding: 0.1rem 0.5rem; border-radius: 999px; font-size: 0.8rem; }
.badge.pending { border: 1px solid #e6a817; color: #e6a817; }
.badge.confirmed { border: 1px solid var(--accent); color: var(--accent); }
.ops { display: flex; gap: 0.5rem; align-items: center; }
.err { color: #ff7a7a; }
.ok-msg { color: var(--accent); }
.warn-msg { color: #e6a817; }
button:disabled { opacity: 0.45; cursor: not-allowed; }
</style>
