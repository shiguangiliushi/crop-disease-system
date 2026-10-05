/**
 * 内容类接口（移动端，第 91 批）
 *
 * 目前只有一个用途：**识别纠错时要选"正确病害"**。
 * 纠错若只存"对/错"，对模型没有增量信息（负反馈只能计数）；
 * 带上正确类别后，这条反馈就成了可训练样本（后端 Feedback.corrected_pest，
 * 导出见 backend 的 `manage.py export_feedback_dataset`）。
 */
import http from './http';

/**
 * 病害精简列表（id / 名称）
 *
 * 只取三个字段：38 条量级，一次拉完，不必再引一个下拉组件。
 * 兼容 DRF 分页（`results`）与裸数组两种返回。
 */
export async function fetchPestOptions({ pageSize = 200 } = {}) {
  const response = await http.get('/pests/', { params: { page: 1, page_size: pageSize } });
  const data = response.data;
  const list = Array.isArray(data)
    ? data
    : (data?.results || data?.data?.items || data?.items || []);

  return list.map((item) => ({
    id: item.id,
    // 英文界面下优先英文名，缺失回落中文
    text: item.name_en || item.name || item.english_identifier,
    nameZh: item.name,
  }));
}

export default { fetchPestOptions };
