import { createApp } from 'vue';
import { createPinia } from 'pinia';
import Vant from 'vant';
import 'vant/lib/index.css';

import '@/styles/app.css';
import App from './App.vue';
import router from './router';

/**
 * 移动端入口
 *
 * 说明：这里**全量注册 Vant**（app.use(Vant) + 全量样式）。
 * 按需引入需要 unplugin-vue-components 之类的构建插件，多一个依赖、多一层
 * "组件没引进来却不报错"的坑；移动端目前只有 5 个页面，全量引入的代价
 * （gzip 后约 100KB 左右）远比调试成本低。
 */
const app = createApp(App);

app.use(createPinia());
app.use(router);
app.use(Vant);

app.mount('#app');
