/**
 * Element Plus 按需注册
 * ------------------------------------------------------------------
 * 原先 main.js 使用 `app.use(ElementPlus)`，会把**整包**组件打进产物
 * （优化前 element-plus chunk 约 877KB / gzip 264KB）。
 *
 * 这里改为只注册项目实际用到的组件（由脚本从所有模板中提取 `el-*` 标签生成），
 * 从而让打包器把未使用的组件摇掉。
 *
 * 安全措施（重要）：
 *   1. 仍然全局引入 element-plus 的完整 CSS（`element-plus/dist/index.css`），
 *      这样 ElMessage / ElMessageBox / ElLoading 这些**编程式调用**的样式一定存在，
 *      不会出现“提示框变成无样式白框”的问题；
 *   2. 组件清单由脚本自动比对模板中的 `el-*` 标签，漏注册会被检查脚本发现；
 *   3. 中文语言包通过 <el-config-provider :locale="zhCn">（无额外 DOM）提供。
 *
 * 若新增了模板里没出现过的组件（例如 el-date-picker），请同步补充到下面的列表。
 */
import {
  ElAlert,
  ElAvatar,
  ElBacktop,
  ElBreadcrumb,
  ElBreadcrumbItem,
  ElButton,
  ElButtonGroup,
  ElCard,
  ElCheckbox,
  ElCheckboxGroup,  // 第 128 批：漏注册会导致 group 里的 v-model 静默失效
  ElCol,
  ElCollapse,
  ElCollapseItem,
  ElConfigProvider,
  ElDescriptions,
  ElDescriptionsItem,
  // 第 78 批：日期选择器。原来「历史记录」页用的是浏览器原生 <input type="date">，
  // 它的占位符（"年/月/日"）由**浏览器语言**决定，页面切英文也变不了；
  // 换成 el-date-picker 后跟随 el-config-provider 的语言包，切语言立即变。
  ElDatePicker,
  ElDialog,
  ElDivider,
  ElDropdown,
  ElDropdownItem,
  ElDropdownMenu,
  ElEmpty,
  ElForm,
  ElFormItem,
  ElIcon,
  ElImage,
  ElInput,
  ElInputNumber,  // 第 128 批：种植日历的任务表单（此前漏注册，月份填不进去）
  ElLoading,
  ElMessage,
  ElMessageBox,
  ElNotification,
  ElOption,
  ElPagination,
  ElPopconfirm,  // 第 162 批：下面 components 里还补了 ElPopover（那次漏注册会让整块模板不渲染）
  ElPopover,
  ElRadio,  // 第 41 批：补导入（下面注释说明为什么此前是坏的）
  ElRadioButton,
  ElRadioGroup,
  ElRow,
  ElSelect,
  ElSkeleton,
  ElSkeletonItem,
  ElSwitch,
  ElTable,
  ElTableColumn,
  ElTabPane,
  ElTabs,
  ElTag,
  ElTooltip,
  ElUpload,
} from 'element-plus';

// 需要注册的全部组件
const components = [
  ElAlert,
  ElAvatar,
  ElBacktop,
  ElBreadcrumb,
  ElBreadcrumbItem,
  ElButton,
  ElButtonGroup,
  ElCard,
  ElCheckbox,
  // 第 128 批：<el-checkbox-group> 此前**没有注册**（只注册了 ElCheckbox）。
  // 后果比"少个样式"隐蔽得多：单个 checkbox 看着正常，但它拿不到 group 的上下文，
  // 于是 v-model 完全不生效 —— 用户管理里"改角色 → 勾选内容模块"的四个框
  // 全是未勾选、点一下只改 DOM，提交上去还是老值（浏览器 E2E 才抓出来）。
  ElCheckboxGroup,
  ElCol,
  ElCollapse,
  ElCollapseItem,
  ElConfigProvider,
  ElDescriptions,
  ElDescriptionsItem,
  ElDatePicker,  // 第 78 批：日期选择器（历史记录页的日期筛选）
  ElDialog,
  ElDivider,
  ElDropdown,
  ElDropdownItem,
  ElDropdownMenu,
  ElEmpty,
  ElForm,
  ElFormItem,
  ElIcon,
  ElImage,
  ElInput,
  // 第 128 批：<el-input-number> 同样**没有注册**（种植日历里"农事任务"表单用它填月份）。
  // 这是上一轮跑检查脚本才发现的**既有**问题：那个输入框一直是坏的
  // （渲染成未知元素，数字填不进去）。
  ElInputNumber,
  ElOption,
  ElPagination,
  ElPopconfirm,
  // 第 162 批：ElPopover 此前没有注册 —— 离线队列面板用了 <el-popover>，
  // Vue 直接报 "Failed to resolve component: el-popover"，
  // **整块模板都不渲染**（页眉那个「N 张同步失败」的入口因此消失）。
  // 这类"用了没注册"的坑本文件里已经踩过三次（ElInputNumber / ElRadio / 这次的 ElPopover）——
  // `npm run check` 里的 check:components 现在会直接报出来，别再靠肉眼。
  ElPopover,
  // 第 41 批修复：ElRadio **此前没有注册**（只注册了 RadioGroup / RadioButton），
  // 于是任何 <el-radio> 都被当成未知自定义元素渲染 —— 界面上只剩一行文字、
  // 点了没反应（举报弹窗的"举报理由"就是这样）。这里补上导入。
  ElRadio,
  ElRadioButton,
  ElRadioGroup,
  ElRow,
  ElSelect,
  ElSkeleton,
  ElSkeletonItem,
  ElSwitch,
  ElTable,
  ElTableColumn,
  ElTabPane,
  ElTabs,
  ElTag,
  ElTooltip,
  ElUpload,
];

/**
 * 在 app 上注册 Element Plus 组件与指令
 * @param {import('vue').App} app
 */
export function setupElementPlus(app) {
  components.forEach((component) => {
    // 组件均带有 name（如 ElButton），直接用 name 注册，避免手写映射出错
    if (component && component.name) {
      app.component(component.name, component);
    }
  });

  // v-loading 指令（全站 6 处使用）
  if (ElLoading && ElLoading.directive) {
    app.directive('loading', ElLoading.directive);
  }

  // 恢复 app.use(ElementPlus) 会注入的全局属性
  // 说明：EditPostView.vue 里使用了 proxy.$message，按需注册后必须手动补上，
  // 否则会报 “Cannot read properties of undefined (reading 'success')”。
  app.config.globalProperties.$message = ElMessage;
  app.config.globalProperties.$notify = ElNotification;
  app.config.globalProperties.$msgbox = ElMessageBox;
  app.config.globalProperties.$alert = ElMessageBox.alert;
  app.config.globalProperties.$confirm = ElMessageBox.confirm;
  app.config.globalProperties.$prompt = ElMessageBox.prompt;
  app.config.globalProperties.$loading = ElLoading.service;
}

export default setupElementPlus;
