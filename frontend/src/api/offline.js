/**
 * 离线资料包接口（第 50 批）
 */
import http from './http';
import { readWikiPack, saveWikiPack, wikiPackVersion } from '@/utils/offlineStorage';
import { t } from '@/i18n';  // 第 83 批：错误文案跟随语言

/**
 * 拉取病害百科离线资料包并缓存到本地
 * · 带上次的 version：内容没变时后端只回 `unchanged:true`，省流量；
 * · 失败（例如断网）时返回本地缓存，让页面仍能显示。
 */
export async function refreshOfflinePack() {
  const known = wikiPackVersion();
  try {
    const response = await http.get('pests/offline-pack/', {
      params: known ? { since: known } : {},
    });
    const data = response.data || {};
    if (data.unchanged) {
      const cached = readWikiPack();
      if (cached) return { ...cached, fromCache: true, unchanged: true };
    }
    saveWikiPack(data);
    return { ...data, fromCache: false };
  } catch (error) {
    const cached = readWikiPack();
    if (cached) return { ...cached, fromCache: true, error: error?.message || t('msg.networkError') };
    throw error;
  }
}

export { readWikiPack };
