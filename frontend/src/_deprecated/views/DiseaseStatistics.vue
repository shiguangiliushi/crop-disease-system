<template>
  <div class="disease-statistics">
    <div class="page-header">
      <h1>病害统计</h1>
      <p class="current-time">当前时间：{{ currentTime }}</p>
    </div>

    <div class="stats-container">
      <div class="chart-card">
        <h2>病害类型分布</h2>
        <div class="chart-wrapper">
          <Bar :data="diseaseTypeData" :options="diseaseTypeOptions" />
        </div>
      </div>

      <div class="chart-card">
        <h2>病害趋势分析</h2>
        <div class="chart-wrapper">
          <Line :data="diseaseTrendData" :options="diseaseTrendOptions" />
        </div>
      </div>

      <div class="chart-card full-width">
        <h2>作物病害统计</h2>
        <div class="chart-wrapper">
          <Pie :data="cropDiseaseData" :options="cropDiseaseOptions" />
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, computed } from 'vue';
import { Bar, Line, Pie } from 'vue-chartjs';
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
  currentTime.value = now.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false
  });
};

// 初始化时更新时间
// 获取统计数据
const fetchStatistics = async () => {
  try {
    console.log('正在请求统计数据...');
    const response = await api.get('/statistics/');
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
        label: item.label || '未命名数据集',
        data: Array.isArray(item.data) ? item.data : []
      }));
    }
    
    console.log('处理后的统计数据:', processedData);
    statisticsData.value = processedData;
    return processedData;
    
  } catch (error) {
    console.error('获取统计数据失败:', error);
    
    // 使用模拟数据作为回退
    const mockData = {
      pest_distribution: [
        { name: '苹果黑星病', count: 125 },
        { name: '番茄晚疫病', count: 98 },
        { name: '黄瓜白粉病', count: 76 },
        { name: '葡萄霜霉病', count: 54 },
        { name: '其他', count: 32 }
      ],
      monthly_trends: [
        {
          label: '苹果黑星病',
          data: [12, 19, 3, 5, 2, 3, 15, 25, 32, 28, 18, 10]
        },
        {
          label: '番茄晚疫病',
          data: [8, 12, 15, 18, 22, 25, 28, 35, 30, 25, 18, 12]
        }
      ],
      crop_distribution: [
        { crop: '苹果', count: 125 },
        { crop: '番茄', count: 98 },
        { crop: '黄瓜', count: 76 },
        { crop: '葡萄', count: 54 },
        { crop: '其他', count: 32 }
      ],
      last_7_days: [
        { date: '2023-05-01', count: 15 },
        { date: '2023-05-02', count: 12 },
        { date: '2023-05-03', count: 18 },
        { date: '2023-05-04', count: 8 },
        { date: '2023-05-05', count: 22 },
        { date: '2023-05-06', count: 14 },
        { date: '2023-05-07', count: 19 }
      ],
      feedback_stats: {
        total: 45,
        positive: 32,
        negative: 8,
        neutral: 5
      }
    };
    
    statisticsData.value = mockData;
    return mockData;
  }
};

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
    error.value = '加载统计数据失败，请稍后重试';
    // 显示错误提示
    ElMessage.error('加载统计数据失败，已显示模拟数据');
  } finally {
    isLoading.value = false;
  }
});

// 病害类型分布数据
const diseaseTypeData = {
  labels: ['苹果黑星病', '番茄晚疫病', '苹果黑腐病', '葡萄黑腐病', '柑橘黄龙病', '其他'],
  datasets: [{
    label: '病例数',
    data: [120, 190, 83, 61, 56, 42],
    backgroundColor: [
      'rgba(255, 99, 132, 0.7)',
      'rgba(54, 162, 235, 0.7)',
      'rgba(255, 206, 86, 0.7)',
      'rgba(75, 192, 192, 0.7)',
      'rgba(153, 102, 255, 0.7)',
      'rgba(255, 159, 64, 0.7)'
    ],
    borderColor: [
      'rgba(255, 99, 132, 1)',
      'rgba(54, 162, 235, 1)',
      'rgba(255, 206, 86, 1)',
      'rgba(75, 192, 192, 1)',
      'rgba(153, 102, 255, 1)',
      'rgba(255, 159, 64, 1)'
    ],
    borderWidth: 1
  }]
};

// 病害类型分布图配置
const diseaseTypeOptions = {
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
      text: '各病害类型发生情况',
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
        text: '病例数',
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
};

// 病害趋势数据
const diseaseTrendData = computed(() => {
  // 默认数据
  const defaultData = {
    labels: ['1月', '2月', '3月', '4月', '5月', '6月', '7月', '8月', '9月', '10月', '11月', '12月'],
    datasets: [
      {
        label: '苹果黑星病',
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
        label: '番茄晚疫病',
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
          label: item.label || `数据集 ${index + 1}`,
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
const diseaseTrendOptions = {
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
      text: '病害月度趋势',
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
        text: '病例数',
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
};

// 作物病害数据
const cropDiseaseData = {
  labels: ['苹果', '番茄', '葡萄', '柑橘', '马铃薯', '其他'],
  datasets: [{
    data: [300, 200, 180, 150, 100, 70],
    backgroundColor: [
      'rgba(255, 99, 132, 0.7)',
      'rgba(54, 162, 235, 0.7)',
      'rgba(255, 206, 86, 0.7)',
      'rgba(75, 192, 192, 0.7)',
      'rgba(153, 102, 255, 0.7)',
      'rgba(255, 159, 64, 0.7)'
    ],
    borderColor: [
      'rgba(255, 99, 132, 1)',
      'rgba(54, 162, 235, 1)',
      'rgba(255, 206, 86, 1)',
      'rgba(75, 192, 192, 1)',
      'rgba(153, 102, 255, 1)',
      'rgba(255, 159, 64, 1)'
    ],
    borderWidth: 1
  }]
};

// 作物病害图配置
const cropDiseaseOptions = {
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
      text: '各作物病害分布',
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
      boxPadding: 4,
      usePointStyle: true,
      callbacks: {
        label: function(context) {
          const label = context.label || '';
          const value = context.raw || 0;
          const total = context.dataset.data.reduce((a, b) => a + b, 0);
          const percentage = Math.round((value / total) * 100);
          return `${label}: ${value} 例 (${percentage}%)`;
        }
      }
    }
  }
};

</script>

<!--
  说明：本文件此前被截断（缺少 </script> 与 <style> 开标签，并残留了
  “// ... (其余代码保持不变)” 与几行游离的 CSS 声明），SFC 解析直接报
  “Element is missing end tag”。由于它没有被任何模块引用，构建时不会暴露该问题。
  这里补齐标签结构，使其至少是一个合法可编译的 SFC（本文件当前未被路由/组件引用）。
-->
<style scoped>
.chart-card {
  box-shadow: none;
  border: 1px solid #eee;
  margin-bottom: 1.5rem;
}
</style>
