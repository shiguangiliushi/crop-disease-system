/**
 * 行业动态订阅接口（第 402 批 · P2-11）
 * ------------------------------------------------------------------
 * 读者可以订阅**一个分类**（如「政策解读」）或**一个病害词条**，
 * 有新动态 / 该病害相关新闻时由后端投递一条 type='news' 的站内通知。
 *
 * 四个接口：
 *   · GET    /api/news-subscriptions/            我的订阅（标准分页）
 *   · POST   /api/news-subscriptions/            新增订阅 {target_type, category|pest}
 *   · DELETE /api/news-subscriptions/<id>/       删除自己的订阅
 *   · GET    /api/news-subscriptions/check/      查某个目标的订阅状态 {subscribed, id}
 *
 * 约定（与后端契约一致）：
 *   · 重复订阅后端返回 400、每人最多 50 条 —— 这类错误**原样抛给调用方**，
 *     页面按自己的文案提示，不在这一层吞掉；
 *   · `check` 接口在未登录时返回 401、接口未上线时 404 —— 调用方（列表/详情页）
 *     自己决定静默降级为「未订阅」，本模块不替它做决定。
 */
import http from './http';

/**
 * 我的订阅列表（分页）
 *
 * 归一化成 `{ count, results }`：后端是标准分页结构；若老后端/测试桩直接返回
 * 数组，也兼容成同样的形状，页面只认一种结构。
 *
 * @param {object} [params] { page, page_size }
 * @returns {Promise<{count:number, results:Array}>}
 */
export async function fetchNewsSubscriptions(params = {}) {
  const response = await http.get('news-subscriptions/', { params });
  const data = response.data;

  if (Array.isArray(data)) {
    return { count: data.length, results: data };
  }
  const results = Array.isArray(data?.results) ? data.results : [];
  return {
    count: typeof data?.count === 'number' ? data.count : results.length,
    results,
  };
}

/**
 * 新增订阅
 *
 * @param {{target_type:'category'|'pest', category?:string, pest?:number}} payload
 * @returns {Promise<object>} 新建的订阅记录 {id, target_type, category, pest, ...}
 */
export async function createNewsSubscription(payload = {}) {
  const response = await http.post('news-subscriptions/', payload);
  return response.data;
}

/**
 * 删除自己的订阅
 *
 * @param {number|string} id 订阅记录 id
 * @returns {Promise<boolean>}
 */
export async function deleteNewsSubscription(id) {
  await http.delete(`news-subscriptions/${id}/`);
  return true;
}

/**
 * 查询某个订阅目标的状态
 *
 * 失败（401/404/网络）直接抛给调用方：列表页与病害详情页在 catch 里把按钮
 * 降级成「未订阅」，不能让订阅辅助功能阻断内容浏览。
 *
 * @param {{target_type:'category'|'pest', category?:string, pest?:number}} params
 * @returns {Promise<{subscribed:boolean, id:number|null}>}
 */
export async function checkNewsSubscription(params = {}) {
  const response = await http.get('news-subscriptions/check/', { params });
  const data = response.data;
  return {
    subscribed: Boolean(data?.subscribed),
    id: data?.id ?? null,
  };
}

export default {
  fetchNewsSubscriptions,
  createNewsSubscription,
  deleteNewsSubscription,
  checkNewsSubscription,
};
