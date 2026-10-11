<template>
  <div class="rich-text-editor">
    <!--
      第 164 批：工具栏从 Quill 的**满配**（代码块 / 字号 / 颜色 / 文字方向 / 视频 …）
      收成农户真正用得上的四个：加粗、图片、列表、分隔线。
      评审意见（用户转来）说得对：农户打开编辑器看到"行内代码""代码块"只会发懵。
      这里用**自定义工具栏容器**（而不是默认的 snow 预设），按钮换成 Font Awesome 图标 + 中文标签。
      ⚠️ 容器用 id 交给 Quill（`toolbar.container` 接受选择器）——
      该 div 在模板里排在编辑器**之前**，Quill 初始化时它已经在 DOM 里了。
    -->
    <div :id="toolbarId" class="farmer-toolbar">
      <!--
        ⚠️ 第 164 批踩过的两个坑（都写在按钮的类名上了）：
        1. **不要用 `ql-*` 类名**：Quill 的 snow 主题会接管这些按钮，
           把里面的 Font Awesome 图标**替换成它自己的 svg**，中文标签也会被清掉
           （第一版四个按钮里只剩"分隔线"有字，因为 Quill 不认识它）。
        2. 按钮点击**自己处理**（调 Quill API），不依赖 toolbar 模块。
      -->
      <button type="button" class="rte-btn rte-btn-bold" :title="$t('editor.boldHint')" @click="formatBold">
        <i class="fas fa-bold"></i><span>{{ $t('editor.bold') }}</span>
      </button>
      <button type="button" class="rte-btn rte-btn-image" :title="$t('editor.imageHint')" @click="pickImage">
        <i class="fas fa-image"></i><span>{{ $t('editor.image') }}</span>
      </button>
      <button type="button" class="rte-btn rte-btn-list" :title="$t('editor.listHint')" @click="formatList">
        <i class="fas fa-list-ul"></i><span>{{ $t('editor.list') }}</span>
      </button>
      <button type="button" class="rte-btn rte-btn-divider" :title="$t('editor.dividerHint')" @click="insertDivider">
        <i class="fas fa-minus"></i><span>{{ $t('editor.divider') }}</span>
      </button>
    </div>

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
import { QuillEditor, Quill } from '@vueup/vue-quill'
import '@vueup/vue-quill/dist/vue-quill.snow.css'
// 第 141 批：两条上传通道（都是现成接口，这里只是把它们接上）
import { uploadNewsImage } from '@/api/news'
import { uploadImage as uploadGenericImage } from '@/api/forum'

/**
 * 第 164 批：给 Quill 注册一个「分隔线」格式。
 *
 * Quill 1.x 自带 bold / list / image，但**没有**分隔线 —— 而"分隔线"是农户最常用的排版手段
 * （把一段话和另一段话隔开）。不注册的话，工具栏上点它插入的 `<hr>` 会被 Quill
 * 在下一次解析内容时**当作未知标签丢掉**（用户会发现"分隔线过一会儿自己没了"）。
 *
 * ⚠️ 必须从 `@vueup/vue-quill` 取 `Quill`，**不能** `import Quill from 'quill'` ——
 * 那个包用的是**自己打包的 Quill 实例**，在另一个实例上注册，编辑器会报
 * `[Parchment] Unable to create divider blot`（第一版就是这样，分隔线插不进去）。
 */
const BlockEmbed = Quill.import('blots/block/embed')
class DividerBlot extends BlockEmbed {}
DividerBlot.blotName = 'divider'
DividerBlot.tagName = 'hr'
Quill.register(DividerBlot)

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
    // 每个实例一个工具栏 id（同一页面可能挂多个编辑器）
    const toolbarId = `rte-toolbar-${Math.random().toString(36).slice(2, 8)}`
    return {
      toolbarId,
      content: this.modelValue,
      uploading: false,
      editorOptions: {
        modules: {
          // 第 164 批：**不要** Quill 自带的工具栏模块 ——
          // 它会接管带 `ql-*` 类的按钮并替换里面的图标/文字（中文标签会被清空）。
          // 工具栏是我们自己的 4 个按钮（见模板），点击直接调 Quill API。
          toolbar: false
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

    /**
     * 加粗选中的文字（第 164 批：自己调 Quill API，不再依赖 `ql-bold` 按钮绑定）
     *
     * 先 `focus()`：用户可能刚点过别处，选区已经不在编辑器里，
     * 不聚焦的话 format 会作用到空位置（点了没反应）。
     */
    formatBold() {
      const quill = this.getQuill()
      if (!quill) return
      quill.focus()
      const current = quill.getFormat().bold
      quill.format('bold', !current, 'user')
      this.$emit('update:modelValue', quill.root.innerHTML)
    },

    /** 把选中的行变成项目符号列表（再点一次取消） */
    formatList() {
      const quill = this.getQuill()
      if (!quill) return
      quill.focus()
      const current = quill.getFormat().list
      quill.format('list', current === 'bullet' ? false : 'bullet', 'user')
      this.$emit('update:modelValue', quill.root.innerHTML)
    },

    /** 在光标处插入一条分隔线（第 164 批；格式见文件顶部的 DividerBlot 注册） */
    insertDivider() {
      const quill = this.getQuill()
      if (!quill) return
      quill.focus()
      const range = quill.getSelection(true) || { index: quill.getLength() }
      quill.insertEmbed(range.index, 'divider', true, 'user')
      quill.setSelection(range.index + 1, 0, 'silent')
      this.$emit('update:modelValue', quill.root.innerHTML)
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
  /*
    第 164 批：占满整行。
    父级 `.el-form-item__content` 在全局样式里是 **flex**，编辑器作为 flex 项
    会被压成内容宽度（实测只有 340px，右边一大片空白）。
    规则放在组件自己身上，三个使用方（编辑帖子 / 发帖 / 新闻管理）一起生效。
  */
  flex: 1 1 100%;
  width: 100%;
}

/* 隐藏的文件选择器（由工具栏 image 按钮触发） */
.editor-file-input {
  display: none;
}

:deep(.ql-container) {
  min-height: 200px;
  font-size: 16px;
}

/* 第 164 批：自定义工具栏（农户四件套）——按钮带中文标签，不是一排看不懂的图标 */
:deep(.farmer-toolbar) {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  padding: 8px 10px;
  border: 1px solid #dcdfe6;
  border-bottom: none;
  border-top-left-radius: 4px;
  border-top-right-radius: 4px;
  background: #fafcfb;
}

:deep(.farmer-toolbar .rte-btn) {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 5px 10px;
  border: 1px solid #dcdfe6;
  border-radius: 6px;
  background: #fff;
  color: var(--ink-700, #46564d);
  font-size: 13px;
  cursor: pointer;
}

:deep(.farmer-toolbar .rte-btn:hover) {
  border-color: var(--brand-400, #5fb088);
  color: var(--brand-600, #2f7a55);
}

/* 选中态（Quill 会给激活的按钮加 .ql-active） */
:deep(.farmer-toolbar .rte-btn.is-on) {
  border-color: var(--brand-500, #3f9a6b);
  background: #eef7f2;
  color: var(--brand-600, #2f7a55);
}

/* 编辑器里的分隔线与图片 */
:deep(.ql-editor hr) {
  border: none;
  border-top: 1px solid #dcdfe6;
  margin: 14px 0;
}

:deep(.ql-editor img) {
  max-width: 100%;
  border-radius: 6px;
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
