<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { getJSON, postJSON } from '../api'
import SegmentTable from '../components/SegmentTable.vue'
const route = useRoute()
const data = ref(null)
const bill = ref(null)
const peak = ref(false)
const load = async () => {
  data.value = await getJSON(`/api/accounts/${route.params.id}`)
  const r = data.value.readings[0]
  if (r) bill.value = await postJSON('/api/bill', { account_id: +route.params.id, kwh: r.kwh, peak: !!r.peak, persist: false })
}
onMounted(load)
watch(() => route.params.id, load)
const account = computed(() => data.value?.account)
</script>
<template>
  <div class="page" v-if="account">
    <h1>{{ account.name }}</h1>
    <p class="muted">表号 {{ account.meter_no }} · {{ account.note }}</p>

    <div class="panel">
      <h3>抄表记录</h3>
      <table>
        <thead>
          <tr><th>#</th><th>账期</th><th>当前有效电量</th><th>尖峰</th><th>原始快照</th><th>更正状态</th><th></th></tr>
        </thead>
        <tbody>
          <tr v-for="r in data.readings" :key="r.id">
            <td>{{ r.id }}</td>
            <td>{{ r.period || '—' }}</td>
            <td><strong>{{ r.kwh }}</strong></td>
            <td>{{ r.peak ? '尖峰' : '平段' }}</td>
            <td class="muted">{{ r.is_corrected ? `${r.original_kwh}（只读）` : '—' }}</td>
            <td>
              <span v-if="r.has_pending_correction" class="badge pending">待确认 #{{ r.pending_correction_id }}</span>
              <span v-else-if="r.is_corrected" class="badge confirmed">已确认 #{{ r.last_correction_id }}</span>
              <span v-else class="muted">正常</span>
            </td>
            <td><router-link :to="`/corrections?reading=${r.id}`">更正/链条</router-link></td>
          </tr>
        </tbody>
      </table>
    </div>

    <div class="panel">
      <h3>最近抄表试算</h3>
      <label><input type="checkbox" v-model="peak" @change="bill = null" /> 尖峰</label>
      <button @click="load">刷新</button>
      <p v-if="bill">合计 <strong class="hero-num" style="font-size:1.5rem">¥{{ bill.total }}</strong></p>
      <SegmentTable :rows="bill?.segments || []" />
    </div>
  </div>
</template>

<style scoped>
.badge { padding: 0.1rem 0.45rem; border-radius: 999px; font-size: 0.78rem; border: 1px solid var(--muted); }
.badge.pending { color: #ffd36b; border-color: #ffd36b; }
.badge.confirmed { color: var(--accent); border-color: var(--accent); }
</style>
