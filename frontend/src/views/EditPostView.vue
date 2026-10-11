<template>
  <div class="edit-post">
    <div class="post-form-container">
      <h2>{{ currentRoute.params.id ? t('post.titleEdit') : t('post.titleNew') }}</h2>
      
      <!--
        开发信息（第 161 批：改成**默认折叠**，并说明只在开发模式出现）
        ----------------------------------------------------------------
        这块是当年排查"编辑页整体不可用"时留下的：它把加载状态、帖子 ID、内容长度、
        草稿保存状态摊在页面最上方，占掉一整屏 —— 截个图、给用户看都显得没做完。
        信息本身有用（自测时一眼看出加载到没有），所以保留，但收进 <details> 里。
      -->
      <details v-if="isDev" class="debug-info">
        <summary>{{ t('post.debugSummary') }}</summary>
        <p>{{ t('post.debugStatus') }}: {{ loading ? t('post.loadingState') : t('post.loadedState') }}</p>
        <p>{{ t('post.debugPostId') }}: {{ currentRoute.params.id || t('post.newPost') }}</p>
        <p>{{ t('post.debugContentLength') }}: {{ form.content?.length || 0 }} {{ t('post.lengthUnit') }}</p>
        <p>{{ t('post.debugSaveStatus') }}: {{ saveStatus || t('post.savedState') }}</p>
      </details>
      
      <el-form 
        ref="postForm" 
        :model="form" 
        :rules="rules" 
        label-width="80px"
        label-position="top"
        v-loading="loading"
      >
        <el-form-item :label="t('post.boardSelect')" prop="board">
          <el-select 
            v-model="form.board" 
            :placeholder="t('post.boardPlaceholder')"
            style="width: 100%"
            :disabled="!isModerator"
          >
            <el-option
              v-for="board in boards"
              :key="board.id"
              :label="localizedField(board, 'name')"
              :value="board.id"
            >
              <div style="display: flex; align-items: center">
                <!-- 第 161 批：版块图标在库里存的是 fa-* 名字（`fa-comments` 之类），
                     原来拼成 `el-icon-xxx` → Element Plus 2 没有图标字体，一片空白。
                     NewPostView 早就按 fa-* 渲染了，这里对齐。 -->
                <i :class="`fas ${board.icon || 'fa-comments'}`" style="margin-right: 8px"></i>
                <span>{{ localizedField(board, 'name') }}</span>
              </div>
            </el-option>
          </el-select>
        </el-form-item>

        <el-form-item :label="t('post.titleLabel')" prop="title">
          <el-input 
            v-model="form.title" 
            :placeholder="t('post.titlePlaceholderEdit')"
            maxlength="100"
            show-word-limit
          />
        </el-form-item>

        <el-form-item :label="t('post.contentLabel')" prop="content">
          <!--
            第 161 批：工具栏三处一起修
            · 图标：el-icon-* 是 Element UI v2 的写法，Element Plus 2 没有图标字体 →
              界面上一排**空方块**（NewPostView 里早就注释过这个坑，这里漏改了）；
            · 插入内容：原来插的是 markdown 片段（**粗体**），而库里正文存的是 **HTML**
              （详情页用 sanitizeRichText 渲染）—— 两边口径不一致，插进去的东西预览里也不对；
              现在统一插 HTML 片段。
          -->
          <div class="editor-toolbar">
            <el-button-group>
              <el-button size="small" @click="insertText(t('post.htmlBold'))" :title="t('post.bold')">
                <i class="fas fa-bold"></i>
              </el-button>
              <el-button size="small" @click="insertText(t('post.htmlItalic'))" :title="t('post.italic')">
                <i class="fas fa-italic"></i>
              </el-button>
              <el-button size="small" @click="insertText(t('post.htmlInlineCode'))" :title="t('post.inlineCode')">
                <i class="fas fa-code"></i>
              </el-button>
              <el-button size="small" @click="insertText(t('post.htmlCodeBlock'))" :title="t('post.codeBlock')">
                <i class="fas fa-file-code"></i>
              </el-button>
              <el-button size="small" @click="insertText(t('post.htmlLink'))" :title="t('post.link')">
                <i class="fas fa-link"></i>
              </el-button>
              <el-button size="small" @click="insertText(t('post.htmlImage'))" :title="t('post.image')">
                <i class="fas fa-image"></i>
              </el-button>
              <el-upload
                class="upload-demo"
                :action="uploadUrl"
                :on-success="handleImageUploadSuccess"
                :on-error="handleImageUploadError"
                :show-file-list="false"
                :headers="uploadHeaders"
                :before-upload="beforeImageUpload"
              >
                <el-button size="small" type="primary" :title="t('post.uploadImage')">
                  <i class="fas fa-upload"></i> {{ t('post.uploadImage') }}
                </el-button>
              </el-upload>
            </el-button-group>
          </div>
          <el-input
            v-model="form.content"
            id="content"
            type="textarea"
            :rows="12"
            :placeholder="t('post.contentPlaceholder')"
            resize="none"
            ref="editor"
          ></el-input>
          <p class="field-hint">{{ t('post.contentFormatHint') }}</p>
          <div class="preview" v-if="form.content">
            <h4>{{ t('post.preview') }}</h4>
            <div class="markdown-body" v-html="compiledMarkdown"></div>
          </div>
        </el-form-item>

        <!--
          第 86 批：英文版本（可选）
          ------------------------------------------------------------------
          编辑页会把库里已有的译文读进来（只展示，不改就不回传），作者可以直接
          修订成更准确的英文 —— 一旦在这里改过，后端会把它记成「人工翻译」，
          自动翻译与 `translate_forum_content --force` 都不会再覆盖。
        -->
        <el-form-item class="en-block">
          <template #label>
            <span class="en-label">
              {{ t('post.englishSection') }}
              <em>{{ t('post.englishOptional') }}</em>
              <button type="button" class="en-toggle" @click="showEnglish = !showEnglish">
                {{ showEnglish ? t('post.englishHide') : t('post.englishFill') }}
              </button>
            </span>
          </template>
          <div v-show="showEnglish" class="en-fields">
            <p class="field-hint">
              <i class="fas fa-language"></i>
              {{ t('post.englishHint') }}
              <template v-if="translationMeta.hasTranslation">
                · {{ translationMeta.source === 'manual' ? t('trans.manual') : t('trans.auto') }}
                <span v-if="translationMeta.stale" class="en-stale">· {{ t('trans.stale') }}</span>
              </template>
            </p>
            <el-input
              v-model="form.title_en"
              maxlength="200"
              show-word-limit
              :placeholder="t('post.titleEnPlaceholder')"
              @input="markEnglishTouched"
            />
            <el-input
              v-model="form.content_en"
              type="textarea"
              :rows="6"
              :placeholder="t('post.contentEnPlaceholder')"
              @input="markEnglishTouched"
            />
          </div>
        </el-form-item>

        <el-form-item class="form-actions">
          <div class="action-left">
            <el-button 
              type="primary" 
              @click="() => submitForm()"
              :loading="submitting"
              :disabled="!isDirty"
            >
              {{ currentRoute.params.id ? t('post.updatePost') : t('post.submit') }}
            </el-button>
            
            <el-button 
              type="info" 
              plain 
              @click="() => submitForm(true)"
              :loading="isSaving"
              :disabled="!isDirty"
            >
              {{ t('post.saveDraft') }}
            </el-button>
            
            <el-button @click="cancel">
              {{ isDirty ? t('post.cancelEdit') : t('post.back') }}
            </el-button>
            
            <span v-if="saveStatus" class="save-status">
              <!-- 第 161 批：`el-icon-loading` 在 Element Plus 2 里没有对应字体图标，
                   会显示成一个空方块；换成 Font Awesome 的转圈图标。 -->
              <i class="fas fa-spinner fa-spin" v-if="isSaving"></i>
              {{ saveStatus }}
            </span>
          </div>
          
          <div class="action-right" v-if="currentRoute.params.id">
            <el-button 
              type="danger" 
              plain 
              @click="showDeleteDialog = true"
              :disabled="deleting"
            >
              <i class="fas fa-trash"></i> {{ t('post.deletePost') }}
            </el-button>
          </div>
        </el-form-item>
      </el-form>
    </div>

    <!-- 删除确认对话框 -->
    <el-dialog
      :title="t('post.deleteTitle')"
      v-model="showDeleteDialog"
      width="400px"
    >
      <p>{{ t('post.deleteConfirm') }}</p>
      <template #footer>
        <el-button @click="showDeleteDialog = false">{{ t('common.cancel') }}</el-button>
        <el-button type="danger" @click="deletePost" :loading="deleting">
          {{ t('post.confirmDelete') }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script>
import { ref, onMounted, computed, nextTick, watch, onBeforeUnmount, getCurrentInstance } from 'vue';
import { useRouter, useRoute } from 'vue-router';
import { ElMessage, ElMessageBox, ElLoading } from 'element-plus';
import { getForumBoards, getPost, updatePost, createPost, deletePost, uploadImage } from '@/api/forum';
import { useUserStore } from '@/stores/user';
import { sanitizeRichText } from '@/utils/richText';  // 第 161 批：预览与详情页同一口径
import { debounce } from 'lodash-es';
// 身份读写统一走适配器（sessionStorage 优先）
import { getToken } from '@/utils/authStorage';
import { timeAgo } from '@/utils/date';  // 第 84 批：相对时间跟随语言
import { useI18n } from '@/i18n';
import { useLocalized } from '@/utils/localized';  // 第 55 批：多语言（第 72 批起也用于版块名等内容数据）
import { useUnsavedChanges } from '@/composables/useUnsavedChanges';  // 第 97 批：离开前提醒（含站内导航）

// 第 161 批：原来这里有一段 `marked.setOptions({...})` —— 预览已改用 sanitizeRichText
// （与详情页同一口径），marked 不再参与渲染，这段配置随之删除。

// 辅助函数：检查字符串是否是Base64图片
const isBase64Image = (str) => {
  return /^data:image\/(jpeg|jpg|png|gif|webp);base64,/.test(str);
};

// 辅助函数：从Base64字符串中提取内容和类型
const extractBase64Data = (base64) => {
  const matches = base64.match(/^data:image\/(jpeg|jpg|png|gif|webp);base64,(.+)$/);
  if (!matches || matches.length !== 3) {
    return null;
  }
  return {
    type: matches[1],
    data: matches[2]
  };
};

export default {
  name: 'EditPostView',
  setup() {
    const { t } = useI18n();  // 第 55 批：多语言
    const { localizedField } = useLocalized();
    const router = useRouter();
    const route = useRoute();
    const userStore = useUserStore();
    const editor = ref(null);
    
    // 在 setup 函数中定义 currentRoute
    const currentRoute = route; // 用于模板中访问

    // 第 16 批修复：模板里 `v-if="isDev"` 的调试信息块引用了从未声明的 isDev，
    // 该属性恒为 undefined → 整块调试信息永远不会显示（本意是"开发环境显示"）。
    // 现按原意声明为开发环境开关。
    const isDev = import.meta.env.DEV;
    
    const form = ref({
      board: '',
      title: '',
      content: '',
      // 第 86 批：英文版本（可选）。编辑页会把**已有译文**读进来展示，
      // 但只有作者真的改动过（enTouched）才回传 —— 详见 syncEnglishFields()。
      title_en: '',
      content_en: '',
      is_essence: false,
      is_pinned: false
    });

    /** 英文区块是否展开（有内容时自动展开） */
    const showEnglish = ref(false);
    /** 作者是否**改过**英文字段：决定提交时是否回传（避免把机器译文"认领"为人工译文） */
    const enTouched = ref(false);
    /** 当前帖子在库里的译文状态（用于给作者提示） */
    const translationMeta = ref({ hasTranslation: false, stale: false, source: '' });

    const markEnglishTouched = () => {
      enTouched.value = true;
    };

    /**
     * 第 86 批：把英文字段挂到提交数据上
     *
     * 只有作者**动过**英文字段（enTouched）才回传，理由有两条：
     *   ① 编辑页会把已有译文读进表单展示，若原样回传，后端会把这份（很可能是机器）
     *      译文记成"人工翻译"，此后自动翻译再也不更新它；
     *   ② 作者只想改中文正文时，不该顺手把英文"认领"下来。
     * 另外只在**非空**时提交：空串在后端会被忽略，但少发一个字段语义更明确。
     */
    const attachEnglishFields = (payload) => {
      if (!enTouched.value) return payload;
      const titleEn = String(form.value.title_en || '').trim();
      const contentEn = String(form.value.content_en || '').trim();
      if (!titleEn && !contentEn) return payload;
      if (titleEn) payload.title_en = titleEn;
      if (contentEn) payload.content_en = contentEn;
      return payload;
    };
    
    const originalForm = ref(JSON.parse(JSON.stringify(form.value)));
    const boards = ref([]);
    const loading = ref(true);
    const submitting = ref(false);
    const showDeleteDialog = ref(false);
    const deleting = ref(false);
    const postForm = ref(null);
    const autoSaveTimer = ref(null);
    const lastSaved = ref(null);
    const isDirty = ref(false);
    const isSaving = ref(false);
    // 第 161 批：初值原来是裸的英文 'saved' —— 中文界面里会看到「保存状态: saved」。
    // 改成空串（未保存过时不显示状态），后续都由 t(...) 赋值。
    const saveStatus = ref('');
    const showPreview = ref(false);
    // 第 24 批：新建帖子时，第一次自动保存会真的创建一条草稿 —— 记住它的 id，
    // 否则每 30 秒的自动保存都会再新建一条，论坛里会堆满半成品帖子。
    const draftPostId = ref(null);
    
    // 切换预览状态
    const togglePreview = () => {
      showPreview.value = !showPreview.value;
    };
    
    // 计算预览内容
    // 第 161 批：预览改用 sanitizeRichText —— 与详情页 / 内容审核页**同一口径**。
    // 原来这里用 marked 把正文当 markdown 渲染，而库里存的是 HTML（<p>…</p>），
    // 于是预览里是一堆转义后的标签，和发布之后看到的样子**不一致**。
    const previewContent = computed(() => sanitizeRichText(form.value.content || ''));
    
    const { proxy } = getCurrentInstance();
    
    // 图片上传相关
    // 修复：原地址是 `${VITE_API_BASE_URL}/api/upload/image/`，而 VITE_API_BASE_URL 已含 /api，
    // 会拼成 /api/api/upload/image/；Token 也取错了键（项目存的是 auth_token）。
    const apiBase = (import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000/api').replace(/\/+$/, '');
    const uploadUrl = ref(`${apiBase}/upload/image/`);
      
    const getCookie = (name) => {
      const value = `; ${document.cookie}`;
      const parts = value.split(`; ${name}=`);
      if (parts.length === 2) return parts.pop().split(';').shift();
      return '';
    };
    
    const uploadHeaders = computed(() => ({
      'Authorization': `Token ${getToken() || ''}`,
      'X-CSRFToken': getCookie('csrftoken')
    }));
    
    // 在编辑器中插入文本
    const insertText = (text) => {
      if (editor.value) {
        const textarea = editor.value.$el.querySelector('textarea');
        if (textarea) {
          const start = textarea.selectionStart;
          const end = textarea.selectionEnd;
          const content = form.value.content;
          
          // 在光标位置插入文本
          form.value.content = content.substring(0, start) + text + content.substring(end);
          
          // 更新光标位置
          nextTick(() => {
            const newPos = start + text.length;
            textarea.setSelectionRange(newPos, newPos);
            textarea.focus();
          });
        } else {
          // 如果找不到textarea，直接追加到内容末尾
          form.value.content += text;
        }
      } else {
        // 如果编辑器未初始化，直接追加到内容
        form.value.content += text;
      }
    };
    
    // 图片上传成功处理
    const handleImageUploadSuccess = (response, file) => {
      proxy.$message.success(t('post.uploadImageOk'));
      // 第 161 批：插入 HTML 图片标签（正文是 HTML；原来插的 markdown 语法不会被渲染）
      if (response && response.url) {
        insertText(`<img src="${response.url}" alt="${file.name}" />`);
      }
    };
    
    // 图片上传失败处理
    const handleImageUploadError = (error, file) => {
      console.error('图片上传失败:', error);
      let errorMessage = t('post.uploadImageFailed');
      if (error.response && error.response.data) {
        errorMessage = error.response.data.detail || error.response.data.message || errorMessage;
      }
      proxy.$message.error(errorMessage);
    };
    
    // 图片上传前验证
    const beforeImageUpload = (file) => {
      const isImage = file.type.startsWith('image/');
      const isLt5M = file.size / 1024 / 1024 < 5;

      if (!isImage) {
        proxy.$message.error(t('msg.imageOnly'));
        return false;
      }
      if (!isLt5M) {
        proxy.$message.error(t('msg.imageTooLarge5'));
        return false;
      }
      return true;
    };
    
    const wordCount = computed(() => {
      return form.value.content ? form.value.content.trim().length : 0;
    });
    
    // 监听表单变化
    watch(() => ({ ...form.value }), (newVal, oldVal) => {
      if (loading.value) return;
      isDirty.value = JSON.stringify(newVal) !== JSON.stringify(originalForm);
    }, { deep: true });

    // ========================================================================
    // 第 97 批：站内导航也要提醒（原来只有 beforeunload）
    // ------------------------------------------------------------------------
    // 原实现是一个局部的 beforeunload 处理函数，**只**在刷新/关标签时弹浏览器原生确认框；
    // 用户点导航栏"论坛"或页内"返回"按钮走的是 vue-router，**完全不触发** ——
    // 编辑到一半点了别的链接，改动就没了，一句提示都没有。
    // 现在交给统一的 composable：站内导航用 Element Plus 确认框，离开站点仍用原生的。
    // ========================================================================
    useUnsavedChanges(() => isDirty.value);
    
    const isModerator = computed(() => {
      // 这里可以根据实际权限系统判断用户是否有版主权限
      return userStore.user?.is_staff || false;
    });
    
    // 第 161 批：与 previewContent 同一个口径（详情页怎么渲染，预览就怎么渲染）
    const compiledMarkdown = computed(() => sanitizeRichText(form.value.content || ''));
    
    const rules = {
      // 第 83 批：校验文案接入 i18n
      board: [
        { required: true, message: t('forum.boardRequired'), trigger: 'change' }
      ],
      title: [
        { required: true, message: t('forum.titleRequired'), trigger: 'blur' },
        { min: 5, max: 100, message: t('forum.titleLength'), trigger: 'blur' }
      ],
      content: [
        { required: true, message: t('forum.contentRequired'), trigger: 'blur' },
        { min: 10, message: t('forum.contentMin'), trigger: 'blur' }
      ]
    };
    
    // 检查用户是否有编辑权限
    const checkEditPermission = (post) => {
      if (!userStore.user) {
        return { canEdit: false, message: t('msg.loginRequired') };
      }
      
      // 管理员可以编辑任何帖子
      if (userStore.user.is_staff) {
        return { canEdit: true };
      }
      
      // 普通用户只能编辑自己的帖子
      if (post.author && post.author.id === userStore.user.id) {
        return { canEdit: true };
      }
      
      return { canEdit: false, message: t('post.noPermissionEditPost') };
    };
    
    // 获取帖子详情
    const fetchPost = async () => {
      try {
        loading.value = true;
        const postId = route.params.id;
        console.log('开始获取帖子详情，ID:', postId);
        
        if (!postId) {
          console.log('未提供帖子ID，进入新建帖子模式');
          loading.value = false;
          return;
        }
        
        const response = await getPost(postId);
        console.log('获取到帖子详情响应:', response);
        
        if (response) {
          console.log('处理帖子内容，原始内容:', response.content);
          
          // 检查是否有权限编辑
          const { canEdit, message } = checkEditPermission(response);
          if (!canEdit) {
            ElMessage.warning(message || t('post.noPermissionEditPost'));
            router.push({ name: 'forum' });
            return;
          }
          
          // 直接使用原始内容，不进行HTML标签处理
          let content = response.content || '';
          console.log('处理后的内容:', content);
          
          // 设置表单数据
          form.value = {
            board: response.board.id,
            title: response.title,
            content: content,
            // 第 86 批：把库里已有的英文译文读进表单，作者可以直接改。
            // 注意 enTouched 仍为 false —— 只"展示"不等于作者"填写"，
            // 提交时必须靠 enTouched 区分，否则会把机器译文误标成"人工翻译"。
            title_en: response.title_en || '',
            content_en: response.content_en || '',
            is_essence: response.is_essence || false,
            is_pinned: response.is_pinned || false
          };

          translationMeta.value = {
            hasTranslation: Boolean((response.title_en || '').trim() || (response.content_en || '').trim()),
            stale: Boolean(response.translation_stale),
            source: response.translation_source || ''
          };
          enTouched.value = false;
          showEnglish.value = Boolean(
            (response.title_en || '').trim() || (response.content_en || '').trim()
          );
          
          // 保存原始数据用于比较
          originalForm.value = JSON.parse(JSON.stringify(form.value));
          // 重置脏数据标记
          isDirty.value = false;
          
          console.log('表单数据已更新:', form.value);
        }
      } catch (error) {
        console.error('获取帖子失败:', error);
        ElMessage.error(t('msg.requestFailedWith', { detail: error.message || t('msg.unknownError') }));
        // 跳转到帖子详情页
        router.push({ name: 'post-detail', params: { id: route.params.id } });
        loading.value = false;
      } finally {
        loading.value = false;
      }
      }
    
    const handleImageUpload = async (file) => {
      const loadingInstance = ElLoading.service({
        lock: true,
        text: t('post.imageUploading'),
        background: 'rgba(0, 0, 0, 0.7)'
      });
      
      try {
        // 检查图片大小（限制5MB）
        const MAX_SIZE = 5 * 1024 * 1024; // 5MB
        if (file.size > MAX_SIZE) {
          throw new Error(t('msg.imageTooLarge5'));
        }
        
        // 检查图片类型
        const validTypes = ['image/jpeg', 'image/png', 'image/gif', 'image/webp'];
        if (!validTypes.includes(file.raw.type)) {
          throw new Error(t('post.unsupportedImage'));
        }
        
        // 创建FormData
        const formData = new FormData();
        formData.append('image', file.raw);
        
        // 调用上传API
        const response = await uploadImage(formData);
        
        if (!response || !response.url) {
          throw new Error(t('post.uploadFailed'));
        }
        
        // 第 163 批：插入 HTML 图片标签。
        // 原来这里插的是 Markdown `![名字](url)` —— 正文口径是 HTML，
        // 插 markdown 的后果是"插了图，预览和详情页都看不到"（用户会以为图片丢了）。
        insertText(`<img src="${response.url}" alt="${file.name || t('post.imageFallback')}" />`);
        
        ElMessage.success(t('post.uploadImageOk'));
        return response.url;
      } catch (error) {
        console.error('图片上传失败:', error);
        ElMessage.error(t('post.uploadImageFailedDetail', { detail: error.message || t('msg.unknownError') }));
        throw error;
      } finally {
        loadingInstance.close();
      }
    };
    
    // 加载草稿
    const loadDraft = () => {
      try {
        const draft = localStorage.getItem(`post_draft_${route.params.id || 'new'}`);
        if (draft) {
          const draftData = JSON.parse(draft);
          form.value.title = draftData.title || '';
          form.value.content = draftData.content || '';
          form.value.board = draftData.board || '';
          
          // 显示恢复草稿的提示
          if (draftData.updatedAt) {
            ElMessageBox.confirm(
              t('post.draftRestoreConfirm'),
              t('post.draftRestoreTitle'),
              {
                confirmButtonText: t('msg.restore'),
                cancelButtonText: t('msg.discard'),
                type: 'warning'
              }
            ).then(() => {
              // 用户选择恢复草稿
              ElMessage.success(t('post.draftRestored'));
            }).catch(() => {
              // 用户选择丢弃草稿
              localStorage.removeItem(`post_draft_${route.params.id || 'new'}`);
            });
          }
        }
      } catch (error) {
        console.error('加载草稿失败:', error);
      }
    };
    
    // 清除草稿
    const clearDraft = () => {
      localStorage.removeItem(`post_draft_${route.params.id || 'new'}`);
    };
    
    const previewPost = () => {
      showPreview.value = !showPreview.value;
    };
    
    // 处理内容中的Base64图片
    const processBase64Images = async (content) => {
      if (!content) return content;

      // 第 163 批：**base64 图片有两种写法**，两种都要认，否则会出现
      // "我明明插了图，提交后图却留在 base64 里（或干脆丢了）"：
      //   · Markdown：`![alt](data:image/png;base64,…)`  ← 老正文/老工具栏
      //   · HTML    ：`<img src="data:image/png;base64,…">` ← 现在的工具栏与粘贴
      // 旧版正则只认 Markdown 那一种，于是 HTML 路径插进来的图**根本抓不到**。
      const base64Regex = new RegExp(
        [
          /!\[([^\]]*)\]\((data:image\/(?:jpeg|jpg|png|gif|webp);base64,[^)]+)\)/.source,
          /<img\b[^>]*src="(data:image\/(?:jpeg|jpg|png|gif|webp);base64,[^"]+)"[^>]*>/i.source,
        ].join('|'),
        'g',
      );
      const matches = content.match(base64Regex) || [];

      if (matches.length === 0) return content;

      const loadingInstance = ElLoading.service({
        lock: true,
        text: t('msg.uploadingImage'),
        background: 'rgba(0, 0, 0, 0.7)'
      });

      try {
        let processedContent = content;

        for (const match of matches) {
          try {
            // 兼容两种写法：先试 Markdown 的 `![alt](data:…)`，再试 HTML 的 `<img src="data:…">`
            const markdownMatch = match.match(/!\[(.*?)\]\((data:image\/\w+;base64,[^)]+)\)/);
            const htmlMatch = match.match(/src="(data:image\/[^"]+)"/);
            const altText = markdownMatch ? markdownMatch[1] : '';
            const base64Data = markdownMatch ? markdownMatch[2] : (htmlMatch ? htmlMatch[1] : '');
            if (!base64Data) continue;

            const imageData = extractBase64Data(base64Data);
            if (!imageData) continue;
            
            // 创建Blob对象
            const byteCharacters = atob(imageData.data);
            const byteNumbers = Array.from({ length: byteCharacters.length }, (_, i) => byteCharacters.charCodeAt(i));
            const byteArray = new Uint8Array(byteNumbers);
            const blob = new Blob([byteArray], { type: `image/${imageData.type}` });
            
            // 创建FormData并上传
            const formData = new FormData();
            const fileName = `image_${Date.now()}.${imageData.type}`;
            formData.append('image', blob, fileName);
            
            const response = await uploadImage(formData);
            
            if (response && response.url) {
              // 第 163 批：统一替换成 **HTML** 图片标签（正文口径是 HTML）
              const safeAlt = String(altText || t('post.imageFallback')).replace(/"/g, '&quot;');
              processedContent = processedContent.replace(
                match, `<img src="${response.url}" alt="${safeAlt}" />`,
              );
            }
          } catch (error) {
            console.error('上传Base64图片失败:', error);
            // 保留原始Base64数据，不中断处理其他图片
            continue;
          }
        }
        
        return processedContent;
      } catch (error) {
        console.error('处理Base64图片时出错:', error);
        return content; // 出错时返回原始内容
      } finally {
        loadingInstance.close();
      }
    };
    
    // 自动保存草稿（真正干活的函数）
    //
    // 第 84 批：这里原来只有 `const autoSaveDraft = debounce(async () => {...}, 3000)`
    // 一个名字，而 submitForm 的两条分支（表单校验失败后"改存草稿"、"保存失败后重试"）
    // 调用的却是 **从未定义过的 `saveDraft()`** —— 一走到那里就是 ReferenceError，
    // 被外层 catch 吞掉，用户点了"保存草稿"其实什么都没发生。
    // 现在把函数体提取成 performDraftSave：定时器用 debounce 包装，显式调用直接执行。
    /**
     * @param {boolean} force 用户**显式**点了"保存草稿"（表单校验失败后改存草稿、
     *        保存失败后重试）时为 true —— 这时即使 isDirty 为 false（比如打开帖子
     *        后一个字没改）也要真的写一次，否则按钮就是个摆设。
     */
    const performDraftSave = async (force = false) => {
      if ((!force && !isDirty.value) || isSaving.value) {
        console.log('内容未修改或正在保存，跳过自动保存');
        return;
      }
      
      try {
        isSaving.value = true;
        saveStatus.value = t('post.draftSaving');
        
        // 基本验证
        if (!form.value.title?.trim() || !form.value.content?.trim()) {
          console.log('标题或内容为空，跳过自动保存');
          saveStatus.value = t('post.draftEmpty');
          setTimeout(() => saveStatus.value = '', 3000);
          return;
        }
        
        const postData = {
          board_id: form.value.board,
          title: form.value.title.trim(),
          content: form.value.content,
          is_draft: true
        };
        // 第 86 批：只有作者**改过**英文才回传（enTouched），否则会把库里的机器译文
        // 当成"人工翻译"重新提交，之后自动翻译就再也不会更新它了。
        attachEnglishFields(postData);

        // 第 24 批：置顶/精华只有版主能设置（后端现在也会拦），普通作者不必也不该发送
        if (isModerator.value) {
          postData.is_essence = !!form.value.is_essence;
          postData.is_pinned = !!form.value.is_pinned;
        }

        console.log('自动保存草稿数据:', postData);

        let response;
        // 编辑已有帖子 → 更新；新建帖子 → 第一次创建后记住 id，后续都走更新
        const existingId = route.params.id || draftPostId.value;
        if (existingId) {
          response = await updatePost(existingId, postData);
        } else {
          response = await createPost(postData);
          if (response?.id) {
            draftPostId.value = response.id;
          }
        }
        
        // 清除本地草稿
        clearDraft();
        
        lastSaved.value = new Date();
        saveStatus.value = t('post.draftSaved', { time: formatTime(lastSaved.value) });
        
        console.log('草稿保存成功:', response);
        return true;
      } catch (error) {
        console.error('自动保存草稿失败:', error);
        saveStatus.value = t('post.draftSaveFailed');
        return false;
      } finally {
        isSaving.value = false;
        const timer = setTimeout(() => {
          saveStatus.value = '';
          clearTimeout(timer);
        }, 3000);
      }
    };
    
    /** 定时器用：30s 一次、且只在内容有改动时触发（debounce 避免连续触发） */
    const autoSaveDraft = debounce(performDraftSave, 3000);
    
    // 生命周期钩子
    onMounted(() => {
      // 加载草稿
      loadDraft();
    });
    
    const submitForm = async (isDraft = false) => {
      try {
        // 验证表单（草稿不需要验证）
        if (!isDraft) {
          try {
            await postForm.value.validate();
          } catch (validateError) {
            // 验证失败时提供保存草稿的选项
            try {
              await ElMessageBox.confirm(
                t('post.draftFormInvalid'),
                t('post.saveDraft'),
                {
                  confirmButtonText: t('post.saveDraft'),
                  cancelButtonText: t('msg.cancel'),
                  type: 'warning'
                }
              );
              
              // 用户选择保存草稿（第 84 批：原来调用的 saveDraft 未定义）
              await performDraftSave(true);
              return;
            } catch (e) {
              // 用户取消保存草稿
              return;
            }
          }
        }
        
        submitting.value = true;
        
        // 处理内容中的Base64图片
        let processedContent = form.value.content.trim();
        if (processedContent) {
          try {
            processedContent = await processBase64Images(processedContent);
            // 更新表单内容为处理后的内容
            form.value.content = processedContent;
          } catch (error) {
            console.error('处理图片时出错:', error);
            ElMessage.warning(t('post.uploadPartialFailed'));
          }
        }
        
        // 准备提交数据
        const postData = {
          board_id: form.value.board,  // 使用 board_id 字段
          title: form.value.title.trim(),
          content: processedContent,
          is_draft: !!isDraft
        };
        // 第 86 批：作者改过英文才带上（见 attachEnglishFields 的注释）
        attachEnglishFields(postData);

        // 第 24 批：置顶/精华仅版主可设置（后端也会拦，普通作者发送只会 403）
        if (isModerator.value) {
          postData.is_essence = !!form.value.is_essence;
          postData.is_pinned = !!form.value.is_pinned;
        }

        console.log('提交数据:', postData);

        // 若之前自动保存已经建过草稿，这里针对同一条更新，避免产生重复帖子
        const targetId = route.params.id || draftPostId.value;
        let response; // 声明 response 变量
        if (targetId) {
          // 更新现有帖子
          response = await updatePost(targetId, postData);
          console.log('更新帖子响应:', response);
        } else {
          // 创建新帖子
          response = await createPost(postData);
          if (response?.id) draftPostId.value = response.id;
          console.log('创建帖子响应:', response);
        }
        
        // createPost/updatePost 返回的是**帖子数据本身**（forum.js 里已 .then(res => res.data)），
        // 不是 AxiosResponse，所以不能用 response.status 判断 HTTP 状态码：
        // 帖子自身的 status 是 'published'/'draft'，永远不等于 200/201
        // → 原来这里恒为 false，服务端明明已保存，前端却无条件抛
        //   "发布失败：服务器返回异常"，用户会重复提交。
        if (response && response.id) {
          // 清除草稿
          clearDraft();
          
          // 显示成功消息
          const successMessage = isDraft ? t('post.draftSavedNoTime') : t('post.postOk');
          ElMessage.success(successMessage);
          
          // 跳转到详情页
          if (!isDraft) {
            router.push({ 
              // ⚠️ 路由名是**小写**的 `post-detail`。这里原来写 'PostDetail'，
              // Vue Router 找不到匹配 → 发布成功后跳到一个空白页（帖子其实已发布成功）。
              name: 'post-detail', 
              params: { id: targetId || response.id },
              query: { updated: 'true' }
            });
          }
        } else {
          throw new Error(isDraft ? `${t('post.draftSaveFailed')}: ${t('post.serverError')}` : `${t('post.publishFailed')}: ${t('post.serverError')}`);
        }
      } catch (error) {
        console.error(isDraft ? '保存草稿失败:' : '发布失败:', error);
        
        // 用户点击取消时不显示错误提示
        if (error === 'cancel' || error === 'close') {
          return;
        }
        
        // 显示友好的错误信息
        let errorMessage = isDraft ? t('post.draftSaveFailed') : t('post.publishFailed');
        if (error.response) {
          const { status, data } = error.response;
          if (status === 403) {
            errorMessage = t('post.noPermission');
          } else if (status === 404) {
            // 第 158 批：原来用的是 `post.postDeleted`，而那个键**被定义了两次**
            // （这条 404 文案 + 保存成功的「帖子已删除」），后者静默覆盖前者 →
            // 这里一直显示成"帖子已删除"。现改用独立的 `post.postNotFound`。
            errorMessage = t('post.postNotFound');
          } else if (data && data.detail) {
            errorMessage = data.detail;
          } else if (data && data.message) {
            errorMessage = data.message;
          }
        } else if (error.request) {
          errorMessage = t('msg.networkError');
        } else if (error.message) {
          errorMessage = error.message;
        }
        
        ElMessage.error(errorMessage);
        
        // 保存草稿失败时，提供重试选项
        if (isDraft) {
          try {
            await ElMessageBox.confirm(
              t('post.retryConfirm', { message: errorMessage }),
              t('post.draftSaveFailedTitle'),
              {
                confirmButtonText: t('msg.retry'),
                cancelButtonText: t('msg.cancel'),
                type: 'error'
              }
            );
            
            // 用户选择重试（第 84 批：原来调用的 saveDraft 未定义）
            await performDraftSave(true);
          } catch (e) {
            // 用户取消重试
          }
        }
      } finally {
        submitting.value = false;
      }
    };
    
    // 格式化时间
    // 第 84 批：删掉本地这份重复实现，改用共享的 timeAgo（跟随语言），
    // 超过一天时回落成绝对日期时间（与原来一致）。
    const formatTime = (date) => {
      if (!date) return '';
      
      const d = new Date(date);
      const now = new Date();
      const diff = Math.floor((now - d) / 1000); // 秒数差
      
      if (diff < 86400) return timeAgo(d);
      
      // 超过一天显示具体日期
      return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
    };
    
    const deleteCurrentPost = async () => {
      try {
        deleting.value = true;
        await deletePost(route.params.id);
        
        ElMessage.success(t('post.postDeleted'));
        router.push({ name: 'forum' });
      } catch (error) {
        console.error('删除失败:', error);
        ElMessage.error(error.message || t('msg.deleteFailed'));
      } finally {
        deleting.value = false;
        showDeleteDialog.value = false;
      }
    };
    
    const cancel = () => {
      router.go(-1);
    };
    
    // 设置键盘快捷键
    const setupKeyboardShortcuts = () => {
      const handleKeyDown = (e) => {
        // 保存快捷键: Ctrl+S 或 Command+S
        if ((e.ctrlKey || e.metaKey) && e.key === 's') {
          e.preventDefault();
          submitForm(true); // 保存草稿
        }
        
        // 预览快捷键: Ctrl+Enter 或 Command+Enter
        if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
          e.preventDefault();
          submitForm();
        }
      };
      
      window.addEventListener('keydown', handleKeyDown);
      
      // 返回清理函数
      return () => {
        window.removeEventListener('keydown', handleKeyDown);
      };
    };
    
    // 离开页面前的确认
    // 第 97 批：这里原来**只**处理刷新/关标签（beforeunload），站内导航完全没拦。
    // 现在统一由 useUnsavedChanges 接管（它内部也挂 beforeunload，文案走 i18n），
    // 所以这段手写实现已删除 —— 保留会让同一个提示出现两次。
    // 见文件上方 `useUnsavedChanges(() => isDirty.value)`。
    
    // 声明自动保存的定时器变量
    let autoSaveInterval;
    
    // 组件挂载时执行
    onMounted(async () => {
      // 设置键盘快捷键
      const cleanupShortcuts = setupKeyboardShortcuts();

      // 第 161 批：**先加载版块列表**。
      //
      // 原来 `getForumBoards` 只 import、从来没调用 → `boards` 一直是空数组 →
      // 下拉框没有任何选项，只能把 `form.board` 的原始值显示出来
      //（界面上就是孤零零一个「1」）；顺带版块图标（`board.icon`）也就无从显示。
      // 放在 fetchPost 之前，让选择框有选项可用；失败也不挡编辑（只提示一下）。
      try {
        const boardResponse = await getForumBoards();
        boards.value = Array.isArray(boardResponse)
          ? boardResponse
          : (boardResponse?.results || boardResponse?.data || []);
      } catch (error) {
        console.warn('[edit-post] 版块列表加载失败（版块下拉将为空）:', error?.message || error);
      }

      // 加载帖子或草稿
      if (route.params.id) {
        await fetchPost();
      } else {
        // 新帖子，尝试加载草稿
        loadDraft();
        loading.value = false;
      }
      
      // 设置自动保存定时器
      autoSaveInterval = setInterval(() => {
        if (isDirty.value) {
          autoSaveDraft();
        }
      }, 30000); // 每30秒自动保存一次
      
      // 组件卸载时清理
      onBeforeUnmount(() => {
        // 清理键盘快捷键
        if (typeof cleanupShortcuts === 'function') {
          cleanupShortcuts();
        }
        // （第 97 批：beforeunload 由 useUnsavedChanges 自己在 onBeforeUnmount 里注销，
        //   这里不再手动清 —— 原来的 cleanupBeforeUnload 已随手写实现一起删除）
        // 清理自动保存定时器
        if (autoSaveInterval) {
          clearInterval(autoSaveInterval);
        }
        // 清理自动保存超时
        if (autoSaveTimer.value) {
          clearTimeout(autoSaveTimer.value);
        }
      });
    });
    
    return {
      t,
      localizedField,
      form,
      // 第 86 批：可选英文版本（展开状态 / 是否改过 / 当前译文状态）
      showEnglish,
      enTouched,
      translationMeta,
      markEnglishTouched,
      rules,
      boards,
      loading,
      submitting,
      showPreview,
      togglePreview,  // 添加切换预览方法
      showDeleteDialog,
      deleting,
      previewContent,
      uploadUrl,
      uploadHeaders,
      handleImageUploadSuccess,
      handleImageUploadError,
      beforeImageUpload,
      insertText,
      editor,
      postForm,
      isModerator,
      handleImageUpload,
      previewPost,
      submitForm,
      deletePost: deleteCurrentPost,
      cancel,
      // 添加缺失的响应式属性
      isDirty,
      isSaving,
      saveStatus,
      currentRoute,
      isDev,
      wordCount,
      compiledMarkdown
    };
  }
};
</script>

<style scoped>
.edit-post {
  max-width: 1000px;
  margin: 0 auto;
  padding: 20px;
  background: #fff;
  border-radius: 8px;
  box-shadow: 0 2px 12px 0 rgba(0, 0, 0, 0.1);
}

.post-form-container {
  padding: 20px;
}

h2 {
  color: #303133;
  margin-bottom: 24px;
  padding-bottom: 12px;
  border-bottom: 1px solid #ebeef5;
}

.debug-info {
  background: #f5f7fa;
  padding: 12px;
  border-radius: 4px;
  margin-bottom: 20px;
  font-size: 13px;
  color: #606266;
  border-left: 4px solid var(--brand-400, #5fb088);
}

/* 第 161 批：折叠后只占一行，点开才展开明细 */
.debug-info summary {
  cursor: pointer;
  color: var(--brand-600, #2f7a55);
  outline: none;
}

.debug-info p {
  margin: 6px 0 0;
}

.debug-info p {
  margin: 4px 0;
  line-height: 1.5;
}

.editor-container {
  position: relative;
  margin-bottom: 20px;
}

.editor-toolbar {
  margin-bottom: 10px;
  padding: 8px;
  background: #f5f7fa;
  border-radius: 4px;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.editor-toolbar .el-button {
  margin-right: 4px;
  margin-bottom: 4px;
}

.el-textarea__inner {
  min-height: 300px !important;
  font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', 'Consolas', 'source-code-pro', monospace;
  line-height: 1.6;
  font-size: 14px;
  padding: 15px;
  resize: vertical;
}

.preview {
  margin-top: 20px;
  padding: 15px;
  border: 1px solid #ebeef5;
  border-radius: 4px;
  background: #f9f9f9;
  min-height: 100px;
}

.preview h4 {
  margin-top: 0;
  color: #606266;
  padding-bottom: 8px;
  border-bottom: 1px solid #ebeef5;
  margin-bottom: 12px;
}

.markdown-body {
  font-size: 14px;
  line-height: 1.7;
  word-wrap: break-word;
}

.markdown-body :deep(h1),
.markdown-body :deep(h2),
.markdown-body :deep(h3) {
  margin-top: 24px;
  margin-bottom: 16px;
  font-weight: 600;
  line-height: 1.25;
}

.markdown-body :deep(p) {
  margin-top: 0;
  margin-bottom: 16px;
}

.markdown-body :deep(ul),
.markdown-body :deep(ol) {
  padding-left: 2em;
  margin-top: 0;
  margin-bottom: 16px;
}

.markdown-body :deep(code) {
  padding: 0.2em 0.4em;
  margin: 0;
  font-size: 85%;
  background-color: rgba(27, 31, 35, 0.05);
  border-radius: 3px;
}

.markdown-body :deep(pre) {
  padding: 16px;
  overflow: auto;
  font-size: 85%;
  line-height: 1.45;
  background-color: #f6f8fa;
  border-radius: 3px;
  margin-bottom: 16px;
}

.markdown-body :deep(pre code) {
  background-color: transparent;
  padding: 0;
  margin: 0;
  font-size: 100%;
  word-break: normal;
  white-space: pre;
  border: 0;
}

.markdown-body :deep(blockquote) {
  padding: 0 1em;
  color: #6a737d;
  border-left: 0.25em solid #dfe2e5;
  margin: 0 0 16px 0;
}

.form-actions {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 30px;
  padding-top: 20px;
  border-top: 1px solid #ebeef5;
}

.save-status {
  margin-left: 15px;
  font-size: 13px;
  color: #67c23a;
}

/* 第 161 批：`.save-status .el-icon-loading` 已删 —— 那个图标类在 Element Plus 2 里
   不存在（显示成空方块），现在用 Font Awesome 的 `fa-spinner fa-spin`。 */

.upload-area {
  margin-top: 10px;
}

.upload-tip {
  font-size: 12px;
  color: #909399;
  margin-top: 5px;
}

/* 响应式调整 */
@media (max-width: 768px) {
  .edit-post {
    padding: 10px;
  }
  
  .form-actions {
    flex-direction: column;
    gap: 10px;
  }
  
  .action-left, .action-right {
    width: 100%;
    display: flex;
    justify-content: center;
  }
}

/* 表单操作区域样式 */
.form-actions {
  margin-top: 24px;
  padding-top: 16px;
  border-top: 1px solid #eee;
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
}

.action-left {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}

.action-right {
  margin-left: auto;
}

.save-status {
  margin-left: 12px;
  font-size: 12px;
  color: #909399;
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

/* 编辑器工具栏样式 */
.editor-toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-bottom: 8px;
  padding: 6px 8px;
  background-color: #f8f9fa;
  border: 1px solid #dcdfe6;
  border-radius: 4px 4px 0 0;
}

/* 预览区域样式 */
.preview-container {
  margin-top: 12px;
  border: 1px solid #e0e0e0;
  border-radius: 4px;
  overflow: hidden;
}

.preview-header {
  padding: 8px 16px;
  background-color: #f5f7fa;
  border-bottom: 1px solid #e0e0e0;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.preview-content {
  padding: 16px;
  min-height: 100px;
  background-color: #fff;
  line-height: 1.6;
  overflow-y: auto;
  max-height: 400px;
}

/* 响应式调整 */
@media (max-width: 768px) {
  .form-actions {
    flex-direction: column;
    align-items: flex-start;
    gap: 12px;
  }
  
  .action-right {
    margin-left: 0;
    width: 100%;
    display: flex;
    justify-content: flex-end;
  }
}

.edit-post {
  max-width: 1000px;
  margin: 0 auto;
  padding: 20px;
}

.post-form-container {
  background: #fff;
  padding: 24px;
  border-radius: 4px;
  box-shadow: 0 2px 12px 0 rgba(0, 0, 0, 0.1);
}

h2 {
  margin-top: 0;
  margin-bottom: 24px;
  padding-bottom: 12px;
  border-bottom: 1px solid #f0f2f5;
  font-size: 20px;
  color: #303133;
}

.editor-item {
  margin-bottom: 24px;
}

.editor-toolbar {
  display: flex;
  align-items: center;
  margin-bottom: 10px;
  padding: 6px 0;
  border: 1px solid #dcdfe6;
  border-bottom: none;
  border-radius: 4px 4px 0 0;
  background-color: #f8f9fa;
}

.preview-container {
  margin-top: 10px;
  border: 1px solid #dcdfe6;
  border-radius: 4px;
  overflow: hidden;
}

.preview-header {
  padding: 8px 16px;
  background-color: #f8f9fa;
  border-bottom: 1px solid #dcdfe6;
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 14px;
  color: #606266;
}

.preview-content {
  padding: 16px;
  min-height: 100px;
  background-color: #fff;
  line-height: 1.6;
}

.preview-content :deep(p) {
  margin: 0 0 16px 0;
}

.preview-content :deep(img) {
  max-width: 100%;
  height: auto;
}

.preview-content :deep(pre) {
  background-color: #f6f8fa;
  padding: 16px;
  border-radius: 4px;
  overflow-x: auto;
}

.preview-content :deep(code) {
  font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace;
  font-size: 14px;
}

.preview-content :deep(blockquote) {
  margin: 0;
  padding: 0 1em;
  color: #6a737d;
  border-left: 0.25em solid #dfe2e5;
}

.el-form-item:last-child {
  margin-bottom: 0;
}

/* ================= 现代化覆写（设计变量见 assets/theme.css） ================= */
.new-post,
.edit-post {
  width: 100%;
  max-width: 1080px;
  margin: 0 auto;
  padding: 8px 24px 48px;
  box-sizing: border-box;
}

.post-form-container,
.editor-item {
  padding: 28px;
  border: 1px solid var(--border);
  border-radius: var(--radius-xl);
  background: var(--surface);
  box-shadow: var(--shadow-md);
}

.editor-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  padding: 12px 16px;
  margin-bottom: 14px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--surface-muted);
}

.action-left,
.action-right {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.save-status {
  font-size: 12.5px;
  color: var(--ink-400);
}

.preview,
.markdown-body {
  padding: 20px;
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  background: var(--surface-muted);
  font-size: 14.5px;
  line-height: 1.9;
  color: var(--ink-700);
}

.debug-info {
  margin-top: 10px;
  font-size: 12px;
  color: var(--ink-400);
}

.upload-demo {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

@media (max-width: 768px) {
  .new-post,
  .edit-post {
    padding: 0 16px 32px;
  }

  .post-form-container,
  .editor-item {
    padding: 20px 18px;
  }
}

/* 第 86 批：可选的英文版本区块（与发帖页保持一致的观感） */
.en-block :deep(.el-form-item__label) {
  width: 100%;
}

.en-label {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.en-label em {
  font-style: normal;
  font-weight: 400;
  color: #8a9a92;
}

.en-toggle {
  margin-left: auto;
  border: none;
  background: transparent;
  color: #2f7d5d;
  font-size: 12px;
  cursor: pointer;
  text-decoration: underline;
}

.en-fields {
  display: flex;
  flex-direction: column;
  gap: 10px;
  width: 100%;
  margin-top: 6px;
}

.en-stale {
  color: #9b5252;
}
</style>
