/**
 * 病害百科批量导入接口（第 44 批）
 */
import http from './http';

/** 下载导入模板（xlsx） */
export function downloadPestTemplate() {
  return http.get('pests/import-template/', { responseType: 'blob' }).then((res) => res.data);
}

/**
 * 批量导入病害
 * @param {File} file .xlsx / .csv
 * @param {'upsert'|'create_only'} mode
 */
export function importPests(file, mode = 'upsert') {
  const form = new FormData();
  form.append('file', file);
  form.append('mode', mode);
  return http
    .post('pests/import/', form, { headers: { 'Content-Type': 'multipart/form-data' } })
    .then((res) => res.data);
}
