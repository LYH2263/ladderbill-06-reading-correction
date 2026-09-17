<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { getJSON, postJSON } from '../api'
import SegmentTable from '../components/SegmentTable.vue'
const route = useRoute()
const data = ref(null)
const corrections = ref([])
const bill = ref(null)
const peak = ref(false)
const load = async () => {
  data.value = await getJSON(`/api/accounts/${route.params.id}`)
  corrections.value = (await getJSON(`/api/corrections?account_id=${route.params.id}`)).items
  const r = data.value.readings[0]
  if (r) bill.value = await postJSON('/api/bill', { account_id: +route.params.id, kwh: r.kwh, peak: !!r.peak, persist: false })
}
onMounted(load)
watch(() => route.params.id, load)
const account = computed(() => data.value?.account)
const pendingOf = (rid) => corrections.value.find((c) => c.reading_id === rid && c.status === 'PENDING')
</script>
<template>
  <div class="page" v-if="account">
    <h1>{{ account.name }}</h1>
    <p class="muted">表号 {{ account.meter_no }} · {{ account.note }}</p>
    <div class="panel">
      <h3>抄表记录</h3>
      <table>
        <thead><tr><th>#</th><th>当前有效电量</th><th>尖峰</th><th>原始快照</th><th>更正</th><th></th></tr></thead>
        <tbody>
          <tr v-for="r in data.readings" :key="r.id">
            <td>{{ r.id }}</td>
            <td><strong>{{ r.kwh }}</strong> kWh</td>
            <td>{{ r.peak ? '是' : '否' }}</td>
            <td>
              <span v-if="r.original_kwh != null" class="muted" title="首次确认更正前的只读快照">{{ r.original_kwh }} kWh</span>
              <span v-else class="muted">—</span>
            </td>
            <td>
              <span v-if="pendingOf(r.id)" class="badge-pending">待确认 #{{ pendingOf(r.id).id }}</span>
              <span v-else class="muted">—</span>
            </td>
            <td><router-link :to="`/corrections?reading_id=${r.id}`">申请更正</router-link></td>
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
.badge-pending { border: 1px solid #e6a817; color: #e6a817; padding: 0.1rem 0.5rem; border-radius: 999px; font-size: 0.8rem; }
</style>
