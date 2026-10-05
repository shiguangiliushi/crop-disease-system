<template>
  <div class="comment-item" :class="{ 'is-reply': isReply }">
    <div class="comment-avatar">
      <el-avatar 
        :size="isReply ? 32 : 36" 
        :src="comment.author?.avatar || ''" 
        style="cursor: pointer;"
        @click.stop="goToUserProfile(comment.author?.id)"
      >
        {{ comment.author?.username ? comment.author.username[0].toUpperCase() : 'U' }}
      </el-avatar>
    </div>
    
    <div class="comment-content">
      <div class="comment-header">
        <span class="comment-author">{{ comment.author?.username || '未知用户' }}</span>
        <span v-if="comment.parent_author" class="reply-to">
          回复 @{{ comment.parent_author }}
        </span>
        <span class="comment-time">{{ formatTime(comment.created_at) }}</span>
        
        <el-button 
          v-if="isAuthor || (comment.author && comment.author.id === currentUser?.id)"
          type="text"
          size="small"
          @click="$emit('delete', comment.id)"
          class="delete-btn"
        >
          删除
        </el-button>
      </div>
      
      <div class="comment-text" v-html="formatCommentContent(comment.content)"></div>
      
      <div class="comment-actions">
        <el-button 
          type="text" 
          size="small" 
          @click="$emit('reply', comment)"
          :class="{ 'is-replying': showReplyForm }"
        >
          <i class="el-icon-chat-round"></i> 回复
          <span v-if="comment.reply_count > 0" class="action-count">
            ({{ comment.reply_count }})
          </span>
        </el-button>
        
        <el-button 
          type="text" 
          size="small" 
          @click="$emit('like', comment)" 
          :class="{ 'liked': comment.is_liked }"
        >
          <i :class="comment.is_liked ? 'el-icon-star-on' : 'el-icon-star-off'"></i>
          <span v-if="comment.like_count > 0" class="action-count">
            {{ comment.like_count }}
          </span>
        </el-button>
      </div>
      
      <slot></slot>
    </div>
  </div>
</template>

<script>
import { computed } from 'vue';
import { useRouter } from 'vue-router';
import { formatTime } from '@/utils/date';

export default {
  name: 'CommentItem',
  props: {
    comment: {
      type: Object,
      required: true
    },
    isReply: {
      type: Boolean,
      default: false
    },
    currentUser: {
      type: Object,
      default: null
    },
    isAuthor: {
      type: Boolean,
      default: false
    },
    showReplyForm: {
      type: Boolean,
      default: false
    }
  },
  setup() {
    const router = useRouter();
    
    const goToUserProfile = (userId) => {
      if (userId) {
        router.push(`/user/${userId}`);
      }
    };
    
    const formatCommentContent = (content) => {
      if (!content) return '';
      try {
        return String(content)
          .replace(/&/g, '&amp;')
          .replace(/</g, '&lt;')
          .replace(/>/g, '&gt;')
          .replace(/"/g, '&quot;')
          .replace(/'/g, '&#039;')
          .replace(/\n/g, '<br>');
      } catch (error) {
        console.error('格式化评论内容出错:', error);
        return '评论内容格式错误';
      }
    };

    return {
      formatTime,
      formatCommentContent,
      goToUserProfile
    };
  }
};
</script>

<style scoped>
.comment-item {
  display: flex;
  padding: 12px 0;
  border-bottom: 1px solid var(--el-border-color-light);
  transition: all 0.3s ease;
}

.comment-item.is-reply {
  padding-left: 12px;
  border-left: 2px solid var(--el-color-primary-light-8);
  margin-left: 28px;
}

.comment-avatar {
  margin-right: 12px;
  flex-shrink: 0;
}

.comment-content {
  flex: 1;
  min-width: 0;
}

.comment-header {
  display: flex;
  align-items: center;
  margin-bottom: 6px;
  flex-wrap: wrap;
}

.comment-author {
  font-weight: 600;
  color: var(--el-text-color-primary);
  margin-right: 8px;
  font-size: 14px;
}

.reply-to {
  color: var(--el-color-primary);
  font-size: 12px;
  margin-right: 8px;
}

.comment-time {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-right: auto;
}

.comment-text {
  font-size: 14px;
  line-height: 1.6;
  word-break: break-word;
  margin-bottom: 8px;
}

.comment-actions {
  display: flex;
  align-items: center;
  margin-top: 4px;
}

.comment-actions .el-button {
  padding: 0 8px 0 0;
  height: auto;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.comment-actions .el-button:hover {
  color: var(--el-color-primary);
}

.comment-actions .el-button.liked {
  color: var(--el-color-warning);
}

.action-count {
  margin-left: 2px;
}

.delete-btn {
  color: var(--el-color-danger) !important;
}

@media (max-width: 768px) {
  .comment-item {
    padding: 8px 0;
  }
  
  .comment-avatar {
    margin-right: 8px;
  }
  
  .comment-actions .el-button {
    padding-right: 6px;
    font-size: 12px;
  }
}
</style>
