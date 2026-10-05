import { parseMarkdown, getPreviewText } from '@/utils/markdown';

export default {
  install: (app) => {
    // 注册全局方法
    app.config.globalProperties.$markdown = parseMarkdown;
    
    // 注册全局过滤器
    app.config.globalProperties.$filters = {
      markdown: parseMarkdown,
      previewText: getPreviewText
    };
    
    // 提供全局属性
    app.provide('markdown', parseMarkdown);
    app.provide('previewText', getPreviewText);
  }
};
