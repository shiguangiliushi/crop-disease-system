<template>
  <div class="pestopedia-container">
    <header class="page-header">
      <h1>病害百科知识库</h1>
      <p>浏览和搜索系统中收录的所有作物病害信息</p>
    </header>

    <div class="controls-container card">
      <input type="text" v-model="searchTerm" placeholder="搜索病害名称..." class="search-input" />
    </div>

    <div v-if="isLoading" class="loading-indicator">
      <p>正在加载数据...</p>
    </div>

    <div v-if="!isLoading && groupedPests" class="results-container">
      <div v-for="(pests, crop) in groupedPests" :key="crop" class="crop-group card">
        <h2 class="crop-title">{{ crop }}</h2>
        <ul>
          <li v-for="pest in pests" :key="pest.id" class="pest-item" @click="togglePest(pest.id)">
            <div class="pest-header">
              <span>{{ pest.description }}</span>
              <span :class="['toggle-icon', { 'is-open': activePestId === pest.id }]">▼</span>
            </div>
            <div v-if="activePestId === pest.id" class="pest-details">
              <h4>主要症状:</h4>
              <p>{{ pest.symptom }}</p>
              <h4>防治措施:</h4>
              <ul class="measures-list">
                <li v-for="(measure, index) in pest.measures" :key="index">{{ measure.measure }}</li>
              </ul>
            </div>
          </li>
        </ul>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, computed } from 'vue';
import apiClient from '@/api';

const pests = ref([]);
const isLoading = ref(true);
const searchTerm = ref('');
const activePestId = ref(null);

onMounted(async () => {
  try {
    const response = await apiClient.get('/api/pests/');
    pests.value = response.data;
  } catch (error) {
    console.error("Failed to fetch pest information:", error);
  } finally {
    isLoading.value = false;
  }
});

const filteredPests = computed(() => {
  if (!searchTerm.value) {
    return pests.value;
  }
  return pests.value.filter(pest =>
    pest.description.toLowerCase().includes(searchTerm.value.toLowerCase()) ||
    pest.name.toLowerCase().includes(searchTerm.value.toLowerCase())
  );
});

const groupedPests = computed(() => {
  return filteredPests.value.reduce((acc, pest) => {
    const crop = pest.crop_variety;
    if (!acc[crop]) {
      acc[crop] = [];
    }
    acc[crop].push(pest);
    return acc;
  }, {});
});

const togglePest = (pestId) => {
  if (activePestId.value === pestId) {
    activePestId.value = null; // Collapse if already open
  } else {
    activePestId.value = pestId; // Expand clicked item
  }
};
</script>

<style scoped>
.pestopedia-container {
  padding: 2rem;
  max-width: 1000px;
  margin: 0 auto;
  background-color: #f9f9f9;
}
.page-header {
  text-align: center;
  margin-bottom: 2rem;
}
.page-header h1 {
  font-size: 2.5rem;
  font-weight: bold;
  color: #333;
}
.page-header p {
  color: #666;
  font-size: 1.1rem;
}
.card {
  background: white;
  padding: 1.5rem;
  border-radius: 8px;
  box-shadow: 0 4px 15px rgba(0, 0, 0, 0.05);
  margin-bottom: 1.5rem;
}
.search-input {
  width: 100%;
  padding: 0.75rem 1rem;
  font-size: 1rem;
  border: 1px solid #ddd;
  border-radius: 4px;
}
.crop-group {
  padding-top: 0.5rem;
}
.crop-title {
  font-size: 1.8rem;
  color: var(--color-primary, #28a745);
  border-bottom: 2px solid #eee;
  padding-bottom: 0.5rem;
  margin-bottom: 1rem;
}
ul {
  list-style: none;
  padding: 0;
}
.pest-item {
  padding: 1rem;
  border-bottom: 1px solid #f0f0f0;
  cursor: pointer;
  transition: background-color 0.2s;
}
.pest-item:hover {
  background-color: #fafafa;
}
.pest-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: 500;
  font-size: 1.1rem;
}
.toggle-icon {
  transition: transform 0.3s;
}
.toggle-icon.is-open {
  transform: rotate(180deg);
}
.pest-details {
  margin-top: 1rem;
  padding-left: 1rem;
  border-left: 3px solid var(--color-primary, #28a745);
  animation: fadeIn 0.5s;
}
.pest-details h4 {
  font-weight: bold;
  margin-top: 1rem;
  margin-bottom: 0.5rem;
}
.pest-details p, .measures-list {
  color: #555;
  line-height: 1.6;
}
.measures-list li {
  margin-bottom: 0.5rem;
}
@keyframes fadeIn {
  from { opacity: 0; transform: translateY(-10px); }
  to { opacity: 1; transform: translateY(0); }
}
</style> 