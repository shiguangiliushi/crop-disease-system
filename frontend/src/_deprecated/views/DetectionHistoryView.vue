<template>
  <div class="detection-history">
    <el-card class="box-card">
      <template #header>
        <div class="card-header">
          <div>
            <h2>识别记录管理</h2>
            <p style="margin: 4px 0 0; font-size: 12px; color: #909399;">
              全部用户的识别记录 · 可按用户名或病害名称搜索、批量删除
            </p>
          </div>
          <div class="header-actions">
            <el-input
              v-model="searchQuery"
              placeholder="搜索用户或病害名称"
              style="width: 300px; margin-right: 10px;"
              clearable
              @clear="handleSearch"
              @keyup.enter="handleSearch"
            >
              <template #suffix>
                <el-icon><search /></el-icon>
              </template>
            </el-input>
            <el-button type="primary" @click="fetchDetectionHistory">
              <el-icon><refresh /></el-icon>
              刷新
            </el-button>
            <el-button 
              v-if="isAdmin" 
              type="danger" 
              :disabled="selectedItems.length === 0"
              @click="handleBatchDelete"
            >
              <el-icon><delete /></el-icon>
              批量删除{{ selectedItems.length > 0 ? ` (${selectedItems.length})` : '' }}
            </el-button>
          </div>
        </div>
      </template>

      <div v-loading="loading" class="detection-grid">
        <div v-if="detectionList.length === 0" class="empty-state">
          <el-empty description="暂无识别记录" />
        </div>
        <div v-else class="grid-container">
          <el-card 
            v-for="item in detectionList" 
            :key="item.id" 
            class="detection-card"
            :class="{ 'selected': isSelected(item.id) }"
          >
            <!-- 选择框：单个复选框不能用 v-model 直接绑数组（会被写成布尔值），
                 改为按“是否包含该 id”计算选中态，再手动维护数组 -->
            <div class="card-selection" v-if="isAdmin">
              <el-checkbox
                :model-value="isSelected(item.id)"
                @change="(val) => toggleSelection(item.id, val)"
              />
            </div>
            <div class="card-header">
              <div class="user-info">
                <el-avatar :size="24" :src="item.user?.avatar" class="user-avatar">
                  {{ item.user?.username?.charAt(0) || 'U' }}
                </el-avatar>
                <span class="username">{{ item.user?.username || '未知用户' }}</span>
              </div>
              <el-button 
                type="primary" 
                size="small" 
                @click.stop="downloadReport(item.id)"
                :loading="downloadingReportId === item.id"
                class="download-btn"
              >
                <el-icon><Download /></el-icon>
                下载报告
              </el-button>
            </div>
            <div class="card-image" @click="viewDetail(item)">
              <el-image
                v-if="item.image"
                :src="getFullImageUrl(item.image)"
                fit="cover"
                class="detection-image"
                :preview-src-list="[getFullImageUrl(item.image)]"
                :initial-index="0"
                hide-on-click-modal
              >
                <template #error>
                  <div class="image-error">
                    <el-icon><Picture /></el-icon>
                    <span>图片加载失败</span>
                  </div>
                </template>
              </el-image>
              <div v-else class="no-image">
                <el-icon><Picture /></el-icon>
                <span>无图片</span>
              </div>
            </div>
            <div class="card-content">
              <div class="card-header">
                <div class="detection-info">
                  <div class="detection-header">
                    <h3>{{ item.detection_result || '未知病害' }}</h3>
                    <div class="header-actions">
                      <el-tag :type="getConfidenceType(item.confidence)" size="small">
                        {{ (item.confidence * 100).toFixed(2) }}%
                      </el-tag>
                    </div>
                  </div>
                  <div class="card-meta">
                    <div class="meta-item">
                      <el-icon><User /></el-icon>
                      <span>{{ item.user?.username || '未知用户' }}</span>
                    </div>
                    <div class="meta-item">
                      <el-icon><Clock /></el-icon>
                      <span>{{ item.timestamp_formatted || '未知时间' }}</span>
                    </div>
                  </div>
                </div>
                <div class="card-actions">
                  <el-button type="primary" size="small" @click="viewDetail(item)">
                    查看详情
                  </el-button>
                  <el-button 
                    v-if="isAdmin"
                    type="danger" 
                    size="small" 
                    @click.stop="handleDelete(item.id, item)"
                  >
                    删除
                  </el-button>
                </div>
              </div>
            </div>
          </el-card>
        </div>
        <!-- 显示记录总数 -->
        <div class="record-count">
          共 {{ detectionList.length }} 条记录
        </div>
      </div>

    </el-card>

    <!-- 识别记录详情对话框 -->
    <el-dialog v-model="detailDialogVisible" title="识别记录详情" width="70%">
      <div v-if="currentDetection">
        <el-descriptions :column="2" border>
          <el-descriptions-item label="用户">{{ currentDetection.user?.username || '未知用户' }}</el-descriptions-item>
          <el-descriptions-item label="检测时间">{{ currentDetection.timestamp_formatted || '未知时间' }}</el-descriptions-item>
          <el-descriptions-item label="检测结果">{{ currentDetection.detection_result }}</el-descriptions-item>
          <el-descriptions-item label="置信度">
            <el-tag :type="getConfidenceType(currentDetection.confidence)">
              {{ (currentDetection.confidence * 100).toFixed(2) }}%
            </el-tag>
          </el-descriptions-item>
        </el-descriptions>

        <div class="image-container">
          <div class="image-wrapper">
            <h4>原始图片</h4>
            <el-image
              :src="getFullImageUrl(currentDetection.image)"
              :preview-src-list="[getFullImageUrl(currentDetection.image)]"
              fit="contain"
              style="max-height: 400px;"
              @error="handleImageError('original', $event)"
            />
          </div>
          <div class="image-wrapper" v-if="currentDetection.annotated_image">
            <h4>标注图片</h4>
            <el-image
              :src="getFullImageUrl(currentDetection.annotated_image)"
              :preview-src-list="[getFullImageUrl(currentDetection.annotated_image)]"
              fit="contain"
              style="max-height: 400px;"
              @error="handleImageError('annotated', $event)"
            />
          </div>
        </div>

        <div v-if="currentDetection.pest_info" class="pest-info">
          <h3>病害信息</h3>
          <el-descriptions :column="1" border>
            <el-descriptions-item label="病害名称">{{ currentDetection.pest_info.name }}</el-descriptions-item>
            <el-descriptions-item label="作物类型">{{ currentDetection.pest_info.crop_type }}</el-descriptions-item>
            <el-descriptions-item label="症状描述">{{ currentDetection.pest_info.symptoms || '无' }}</el-descriptions-item>
            <el-descriptions-item label="详细描述">
              <div v-html="currentDetection.pest_info.description || '无'"></div>
            </el-descriptions-item>
          </el-descriptions>

          <div v-if="currentDetection.pest_info.prevention_methods?.length > 0" class="prevention-methods">
            <h3>防治方法</h3>
            <el-collapse>
              <el-collapse-item
                v-for="(method, index) in currentDetection.pest_info.prevention_methods"
                :key="index"
                :title="getPreventionMethodTitle(method.category)"
              >
                <div v-html="method.measure"></div>
              </el-collapse-item>
            </el-collapse>
          </div>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted, computed } from 'vue';
import { Picture, User, Clock, Download } from '@element-plus/icons-vue';
import { ElMessage, ElMessageBox } from 'element-plus';
import { getAllDetectionHistory, getDetectionHistory, deleteDetection, batchDeleteDetectionHistory } from '@/api/detection';
import { useAuthStore } from '@/stores/auth';
import http, { toAbsoluteMediaUrl } from '@/api/http';

const authStore = useAuthStore();
// 第 17 批：统一用 store 的管理员口径（is_staff / is_superuser / role=ADMIN），
// 与后端 all_users、以及路由守卫保持一致；原来只认 is_staff，
// 会让"仅角色管理员"进得来页面却看不到全选/删除等管理控件。
const isAdmin = computed(() => Boolean(authStore.isAdmin));

// 数据
const loading = ref(false);
const detectionList = ref([]);
const downloadingReportId = ref(null);
const currentDetection = ref(null);
const detailDialogVisible = ref(false);
const searchQuery = ref('');
const selectedItems = ref([]);
const isIndeterminate = ref(false);
const totalRecords = ref(0);

// 获取识别记录
const fetchDetectionHistory = async () => {
  loading.value = true;
  try {
    const response = await getAllDetectionHistory({
      search: searchQuery.value || undefined,
      // 本页是管理端：要的正是**全部用户**的记录。
      // 后端只有"管理员 + all_users=true"才会返回全部数据；
      // 第 21 批之前这里从未带过该参数，于是「识别记录管理」实际只显示管理员自己的记录，
      // 与「历史识别记录」页看起来高度重复。
      all_users: 'true',
    });
    detectionList.value = response.items || [];
    totalRecords.value = response.total || 0;
  } catch (error) {
    console.error('获取识别记录失败:', error);
    ElMessage.error('获取识别记录失败');
  } finally {
    loading.value = false;
  }
};

// 搜索
const handleSearch = () => {
  fetchDetectionHistory();
};

// 查看详情
const viewDetail = async (row) => {
  try {
    loading.value = true;
    console.log('Fetching detection detail for ID:', row.id);
    const detail = await getDetectionHistory({ id: row.id });
    console.log('API Response:', JSON.stringify(detail, null, 2));
    currentDetection.value = detail;
    console.log('Current detection data:', JSON.stringify(currentDetection.value, null, 2));
    detailDialogVisible.value = true;
  } catch (error) {
    console.error('获取详情失败:', error);
    ElMessage.error('获取详情失败');
  } finally {
    loading.value = false;
  }
};

// 删除单条识别记录
//
// 第 16 批补齐：模板里「删除」按钮一直绑定 handleDelete(item.id, item)，
// 但本组件**从未定义该函数**（只实现了 handleBatchDelete），点击会直接抛
// `handleDelete is not a function`，管理端的单条删除按钮完全不可用。
// 后端接口 DELETE /api/detection-history/{id}/ 一直存在，这里是把它接上。
const handleDelete = (id, item) => {
  if (!id) {
    ElMessage.error('删除失败：记录 ID 无效');
    return;
  }

  const label = item?.detection_result ? `「${item.detection_result}」` : '这条';

  ElMessageBox.confirm(
    `确定要删除${label}识别记录吗？此操作不可恢复！`,
    '警告',
    {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning',
    }
  )
    .then(async () => {
      try {
        await deleteDetection(id);
        ElMessage.success('删除成功');
        // 同步清理选中态，避免批量删除时带上已删除的 id
        selectedItems.value = selectedItems.value.filter((itemId) => itemId !== id);
        handleSelectionChange();
        await fetchDetectionHistory();
      } catch (error) {
        console.error('删除记录失败:', error);
        ElMessage.error(error.response?.data?.detail || error.message || '删除失败');
      }
    })
    .catch(() => {
      ElMessage.info('已取消删除');
    });
};

// 批量删除
const handleBatchDelete = () => {
  if (selectedItems.value.length === 0) {
    ElMessage.warning('请选择要删除的记录');
    return;
  }

  ElMessageBox.confirm(
    `确定要删除选中的 ${selectedItems.value.length} 条记录吗？此操作不可恢复！`,
    '警告',
    {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning',
    }
  )
    .then(async () => {
      try {
        await batchDeleteDetectionHistory({ ids: selectedItems.value });
        ElMessage.success(`成功删除 ${selectedItems.value.length} 条记录`);
        selectedItems.value = [];
        isIndeterminate.value = false;
        // 重新获取所有记录
        fetchDetectionHistory();
      } catch (error) {
        console.error('批量删除失败:', error);
        ElMessage.error('批量删除失败');
      }
    })
    .catch(() => {
      ElMessage.info('已取消删除');
    });
};

// 处理选择项变化
const handleSelectionChange = () => {
  isIndeterminate.value =
    selectedItems.value.length > 0 && selectedItems.value.length < detectionList.value.length;
};

// 勾选/取消勾选单条记录
const toggleSelection = (id, checked) => {
  if (checked) {
    if (!selectedItems.value.includes(id)) {
      selectedItems.value = [...selectedItems.value, id];
    }
  } else {
    selectedItems.value = selectedItems.value.filter((itemId) => itemId !== id);
  }
  handleSelectionChange();
};

// 全选/取消全选
const handleSelectAll = (val) => {
  if (val) {
    selectedItems.value = [...new Set(detectionList.value.map(item => item.id))];
  } else {
    selectedItems.value = [];
  }
  isIndeterminate.value = false;
};

// 检查是否已选择
const isSelected = (id) => {
  return selectedItems.value.includes(id);
};

// 根据置信度获取标签类型
const getConfidenceType = (confidence) => {
  if (!confidence) return 'info';
  if (confidence >= 0.8) return 'success';
  if (confidence >= 0.5) return 'warning';
  return 'danger';
};

// 获取防治方法标题
const getPreventionMethodTitle = (category) => {
  const titles = {
    'AGRICULTURAL': '农业防治',
    'CHEMICAL': '化学防治',
    'ECOLOGICAL': '生态防治',
    'PHYSICAL': '物理防治',
    'MONITORING': '监测预警'
  };
  return titles[category] || category;
};

// 获取完整的图片URL
// 说明：原来这里用 `${VITE_API_BASE_URL}${path}` 拼接，而 VITE_API_BASE_URL
// 已经包含 /api，会得到 ".../api/media/xxx" 这种错误地址（媒体文件在 /media/ 下）。
// 统一改用 @/api/http 的 toAbsoluteMediaUrl。
const getFullImageUrl = (path) => toAbsoluteMediaUrl(path);

// 处理图片加载错误
const handleImageError = (type, event) => {
  console.error(`加载${type === 'original' ? '原始' : '标注'}图片失败:`, event);
  ElMessage.error(`加载${type === 'original' ? '原始' : '标注'}图片失败`);
};

/**
 * 从 Content-Disposition 中解析文件名
 * 兼容三种形式：
 *  1. 整个头部被 MIME 编码：=?utf-8?b?YXR0YWNobWVudDsgZmlsZW5hbWU9...?=（Django 对非 ASCII 头的处理）
 *  2. RFC 5987：filename*=UTF-8''%E6%A3%80%E6%B5%8B...
 *  3. 普通：filename="检测报告.pdf"
 */
const parseFilename = (contentDisposition, fallback) => {
  if (!contentDisposition) return fallback;

  let header = contentDisposition;

  // 情况 1：MIME 编码
  const mimeMatch = header.match(/=\?utf-8\?b\?(.+?)\?=/i);
  if (mimeMatch) {
    try {
      const bytes = Uint8Array.from(atob(mimeMatch[1]), (c) => c.charCodeAt(0));
      header = new TextDecoder('utf-8').decode(bytes);
    } catch {
      /* 解码失败则继续用原始头 */
    }
  }

  // 情况 2：filename*=UTF-8''xxx
  const extendedMatch = header.match(/filename\*=\s*UTF-8''([^;\n]+)/i);
  if (extendedMatch) {
    try {
      return decodeURIComponent(extendedMatch[1].trim().replace(/^["']|["']$/g, ''));
    } catch {
      /* 继续尝试普通形式 */
    }
  }

  // 情况 3：filename=xxx
  const plainMatch = header.match(/filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/);
  if (plainMatch && plainMatch[1]) {
    const name = plainMatch[1].replace(/['"]/g, '').trim();
    if (name) {
      try {
        return decodeURIComponent(name);
      } catch {
        return name;
      }
    }
  }

  return fallback;
};

// 下载报告
// 说明：原来用 localStorage.getItem('token') 取 Token，但项目实际保存的键是
// 'auth_token'，导致请求头是 "Token null"，后端直接 401 —— 管理端的下载报告一直是失效的。
// 现在改用统一的 http 客户端（自动附带正确的 Token 与 CSRF 头）。
const downloadReport = async (id) => {
  try {
    downloadingReportId.value = id;
    const response = await http.get(`/detection-history/${id}/report/`, {
      responseType: 'blob',
    });

    // 创建下载链接
    const url = window.URL.createObjectURL(new Blob([response.data], { type: 'application/pdf' }));
    const link = document.createElement('a');
    const filename = parseFilename(response.headers['content-disposition'], `检测报告_${id}.pdf`);

    link.href = url;
    link.setAttribute('download', filename);
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.URL.revokeObjectURL(url);

    ElMessage.success('报告下载成功');
  } catch (error) {
    console.error('下载报告失败:', error);
    let detail = error?.response?.data;
    // blob 响应下的错误体需要读取文本
    if (detail instanceof Blob) {
      const text = await detail.text();
      try {
        const parsed = JSON.parse(text);
        detail = parsed;
      } catch {
        detail = null;
      }
    }
    ElMessage.error('下载报告失败: ' + (detail?.error || detail?.detail || error.message || '请稍后重试'));
  } finally {
    downloadingReportId.value = null;
  }
};

// 组件挂载时获取数据
onMounted(() => {
  fetchDetectionHistory();
});
</script>

<style scoped>
/* 选择框样式 */
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
  padding-bottom: 10px;
  border-bottom: 1px solid #eee;
}

.user-info {
  display: flex;
  align-items: center;
  gap: 8px;
}

.user-avatar {
  background-color: #409EFF;
  color: white;
  font-weight: bold;
}

.username {
  font-size: 14px;
  font-weight: 500;
}

.card-selection {
  position: absolute;
  top: 10px;
  left: 10px;
  z-index: 2;
}

/* 选中状态 */
.detection-card {
  position: relative;
  transition: all 0.3s;
}

.detection-card.selected {
  box-shadow: 0 0 0 2px #409EFF;
  border-color: #409EFF;
}

/* 批量操作栏 */
.batch-actions {
  margin-bottom: 20px;
  padding: 10px 0;
  border-bottom: 1px solid #ebeef5;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

/* 响应式调整 */
@media (max-width: 768px) {
  .header-actions {
    flex-direction: column;
    gap: 10px;
  }
  
  .header-actions .el-input {
    width: 100% !important;
    margin-right: 0 !important;
  }
}

.detection-history {
  padding: 20px;
}

.pagination-container {
  margin-top: 24px;
  display: flex;
  justify-content: center;
}

.detection-grid {
  padding: 12px 0;
}

.grid-container {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 24px;
  padding: 0 8px;
}

.detection-card {
  transition: all 0.3s ease;
  height: 100%;
  display: flex;
  flex-direction: column;
  
  &:hover {
    transform: translateY(-4px);
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  }
}

.card-image {
  position: relative;
  padding-top: 75%;
  overflow: hidden;
  cursor: pointer;
  background-color: #f5f7fa;
  border-radius: 4px;
  
  .detection-image,
  .no-image,
  .image-error {
    position: absolute;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    display: flex;
    align-items: center;
    justify-content: center;
    flex-direction: column;
    color: #909399;
    background-color: #f5f7fa;
  }
  
  .el-image {
    width: 100%;
    height: 100%;
  }
  
  .el-icon {
    font-size: 36px;
    margin-bottom: 8px;
  }
}

.card-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  padding: 16px 0 0;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 12px;
  
  .detection-title {
    margin: 0;
    font-size: 16px;
    font-weight: 500;
    color: #303133;
    flex: 1;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    padding-right: 8px;
  }
}

.card-meta {
  margin-bottom: 16px;
  
  .meta-item {
    display: flex;
    align-items: center;
    font-size: 13px;
    color: #606266;
    margin-bottom: 6px;
    
    .el-icon {
      margin-right: 6px;
      font-size: 14px;
    }
  }
}

.card-actions {
  margin-top: auto;
  display: flex;
  justify-content: space-between;
  padding-top: 12px;
  border-top: 1px solid #ebeef5;
  
  .el-button + .el-button {
    margin-left: 8px;
  }
}

.empty-state {
  padding: 80px 0;
  text-align: center;
  color: #909399;
}

/* 响应式调整 */
@media (max-width: 1200px) {
  .grid-container {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 768px) {
  .grid-container {
    grid-template-columns: 1fr;
  }
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.header-actions {
  flex-wrap: wrap;
}

.image-wrapper {
  flex: 1;
  min-width: 300px;
}

.image-wrapper h4 {
  margin: 10px 0;
  text-align: center;
}

.pest-info {
  margin-top: 20px;
}

.prevention-methods {
  margin-top: 20px;
}

/* ================= 现代化覆写（设计变量见 assets/theme.css） ================= */
.detection-history {
  width: 100%;
  max-width: 1560px;
  margin: 0 auto;
  padding: 8px 24px 48px;
  box-sizing: border-box;
}

.detection-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  flex-wrap: wrap;
  padding: 24px 28px;
  margin-bottom: 22px;
  border-radius: var(--radius-xl);
  background: var(--gradient-brand-soft);
  border: 1px solid var(--border);
  box-shadow: var(--shadow-sm);
}

.detection-header h1,
.detection-header h2 {
  margin: 0 0 6px;
  font-size: 24px;
  font-weight: 800;
  color: var(--brand-800);
}

.record-count {
  font-size: 13.5px;
  color: var(--ink-500);
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.grid-container {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 20px;
}

.detection-card {
  display: flex;
  flex-direction: column;
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  background: var(--surface);
  box-shadow: var(--shadow-sm);
  overflow: hidden;
  transition: transform var(--dur) var(--ease), box-shadow var(--dur) var(--ease),
    border-color var(--dur) var(--ease);
}

.detection-card:hover {
  transform: translateY(-5px);
  box-shadow: var(--shadow-lg);
}

.detection-card.selected {
  border-color: var(--brand-500);
  box-shadow: 0 0 0 3px rgba(42, 127, 83, 0.15);
}

.card-image,
.image-wrapper {
  position: relative;
  aspect-ratio: 4 / 3;
  overflow: hidden;
  background: var(--ink-50);
}

.detection-image {
  width: 100%;
  height: 100%;
  object-fit: cover;
  transition: transform 0.45s var(--ease);
}

.detection-card:hover .detection-image {
  transform: scale(1.05);
}

.no-image,
.image-error {
  display: grid;
  place-items: center;
  width: 100%;
  height: 100%;
  color: var(--ink-300);
  font-size: 30px;
  background: var(--ink-50);
}

.card-content,
.detection-info {
  display: flex;
  flex-direction: column;
  flex: 1;
  padding: 18px;
  gap: 8px;
}

.card-header {
  padding: 14px 18px;
  background: var(--surface);
  border-bottom: 1px solid var(--border);
}

.user-info {
  display: flex;
  align-items: center;
  gap: 10px;
}

.user-avatar {
  width: 32px;
  height: 32px;
  display: grid;
  place-items: center;
  border-radius: 50%;
  background: var(--gradient-brand);
  color: #fff;
  font-size: 13px;
  font-weight: 700;
}

.username {
  font-size: 14px;
  font-weight: 600;
  color: var(--ink-700);
}

.card-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}

.meta-item {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 12.5px;
  color: var(--ink-500);
}

.meta-item i {
  color: var(--brand-500);
}

.pest-info {
  font-size: 14px;
  font-weight: 600;
  color: var(--brand-700);
}

.card-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: auto;
  padding-top: 12px;
}

.download-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  border: 1px solid var(--brand-200);
  border-radius: var(--radius-pill);
  background: var(--brand-50);
  color: var(--brand-700);
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: all var(--dur) var(--ease);
}

.download-btn:hover:not(:disabled) {
  background: var(--gradient-brand);
  border-color: transparent;
  color: #fff;
}

.download-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.card-selection {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: var(--ink-500);
}

.prevention-methods {
  font-size: 13px;
  color: var(--ink-500);
}

.empty-state {
  padding: 64px 24px;
  text-align: center;
  color: var(--ink-400);
  font-size: 15px;
}

@media (max-width: 768px) {
  .detection-history {
    padding: 0 16px 32px;
  }

  .grid-container {
    grid-template-columns: 1fr;
  }

  .detection-header {
    padding: 20px;
  }
}
</style>
