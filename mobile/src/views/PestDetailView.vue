<template>
  <div class="pest-detail">
    <div v-if="loading" class="loading-wrap">
      <van-loading color="var(--brand)" vertical>{{ t('common.loading') }}</van-loading>
    </div>

    <template v-else-if="pest">
      <div class="card hero">
        <h2 class="pest-name">{{ displayName }}</h2>
        <p class="muted">{{ displayCrop }} · {{ pest.scientific_name || '' }}</p>
      </div>

      <div class="card">
        <p class="card-title">{{ t('pestWiki.symptoms') }}</p>
        <p class="pre-wrap">{{ displaySymptoms || t('pestWiki.noSymptoms') }}</p>
      </div>

      <div class="card">
        <p class="card-title">{{ t('pestWiki.prevention') }}</p>
        <ul v-if="prevention.length" class="prevention-list">
          <li v-for="(item, index) in prevention" :key="index">
            <van-tag v-if="item.category" size="mini" plain>{{ item.category }}</van-tag>
            <span class="pre-wrap">{{ item.measure }}</span>
          </li>
        </ul>
        <p v-else class="muted">{{ t('pestWiki.noPrevention') }}</p>
      </div>

      <div v-if="description" class="card">
        <p class="card-title">{{ t('pestWiki.description') }}</p>
        <p class="pre-wrap">{{ description }}</p>
      </div>

      <div v-if="sources.length" class="card">
        <p class="card-title">{{ t('pestWiki.sources') }}</p>
        <ul class="source-list">
          <li v-for="(url, index) in sources" :key="index">
            <a :href="url" target="_blank" rel="noopener noreferrer">{{ url }}</a>
          </li>
        </ul>
      </div>
    </template>

    <van-empty v-else :description="t('pestWiki.notFound')" />
  </div>
</template>

<script setup>
/** 病害百科详情（移动端，第 260 批）—— 结果页点「查看病害百科」进来 */
import { computed, onMounted, ref } from 'vue';
import { useRoute } from 'vue-router';
import { fetchPestDetail, findPest } from '@/api/pest';
import { useI18n } from '@/i18n';

const route = useRoute();
const { t, locale } = useI18n();

const loading = ref(true);
const pest = ref(null);

const isEnglish = computed(() => String(locale.value || '').startsWith('en'));
const displayName = computed(() => (isEnglish.value ? pest.value?.name_en || pest.value?.name : pest.value?.name) || '');
const displayCrop = computed(() => (isEnglish.value ? pest.value?.crop_type_en || pest.value?.crop_type : pest.value?.crop_type) || '');
const displaySymptoms = computed(() => (isEnglish.value ? pest.value?.symptoms_en || pest.value?.symptoms : pest.value?.symptoms) || '');
const description = computed(() => (isEnglish.value ? pest.value?.description_en || pest.value?.description : pest.value?.description) || '');
const prevention = computed(() => {
  const rows = Array.isArray(pest.value?.prevention_methods) ? pest.value.prevention_methods : [];
  return rows
    .map((row) => ({
      category: row.category || '',
      measure: (isEnglish.value ? row.measure_en || row.measure : row.measure) || '',
    }))
    .filter((row) => row.measure);
});
const sources = computed(() => (Array.isArray(pest.value?.sources) ? pest.value.sources : []));

onMounted(async () => {
  const keyword = String(route.params.keyword || route.query.keyword || '').trim();
  try {
    let hit = await findPest(keyword);
    if (!hit?.id) hit = await findPest(keyword.replace(/[_]+/g, ' '));  // 类名兜底
    if (!hit?.id) hit = await findPest(keyword.split('_').pop());
    if (hit?.id) pest.value = await fetchPestDetail(hit.id);
  } catch (error) {
    console.warn('[pest] 加载百科详情失败', error);
    pest.value = null;
  } finally {
    loading.value = false;
  }
});
</script>

<style scoped>
.pest-detail {
  padding: 12px 12px calc(env(safe-area-inset-bottom, 0px) + 24px);
  background: #f6f8f7;
  min-height: 100vh;
}

.loading-wrap {
  display: grid;
  place-items: center;
  padding: 48px 0;
}

.card {
  background: #fff;
  border-radius: 14px;
  padding: 14px 16px;
  margin-bottom: 12px;
  box-shadow: 0 1px 2px rgba(15, 31, 23, 0.04);
}

.pest-name {
  margin: 0 0 4px;
  font-size: 20px;
  color: #1f2d26;
}

.card-title {
  margin: 0 0 8px;
  font-size: 14px;
  font-weight: 600;
  color: #2f4238;
}

.pre-wrap {
  white-space: pre-wrap;
  line-height: 1.7;
  font-size: 14px;
  color: #3d4a3d;
  margin: 0;
}

.muted {
  color: #8b9a91;
  font-size: 12.5px;
}

.prevention-list {
  margin: 0;
  padding-left: 18px;
}

.prevention-list li {
  margin-bottom: 10px;
  font-size: 14px;
  line-height: 1.7;
  color: #3d4a3d;
}

.prevention-list li .van-tag {
  margin-right: 6px;
}

.source-list {
  margin: 0;
  padding-left: 16px;
  font-size: 12.5px;
  line-height: 1.8;
}

.source-list a {
  color: #2f855a;
  word-break: break-all;
}
</style>
