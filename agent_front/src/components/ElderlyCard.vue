<template>
  <!-- 三态卡片：ok=可以换 / no=不行 / contacted=已帮您联系；高度 ≥120px；白字对比度 ≥4.5:1 -->
  <div class="elderly-card" :class="`status-${card.status}`" role="status" :aria-label="ariaText" tabindex="0">
    <span class="icon" aria-hidden="true">
      <svg v-if="card.status === 'ok'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5"/></svg>
      <svg v-else-if="card.status === 'no'" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round"><path d="M18 6 6 18M6 6l12 12"/></svg>
      <svg v-else viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72c.13.96.36 1.9.7 2.81a2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45c.91.34 1.85.57 2.81.7A2 2 0 0 1 22 16.92z"/></svg>
    </span>
    <div class="texts">
      <span class="label">{{ card.label }}</span>
      <span v-if="card.item_title" class="item-title">{{ card.item_title }}</span>
    </div>
    <button
      v-if="card.status === 'ok' && card.item_id"
      class="view-btn"
      type="button"
      aria-label="看看这个物品"
      @click="$emit('view-item', card.item_id)"
    >
      看看这个物品
    </button>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  card: { type: Object, required: true }, // { status, label, item_id?, item_title? }
})
defineEmits(['view-item'])

const ariaText = computed(() =>
  props.card.item_title
    ? `${props.card.label}：${props.card.item_title}`
    : props.card.label,
)
</script>

<style scoped>
.elderly-card {
  display: flex; align-items: center; gap: 20px;
  min-height: 120px; padding: 20px 28px;
  border-radius: 24px; color: #ffffff;
  font-size: 26px;
}
.elderly-card:focus-visible { outline: 4px solid #1a1a1a; outline-offset: 3px; }
.icon { flex: none; width: 48px; height: 48px; }
.icon svg { width: 100%; height: 100%; }
.texts { display: flex; flex-direction: column; gap: 6px; flex: 1; }
.label { font-size: 30px; font-weight: 800; }
.item-title { font-size: 24px; opacity: 0.95; }

.status-ok { background: #1B5E20; }        /* 白字对比度 7.4:1 */
.status-no { background: #B71C1C; }        /* 白字对比度 6.6:1 */
.status-contacted { background: #0D47A1; } /* 白字对比度 8.6:1 */

.view-btn {
  flex: none; min-height: 64px; padding: 0 24px;
  font-size: 24px; font-weight: 700;
  color: #1B5E20; background: #fff; border: none; border-radius: 16px; cursor: pointer;
}
.view-btn:focus-visible { outline: 4px solid #1a1a1a; outline-offset: 3px; }
</style>
