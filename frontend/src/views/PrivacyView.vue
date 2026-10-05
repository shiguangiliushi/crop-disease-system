<template>
  <LegalDoc
    :title="t('legal.privacyTitle')"
    :subtitle="t('legal.privacySubtitle')"
    updated-at="2026-09-18"
    :sections="sections"
  />
</template>

<script setup>
/**
 * 隐私政策（第 26 批新增；页脚的原「隐私政策」是一个 href="#" 的死链）
 *
 * 逐项对照系统的**真实字段与行为**撰写（账号字段、识别记录、论坛内容、反馈、
 * 本地存储与 Cookie、密码哈希、权限隔离、日志轮转），而不是通用模板。
 * 第 71 批：正文改为按当前语言从 i18n 取，切换语言时整篇跟着变。
 */
import { computed } from 'vue';
import LegalDoc from '@/components/LegalDoc.vue';
import { tl, useI18n } from '@/i18n';

const { t } = useI18n();

const sections = computed(() => [
  {
    id: 'collect',
    heading: t('legal.privacy.secACollectHeading'),
    paragraphs: tl('legal.privacy.secACollectParagraphs'),
    items: tl('legal.privacy.secACollectItems'),
  },
  {
    id: 'purpose',
    heading: t('legal.privacy.secBPurposeHeading'),
    items: tl('legal.privacy.secBPurposeItems'),
  },
  {
    id: 'storage',
    heading: t('legal.privacy.secCStorageHeading'),
    items: tl('legal.privacy.secCStorageItems'),
  },
  {
    id: 'share',
    heading: t('legal.privacy.secDShareHeading'),
    items: tl('legal.privacy.secDShareItems'),
  },
  {
    id: 'cookie',
    heading: t('legal.privacy.secECookieHeading'),
    items: tl('legal.privacy.secECookieItems'),
  },
  {
    id: 'rights',
    heading: t('legal.privacy.secFRightsHeading'),
    paragraphs: tl('legal.privacy.secFRightsParagraphs'),
    items: tl('legal.privacy.secFRightsItems'),
  },
  {
    id: 'retention',
    heading: t('legal.privacy.secGRetentionHeading'),
    paragraphs: tl('legal.privacy.secGRetentionParagraphs'),
  },
  {
    id: 'minor',
    heading: t('legal.privacy.secHMinorHeading'),
    paragraphs: tl('legal.privacy.secHMinorParagraphs'),
  },
  {
    id: 'update',
    heading: t('legal.privacy.secIUpdateHeading'),
    items: tl('legal.privacy.secIUpdateItems'),
  },
]);
</script>
