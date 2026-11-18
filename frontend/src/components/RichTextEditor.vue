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

    <!--
      第 400 批：1.5.5 的编辑器初始化是**异步**的（`loadQuill()` resolve 后才 `new Quill`），
      实例只有在 `ready` 事件里才可靠拿到。粘贴/拖拽监听、就绪前缓存内容的补写，
      统一在 `onEditorReady` 里处理（时序原因见下方脚本里的注释）。
    -->
    <quill-editor
      ref="editor"
      v-model:content="content"
      :options="editorOptions"
      contentType="html"
      @update:content="handleChange"
      @ready="onEditorReady"
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
 *
 * 第 400 批：**依赖漂移修复**。package.json 原来声明的是 `^1.0.0-beta.11`，
 * 但实际安装、package-lock.json 锁定的都是 1.5.5。1.5.5 把 `Quill` 导出换成了 Proxy：
 * 在 Quill 的动态 import 完成之前，访问它的**任何**属性（包括 `Quill.import(...)`）都会抛
 * 「@vueup/vue-quill: Quill is not loaded yet. Use loadQuill() in a browser-only lifecycle
 * hook, or access the Quill instance from the ready event.」
 * 而本文件原来在**模块求值期**就 `Quill.import('blots/block/embed')` + `Quill.register(...)`，
 * 于是模块一被 import 就抛错 —— 所有使用本组件的页面（`/admin/news`、发帖、编辑帖子）
 * 在 dev 与生产构建里都整页渲染失败（白屏 + 控制台红字）。
 * 现在按 1.5.5 官方 API 改成三段异步处理：
 *   1. 分隔线 Blot 的 import / register 挂到 `loadQuill()` 的 then 里（仍早于编辑器初始化）；
 *   2. 粘贴/拖拽监听改在编辑器 `ready` 事件里绑定（原来在 mounted 里拿不到异步初始化的实例）；
 *   3. 编辑器就绪前收到的 modelValue 先缓存，`ready` 后再补写一次（避免编辑已有内容时首屏空白）。
 */
import { QuillEditor, loadQuill } from '@vueup/vue-quill'
import '@vueup/vue-quill/dist/vue-quill.snow.css'
// 第 141 批：两条上传通道（都是现成接口，这里只是把它们接上）
import { uploadNewsImage } from '@/api/news'
import { uploadImage as uploadGenericImage } from '@/api/forum'
// 第 165 批：上传前压缩 —— 农户拍的照片常 3~8MB，直传会撞 5MB 上限被拒
import { compressImage } from '@/utils/imageCompress'

/**
 * 第 164 批：给 Quill 注册一个「分隔线」格式。
 *
 * Quill 1.x 自带 bold / list / image，但**没有**分隔线 —— 而"分隔线"是农户最常用的排版手段
 * （把一段话和另一段话隔开）。不注册的话，工具栏上点它插入的 `<hr>` 会被 Quill
 * 在下一次解析内容时**当作未知标签丢掉**（用户会发现"分隔线过一会儿自己没了"）。
 *
 * 第 400 批：注册**必须**挪到 `loadQuill()` resolve 之后（原来在模块顶层同步执行，
 * 1.5.5 里那一步就是上面说的整页崩溃源头）。现在的时序依据：
 *   · `loadQuill()` 内部用同一个 `quillLoadPromise` 缓存加载过程（见
 *     `dist/vue-quill.esm-bundler.js`），本文件在**模块顶层**先 attach 下面这个 then；
 *     `QuillEditor` 的初始化是在 onMounted 里（更晚）才 `<await loadQuill()>` 同一个 promise。
 *     Promise 的回调按 attach 顺序入队，所以「本文件的 then」一定早于「编辑器的 await 续体」，
 *     注册必然发生在 `new Quill(...)` 之前，不会出现 [Parchment] Unable to create divider blot。
 *   · `.catch` 里只 warn、不抛出：注册失败就当"没有分隔线格式"降级，**不能**因为一个格式
 *     注册失败再把整页拖垮一次。
 *   · 幂等：Quill 2 的 `Quill.register(Blot)` 会同时写 `formats/divider` 与 `blots/divider`，
 *     这里先查 `Quill.imports`，已注册则跳过（HMR / 重复求值不会重复注册、也不会打告警）。
 *
 * ⚠️ 必须从 `@vueup/vue-quill` 取 Quill，**不能** `import Quill from 'quill'` ——
 * 那个包用的是**自己打包的 Quill 实例**，在另一个实例上注册，编辑器会报
 * `[Parchment] Unable to create divider blot`（第一版就是这样，分隔线插不进去）。
 * 第 400 批起直接用 `loadQuill()` resolve 出来的构造函数（正是同一个打包实例），
 * 不再需要导入 1.5.5 里那个 Proxy 版的 `Quill`。
 */
let dividerBlotRegistered = false
const dividerReady = loadQuill()
  .then((LoadedQuill) => {
    const alreadyRegistered = !!(
      LoadedQuill.imports
      && (LoadedQuill.imports['formats/divider'] || LoadedQuill.imports['blots/divider'])
    )
    if (alreadyRegistered) {
      dividerBlotRegistered = true
      return LoadedQuill
    }
    const BlockEmbed = LoadedQuill.import('blots/block/embed')
    class DividerBlot extends BlockEmbed {}
    DividerBlot.blotName = 'divider'
    DividerBlot.tagName = 'hr'
    LoadedQuill.register(DividerBlot)
    dividerBlotRegistered = true
    return LoadedQuill
  })
  .catch((error) => {
    // 第 400 批：失败只降级（分隔线按钮不可用），编辑器其余功能照常
    console.warn('[RichTextEditor] 第 400 批：分隔线格式注册失败，编辑器其余功能不受影响。', error)
    return null
  })

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
  created() {
    // 第 400 批：下面这些是「非响应式」的实例状态（编辑器实例 / DOM 引用 / 事件处理函数），
    // 放进 data 会被 Vue 包成 Proxy（DOM 元素被代理容易出怪问题），所以挂在实例上。
    this.quillInstance = null
    this.boundEditorRoot = null
    this.handlePaste = null
    this.handleDrop = null
    this.pendingModelValue = null
  },
  watch: {
    modelValue(newVal) {
      const next = newVal ?? ''
      if (next === this.content) return

      this.content = next

      // 第 400 批：1.5.5 的编辑器要等 loadQuill() 完成才存在，在此之前拿不到实例
      // （原写法 `editor?.getQuill?.()` 在就绪前会直接抛错）。未就绪时先把待同步内容
      // 缓存下来，等 @ready 触发后在 onEditorReady 里补写一次 ——
      // 否则「恢复草稿 / 编辑已有内容」时外部传来的正文会被丢掉，首屏是空白的。
      if (!this.getQuill()) {
        this.pendingModelValue = next
        return
      }
      // 等 Quill 之后把外部内容同步进编辑器
      this.$nextTick(() => this.applyExternalContent(next))
    }
  },
  mounted() {
    // 第 164 批原有逻辑：粘贴 / 拖拽进来的图片也要走上传，而不是留成 base64。
    // 第 400 批：1.5.5 的编辑器初始化是异步的，父组件 mounted 时 getQuill() 通常还拿不到
    // 实例，真正的绑定在 @ready 的 onEditorReady 里；这里先试一次只是防御
    // （万一 ready 早于父 mounted —— 正常不会）。bindClipboardHandlers 按 root 去重，
    // 两条路径都走到也不会重复绑定。
    this.bindClipboardHandlers()
  },
  beforeUnmount() {
    // 第 400 批：用绑定时记下的 root 解绑。卸载时编辑器可能已经不可用
    // （QuillEditor 自己的 onBeforeUnmount 会把实例置空），不能再依赖 getQuill()。
    this.unbindClipboardHandlers()
  },
  methods: {
    handleChange(content) {
      this.$emit('update:modelValue', content)
    },

    /**
     * 第 400 批：拿 Quill 实例的安全入口。
     * 1.5.5 的 QuillEditor 在就绪前调用 getQuill() 是**抛字符串**而不是返回 undefined
     * （见 dist/vue-quill.esm-bundler.js 里的 getQuill 实现），所以原写法
     * `editor?.getQuill?.()` 会在异步初始化完成前把错误抛进 watch / 工具栏方法里。
     * 这里 try/catch 兜住，统一按「还没就绪」处理；就绪后优先用 ready 事件缓存的实例。
     */
    getQuill() {
      if (this.quillInstance) return this.quillInstance
      const editor = this.$refs.editor
      if (!editor || typeof editor.getQuill !== 'function') return undefined
      try {
        const quill = editor.getQuill()
        if (quill) this.quillInstance = quill
        return quill || undefined
      } catch (error) {
        return undefined
      }
    },

    /**
     * 第 400 批：编辑器就绪（1.5.5 的编辑器异步初始化完成时触发，参数就是 Quill 实例）。
     * 这里做三件事：
     *   1. 记住实例，作为 getQuill() 的兜底；
     *   2. 绑定 paste / drop 监听（原来在 mounted 里拿不到异步初始化的实例，
     *      "粘贴 / 拖拽图片走上传"会静默失效）；
     *   3. 把就绪前缓存的外部内容补写进编辑器（避免编辑已有内容时首屏空白）。
     */
    onEditorReady(quill) {
      this.quillInstance = quill || this.getQuill()
      this.bindClipboardHandlers()

      if (this.pendingModelValue !== null) {
        const pending = this.pendingModelValue
        this.pendingModelValue = null
        // 第 400 批：先进 nextTick，让 QuillEditor 在 initialize 里
        // `setContents(props.content)` 的那一步先落地；applyExternalContent 会比对
        // innerHTML，内容相同则跳过，因此不会打断输入或重置光标。
        this.$nextTick(() => this.applyExternalContent(pending))
      }
    },

    /**
     * 第 400 批：把粘贴 / 拖拽监听绑到 Quill 的 root 上。
     * 用 `boundEditorRoot` 记住绑的是哪个 root：mounted 兜底与 ready 正常路径都可能调用，
     * 同一个 root 只绑一次，避免一次粘贴/拖拽触发两遍上传。
     */
    bindClipboardHandlers() {
      const quill = this.getQuill()
      const root = quill && quill.root
      if (!root) return
      if (this.boundEditorRoot === root) return
      this.unbindClipboardHandlers()
      this.handlePaste = (event) => this.uploadFromClipboard(event)
      this.handleDrop = (event) => this.uploadFromClipboard(event, true)
      root.addEventListener('paste', this.handlePaste)
      root.addEventListener('drop', this.handleDrop)
      this.boundEditorRoot = root
    },

    unbindClipboardHandlers() {
      const root = this.boundEditorRoot
      if (root) {
        if (this.handlePaste) root.removeEventListener('paste', this.handlePaste)
        if (this.handleDrop) root.removeEventListener('drop', this.handleDrop)
      }
      this.boundEditorRoot = null
      this.handlePaste = null
      this.handleDrop = null
    },

    /**
     * 第 400 批：把外部传入的 HTML 写进编辑器（原来只在 watch 里的逻辑，抽出来复用）。
     * 编辑器还没就绪时缓存到 pendingModelValue，等 ready 后再调用一次。
     */
    applyExternalContent(html) {
      const editor = this.$refs.editor
      const quill = this.getQuill()
      if (!quill) {
        this.pendingModelValue = html
        return false
      }
      // 编辑器里已经是这段内容就不用再写（避免打断输入 / 把光标顶回开头）
      if (quill.root.innerHTML === html) return true
      if (editor && typeof editor.setContents === 'function') {
        editor.setContents(html, 'silent')
      } else {
        quill.root.innerHTML = html
      }
      return true
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

    /**
     * 在光标处插入一条分隔线（第 164 批；格式见文件中部 dividerReady 的注册）。
     *
     * 第 400 批：注册挂在 dividerReady 上。正常情况下编辑器 ready 时注册一定已经完成
     * （时序依据见注册处注释），这里 await 只是兜底极早期点击；注册失败时直接返回，
     * 不让 insertEmbed 抛 `[Parchment] Unable to create divider blot` 把页面错误弹出来。
     */
    async insertDivider() {
      await dividerReady
      const quill = this.getQuill()
      if (!quill || !dividerBlotRegistered) return
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
      // 第 165 批：先压缩（失败或压完更大时自动用原图，见 utils/imageCompress）
      const prepared = await compressImage(file)
      // 拖拽时先记住落点，上传完插回原处
      const range = quill.getSelection(true)
      const index = isDrop && range ? range.index : undefined
      this.uploading = true
      try {
        const response = await this.uploadFile(prepared)
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
