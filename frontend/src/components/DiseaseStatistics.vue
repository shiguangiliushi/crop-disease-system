<template>
  <div class="disease-statistics">
    <div class="page-header">
      <h1>{{ t('stats.title') }}</h1>
      <p class="current-time">{{ t('stats.currentTime') }}{{ currentTime }}</p>
    </div>

    <div v-if="error" class="stats-notice">
      <i class="fas fa-exclamation-circle"></i>
      <span>{{ error }}</span>
      <button class="stats-retry" @click="reload">{{ t('history.reload') }}</button>
    </div>

    <!-- 第 74 批：无数据时给明确的空态，而不是画两张空图表。
         原来新账号进来看到的是两个空白坐标系，看不出是"没数据"还是"坏了"。 -->
    <div v-else-if="hasNoData" class="stats-empty">
      <i class="fas fa-chart-simple"></i>
      <h2>{{ t('stats.emptyTitle') }}</h2>
      <p>{{ t('stats.emptyDesc') }}</p>
      <RouterLink to="/detect" class="stats-empty-btn">
        <i class="fas fa-camera"></i> {{ t('history.goDetect') }}
      </RouterLink>
    </div>

    <div v-else class="stats-container">
      <div class="chart-card">
        <h2>{{ t('stats.typeDistribution') }}</h2>
        <div class="chart-wrapper">
          <Bar :data="diseaseTypeData" :options="diseaseTypeOptions" />
        </div>
      </div>

      <div class="chart-card">
        <h2>{{ t('stats.cropDistribution') }}</h2>
        <div class="chart-wrapper">
          <Pie :data="cropDiseaseData" :options="cropDiseaseOptions" />
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, computed, watch } from 'vue';
import { RouterLink } from 'vue-router';
import api from '@/api';
import { Bar, Line, Pie } from 'vue-chartjs';
import { useI18n } from '@/i18n';  // 第 62 批：多语言
import { useLocalized } from '@/utils/localized';  // 第 77 批：内容数据（病害名/作物名）多语言

const { t, locale } = useI18n();
const { localizedField } = useLocalized();

/**
 * 第 77 批：图表标签的取值
 * ------------------------------------------------------------------
 * 本组件的图表有两类文字，之前都写死成中文，英文界面下会露出中文：
 *   ① 图表标题/轴标签/图例 —— Chart.js 自己在 canvas 里画的，模板里的 t() 够不着；
 *   ② 柱子/扇区的名字 —— 来自后端聚合接口，需要 `*_en`（后端已随第 77 批补上）。
 * 占位行（后端对"没有匹配到病害"的记录兜出来的"未知病害/未知作物"）没有英文名，
 * 这里按界面语言换成对应文案，而不是把中文透到英文界面上。
 */
const UNKNOWN_LABELS = {
  '未知病害': 'stats.unknownPest',
  '未知作物': 'stats.unknownCrop',
};

const chartLabel = (row, base) => {
  const placeholderKey = UNKNOWN_LABELS[row?.[base]];
  if (placeholderKey) return t(placeholderKey);
  return localizedField(row, base);
};

// 第 77 批：12 个月的短标签跟随语言（原来写死成 '1月'…'12月'）
const monthLabels = computed(() =>
  Array.from({ length: 12 }, (_, index) =>
    new Date(2024, index, 1).toLocaleDateString(locale.value === 'en' ? 'en-US' : 'zh-CN', {
      month: 'short',
    }),
  ),
);
import {
  Chart as ChartJS,
  Title,
  Tooltip,
  Legend,
  BarElement,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  ArcElement,
  Filler
} from 'chart.js';

// 状态管理
const isLoading = ref(false);
const error = ref(null);

// 注册所有组件
ChartJS.register(
  Title,
  Tooltip,
  Legend,
  BarElement,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  ArcElement,
  Filler
);

// 配置全局图表默认值
ChartJS.defaults.plugins.legend.display = true;
ChartJS.defaults.plugins.tooltip.enabled = true;
ChartJS.defaults.maintainAspectRatio = false;

// 响应式数据
const statisticsData = ref({
  pest_distribution: [],
  monthly_trends: [],
  crop_distribution: [],
  last_7_days: [],
  feedback_stats: {}
});

// 当前时间
const currentTime = ref('');

// 更新当前时间
const updateCurrentTime = () => {
  const now = new Date();
  // 第 77 批：时间的书写习惯跟随界面语言（英文界面用 en-US，而不是固定的 zh-CN）
  currentTime.value = now.toLocaleString(locale.value === 'en' ? 'en-US' : 'zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false
  });
};

// 说明（第 22 批）：本组件只出现在「识别记录」页。统计范围必须与该页的列表
// **完全一致**，否则会出现"列表只有我的、图表却是所有人"的自相矛盾。
// 因此范围由父组件通过 allUsers 传进来（管理员在页面上切换"查看全部用户"）。
const props = defineProps({
  allUsers: {
    type: Boolean,
    default: false,
  },
});

// 获取统计数据
const fetchStatistics = async () => {
  try {
    console.log('正在请求统计数据...');
    const response = await api.get('/statistics/', {
      params: props.allUsers ? { all_users: 'true' } : {},
    });
    console.log('统计接口响应:', response);

    // 确保响应数据存在
    if (!response || !response.data) {
      console.warn('统计接口返回数据为空');
      throw new Error('Empty response data');
    }

    const data = response.data;
    console.log('原始统计数据:', data);

    // 确保数据结构正确
    const processedData = {
      pest_distribution: Array.isArray(data.pest_distribution) ? data.pest_distribution : [],
      monthly_trends: Array.isArray(data.monthly_trends) ? data.monthly_trends : [],
      crop_distribution: Array.isArray(data.crop_distribution) ? data.crop_distribution : [],
      last_7_days: Array.isArray(data.last_7_days) ? data.last_7_days : [],
      feedback_stats: data.feedback_stats && typeof data.feedback_stats === 'object'
        ? data.feedback_stats
        : { total: 0, positive: 0, negative: 0, neutral: 0 }
    };

    // 确保 monthly_trends 中的每个条目都有正确的格式
    if (processedData.monthly_trends.length > 0) {
      processedData.monthly_trends = processedData.monthly_trends.map(item => ({
        label: item.label || t('stats.unnamedDataset'),
        data: Array.isArray(item.data) ? item.data : []
      }));
    }

    console.log('处理后的统计数据:', processedData);
    statisticsData.value = processedData;
    return processedData;

  } catch (error) {
    console.error('获取统计数据失败:', error);

    // 原来这里会回退到一份写死的模拟数据（而且字段名与图表要求不一致，
    // 会显示成一堆“未知病害”的假数字）。统计数据必须真实，失败时给出空数据 + 错误提示。
    statisticsData.value = {
      pest_distribution: [],
      monthly_trends: [],
      crop_distribution: [],
      last_7_days: [],
      feedback_stats: { total: 0, positive: 0, negative: 0, neutral: 0 }
    };
    error.value = t('stats.loadFailed');
    return statisticsData.value;
  }
};

// 重新加载
const reload = async () => {
  isLoading.value = true;
  error.value = null;
  try {
    await fetchStatistics();
  } finally {
    isLoading.value = false;
  }
};

// 统计范围变化时（管理员切换"查看全部用户"）重新拉取
watch(() => props.allUsers, () => {
  reload();
});

// 初始化时获取数据
onMounted(async () => {
  updateCurrentTime();
  // 每秒更新一次时间
  setInterval(updateCurrentTime, 1000);

  try {
    isLoading.value = true;
    error.value = null;
    await fetchStatistics();
  } catch (err) {
    console.error('初始化数据失败:', err);
    error.value = t('stats.loadFailed');
  } finally {
    isLoading.value = false;
  }
});

// 第 74 批：判断是否"完全没有数据"（两个维度都为空）→ 显示空态而不是空图表
const hasNoData = computed(() => {
  const data = statisticsData.value || {};
  const pests = data.pest_distribution?.length || 0;
  const crops = data.crop_distribution?.length || 0;
  return pests === 0 && crops === 0;
});

// 病害类型分布数据
const diseaseTypeData = computed(() => {
  // 默认数据
  const defaultData = {
    labels: [],
    datasets: [
      {
        label: t('stats.cases'),
        data: [],
        backgroundColor: [],
        borderColor: [],
        borderWidth: 1
      }
    ]
  };

  try {
    if (statisticsData.value?.pest_distribution?.length > 0) {
      // 颜色配置
      const colors = [
        'rgba(255, 99, 132, 0.7)', 'rgba(54, 162, 235, 0.7)', 'rgba(255, 206, 86, 0.7)',
        'rgba(75, 192, 192, 0.7)', 'rgba(153, 102, 255, 0.7)', 'rgba(255, 159, 64, 0.7)',
        'rgba(199, 199, 199, 0.7)', 'rgba(83, 102, 255, 0.7)', 'rgba(40, 208, 148, 0.7)'
      ];
      const borderColors = [
        'rgba(255, 99, 132, 1)', 'rgba(54, 162, 235, 1)', 'rgba(255, 206, 86, 1)',
        'rgba(75, 192, 192, 1)', 'rgba(153, 102, 255, 1)', 'rgba(255, 159, 64, 1)',
        'rgba(199, 199, 199, 1)', 'rgba(83, 102, 255, 1)', 'rgba(40, 208, 148, 1)'
      ];

      // 处理数据
      const labels = [];
      const data = [];
      const bgColors = [];
      const borderColorsList = [];

      statisticsData.value.pest_distribution.forEach((item, index) => {
        const colorIndex = index % colors.length;
        labels.push(chartLabel(item, 'pest_info__name') || t('stats.unknownPest'));
        data.push(item.count);
        bgColors.push(colors[colorIndex]);
        borderColorsList.push(borderColors[colorIndex]);
      });

      return {
        labels,
        datasets: [
          {
            ...defaultData.datasets[0],
            data,
            backgroundColor: bgColors,
            borderColor: borderColorsList
          }
        ]
      };
    }
  } catch (error) {
    console.error('处理病害类型数据时出错:', error);
  }

  return defaultData;
});

// 病害类型分布图配置
// 第 77 批：改成 computed —— 图表标题/轴标签是 t() 出来的，必须是响应式的，
// 否则切换语言后要刷新整页才会变。
const diseaseTypeOptions = computed(() => ({
  responsive: true,
  maintainAspectRatio: false,
  plugins: {
    legend: {
      position: 'top',
      labels: {
        font: {
          family: '"PingFang SC", "Microsoft YaHei", sans-serif',
          size: 14,
          weight: 'bold'
        }
      }
    },
    title: {
      display: true,
      text: t('stats.chartType'),
      font: {
        family: '"PingFang SC", "Microsoft YaHei", sans-serif',
        size: 16,
        weight: 'bold'
      }
    },
    tooltip: {
      titleFont: {
        family: '"PingFang SC", "Microsoft YaHei", sans-serif',
        size: 14,
        weight: 'bold'
      },
      bodyFont: {
        family: '"PingFang SC", "Microsoft YaHei", sans-serif',
        size: 14
      }
    }
  },
  scales: {
    y: {
      beginAtZero: true,
      ticks: {
        font: {
          family: '"PingFang SC", "Microsoft YaHei", sans-serif',
          size: 12,
          weight: 'bold'
        }
      },
      title: {
        display: true,
        text: t('stats.cases'),
        font: {
          family: '"PingFang SC", "Microsoft YaHei", sans-serif',
          size: 14,
          weight: 'bold'
        }
      }
    },
    x: {
      ticks: {
        font: {
          family: '"PingFang SC", "Microsoft YaHei", sans-serif',
          size: 12,
          weight: 'bold'
        }
      }
    }
  }
}));

// 病害趋势数据
// ⚠️ 本块（diseaseTrendData / diseaseTrendOptions）当前**没有被模板使用**：
//    页面只渲染"病害类型分布"与"作物病害分布"两张图。保留下来的示例数字是**假的**，
//    将来要恢复趋势图请改用 statisticsData.monthly_trends 的真实数据。
//    第 77 批：这里的月份/文案也接上了多语言，避免将来直接启用时英文界面又冒出中文。
const diseaseTrendData = computed(() => {
  // 默认数据
  const defaultData = {
    labels: monthLabels.value,
    datasets: [
      {
        label: t('stats.datasetN', { n: 1 }),
        data: [12, 19, 3, 5, 2, 3, 15, 25, 32, 28, 18, 10],
        borderColor: 'rgba(75, 192, 192, 1)',
        backgroundColor: 'rgba(75, 192, 192, 0.2)',
        borderWidth: 2,
        tension: 0.4,
        fill: {
          target: 'origin',
          above: 'rgba(75, 192, 192, 0.2)'
        },
        pointBackgroundColor: '#fff',
        pointBorderColor: 'rgba(75, 192, 192, 1)',
        pointHoverBackgroundColor: 'rgba(75, 192, 192, 1)',
        pointHoverBorderColor: '#fff',
        pointRadius: 4,
        pointHoverRadius: 6,
        pointBorderWidth: 2,
        pointHoverBorderWidth: 2,
        pointHitRadius: 10
      },
      {
        label: t('stats.datasetN', { n: 2 }),
        data: [8, 12, 15, 18, 22, 25, 28, 35, 30, 25, 18, 12],
        borderColor: 'rgba(54, 162, 235, 1)',
        backgroundColor: 'rgba(54, 162, 235, 0.2)',
        borderWidth: 2,
        tension: 0.4,
        fill: {
          target: 'origin',
          above: 'rgba(54, 162, 235, 0.2)'
        },
        pointBackgroundColor: '#fff',
        pointBorderColor: 'rgba(54, 162, 235, 1)',
        pointHoverBackgroundColor: 'rgba(54, 162, 235, 1)',
        pointHoverBorderColor: '#fff',
        pointRadius: 4,
        pointHoverRadius: 6,
        pointBorderWidth: 2,
        pointHoverBorderWidth: 2,
        pointHitRadius: 10
      }
    ]
  };

  try {
    // 如果API返回了月度趋势数据，则使用API数据
    if (statisticsData.value?.monthly_trends?.length > 0) {
      const colors = [
        { border: 'rgba(75, 192, 192, 1)', background: 'rgba(75, 192, 192, 0.2)' },
        { border: 'rgba(54, 162, 235, 1)', background: 'rgba(54, 162, 235, 0.2)' },
        { border: 'rgba(255, 159, 64, 1)', background: 'rgba(255, 159, 64, 0.2)' },
        { border: 'rgba(255, 99, 132, 1)', background: 'rgba(255, 99, 132, 0.2)' },
        { border: 'rgba(153, 102, 255, 1)', background: 'rgba(153, 102, 255, 0.2)' }
      ];

      const datasets = statisticsData.value.monthly_trends.map((item, index) => {
        const colorIndex = index % colors.length;
        return {
          label: item.label || t('stats.datasetN', { n: index + 1 }),
          data: Array.isArray(item.data) ? item.data : [],
          borderColor: colors[colorIndex].border,
          backgroundColor: colors[colorIndex].background,
          borderWidth: 2,
          tension: 0.4,
          fill: {
            target: 'origin',
            above: colors[colorIndex].background
          },
          pointBackgroundColor: '#fff',
          pointBorderColor: colors[colorIndex].border,
          pointHoverBackgroundColor: colors[colorIndex].border,
          pointHoverBorderColor: '#fff',
          pointRadius: 4,
          pointHoverRadius: 6,
          pointBorderWidth: 2,
          pointHoverBorderWidth: 2,
          pointHitRadius: 10
        };
      });

      return {
        labels: defaultData.labels.slice(0, Math.max(...datasets.map(ds => ds.data.length))),
        datasets
      };
    }
  } catch (error) {
    console.error('处理趋势数据时出错:', error);
    // 返回默认数据时确保数据结构完整
    if (!defaultData.datasets || !Array.isArray(defaultData.datasets)) {
      defaultData.datasets = [];
    }
  }

  return defaultData;
});

// 病害趋势图配置
const diseaseTrendOptions = computed(() => ({
  responsive: true,
  maintainAspectRatio: false,
  plugins: {
    legend: {
      position: 'top',
      labels: {
        font: {
          family: '"PingFang SC", "Microsoft YaHei", sans-serif',
          size: 14,
          weight: 'bold'
        }
      }
    },
    title: {
      display: true,
      text: t('stats.chartTrend'),
      font: {
        family: '"PingFang SC", "Microsoft YaHei", sans-serif',
        size: 16,
        weight: 'bold'
      }
    },
    tooltip: {
      titleFont: {
        family: '"PingFang SC", "Microsoft YaHei", sans-serif',
        size: 14,
        weight: 'bold'
      },
      bodyFont: {
        family: '"PingFang SC", "Microsoft YaHei", sans-serif',
        size: 14
      }
    }
  },
  scales: {
    y: {
      beginAtZero: true,
      ticks: {
        font: {
          family: '"PingFang SC", "Microsoft YaHei", sans-serif',
          size: 12,
          weight: 'bold'
        }
      },
      title: {
        display: true,
        text: t('stats.cases'),
        font: {
          family: '"PingFang SC", "Microsoft YaHei", sans-serif',
          size: 14,
          weight: 'bold'
        }
      }
    },
    x: {
      ticks: {
        font: {
          family: '"PingFang SC", "Microsoft YaHei", sans-serif',
          size: 12,
          weight: 'bold'
        }
      }
    }
  }
}));

// 作物病害数据
const cropDiseaseData = computed(() => {
  // 默认数据
  const defaultData = {
    labels: [],
    datasets: [{
      data: [],
      backgroundColor: [],
      borderColor: [],
      borderWidth: 1
    }]
  };

  try {
    if (statisticsData.value?.crop_distribution?.length > 0) {
      // 颜色配置
      const colors = [
        'rgba(255, 99, 132, 0.7)', 'rgba(54, 162, 235, 0.7)', 'rgba(255, 206, 86, 0.7)',
        'rgba(75, 192, 192, 0.7)', 'rgba(153, 102, 255, 0.7)', 'rgba(255, 159, 64, 0.7)',
        'rgba(199, 199, 199, 0.7)', 'rgba(83, 102, 255, 0.7)', 'rgba(40, 208, 148, 0.7)'
      ];
      const borderColors = [
        'rgba(255, 99, 132, 1)', 'rgba(54, 162, 235, 1)', 'rgba(255, 206, 86, 1)',
        'rgba(75, 192, 192, 1)', 'rgba(153, 102, 255, 1)', 'rgba(255, 159, 64, 1)',
        'rgba(199, 199, 199, 1)', 'rgba(83, 102, 255, 1)', 'rgba(40, 208, 148, 1)'
      ];

      // 处理数据
      const labels = [];
      const data = [];
      const bgColors = [];
      const borderColorsList = [];
      const cropMap = new Map(); // 使用Map来统计每种作物的总数
      // 第 77 批：按**中文作物名**聚合（分组口径不变），另存一份显示名，
      // 英文界面下扇区/图例/浮层用英文名。
      const cropDisplayName = new Map();

      // 处理作物分布数据
      console.log('原始 crop_distribution 数据:', JSON.parse(JSON.stringify(statisticsData.value.crop_distribution)));
      
      statisticsData.value.crop_distribution.forEach(item => {
        const cropType = item.pest_info__crop_type || '未知作物';
        const count = item.count || 0;
        
        console.log(`处理作物: ${cropType}, 数量: ${count}`);

        if (!cropDisplayName.has(cropType)) {
          cropDisplayName.set(cropType, chartLabel(item, 'pest_info__crop_type') || t('stats.unknownCrop'));
        }

        // 统计每种作物的总数
        if (cropMap.has(cropType)) {
          cropMap.set(cropType, cropMap.get(cropType) + count);
        } else {
          cropMap.set(cropType, count);
        }
      });

      // 按数量降序排序
      const sortedCrops = Array.from(cropMap.entries())
        .sort((a, b) => b[1] - a[1]);

      // 准备图表数据
      sortedCrops.forEach(([cropName, count], index) => {
        const colorIndex = index % colors.length;
        labels.push(cropDisplayName.get(cropName) || cropName);
        data.push(count);
        bgColors.push(colors[colorIndex]);
        borderColorsList.push(borderColors[colorIndex]);
      });

      return {
        labels,
        datasets: [{
          ...defaultData.datasets[0],
          data,
          backgroundColor: bgColors,
          borderColor: borderColorsList
        }]
      };
    }
  } catch (error) {
    console.error('处理作物病害数据时出错:', error);
  }

  return defaultData;
});

// 作物病害图配置
// 第 77 批：同样是 computed（标题要跟着语言变）
const cropDiseaseOptions = computed(() => ({
  responsive: true,
  maintainAspectRatio: false,
  animation: {
    duration: 1000,
    easing: 'easeInOutQuart'
  },
  plugins: {
    legend: {
      position: 'right',
      labels: {
        color: '#495057',
        font: {
          size: 12
        },
        padding: 20,
        usePointStyle: true,
        pointStyle: 'circle'
      }
    },
    title: {
      display: true,
      text: t('stats.chartCrop'),
      font: {
        family: '"PingFang SC", "Microsoft YaHei", sans-serif',
        size: 16,
        weight: 'bold'
      }
    },
    tooltip: {
      backgroundColor: 'rgba(0, 0, 0, 0.8)',
      titleFont: {
        size: 13,
        weight: 'bold',
        family: "'PingFang SC', 'Microsoft YaHei', sans-serif"
      },
      bodyFont: {
        size: 12,
        family: "'PingFang SC', 'Microsoft YaHei', sans-serif"
      },
      padding: 10,
      cornerRadius: 4,
      displayColors: true,
      mode: 'index',
      intersect: false,
      boxWidth: 10,
      boxHeight: 10,
      boxShadow: 'none',
      border: '1px solid #eee',
      marginBottom: '1.5rem'
    }
  }
}));
</script>

<style scoped>
.disease-statistics {
  padding: 20px;
  font-family: 'PingFang SC', 'Microsoft YaHei', sans-serif;
}

.page-header {
  margin-bottom: 30px;
  text-align: center;
}

.page-header h1 {
  color: #2c3e50;
  margin-bottom: 10px;
}

.current-time {
  color: #7f8c8d;
  font-size: 14px;
}

.stats-container {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(400px, 1fr));
  gap: 20px;
  margin-top: 20px;
}

.chart-card {
  background: #fff;
  border-radius: 8px;
  box-shadow: 0 2px 12px 0 rgba(0, 0, 0, 0.1);
  padding: 20px;
  transition: all 0.3s;
}

.chart-card:hover {
  transform: translateY(-5px);
  box-shadow: 0 5px 15px rgba(0, 0, 0, 0.1);
}

.chart-card h2 {
  color: #2c3e50;
  font-size: 18px;
  margin-bottom: 20px;
  text-align: center;
}

.chart-wrapper {
  position: relative;
  height: 300px;
  width: 100%;
}

.full-width {
  grid-column: 1 / -1;
}

.stats-notice {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 18px;
  padding: 12px 16px;
  border-radius: 12px;
  background: #fdf6ec;
  border: 1px solid #f5dab1;
  color: #b8860b;
  font-size: 14px;
}

.stats-retry {
  margin-left: auto;
  padding: 5px 14px;
  border: 1px solid #e0b877;
  border-radius: 16px;
  background: #fff;
  color: #b8860b;
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.stats-retry:hover {
  background: #fdf2e0;
}

@media (max-width: 768px) {
  .stats-container {
    grid-template-columns: 1fr;
  }
  
  .chart-card {
    margin-bottom: 20px;
  }
  
  .chart-wrapper {
    height: 250px;
  }
}

/* 第 74 批：无数据空态 —— 插画 + 说明 + 明确的下一步按钮 */
.stats-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  padding: 56px 24px;
  text-align: center;
  border: 1px dashed var(--border-strong, #d3dfd8);
  border-radius: var(--radius, 14px);
  background: var(--surface, #fff);
}

.stats-empty > i {
  font-size: 42px;
  color: var(--brand-300, #93cdad);
}

.stats-empty h2 {
  margin: 4px 0 0;
  font-size: var(--font-size-title-sm, 18px);
  font-weight: 700;
  color: var(--ink-800, #24352c);
}

.stats-empty p {
  margin: 0;
  max-width: 460px;
  font-size: var(--font-size-base, 16px);
  line-height: 1.8;
  color: var(--ink-500, #78897f);
}

.stats-empty-btn {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-height: 44px;
  margin-top: 8px;
  padding: 11px 24px;
  border-radius: var(--radius-pill, 999px);
  background: var(--gradient-brand, linear-gradient(135deg, #3d9a68, #1f6343));
  color: #fff;
  font-size: var(--font-size-base, 16px);
  font-weight: 700;
  text-decoration: none;
  box-shadow: 0 6px 16px rgba(31, 99, 67, 0.22);
  transition: transform var(--dur, 0.24s) var(--ease, ease),
    box-shadow var(--dur, 0.24s) var(--ease, ease);
}

.stats-empty-btn:hover {
  color: #fff;
  transform: translateY(-1px);
  box-shadow: 0 10px 22px rgba(31, 99, 67, 0.3);
}
</style>
