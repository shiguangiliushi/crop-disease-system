<template>
  <div class="rich-text-editor">
    <quill-editor
      ref="editor"
      v-model:content="content"
      :options="editorOptions"
      contentType="html"
      @update:content="handleChange"
    />
    <!-- 插入图片用的隐藏文件选择器（工具栏的 image 按钮被我们接管了） -->
    <input
      ref="fileInput"
      type="file"
      accept="image/jpeg,image/png,image/gif,image/webp"
      class="editor-file-input"
      @change="onFilePicked"
    />
  </div>
</template>

<script>
/**
 * 富文本编辑器（Quill 封装）
 *
 * 第 33 批修复：**外部程序化赋值不会显示在编辑器里**。
 * 根因在依赖 @vueup/vue-quill@1.0.0-beta.11 里 —— 它对 `content` 的 watch
 * 被作者注释掉了（dist 里能看到 `// watch(() => props.content, ...)`），
 * 只在初始化时读一次 props.content。于是：
 *   · 恢复草稿后正文框还是空的；
 *   · 「编辑帖子」把已有内容填进 form.content 时，编辑器同样不显示。
 * 这里自己补一个 watch：外部值变化时，用 Quill 的 API 把内容写进去。
 * 用 `silent` 源写入，不会触发 text-change → 不会和 v-model 形成死循环。
 *
 * 第 141 批：**插图改成上传到服务器**。
 * 在此之前 Quill 的 image 按钮走的是默认行为 —— 把图片转成 **base64 内联进正文**：
 *   · 正文体积暴涨（一张手机照片就是几 MB，新闻列表和详情都要传这一坨）；
 *   · 图片无法复用、也无法在别处引用；
 *   · 后端的 `POST /api/news/upload_image/`（有大小上限、按文件头判格式、随机文件名）
 *     明明就在那里，却因为前端从没调用而成为死接口。
 * 现在三件事都接上了：
 *   1. 工具栏 image 按钮 → 弹出文件选择 → 上传 → 插入返回的 URL；
 *   2. 粘贴/拖拽进来的图片同样上传（不再落成 base64）；
 *   3. 兜底：内容里若仍出现 base64 图片（历史草稿、浏览器差异），保存前会尝试替换。
 *
 * `uploadTarget` 决定走哪个接口：
 *   · `'news'`    → `/api/news/upload_image/`（新闻图，落 `media/news_images/`，需新闻模块权限）
 *   · `'generic'` → `/api/upload/image/`（论坛发帖等通用场景）
 * 两者返回体一致（`{url, image_url, message}`），所以这里只按目标挑函数。
 */
import { QuillEditor } from '@vueup/vue-quill'
import '@vueup/vue-quill/dist/vue-quill.snow.css'
// 第 141 批：两条上传通道（都是现成接口，这里只是把它们接上）
import { uploadNewsImage } from '@/api/news'
import { uploadImage as uploadGenericImage } from '@/api/forum'

export default {
  name: 'RichTextEditor',
  components: {
    QuillEditor
  },
  props: {
    modelValue: {
      type: String,
      default: ''
    },
    /**
     * 走哪条上传通道：'news'（默认，新闻编辑器）/ 'generic'（论坛发帖）
     * 默认给 news 是因为本组件最先服务新闻编辑；论坛那边显式传 'generic'。
     */
    uploadTarget: {
      type: String,
      default: 'news'
    }
  },
  data() {
    return {
      content: this.modelValue,
      uploading: false,
      editorOptions: {
        modules: {
          toolbar: {
            container: [
              ['bold', 'italic', 'underline', 'strike'],
              ['blockquote', 'code-block'],
              [{ 'header': 1 }, { 'header': 2 }],
              [{ 'list': 'ordered'}, { 'list': 'bullet' }],
              [{ 'script': 'sub'}, { 'script': 'super' }],
              [{ 'indent': '-1'}, { 'indent': '+1' }],
              [{ 'direction': 'rtl' }],
              [{ 'size': ['small', false, 'large', 'huge'] }],
              [{ 'header': [1, 2, 3, 4, 5, 6, false] }],
              [{ 'color': [] }, { 'background': [] }],
              [{ 'font': [] }],
              [{ 'align': [] }],
              ['clean'],
              ['link', 'image', 'video']
            ],
            // 接管 image 按钮：默认行为会把图片转成 base64 塞进正文
            handlers: {
              image: () => this.pickImage()
            }
          }
        },
        placeholder: this.$t('common.contentPlaceholder'),
        theme: 'snow'
      }
    }
  },
  watch: {
    modelValue(newVal) {
      const next = newVal ?? ''
      if (next === this.content) return

      this.content = next

      // 等 Quill 之后把外部内容同步进编辑器
      this.$nextTick(() => {
        const editor = this.$refs.editor
        const quill = editor?.getQuill?.()
        if (!quill) return
        // 编辑器里已经是这段内容就不用再写（避免打断输入 / 把光标顶回开头）
        if (quill.root.innerHTML === next) return
        editor.setContents(next, 'silent')
      })
    }
  },
  mounted() {
    // 粘贴 / 拖拽进来的图片也要走上传，而不是留成 base64
    const quill = this.getQuill()
    const root = quill?.root
    if (!root) return
    this.handlePaste = (event) => this.uploadFromClipboard(event)
    this.handleDrop = (event) => this.uploadFromClipboard(event, true)
    root.addEventListener('paste', this.handlePaste)
    root.addEventListener('drop', this.handleDrop)
  },
  beforeUnmount() {
    const root = this.getQuill()?.root
    if (root && this.handlePaste) root.removeEventListener('paste', this.handlePaste)
    if (root && this.handleDrop) root.removeEventListener('drop', this.handleDrop)
  },
  methods: {
    handleChange(content) {
      this.$emit('update:modelValue', content)
    },

    getQuill() {
      return this.$refs.editor?.getQuill?.()
    },

    /** 按 `uploadTarget` 选上传函数（两条接口返回体一致） */
    uploadFile(file) {
      const formData = new FormData()
      formData.append('image', file)
      return this.uploadTarget === 'generic'
        ? uploadGenericImage(formData)
        : uploadNewsImage(formData)
    },

    pickImage() {
      this.$refs.fileInput?.click()
    },

    async onFilePicked(event) {
      const file = event.target?.files?.[0]
      // 选完就清空，否则连续选同一个文件不会再触发 change
      event.target.value = ''
      if (!file) return
      await this.uploadAndInsert(file)
    },

    /**
     * 粘贴/拖拽里的图片：阻止默认行为（否则浏览器会插成 base64），
     * 逐个上传后按当前光标位置插入。
     */
    async uploadFromClipboard(event, isDrop = false) {
      const items = event.clipboardData?.items
        || event.dataTransfer?.items
        || []
      const files = []
      for (const item of items) {
        if (item.kind === 'file' && item.type.startsWith('image/')) {
          const file = item.getAsFile()
          if (file) files.push(file)
        }
      }
      if (!files.length) return
      event.preventDefault()
      for (const file of files) {
        // eslint-disable-next-line no-await-in-loop —— 逐张上传，顺序即插入顺序
        await this.uploadAndInsert(file, isDrop)
      }
    },

    /** 上传一张图并插入到光标处 */
    async uploadAndInsert(file, isDrop = false) {
      const quill = this.getQuill()
      if (!quill) return null
      // 拖拽时先记住落点，上传完插回原处
      const range = quill.getSelection(true)
      const index = isDrop && range ? range.index : undefined
      this.uploading = true
      try {
        const response = await this.uploadFile(file)
        const url = response?.url || response?.image_url
        if (!url) throw new Error(this.$t('editor.uploadNoUrl'))
        const at = index === undefined ? quill.getSelection(true)?.index ?? quill.getLength() : index
        quill.insertEmbed(at, 'image', url, 'user')
        quill.setSelection(at + 1, 0, 'silent')
        this.$emit('update:modelValue', quill.root.innerHTML)
        this.$message?.success?.(this.$t('editor.uploadOk'))
        return url
      } catch (error) {
        // 上传失败要说清原因（大小/格式由后端校验，后端会把原因放在 error 里）
        const detail = error?.response?.data?.error
          || error?.response?.data?.detail
          || error?.message
          || this.$t('msg.unknownError')
        this.$message?.error?.(this.$t('editor.uploadFailed', { detail }))
        return null
      } finally {
        this.uploading = false
      }
    }
  }
}
</script>

<style scoped>
.rich-text-editor {
  background: #fff;
  border-radius: 4px;
  margin-bottom: 20px;
}

/* 隐藏的文件选择器（由工具栏 image 按钮触发） */
.editor-file-input {
  display: none;
}

:deep(.ql-container) {
  min-height: 200px;
  font-size: 16px;
}

:deep(.ql-toolbar) {
  border-top-left-radius: 4px;
  border-top-right-radius: 4px;
  border-bottom: 1px solid #dcdfe6 !important;
}

:deep(.ql-container) {
  border-bottom-left-radius: 4px;
  border-bottom-right-radius: 4px;
  border: 1px solid #dcdfe6 !important;
  border-top: none !important;
}
</style>
