<template>
  <div class="rich-text-editor">
    <quill-editor
      ref="editor"
      v-model:content="content"
      :options="editorOptions"
      contentType="html"
      @update:content="handleChange"
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
 */
import { QuillEditor } from '@vueup/vue-quill'
import '@vueup/vue-quill/dist/vue-quill.snow.css'

export default {
  name: 'RichTextEditor',
  components: {
    QuillEditor
  },
  props: {
    modelValue: {
      type: String,
      default: ''
    }
  },
  data() {
    return {
      content: this.modelValue,
      editorOptions: {
        modules: {
          toolbar: [
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
          ]
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
  methods: {
    handleChange(content) {
      this.$emit('update:modelValue', content)
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
