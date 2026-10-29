/**
 * 「我的」页要的三个统计（第 236 批）
 *
 * 与现有 H5（`mobile/src/api/user.js`）一致：
 *   GET /api/users/{id}/stats/   发帖 / 评论 / 获赞
 *   GET /api/users/me/points/    积分与等级
 *   GET /api/detection-history/?page_size=1   借 total 拿"识别次数"
 *
 * 三个都是**非主流程**：任何一个失败都返回兜底值，不让整页打不开。
 * （H5 版第 232 批也踩过"统计接口 500 导致整页白屏"的坑。）
 */
import { request } from '../utils/request'

export async function fetchUserStats(userId) {
  try {
    const body = await request({ url: `/users/${userId}/stats/` })
    const data = body.data || body || {}
    return {
      postCount: data.post_count ?? 0,
      commentCount: data.comment_count ?? 0,
      likeCount: data.like_count ?? 0,
    }
  } catch (error) {
    console.warn('[profile] 统计接口失败', error?.message || error)
    return { postCount: 0, commentCount: 0, likeCount: 0 }
  }
}

export async function fetchMyPoints() {
  try {
    const body = await request({ url: '/users/me/points/' })
    const data = body.data || body || {}
    return {
      points: data.points ?? data.total_points ?? 0,
      levelName: data.level_name || data.level_display || '',
    }
  } catch (error) {
    console.warn('[profile] 积分接口失败', error?.message || error)
    return { points: 0, levelName: '' }
  }
}

export async function fetchDetectionCount() {
  try {
    const body = await request({ url: '/detection-history/', data: { page: 1, page_size: 1 } })
    const inner = body.data || body || {}
    return inner.total ?? 0
  } catch (error) {
    console.warn('[profile] 识别次数接口失败', error?.message || error)
    return 0
  }
}
