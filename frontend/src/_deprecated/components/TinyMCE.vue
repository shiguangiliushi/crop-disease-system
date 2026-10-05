<template>
  <div class="tinymce-container">
    <textarea :id="editorId" class="tinymce-textarea" :value="modelValue" />
  </div>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount, watch, onBeforeMount } from 'vue';

const props = defineProps({
  modelValue: {
    type: String,
    default: ''
  },
  height: {
    type: [Number, String],
    default: 400
  },
  placeholder: {
    type: String,
    default: ''
  },
  disabled: {
    type: Boolean,
    default: false
  },
  init: {
    type: Object,
    default: () => ({}),
  },
});

const emit = defineEmits(['update:modelValue']);
const editorRef = ref(null);
const editorId = `tinymce-editor-${Math.random().toString(36).substring(2, 9)}`;
const loading = ref(true);
const error = ref(null);

// 添加TinyMCE脚本
const loadTinyMCE = () => {
  return new Promise((resolve, reject) => {
    if (window.tinymce) {
      resolve();
      return;
    }

    const script = document.createElement('script');
    script.src = 'https://cdn.tiny.cloud/1/no-api-key/tinymce/6/tinymce.min.js';
    script.referrerPolicy = 'origin';
    
    script.onload = () => {
      if (window.tinymce) {
        resolve();
      } else {
        reject(new Error('Failed to load TinyMCE'));
      }
    };
    
    script.onerror = () => {
      reject(new Error('Failed to load TinyMCE script'));
    };
    
    document.head.appendChild(script);
  });
};

// 初始化编辑器
const initEditor = async () => {
  try {
    await loadTinyMCE();
    
    // 初始化编辑器
    window.tinymce.init({
      selector: `#${editorId}`,
      height: props.height,
      menubar: true,
      plugins: [
        'advlist autolink lists link image charmap print preview anchor',
        'searchreplace visualblocks code fullscreen',
        'insertdatetime media table paste code help wordcount'
      ],
      toolbar:
        'undo redo | formatselect | bold italic backcolor | ' +
        'alignleft aligncenter alignright alignjustify | ' +
        'bullist numlist outdent indent | removeformat | help',
      content_style: 'body { font-family: Arial, sans-serif; font-size: 14px }',
      ...props.init,
      setup: (editor) => {
        editor.on('init', () => {
          editor.setContent(props.modelValue);
          loading.value = false;
        });
        
        editor.on('change', () => {
          emit('update:modelValue', editor.getContent());
        });
      }
    });
  } catch (err) {
    console.error('Failed to initialize TinyMCE:', err);
    error.value = '富文本编辑器加载失败，请刷新页面重试';
    loading.value = false;
  }
};

// 组件挂载时初始化编辑器
onMounted(() => {
  initEditor();
});

// 组件卸载前销毁编辑器
onBeforeUnmount(() => {
  if (window.tinymce) {
    const editor = window.tinymce.get(editorId);
    if (editor) {
      editor.destroy();
    }
  }
});

// 监听 modelValue 变化
watch(() => props.modelValue, (newValue) => {
  if (window.tinymce) {
    const editor = window.tinymce.get(editorId);
    if (editor && editor.getContent() !== newValue) {
      editor.setContent(newValue || '');
    }
  }
});

// 监听禁用状态变化
watch(() => props.disabled, (newValue) => {
  if (window.tinymce) {
    const editor = window.tinymce.get(editorId);
    if (editor) {
      editor.setMode(newValue ? 'readonly' : 'design');
    }
  }
});
</script>

<style scoped>
.tinymce-container {
  position: relative;
  line-height: normal;
}

.tinymce-textarea {
  visibility: hidden;
  height: 0;
  width: 0;
}
</style>
