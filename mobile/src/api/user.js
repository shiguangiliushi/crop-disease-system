/**
 * 用户与积分接口（移动端「我的」页）
 *
 * | 接口 | 用途 |
 * |---|---|
 * | GET /api/users/{id}/stats/ | 发帖 / 评论 / 获赞 |
 * | GET /api/users/me/points/  | 积分与等级 |
 * | GET /api/detection-history/?page_size=1 | 借 total 得到"识别次数" |
 *
 * 这些统计都**不是**主流程，接口失败一律返回兜底空值，
 * 不让"我的"页面因为某个统计接口 500 而整页打不开。
 */
import http from './http';

export async function fetchUserStats(userId) {
  try {
    const response = await http.get(`/users/${userId}/stats/`);
    const data = response.data?.data || response.data || {};
    return {
      postCount: data.post_count ?? 0,
      commentCount: data.comment_count ?? 0,
      likeCount: data.like_count ?? 0,
    };
  } catch (error) {
    console.warn('[user] 统计接口失败:', error?.message || error);
    return { postCount: 0, commentCount: 0, likeCount: 0 };
  }
}

export async function fetchMyPoints() {
  try {
    const response = await http.get('/users/me/points/');
    const data = response.data?.data || response.data || {};
    return {
      points: data.points ?? data.total_points ?? 0,
      level: data.level ?? null,
      levelName: data.level_name || data.level_display || '',
    };
  } catch (error) {
    console.warn('[user] 积分接口失败:', error?.message || error);
    return { points: 0, level: null, levelName: '' };
  }
}

export async function fetchDetectionCount() {
  try {
    const response = await http.get('/detection-history/', { params: { page: 1, page_size: 1 } });
    const inner = response.data?.data || response.data || {};
    return inner.total ?? 0;
  } catch (error) {
    console.warn('[user] 识别次数接口失败:', error?.message || error);
    return 0;
  }
}

export default { fetchUserStats, fetchMyPoints, fetchDetectionCount };
