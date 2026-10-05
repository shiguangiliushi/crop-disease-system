<template>
  <!--
    举报弹窗（第 41 批）
    ------------------------------------------------------------------
    帖子详情页、评论操作、用户资料页共用这一个组件：
      <ReportDialog v-model="visible" target-type="post" :target-id="post.id" />
    提交成功后提示"管理员会尽快处理"，失败时给出后端返回的具体原因
    （例如"你已经举报过这条内容了"）。
  -->
  <el-dialog
    v-model="visible"
    width="520px"
    :close-on-click-modal="false"
    class="form-dialog"
  >
    <template #header>
      <div class="form-dialog-head">
        <span class="form-dialog-head-icon"><i class="fas fa-flag"></i></span>
        <div>
          <h3>{{ t('report.dialogTitle', { target: targetLabel }) }}</h3>
          <p>{{ t('report.hint') }}</p>
        </div>
      </div>
    </template>

    <div class="form-dialog-body">
      <el-form label-position="top">
        <el-form-item :label="t('report.reason')">
          <el-radio-group v-model="form.reason" class="report-reasons">
            <el-radio v-for="item in reasons" :key="item.value" :value="item.value">
              {{ item.label }}
            </el-radio>
          </el-radio-group>
        </el-form-item>

        <el-form-item :label="t('report.detail')">
          <el-input
            v-model="form.detail"
            type="textarea"
            :rows="4"
            resize="none"
            maxlength="500"
            show-word-limit
            :placeholder="t('report.detailPlaceholder')"
          />
        </el-form-item>
      </el-form>

      <p class="report-tip">
        <i class="fas fa-circle-info"></i>
        {{ t('report.notice') }}
      </p>
    </div>

    <template #footer>
      <div class="form-dialog-footer">
        <span class="footer-hint"><i class="fas fa-shield-halved"></i> {{ t('report.onlyAdminSees') }}</span>
        <span>
          <el-button @click="visible = false">{{ t('common.cancel') }}</el-button>
          <el-button type="danger" :loading="submitting" @click="submit">
            <i class="fas fa-flag"></i> {{ t('report.submit') }}
          </el-button>
        </span>
      </div>
    </template>
  </el-dialog>
</template>

<script>
import { computed, ref, watch } from 'vue';
import { ElMessage } from 'element-plus';
import { submitReport } from '@/api/report';
import { formatApiError } from '@/api/http';
import { useI18n } from '@/i18n';

// 举报理由：value 与后端枚举一致，label 走多语言（第 71 批）
const REASON_KEYS = [
  { value: 'spam', labelKey: 'review.catAd' },
  { value: 'abuse', labelKey: 'review.catAbuse' },
  { value: 'politics', labelKey: 'review.catPolitics' },
  { value: 'irrelevant', labelKey: 'report.reasonIrrelevant' },
  { value: 'other', labelKey: 'review.catOther' },
];

export default {
  name: 'ReportDialog',
  props: {
    modelValue: { type: Boolean, default: false },
    targetType: { type: String, required: true },
    targetId: { type: [Number, String], default: null },
  },
  emits: ['update:modelValue', 'submitted'],
  setup(props, { emit }) {
    const { t } = useI18n();
    const visible = computed({
      get: () => props.modelValue,
      set: (value) => emit('update:modelValue', value),
    });

    const submitting = ref(false);
    const form = ref({ reason: 'spam', detail: '' });
    const reasons = computed(() =>
      REASON_KEYS.map((item) => ({ value: item.value, label: t(item.labelKey) })),
    );

    const targetLabel = computed(
      () =>
        ({
          post: t('report.targetPost'),
          comment: t('report.targetComment'),
          user: t('report.targetUser'),
        })[props.targetType] || t('report.targetContent'),
    );

    watch(visible, (open) => {
      if (open) {
        form.value = { reason: 'spam', detail: '' };
      }
    });

    const submit = async () => {
      if (!props.targetId) {
        ElMessage.warning(t('report.missingTarget'));
        return;
      }
      submitting.value = true;
      try {
        await submitReport({
          target_type: props.targetType,
          target_id: Number(props.targetId),
          reason: form.value.reason,
          detail: form.value.detail,
        });
        ElMessage.success(t('report.submitted'));
        visible.value = false;
        emit('submitted');
      } catch (error) {
        ElMessage.error(formatApiError(error, t('report.submitFailed')));
      } finally {
        submitting.value = false;
      }
    };

    return { visible, submitting, form, reasons, targetLabel, submit, t };
  },
};
</script>

<style scoped>
.report-reasons {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 18px;
}

.report-tip {
  margin: 4px 0 0;
  font-size: 12.5px;
  line-height: 1.7;
  color: var(--ink-500, #78897f);
}

.report-tip i {
  margin-right: 4px;
  color: var(--brand-500, #3d9a68);
}
</style>
