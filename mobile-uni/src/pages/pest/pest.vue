<template>
  <view class="page">
    <view v-if="loading" class="loading">{{ t('common.loading') }}</view>

    <template v-else-if="pest">
      <view class="card">
        <text class="name">{{ displayName }}</text>
        <text class="crop">{{ displayCrop }}{{ pest.scientific_name ? ' · ' + pest.scientific_name : '' }}</text>
      </view>

      <view class="card">
        <text class="block-title">{{ t('pestWiki.symptoms') }}</text>
        <text class="block-text">{{ displaySymptoms || t('pestWiki.noSymptoms') }}</text>
      </view>

      <view class="card">
        <text class="block-title">{{ t('pestWiki.prevention') }}</text>
        <view v-if="prevention.length">
          <view v-for="(item, index) in prevention" :key="index" class="prevention-row">
            <text v-if="item.category" class="tag">{{ item.category }}</text>
            <text class="block-text">{{ item.measure }}</text>
          </view>
        </view>
        <text v-else class="block-text">{{ t('pestWiki.noPrevention') }}</text>
      </view>

      <view v-if="description" class="card">
        <text class="block-title">{{ t('pestWiki.description') }}</text>
        <text class="block-text">{{ description }}</text>
      </view>
    </template>

    <view v-else class="empty">{{ t('pestWiki.notFound') }}</view>
  </view>
</template>

<script setup>
/** 病害百科详情（第 263 批）—— 结果页点「查看病害百科」进来 */
import { computed, onMounted, ref } from 'vue'
import { fetchPestDetail, findPest } from '@/api/pest'
import { locale, t } from '@/i18n'
import { onLoad } from '@dcloudio/uni-app'

const loading = ref(true)
const pest = ref(null)
const keyword = ref('')

const isEnglish = computed(() => String(locale.value || '').startsWith('en'))
const displayName = computed(() => (isEnglish.value ? pest.value?.name_en || pest.value?.name : pest.value?.name) || '')
const displayCrop = computed(() => (isEnglish.value ? pest.value?.crop_type_en || pest.value?.crop_type : pest.value?.crop_type) || '')
const displaySymptoms = computed(() => (isEnglish.value ? pest.value?.symptoms_en || pest.value?.symptoms : pest.value?.symptoms) || '')
const description = computed(() => (isEnglish.value ? pest.value?.description_en || pest.value?.description : pest.value?.description) || '')
const prevention = computed(() => {
  const rows = Array.isArray(pest.value?.prevention_methods) ? pest.value.prevention_methods : []
  return rows
    .map((row) => ({
      category: row.category || '',
      measure: (isEnglish.value ? row.measure_en || row.measure : row.measure) || '',
    }))
    .filter((row) => row.measure)
})

async function load() {
  loading.value = true
  try {
    let hit = await findPest(keyword.value)
    if (!hit?.id) hit = await findPest(String(keyword.value).replace(/[_]+/g, ' '))
    if (hit?.id) pest.value = await fetchPestDetail(hit.id)
  } catch (error) {
    console.warn('[pest] 加载失败', error)
    pest.value = null
  } finally {
    loading.value = false
  }
}

onLoad((options) => {
  keyword.value = decodeURIComponent(options?.keyword || '')
  load()
})
</script>

<style scoped>
.page { min-height: 100vh; background: #f6f8f7; padding: 24rpx; box-sizing: border-box; }
.loading, .empty { padding: 80rpx 0; text-align: center; color: #8b9a91; font-size: 26rpx; }
.card { background: #fff; border-radius: 20rpx; padding: 24rpx; margin-bottom: 20rpx; }
.name { display: block; font-size: 36rpx; color: #1f2d26; font-weight: 600; }
.crop { display: block; margin-top: 8rpx; color: #8b9a91; font-size: 24rpx; }
.block-title { display: block; font-size: 26rpx; color: #2f4238; font-weight: 600; margin-bottom: 12rpx; }
.block-text { display: block; font-size: 26rpx; line-height: 1.8; color: #3d4a3d; }
.prevention-row { margin-bottom: 16rpx; }
.tag { display: inline-block; margin-right: 8rpx; padding: 2rpx 12rpx; border-radius: 999rpx;
  background: #eef6f1; color: #2f855a; font-size: 22rpx; }
</style>
